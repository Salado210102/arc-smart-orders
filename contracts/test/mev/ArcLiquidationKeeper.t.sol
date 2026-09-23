// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {ArcLiquidationKeeper} from "../../src/mev/ArcLiquidationKeeper.sol";
import {MockUSDC, MockERC20} from "../../src/launchpad/mocks/Mocks.sol";

interface IFlashRecipient {
    function receiveFlashLoan(
        address[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external;
}

interface ISwapRouterV3T {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
}

/// @notice Balancer-V2-style flash-loan provider mock: lends USDC, calls back, then pulls principal + fee.
contract MockFlashProvider {
    MockUSDC public usdc;
    uint256 public feeBps;

    constructor(MockUSDC usdc_, uint256 feeBps_) {
        usdc = usdc_;
        feeBps = feeBps_;
    }

    function setFeeBps(uint256 v) external {
        feeBps = v;
    }

    function flashLoan(address recipient, address[] memory tokens, uint256[] memory amounts, bytes memory data) external {
        require(tokens.length == 1 && amounts.length == 1, "bad loan");
        usdc.transfer(recipient, amounts[0]);
        uint256[] memory fees = new uint256[](1);
        fees[0] = (amounts[0] * feeBps) / 10_000;
        IFlashRecipient(recipient).receiveFlashLoan(tokens, amounts, fees, data);
        // pull repayment
        usdc.transferFrom(recipient, address(this), amounts[0] + fees[0]);
    }
}

/// @notice Aave-v3/Morpho-style pool mock: an insolvent user (HF = 0.95) whose collateral pays a bonus.
contract MockLendingPool {
    MockUSDC public usdc;
    MockERC20 public collateral;
    uint256 public collateralOut; // collateral units sent to the liquidator
    uint256 public healthFactor = 0.95e18; // < 1e18 => insolvent

    constructor(MockUSDC usdc_, MockERC20 collateral_, uint256 collateralOut_) {
        usdc = usdc_;
        collateral = collateral_;
        collateralOut = collateralOut_;
    }

    function setCollateralOut(uint256 v) external {
        collateralOut = v;
    }

    function liquidationCall(address, address, address, uint256 debtToCover, bool) external {
        usdc.transferFrom(msg.sender, address(this), debtToCover); // repay the user's debt
        collateral.transfer(msg.sender, collateralOut); // deliver collateral + liquidation bonus
    }

    function getUserAccountData(address)
        external
        view
        returns (uint256, uint256, uint256, uint256, uint256, uint256)
    {
        return (0, 0, 0, 0, 0, healthFactor);
    }
}

/// @notice Uniswap-v3 SwapRouter mock: pulls the collateral and pays a configurable amount of USDC.
contract MockSwapRouterV3 {
    MockUSDC public usdc;
    uint256 public outAmount;

    constructor(MockUSDC usdc_) {
        usdc = usdc_;
    }

    function setOut(uint256 v) external {
        outAmount = v;
    }

    function exactInputSingle(ISwapRouterV3T.ExactInputSingleParams calldata p) external payable returns (uint256) {
        MockERC20(p.tokenIn).transferFrom(msg.sender, address(this), p.amountIn);
        usdc.transfer(p.recipient, outAmount);
        return outAmount;
    }
}

contract ArcLiquidationKeeperTest is Test {
    MockUSDC internal usdc;
    MockERC20 internal coll; // cirBTC-like (8 decimals)
    MockFlashProvider internal provider;
    MockLendingPool internal pool;
    MockSwapRouterV3 internal router;
    ArcLiquidationKeeper internal keeper;

    address internal owner = address(0xA11CE);
    address internal user = address(0xBEEF);

    uint256 internal constant ONE_USDC = 1_000_000; // 1 USDC (6 dec)

    function setUp() public {
        usdc = new MockUSDC();
        coll = new MockERC20("cirBTC", "cirBTC", 8);
        provider = new MockFlashProvider(usdc, 0); // Balancer-style fee = 0
        pool = new MockLendingPool(usdc, coll, 105_000_000); // 1.05e8 collateral for 1 USDC debt
        router = new MockSwapRouterV3(usdc);
        keeper = new ArcLiquidationKeeper(address(usdc), address(provider), address(pool), address(router), owner);

        usdc.mint(address(provider), 1_000_000_000); // lending liquidity for the flash loan
        coll.mint(address(pool), 1_000_000_000); // collateral the pool can hand out
    }

    function _params(uint256 minProfit) internal view returns (ArcLiquidationKeeper.LiquidationParams memory) {
        return ArcLiquidationKeeper.LiquidationParams({
            collateralAsset: address(coll),
            debtAsset: address(usdc),
            user: user,
            debtToCover: ONE_USDC,
            swapFee: 500,
            minProfit: minProfit,
            flashLoanFeeBps: 0
        });
    }

    function test_insolvent_position_detected() public view {
        (uint256 c, uint256 d, uint256 a, uint256 t, uint256 l, uint256 hf) = pool.getUserAccountData(user);
        c;
        d;
        a;
        t;
        l;
        assertLt(hf, 1e18, "position must be insolvent (HF < 1.0)");
    }

    function test_liquidation_profitable() public {
        router.setOut(1_020_000); // 1.02 USDC received -> 0.02 profit before fee
        uint256 minProfit = 10_000; // 0.01 USDC

        vm.prank(owner);
        keeper.executeLiquidation(_params(minProfit), ONE_USDC);

        assertEq(usdc.balanceOf(owner), 20_000, "net profit -> owner");
        assertEq(usdc.balanceOf(address(keeper)), 0, "no funds stuck");
        assertEq(usdc.balanceOf(address(provider)), 1_000_000_000, "flash loan repaid (provider whole)");
    }

    function test_liquidation_with_flash_fee() public {
        provider.setFeeBps(9); // 0.09% flash fee -> 900 units
        router.setOut(1_020_000); // 1.02 received, owed 1.0009 -> profit 0.0191

        vm.prank(owner);
        keeper.executeLiquidation(_params(10_000), ONE_USDC);

        assertEq(usdc.balanceOf(owner), 19_100, "profit after flash fee");
        assertEq(usdc.balanceOf(address(provider)), 1_000_000_900, "principal + fee repaid");
    }

    function test_revert_when_swap_not_profitable() public {
        router.setOut(990_000); // 0.99 USDC < owed 1.0 + minProfit 0.01

        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(ArcLiquidationKeeper.InsufficientProfit.selector, 990_000, 1_010_000));
        keeper.executeLiquidation(_params(10_000), ONE_USDC);
    }

    function test_onlyOwner() public {
        router.setOut(1_020_000);
        vm.prank(address(0xBAD));
        vm.expectRevert(ArcLiquidationKeeper.NotOwner.selector);
        keeper.executeLiquidation(_params(10_000), ONE_USDC);
    }

    function test_emergency_withdraw() public {
        usdc.mint(address(keeper), 5_000_000);
        vm.prank(owner);
        keeper.emergencyWithdraw(address(usdc), owner);
        assertEq(usdc.balanceOf(owner), 5_000_000);
    }
}
