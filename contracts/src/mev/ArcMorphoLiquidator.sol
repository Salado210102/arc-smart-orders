// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

//  ArcMorphoLiquidator — capital-free liquidations on Arc via Morpho Blue's native flash loan.
//
//  Morpho Blue on Arc mainnet (5042): 0x34CD04070dD72b14E241112F6d83812Df5Af7fCD
//  Instead of an Aave-style pool, this module targets Morpho's `flashLoan` + `liquidate`.
//
//  Atomic flow (one tx):
//    1) morpho.flashLoan(USDC, amount, data)  -> Morpho sends USDC here and calls onMorphoFlashLoan
//    2) onMorphoFlashLoan: morpho.liquidate(marketParams, borrower, seizedAssets, repaidShares, "")  (pulls the debt)
//    3) swap the seized collateral back to USDC on Uniswap v3 (exactInputSingle)
//    4) require(balance >= flashAmount + minProfit)        (Morpho flash loans have ZERO fee)
//    5) return the flash loan to Morpho + send the net profit to the owner (Safe)
//
//  Owner-only. If the liquidation is not profitable the whole tx reverts — no capital at risk.

interface IERC20M {
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IMorpho {
    struct MarketParams {
        address loanToken;
        address collateralToken;
        address oracle;
        address irm;
        uint256 lltv;
    }

    function flashLoan(address token, uint256 assets, bytes calldata data) external;

    function liquidate(
        MarketParams memory marketParams,
        address borrower,
        uint256 seizedAssets,
        uint256 repaidShares,
        bytes calldata data
    ) external returns (uint256 seizedAssetsOut, uint256 repaidAssets);

    function idToMarketParams(bytes32 id) external view returns (MarketParams memory);
}

interface IMorphoFlashLoanCallback {
    function onMorphoFlashLoan(uint256 assets, bytes calldata data) external;
}

interface ISwapRouterV3M {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceX96;
    }

    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

contract ArcMorphoLiquidator is IMorphoFlashLoanCallback {
    address public owner;
    address public morpho;
    address public usdc;
    ISwapRouterV3M public swapRouter;

    /// @notice Hard cap on the flash amount per liquidation (0 = uncapped). Set small for a pilot.
    uint256 public maxFlashAmount;

    uint256 public lastProfit; // set in the callback (returned by executeLiquidation, for eth_call sims)
    bool private _locked;

    /// @notice One liquidation target (market + borrower + swap config).
    struct LiqParams {
        address collateralToken; // the collateral to seize (e.g. cirBTC)
        address oracle; // Morpho oracle for the market
        address irm; // interest rate model
        uint256 lltv; // liquidation LTV (WAD, e.g. 0.86e18)
        address borrower; // insolvent borrower
        uint256 seizedAssets; // collateral to seize (or 0 if using repaidShares)
        uint256 repaidShares; // debt shares to repay (or 0 if using seizedAssets)
        uint24 swapFee; // Uniswap v3 fee for collateral -> USDC
        uint256 minProfit; // minimum net profit (USDC), else revert
    }

    event MorphoLiquidation(
        address indexed borrower,
        address indexed collateralToken,
        uint256 flashAmount,
        uint256 collateralSeized,
        uint256 usdcReceived,
        uint256 profit
    );
    event ConfigUpdated(address morpho, address usdc, address swapRouter);
    event FlashCapUpdated(uint256 cap);
    event ProfitSent(address indexed to, uint256 amount);
    event OwnershipTransferred(address indexed from, address indexed to);
    event EmergencyWithdraw(address indexed token, address indexed to, uint256 amount);

    error NotOwner();
    error NotMorpho();
    error ZeroAddr();
    error NothingToLiquidate();
    error NothingSeized();
    error InsufficientProfit(uint256 received, uint256 required);
    error FlashCapExceeded(uint256 amount, uint256 cap);
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

    constructor(address morpho_, address usdc_, address swapRouter_, address owner_) {
        if (morpho_ == address(0) || usdc_ == address(0) || owner_ == address(0)) revert ZeroAddr();
        morpho = morpho_;
        usdc = usdc_;
        swapRouter = ISwapRouterV3M(swapRouter_);
        owner = owner_;
        emit ConfigUpdated(morpho_, usdc_, swapRouter_);
    }

    // --------------------------------------------------------------- admin
    function setConfig(address morpho_, address usdc_, address swapRouter_) external onlyOwner {
        if (morpho_ == address(0) || usdc_ == address(0)) revert ZeroAddr();
        morpho = morpho_;
        usdc = usdc_;
        swapRouter = ISwapRouterV3M(swapRouter_);
        emit ConfigUpdated(morpho_, usdc_, swapRouter_);
    }

    /// @notice Set the per-liquidation flash cap (0 = uncapped). Use a small value for a pilot.
    function setMaxFlashAmount(uint256 cap) external onlyOwner {
        maxFlashAmount = cap;
        emit FlashCapUpdated(cap);
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert ZeroAddr();
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    function emergencyWithdraw(address token, address to) external onlyOwner nonReentrant {
        if (to == address(0)) revert ZeroAddr();
        uint256 bal = IERC20M(token).balanceOf(address(this));
        if (!IERC20M(token).transfer(to, bal)) revert CallFailed();
        emit EmergencyWithdraw(token, to, bal);
    }

    // --------------------------------------------------------------- entrypoint
    /// @notice Flash-borrow USDC from Morpho and liquidate `p.borrower`.
    /// @dev NOT nonReentrant: Morpho re-enters via `onMorphoFlashLoan` (which IS guarded).
    function executeLiquidation(LiqParams calldata p, uint256 flashAmount) external onlyOwner returns (uint256 profit) {
        if (p.borrower == address(0) || flashAmount == 0) revert NothingToLiquidate();
        if (p.seizedAssets == 0 && p.repaidShares == 0) revert NothingToLiquidate();
        if (maxFlashAmount != 0 && flashAmount > maxFlashAmount) revert FlashCapExceeded(flashAmount, maxFlashAmount);
        IMorpho.MarketParams memory mp = IMorpho.MarketParams({
            loanToken: usdc,
            collateralToken: p.collateralToken,
            oracle: p.oracle,
            irm: p.irm,
            lltv: p.lltv
        });
        IMorpho(morpho).flashLoan(usdc, flashAmount, abi.encode(mp, p));
        return lastProfit;
    }

    // --------------------------------------------------------------- Morpho flash-loan callback
    function onMorphoFlashLoan(uint256 assets, bytes calldata data) external nonReentrant {
        if (msg.sender != morpho) revert NotMorpho();
        (IMorpho.MarketParams memory mp, LiqParams memory p) = abi.decode(data, (IMorpho.MarketParams, LiqParams));

        // 1) Liquidate: Morpho pulls the debt (USDC) from this contract and sends the collateral + bonus.
        _safeApprove(usdc, morpho, assets);
        uint256 collBefore = IERC20M(p.collateralToken).balanceOf(address(this));
        IMorpho(morpho).liquidate(mp, p.borrower, p.seizedAssets, p.repaidShares, "");
        uint256 collateralSeized = IERC20M(p.collateralToken).balanceOf(address(this)) - collBefore;
        _safeApprove(usdc, morpho, 0);
        if (collateralSeized == 0) revert NothingSeized();

        // 2) Swap the collateral back to USDC (Uniswap v3).
        _safeApprove(p.collateralToken, address(swapRouter), collateralSeized);
        uint256 received = swapRouter.exactInputSingle(
            ISwapRouterV3M.ExactInputSingleParams({
                tokenIn: p.collateralToken,
                tokenOut: usdc,
                fee: p.swapFee,
                recipient: address(this),
                amountIn: collateralSeized,
                amountOutMinimum: 0, // the profit check below is the real guard
                sqrtPriceX96: 0
            })
        );
        _safeApprove(p.collateralToken, address(swapRouter), 0);

        // 3) Morpho flash loans are fee-free: repay exactly `assets`.
        uint256 balance = IERC20M(usdc).balanceOf(address(this));
        if (balance < assets + p.minProfit) revert InsufficientProfit(balance, assets + p.minProfit);
        if (!IERC20M(usdc).transfer(morpho, assets)) revert CallFailed();

        uint256 profit = balance - assets;
        if (profit > 0) {
            if (!IERC20M(usdc).transfer(owner, profit)) revert CallFailed();
            emit ProfitSent(owner, profit);
        }
        lastProfit = profit;
        emit MorphoLiquidation(p.borrower, p.collateralToken, assets, collateralSeized, received, profit);
    }

    // --------------------------------------------------------------- internal
    function _safeApprove(address token, address spender, uint256 amount) private {
        (bool ok0, ) = token.call(abi.encodeWithSelector(IERC20M.approve.selector, spender, 0));
        ok0;
        (bool ok1, bytes memory r) = token.call(abi.encodeWithSelector(IERC20M.approve.selector, spender, amount));
        if (!(ok1 && (r.length == 0 || abi.decode(r, (bool))))) revert CallFailed();
    }
}
