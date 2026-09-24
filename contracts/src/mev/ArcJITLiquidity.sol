// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

//  ArcJITLiquidity — Just-In-Time liquidity for Uniswap v3 (Arc mainnet, 5042).
//
//  Atomic lifecycle inside a single call:
//    1) mint a 1-tick-wide position right at the current price (NonfungiblePositionManager),
//    2) run the target swap (whale) so the swap pays the bulk of its fee to *this* position,
//    3) decrease liquidity + collect (principal + fees) + burn the NFT,
//    4) IMPORTANT: value the outcome and require
//         value(end) >= value(start) + gasCost + minProfit
//       else the whole tx REVERTS (no capital is deployed when it is not worth it),
//    5) return capital + net profit to the owner (the Safe).
//
//  The contract is funded by the owner before the call; it measures the value at the start and at the end
//  (token1 is valued in token0=USDC via `priceToken1InToken0`). In production the mint/swap/burn is atomic
//  with the target tx via a bundler; `swapData` is an optional self-execute mode where this contract sends
//  the target swap itself (useful for testing / keeper-executed JIT).

interface IERC20J {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IUniswapV3PoolMin {
    function slot0()
        external
        view
        returns (uint160 sqrtPriceX96, int24 tick, uint16 a, uint16 b, uint16 c, uint8 d, bool e);
}

interface INonfungiblePositionManager {
    struct MintParams {
        address token0;
        address token1;
        uint24 fee;
        int24 tickLower;
        int24 tickUpper;
        uint256 amount0Desired;
        uint256 amount1Desired;
        uint256 amount0Min;
        uint256 amount1Min;
        address recipient;
        uint256 deadline;
    }

    struct DecreaseLiquidityParams {
        uint256 tokenId;
        uint128 liquidity;
        uint256 amount0Min;
        uint256 amount1Min;
        uint256 deadline;
    }

    struct CollectParams {
        uint256 tokenId;
        address recipient;
        uint128 amount0Max;
        uint128 amount1Max;
    }

    function mint(MintParams calldata params)
        external
        payable
        returns (uint256 tokenId, uint128 liquidity, uint256 amount0, uint256 amount1);

    function decreaseLiquidity(DecreaseLiquidityParams calldata params)
        external
        payable
        returns (uint256 amount0, uint256 amount1);

    function collect(CollectParams calldata params) external payable returns (uint256 amount0, uint256 amount1);

