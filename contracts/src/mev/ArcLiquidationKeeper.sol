// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

//  ArcLiquidationKeeper — capital-free liquidations via USDC flash loans (Arc mainnet, chain 5042).
//
//  Flow (single atomic tx):
//    1) borrow USDC from a flash-loan provider (Balancer-V2-style vault; on Arc use the vault/provider
//       address you have — e.g. Morpho Blue's flashLoan is wrapped by an adapter implementing this ABI),
//    2) liquidate an insolvent borrower in an Aave-v3/Morpho-style pool (getUserAccountData HF < 1e18),
//    3) receive the collateral with the liquidation bonus,
//    4) swap the collateral back to USDC on Uniswap v3 (exactInputSingle),
//    5) require USDC_received >= flashLoan_debt + fee + minProfit, else REVERT (no capital ever at risk),
//    6) repay the flash loan and send the net profit to the owner Safe.
//
//  The flash loan requires NO upfront capital: if the trade is not profitable the whole tx reverts.

interface IERC20M {
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @notice Balancer-V2-style flash-loan provider. `flashLoan` sends `amounts` to `recipient` and then
///         calls `receiveFlashLoan` on it; afterwards the provider pulls `amounts + feeAmounts` back.
interface IFlashLoanProvider {
    function flashLoan(address recipient, address[] memory tokens, uint256[] memory amounts, bytes memory userData) external;
}

/// @notice Minimal Aave-v3-style lending pool (works for any pool exposing these two functions).
interface IAaveLikePool {
    struct AccountData {
        uint256 totalCollateralBase;
        uint256 totalDebtBase;
        uint256 availableBorrowsBase;
        uint256 currentLiquidationThreshold;
        uint256 ltv;
        uint256 healthFactor;
    }

    function liquidationCall(
        address collateralAsset,
        address debtAsset,
        address user,
        uint256 debtToCover,
        bool receiveAToken
    ) external;

