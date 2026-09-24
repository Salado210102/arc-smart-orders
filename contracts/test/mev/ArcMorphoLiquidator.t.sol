// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {ArcMorphoLiquidator} from "../../src/mev/ArcMorphoLiquidator.sol";
import {MockUSDC, MockERC20} from "../../src/launchpad/mocks/Mocks.sol";

interface IERC20T {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IMorphoCallback {
    function onMorphoFlashLoan(uint256 assets, bytes calldata data) external;
}

interface IMorphoTest {
    struct MarketParams {
        address loanToken;
        address collateralToken;
        address oracle;
        address irm;
        uint256 lltv;
    }
}

/// @notice Morpho Blue mock: fee-free flash loan + a liquidate that pulls the debt and pays the collateral.
contract MockMorpho {
    IERC20T public usdc;
    IERC20T public collateral;
    uint256 public repayAmount; // USDC pulled from the liquidator (the debt repaid)
    uint256 public collateralOut; // collateral sent to the liquidator

    constructor(IERC20T usdc_, IERC20T collateral_) {
        usdc = usdc_;
        collateral = collateral_;
    }

    function setLiquidation(uint256 repayAmount_, uint256 collateralOut_) external {
        repayAmount = repayAmount_;
        collateralOut = collateralOut_;
    }

    function flashLoan(address token, uint256 assets, bytes calldata data) external {
        require(token == address(usdc), "token");
        uint256 before = usdc.balanceOf(address(this));
        usdc.transfer(msg.sender, assets);
        IMorphoCallback(msg.sender).onMorphoFlashLoan(assets, data);
        require(usdc.balanceOf(address(this)) >= before + assets, "flash not repaid");
    }

    function liquidate(IMorphoTest.MarketParams calldata, address, uint256, uint256, bytes calldata)
        external
        returns (uint256, uint256)
    {
        usdc.transferFrom(msg.sender, address(this), repayAmount); // pull the debt
        collateral.transfer(msg.sender, collateralOut); // deliver collateral + bonus
        return (collateralOut, repayAmount);
    }
}

/// @notice Uniswap v3 SwapRouter mock (collateral -> USDC at a configurable rate).
contract MockSwapM {
    MockUSDC public usdc;
    uint256 public outAmount;

    constructor(MockUSDC usdc_) {
        usdc = usdc_;
    }

    function setOut(uint256 v) external {
        outAmount = v;
    }

    function exactInputSingle(
        ISwapRouterV3M.ExactInputSingleParams calldata p
    ) external payable returns (uint256) {
        IERC20T(p.tokenIn).transferFrom(msg.sender, address(this), p.amountIn);
        usdc.transfer(p.recipient, outAmount);
        return outAmount;
    }
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
}

contract ArcMorphoLiquidatorTest is Test {
    MockUSDC internal usdc;
    MockERC20 internal coll; // cirBTC-like
    MockMorpho internal morpho;
    MockSwapM internal router;
    ArcMorphoLiquidator internal keeper;

    address internal owner = address(0xA11CE);
    address internal borrower = address(0xBEEF);
    uint256 internal constant ONE_USDC = 1_000_000;

    function setUp() public {
        usdc = new MockUSDC();
        coll = new MockERC20("cirBTC", "cirBTC", 8);
        morpho = new MockMorpho(IERC20T(address(usdc)), IERC20T(address(coll)));
        router = new MockSwapM(usdc);
        keeper = new ArcMorphoLiquidator(address(morpho), address(usdc), address(router), owner);

        usdc.mint(address(morpho), 1_000_000_000); // flash liquidity
        coll.mint(address(morpho), 1_000_000_000); // collateral to hand out
        usdc.mint(address(router), 1_000_000_000); // USDC the swap pays out
    }

    function _params(uint256 minProfit) internal view returns (ArcMorphoLiquidator.LiqParams memory) {
        return ArcMorphoLiquidator.LiqParams({
            collateralToken: address(coll),
            oracle: address(0),
            irm: address(0x1),
            lltv: 0.86e18,
            borrower: borrower,
            seizedAssets: 100_000_000,
            repaidShares: 0,
            swapFee: 500,
            minProfit: minProfit
        });
    }

    function test_morpho_liquidation_profitable() public {
        morpho.setLiquidation(ONE_USDC, 105_000_000); // repay 1 USDC, seize 1.05e8 collateral
        router.setOut(1_020_000); // 1.02 USDC out

        vm.prank(owner);
        uint256 profit = keeper.executeLiquidation(_params(10_000), ONE_USDC);

        assertEq(profit, 20_000, "net profit (0.02 USDC)"); // 1.02 - 1.00 (fee-free flash loan)
        assertEq(usdc.balanceOf(owner), 20_000, "profit -> owner Safe");
        assertEq(usdc.balanceOf(address(keeper)), 0, "no funds stuck");
        // Morpho nets +1 USDC: the flash loan is returned in full (net 0) and the liquidated debt (1 USDC) stays in the pool.
        assertEq(usdc.balanceOf(address(morpho)), 1_001_000_000, "flash repaid + liquidated debt in the pool");
    }

    function test_revert_when_not_profitable() public {
        morpho.setLiquidation(ONE_USDC, 105_000_000);
        router.setOut(990_000); // 0.99 < 1.00 + 0.01

        vm.prank(owner);
        vm.expectRevert(
            abi.encodeWithSelector(ArcMorphoLiquidator.InsufficientProfit.selector, 990_000, 1_010_000)
        );
        keeper.executeLiquidation(_params(10_000), ONE_USDC);
    }

    function test_callback_only_morpho() public {
        vm.expectRevert(ArcMorphoLiquidator.NotMorpho.selector);
        keeper.onMorphoFlashLoan(1, "");
    }

    function test_only_owner() public {
        vm.prank(address(0xBAD));
        vm.expectRevert(ArcMorphoLiquidator.NotOwner.selector);
        keeper.executeLiquidation(_params(10_000), ONE_USDC);
    }

    function test_emergency_withdraw() public {
        usdc.mint(address(keeper), 3_000_000);
        vm.prank(owner);
        keeper.emergencyWithdraw(address(usdc), owner);
        assertEq(usdc.balanceOf(owner), 3_000_000);
    }
}
