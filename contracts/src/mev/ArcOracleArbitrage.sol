// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

//  ArcOracleArbitrage — capital-free oracle arbitrage via Uniswap v3 flash loans (Arc mainnet, 5042).
//
//  Idea: when a Uniswap v3 pool's price lags the oracle feed, flash-borrow USDC from that pool, run an
//  arbitrage swap along a multi-hop route (USDC -> ... -> USDC) where one leg is mispriced, then repay the
//  flash loan and keep the net profit. If the trade does not clear `amountIn + fee + minProfit` the whole
//  transaction reverts, so no capital is ever at risk.
//
//  The oracle (Pyth/Chainlink) is used OFF-CHAIN to detect the misalignment and pick the route/size; the
//  on-chain guard is the strict profit check below.

interface IERC20A {
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @notice Uniswap v3 pool flash-loan interface (the pool pulls the repayment implicitly via the balance check).
interface IUniswapV3Pool {
    function flash(address recipient, uint256 amount0, uint256 amount1, bytes calldata data) external;
    function token0() external view returns (address);
    function token1() external view returns (address);
}

interface IUniswapV3FlashCallback {
    function uniswapV3FlashCallback(uint256 fee0, uint256 fee1, bytes calldata data) external;
}

interface ISwapRouterV3A {
    struct ExactInputParams {
        bytes path;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }

    function exactInput(ExactInputParams calldata params) external payable returns (uint256 amountOut);
}

contract ArcOracleArbitrage is IUniswapV3FlashCallback {
    address public owner;
    address public usdc; // flash-borrowed + final profit token
    ISwapRouterV3A public swapRouter; // Uniswap v3 SwapRouter02

    uint256 public lastProfit; // set during the callback; returned by executeArbitrage (for eth_call simulation)
    bool private _locked;

    /// @notice Parameters for one arbitrage (encoded into the flash-loan callback data).
    struct ArbParams {
        address flashPool; // Uniswap v3 pool to flash-borrow USDC from
        bytes path; // SwapRouter02 packed path: USDC -> ... -> USDC (multi-hop)
        uint256 amountIn; // USDC to borrow (and to swap)
        uint256 minProfit; // minimum net profit (USDC) required, else revert
    }

    event ArbitrageExecuted(
        address indexed flashPool,
        uint256 amountIn,
        uint256 flashFee,
        uint256 received,
        uint256 profit
    );
    event ProfitSent(address indexed to, uint256 amount);
    event ConfigUpdated(address usdc, address swapRouter);
    event OwnershipTransferred(address indexed from, address indexed to);
    event EmergencyWithdraw(address indexed token, address indexed to, uint256 amount);

    error NotOwner();
    error NotPool();
    error ZeroAddr();
    error NothingToArbitrage();
    error InsufficientProfit(uint256 received, uint256 required);
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

    constructor(address usdc_, address swapRouter_, address owner_) {
        if (usdc_ == address(0) || swapRouter_ == address(0) || owner_ == address(0)) revert ZeroAddr();
        usdc = usdc_;
        swapRouter = ISwapRouterV3A(swapRouter_);
        owner = owner_;
        emit ConfigUpdated(usdc_, swapRouter_);
    }

    // --------------------------------------------------------------- admin
    function setConfig(address usdc_, address swapRouter_) external onlyOwner {
        if (usdc_ == address(0) || swapRouter_ == address(0)) revert ZeroAddr();
        usdc = usdc_;
        swapRouter = ISwapRouterV3A(swapRouter_);
        emit ConfigUpdated(usdc_, swapRouter_);
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert ZeroAddr();
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    function emergencyWithdraw(address token, address to) external onlyOwner nonReentrant {
        if (to == address(0)) revert ZeroAddr();
        uint256 bal = IERC20A(token).balanceOf(address(this));
        if (!IERC20A(token).transfer(to, bal)) revert CallFailed();
        emit EmergencyWithdraw(token, to, bal);
    }

    // --------------------------------------------------------------- entrypoint
    /// @notice Flash-borrow USDC from `p.flashPool` and run the arbitrage route.
    /// @dev NOT nonReentrant: the pool re-enters via `uniswapV3FlashCallback` (which IS guarded).
    /// @return profit the net profit sent to the owner (also stored in `lastProfit`).
    function executeArbitrage(ArbParams calldata p) external onlyOwner returns (uint256 profit) {
        if (p.flashPool == address(0) || p.amountIn == 0) revert NothingToArbitrage();
        IUniswapV3Pool pool = IUniswapV3Pool(p.flashPool);
        bool usdcIsToken0 = pool.token0() == usdc;
        uint256 amount0 = usdcIsToken0 ? p.amountIn : 0;
        uint256 amount1 = usdcIsToken0 ? 0 : p.amountIn;
        pool.flash(address(this), amount0, amount1, abi.encode(p));
        return lastProfit;
    }

    // --------------------------------------------------------------- flash-loan callback
    function uniswapV3FlashCallback(uint256 fee0, uint256 fee1, bytes calldata data) external nonReentrant {
        ArbParams memory p = abi.decode(data, (ArbParams));
        IUniswapV3Pool pool = IUniswapV3Pool(msg.sender);
        if (pool.token0() != usdc && pool.token1() != usdc) revert NotPool();

        uint256 fee = pool.token0() == usdc ? fee0 : fee1;
        uint256 owed = p.amountIn + fee;

        // 1) Arbitrage swap along the misaligned route (USDC -> ... -> USDC), output back to this contract.
        _safeApprove(usdc, address(swapRouter), p.amountIn);
        uint256 received = swapRouter.exactInput(
            ISwapRouterV3A.ExactInputParams({path: p.path, recipient: address(this), amountIn: p.amountIn, amountOutMinimum: 0})
        );
        _safeApprove(usdc, address(swapRouter), 0);

        // 2) Strict profit check against the flash loan + fee + minProfit.
        uint256 balance = IERC20A(usdc).balanceOf(address(this));
        if (balance < owed + p.minProfit) revert InsufficientProfit(balance, owed + p.minProfit);

        // 3) Repay the flash loan to the pool (balance check) and send the net profit to the owner.
        if (!IERC20A(usdc).transfer(msg.sender, owed)) revert CallFailed();
        uint256 profit = balance - owed;
        if (profit > 0) {
            if (!IERC20A(usdc).transfer(owner, profit)) revert CallFailed();
            emit ProfitSent(owner, profit);
        }
        lastProfit = profit;
        emit ArbitrageExecuted(p.flashPool, p.amountIn, fee, received, profit);
    }

    // --------------------------------------------------------------- internal
    function _safeApprove(address token, address spender, uint256 amount) private {
        (bool ok0, ) = token.call(abi.encodeWithSelector(IERC20A.approve.selector, spender, 0));
        ok0;
        (bool ok1, bytes memory r) = token.call(abi.encodeWithSelector(IERC20A.approve.selector, spender, amount));
        if (!(ok1 && (r.length == 0 || abi.decode(r, (bool))))) revert CallFailed();
    }
}