    function burn(uint256 tokenId) external payable;
}

contract ArcJITLiquidity {
    address public owner;
    address public usdc; // token0 (profit / valuation token)

    bool private _locked;

    struct JITParams {
        address pool; // Uniswap v3 pool (to read the current tick)
        address nfpm; // NonfungiblePositionManager
        address token1; // the paired token (token0 is `usdc`)
        uint24 poolFee; // pool fee tier (e.g. 500)
        int24 tickLower; // single-tick range: [tickLower, tickUpper)
        int24 tickUpper;
        uint256 amount0Desired; // USDC to deploy
        uint256 amount1Desired; // token1 to deploy
        uint256 amount0Min;
        uint256 amount1Min;
        address swapTarget; // optional: self-execute the target swap
        bytes swapData; // optional swap calldata (empty = skip; rely on a bundler)
        uint256 priceToken1InToken0; // token1 price in USDC, scaled 1e18 (used for valuation)
        uint256 gasCost; // estimated gas cost in USDC
        uint256 minProfit; // minimum net profit (USDC) required
        uint256 deadline;
    }

    event JITExecuted(
        address indexed pool,
        uint256 tokenId,
        uint128 liquidity,
        uint256 startValue,
        uint256 endValue,
        uint256 profit
    );
    event ProfitSent(address indexed to, uint256 amount);
    event OwnershipTransferred(address indexed from, address indexed to);
    event EmergencyWithdraw(address indexed token, address indexed to, uint256 amount);

    error NotOwner();
    error ZeroAddr();
    error TickOutOfRange(int24 tick, int24 lower, int24 upper);
    error NothingToDeploy();
    error SwapFailed();
    error InsufficientProfit(uint256 endValue, uint256 required);
    error Reentrancy();
    error CallFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier nonReentrant() {
        if (_locked) revert Reentrancy();
        _locked = true;
        _;
        _locked = false;
    }

    constructor(address usdc_, address owner_) {
        if (usdc_ == address(0) || owner_ == address(0)) revert ZeroAddr();
        usdc = usdc_;
        owner = owner_;
    }

    // --------------------------------------------------------------- admin
    function setUsdc(address usdc_) external onlyOwner {
        if (usdc_ == address(0)) revert ZeroAddr();
        usdc = usdc_;
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert ZeroAddr();
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    function emergencyWithdraw(address token, address to) external onlyOwner nonReentrant {
        if (to == address(0)) revert ZeroAddr();
        uint256 bal = IERC20J(token).balanceOf(address(this));
        if (!IERC20J(token).transfer(to, bal)) revert CallFailed();
        emit EmergencyWithdraw(token, to, bal);
    }

    // --------------------------------------------------------------- main
    /// @notice Atomic JIT: mint -> (target swap) -> decrease -> collect -> burn -> profit check -> pay owner.
    function executeJIT(JITParams calldata p) external onlyOwner nonReentrant returns (uint256 profit) {
        if (p.nfpm == address(0) || p.token1 == address(0) || p.pool == address(0)) revert ZeroAddr();
        if (p.amount0Desired == 0 && p.amount1Desired == 0) revert NothingToDeploy();
        if (p.priceToken1InToken0 == 0) revert NothingToDeploy();

        // 1) range must bracket the current tick (1-tick JIT)
        (, int24 tick, , , , , ) = IUniswapV3PoolMin(p.pool).slot0();
        if (!(tick >= p.tickLower && tick < p.tickUpper)) revert TickOutOfRange(tick, p.tickLower, p.tickUpper);

        // 2) valuation at the start (owner has pre-funded this contract)
        uint256 start0 = IERC20J(usdc).balanceOf(address(this));
        uint256 start1 = IERC20J(p.token1).balanceOf(address(this));
        uint256 startValue = start0 + (start1 * p.priceToken1InToken0) / 1e18;

        // 3) mint the ultra-narrow position
        _safeApprove(usdc, p.nfpm, p.amount0Desired);
        _safeApprove(p.token1, p.nfpm, p.amount1Desired);
        (uint256 tokenId, uint128 liquidity, , ) = INonfungiblePositionManager(p.nfpm).mint(
            INonfungiblePositionManager.MintParams({
                token0: usdc,
                token1: p.token1,
                fee: p.poolFee,
                tickLower: p.tickLower,
                tickUpper: p.tickUpper,
                amount0Desired: p.amount0Desired,
                amount1Desired: p.amount1Desired,
                amount0Min: p.amount0Min,
                amount1Min: p.amount1Min,
                recipient: address(this),
                deadline: p.deadline
            })
        );
        _safeApprove(usdc, p.nfpm, 0);
        _safeApprove(p.token1, p.nfpm, 0);

        // 4) optional self-execute of the target swap (else it is bundled externally)
        if (p.swapTarget != address(0) && p.swapData.length > 0) {
            (bool ok, ) = p.swapTarget.call(p.swapData);
            if (!ok) revert SwapFailed();
        }

        // 5) remove liquidity + collect (principal + fees) + burn
        INonfungiblePositionManager(p.nfpm).decreaseLiquidity(
            INonfungiblePositionManager.DecreaseLiquidityParams({
                tokenId: tokenId,
                liquidity: liquidity,
                amount0Min: 0,
                amount1Min: 0,
                deadline: p.deadline
            })
        );
        INonfungiblePositionManager(p.nfpm).collect(
            INonfungiblePositionManager.CollectParams({
                tokenId: tokenId,
                recipient: address(this),
                amount0Max: type(uint128).max,
                amount1Max: type(uint128).max
            })
        );
        INonfungiblePositionManager(p.nfpm).burn(tokenId);

        // 6) strict profit check
        uint256 end0 = IERC20J(usdc).balanceOf(address(this));
        uint256 end1 = IERC20J(p.token1).balanceOf(address(this));
        uint256 endValue = end0 + (end1 * p.priceToken1InToken0) / 1e18;
        uint256 required = startValue + p.gasCost + p.minProfit;
        if (endValue < required) revert InsufficientProfit(endValue, required);

        // 7) return capital + net profit to the owner
        if (end0 > 0 && !IERC20J(usdc).transfer(owner, end0)) revert CallFailed();
        if (end1 > 0 && !IERC20J(p.token1).transfer(owner, end1)) revert CallFailed();

        profit = endValue - startValue - p.gasCost;
        emit JITExecuted(p.pool, tokenId, liquidity, startValue, endValue, profit);
    }

    // --------------------------------------------------------------- internal
    function _safeApprove(address token, address spender, uint256 amount) private {
        (bool ok0, ) = token.call(abi.encodeWithSelector(IERC20J.approve.selector, spender, 0));
        ok0;
        (bool ok1, bytes memory r) = token.call(abi.encodeWithSelector(IERC20J.approve.selector, spender, amount));
        if (!(ok1 && (r.length == 0 || abi.decode(r, (bool))))) revert CallFailed();
    }
}