    /// @dev Aave v3 returns 6 values; wrapped here as a struct for readability.
    function getUserAccountData(address user) external view returns (AccountData memory);
}

interface ISwapRouterV3 {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

contract ArcLiquidationKeeper {
    address public owner;
    address public usdc;

    IFlashLoanProvider public provider; // flash-loan source (Balancer-style vault / adapter)
    IAaveLikePool public lendingPool; // Aave v3 / Morpho-style pool
    ISwapRouterV3 public swapRouter; // Uniswap v3 SwapRouter02

    bool private _locked;

    /// @notice Parameters for a single liquidation (encoded into the flash-loan `userData`).
    struct LiquidationParams {
        address collateralAsset; // e.g. cirBTC
        address debtAsset; // USDC
        address user; // insolvent borrower
        uint256 debtToCover; // USDC to repay on behalf of the user (<= flash amount)
        uint24 swapFee; // Uniswap v3 pool fee for collateral->USDC (e.g. 500)
        uint256 minProfit; // minimum net profit (USDC) required to execute
        uint256 flashLoanFeeBps; // provider fee in bps, used if the provider reports no fee
    }

    event LiquidationExecuted(
        address indexed user,
        address indexed collateralAsset,
        address indexed debtAsset,
        uint256 debtRepaid,
        uint256 collateralSold,
        uint256 usdcReceived,
        uint256 profit
    );
    event ProfitSent(address indexed to, uint256 amount);
    event ConfigUpdated(address provider, address lendingPool, address swapRouter, address usdc);
    event OwnershipTransferred(address indexed from, address indexed to);
    event EmergencyWithdraw(address indexed token, address indexed to, uint256 amount);

    error NotOwner();
    error NotProvider();
    error ZeroAddr();
    error NothingToLiquidate();
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

    constructor(address usdc_, address provider_, address lendingPool_, address swapRouter_, address owner_) {
        if (usdc_ == address(0) || owner_ == address(0)) revert ZeroAddr();
        usdc = usdc_;
        provider = IFlashLoanProvider(provider_);
        lendingPool = IAaveLikePool(lendingPool_);
        swapRouter = ISwapRouterV3(swapRouter_);
        owner = owner_;
        emit ConfigUpdated(provider_, lendingPool_, swapRouter_, usdc_);
    }

    // --------------------------------------------------------------- admin
    function setConfig(address provider_, address lendingPool_, address swapRouter_, address usdc_) external onlyOwner {
        if (usdc_ == address(0)) revert ZeroAddr();
        provider = IFlashLoanProvider(provider_);
        lendingPool = IAaveLikePool(lendingPool_);
        swapRouter = ISwapRouterV3(swapRouter_);
        usdc = usdc_;
        emit ConfigUpdated(provider_, lendingPool_, swapRouter_, usdc_);
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert ZeroAddr();
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    /// @notice Rescue tokens accidentally held by this contract (never during a flash loan).
    function emergencyWithdraw(address token, address to) external onlyOwner nonReentrant {
        if (to == address(0)) revert ZeroAddr();
        uint256 bal = IERC20M(token).balanceOf(address(this));
        if (!IERC20M(token).transfer(to, bal)) revert CallFailed();
        emit EmergencyWithdraw(token, to, bal);
    }

    // --------------------------------------------------------------- entrypoint
    /// @notice Kick off a capital-free liquidation using a USDC flash loan.
    /// @dev NOT nonReentrant: the provider re-enters via `receiveFlashLoan` (which IS guarded), so the
    ///      guard lives on the callback to prevent nested flash loans.
    function executeLiquidation(LiquidationParams calldata p, uint256 flashAmount) external onlyOwner {
        if (p.collateralAsset == address(0) || p.user == address(0)) revert ZeroAddr();
        if (flashAmount == 0 || p.debtToCover == 0 || p.debtToCover > flashAmount) revert NothingToLiquidate();

        address[] memory tokens = new address[](1);
        uint256[] memory amounts = new uint256[](1);
        tokens[0] = usdc;
        amounts[0] = flashAmount;

        provider.flashLoan(address(this), tokens, amounts, abi.encode(p));
    }

    // --------------------------------------------------------------- flash-loan callback
    /// @dev Called by the flash-loan provider after it has sent the borrowed `amounts` to this contract.
    function receiveFlashLoan(
        address[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external nonReentrant {
        if (msg.sender != address(provider)) revert NotProvider();
        if (tokens.length != 1 || tokens[0] != usdc) revert NothingToLiquidate();

        LiquidationParams memory p = abi.decode(userData, (LiquidationParams));
        uint256 borrowed = amounts[0];

        // 1) Liquidate: the pool pulls `debtToCover` USDC from this contract and sends the collateral + bonus.
        _safeApprove(usdc, address(lendingPool), p.debtToCover);
        uint256 collBefore = IERC20M(p.collateralAsset).balanceOf(address(this));
        lendingPool.liquidationCall(p.collateralAsset, p.debtAsset, p.user, p.debtToCover, false);
        uint256 collateralSold = IERC20M(p.collateralAsset).balanceOf(address(this)) - collBefore;
        if (collateralSold == 0) revert NothingToLiquidate();
        _safeApprove(usdc, address(lendingPool), 0);

        // 2) Swap the collateral back to USDC via Uniswap v3.
        _safeApprove(p.collateralAsset, address(swapRouter), collateralSold);
        uint256 usdcReceived = swapRouter.exactInputSingle(
            ISwapRouterV3.ExactInputSingleParams({
                tokenIn: p.collateralAsset,
                tokenOut: usdc,
                fee: p.swapFee,
                recipient: address(this),
                amountIn: collateralSold,
                amountOutMinimum: 0, // profit check below is the real guard
                sqrtPriceLimitX96: 0
            })
        );
        _safeApprove(p.collateralAsset, address(swapRouter), 0);

        // 3) Profit check: received must cover the flash loan + fee + minProfit, else revert.
        uint256 fee = feeAmounts.length > 0 && feeAmounts[0] > 0 ? feeAmounts[0] : (borrowed * p.flashLoanFeeBps) / 10_000;
        uint256 owed = borrowed + fee;
        uint256 balance = IERC20M(usdc).balanceOf(address(this));
        if (balance < owed + p.minProfit) revert InsufficientProfit(balance, owed + p.minProfit);

        // 4) Repay the flash loan (approve the provider to pull `owed`) and send the net profit to the owner.
        _safeApprove(usdc, address(provider), owed);
        uint256 profit = balance - owed;
        if (profit > 0) {
            if (!IERC20M(usdc).transfer(owner, profit)) revert CallFailed();
            emit ProfitSent(owner, profit);
        }

        emit LiquidationExecuted(p.user, p.collateralAsset, p.debtAsset, p.debtToCover, collateralSold, usdcReceived, profit);
    }

    // --------------------------------------------------------------- internal
    /// @dev USDT-style safe approve: set to 0 first, then to `amount`.
    function _safeApprove(address token, address spender, uint256 amount) private {
        (bool ok0, ) = token.call(abi.encodeWithSelector(IERC20M.approve.selector, spender, 0));
        ok0;
        (bool ok1, bytes memory r) = token.call(abi.encodeWithSelector(IERC20M.approve.selector, spender, amount));
        if (!(ok1 && (r.length == 0 || abi.decode(r, (bool))))) revert CallFailed();
    }
}
