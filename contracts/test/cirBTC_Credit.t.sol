// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {AgentCreditPool} from "../src/credit/AgentCreditPool.sol";
import {AgentYieldVault} from "../src/credit/AgentYieldVault.sol";
import {MockPriceOracle, MockYieldStrategy} from "../src/credit/mocks/Mocks.sol";
import {MockUSDC, MockERC20} from "../src/launchpad/mocks/Mocks.sol";

/// @notice cirBTC collateral + yield vault tests. Run:
///         forge test --match-contract CirBtcCreditTest -vvv
contract CirBtcCreditTest is Test {
    MockUSDC internal usdc; // 6 dec
    MockERC20 internal cirbtc; // 8 dec
    MockPriceOracle internal oracle;
    AgentCreditPool internal pool;
    AgentYieldVault internal vault;
    MockYieldStrategy internal strategy;

    address internal owner = makeAddr("owner");
    address internal treasury = makeAddr("treasury");
    address internal risk = makeAddr("risk");
    address internal lp = makeAddr("lp");
    address internal agent = makeAddr("agent");

    uint256 internal constant USDC_1 = 1e6;
    uint256 internal constant BTC_1 = 1e8; // cirBTC 8 dec

    function setUp() public {
        usdc = new MockUSDC();
        cirbtc = new MockERC20("Circle Wrapped BTC", "cirBTC", 8);
        oracle = new MockPriceOracle(); // 60,000 USD/BTC (1e18)
        pool = new AgentCreditPool(address(usdc), owner, treasury, risk);
        vault = new AgentYieldVault(address(cirbtc), owner, "Yield cirBTC", "yBTC");
        strategy = new MockYieldStrategy(address(cirbtc));

        vm.prank(owner);
        pool.setCollateralConfig(address(cirbtc), address(oracle));
        vm.prank(owner);
        pool.setRiskParams(7000, 8000, 500); // 70% LTV, 80% liq, 5% penalty

        // LP funds the pool
        vm.prank(risk);
        pool.setLP(lp, true);
        usdc.mint(lp, 1_000_000 * USDC_1);
        vm.startPrank(lp);
        usdc.approve(address(pool), type(uint256).max);
        pool.deposit(100_000 * USDC_1);
        vm.stopPrank();

        // agent holds cirBTC
        cirbtc.mint(agent, 10 * BTC_1);
        vm.prank(agent);
        cirbtc.approve(address(pool), type(uint256).max);
    }

    // ---------------------------------------------------------- (a) collateral + borrow
    function test_depositCirbtcAndBorrow() public {
        vm.startPrank(agent);
        pool.depositCollateral(1 * BTC_1); // 1 BTC = $60k
        assertEq(pool.collateral(agent), 1 * BTC_1);
        assertEq(pool.collateralValueUsdc(agent), 60_000 * USDC_1);

        pool.borrowAgainstCollateral(30_000 * USDC_1);
        vm.stopPrank();

        assertEq(pool.collateralDebt(agent), 30_000 * USDC_1);
        assertEq(usdc.balanceOf(agent), 30_000 * USDC_1);
        // LTV = owed (30k + 1% flat interest) / 60k = 5050 bps
        assertEq(pool.collateralLtvBps(agent), 5050);

        // withdraw collateral within LTV is allowed
        vm.prank(agent);
        pool.withdrawCollateral(BTC_1 / 10); // remove 0.1 BTC → still healthy
        assertEq(pool.collateral(agent), (9 * BTC_1) / 10);
    }

    // ---------------------------------------------------------- (b) LTV limit + liquidation
    function test_ltvLimitReverts() public {
        vm.startPrank(agent);
        pool.depositCollateral(1 * BTC_1);
        // 70% of $60k = $42k max; $45k exceeds it
        vm.expectRevert(AgentCreditPool.LtvTooHigh.selector);
        pool.borrowAgainstCollateral(45_000 * USDC_1);
        vm.stopPrank();
    }

    function test_liquidationOnPriceDrop() public {
        vm.startPrank(agent);
        pool.depositCollateral(1 * BTC_1);
        pool.borrowAgainstCollateral(40_000 * USDC_1); // LTV ≈ 67% (ok)
        vm.stopPrank();
        assertLt(pool.collateralLtvBps(agent), 7000);

        // price crashes 60k → 45k: LTV = 40.4k / 45k ≈ 89.8% > 80% → liquidatable
        oracle.setPrice(45_000e18);
        assertGt(pool.collateralLtvBps(agent), 8000);

        uint256 treasuryBtcBefore = cirbtc.balanceOf(treasury);
        pool.liquidate(agent); // permissionless

        assertEq(pool.collateralDebt(agent), 0);
        assertEq(pool.collateralLtvBps(agent), 0);
        assertGt(cirbtc.balanceOf(treasury), treasuryBtcBefore); // seized cirBTC to treasury
    }

    function test_cannotLiquidateHealthy() public {
        vm.startPrank(agent);
        pool.depositCollateral(1 * BTC_1);
        pool.borrowAgainstCollateral(20_000 * USDC_1);
        vm.stopPrank();
        vm.expectRevert(AgentCreditPool.NotLiquidatable.selector);
        pool.liquidate(agent);
    }

    // ---------------------------------------------------------- (c) yield vault
    function test_yieldVaultSharesAndYield() public {
        vm.startPrank(agent);
        cirbtc.approve(address(vault), type(uint256).max);
        uint256 shares = vault.deposit(1 * BTC_1, agent);
        vm.stopPrank();
        assertEq(shares, 1 * BTC_1); // first depositor, 1:1
        assertEq(vault.totalAssets(), 1 * BTC_1);

        // simulate fees: +10% cirBTC into the vault
        cirbtc.mint(address(vault), BTC_1 / 10);
        assertEq(vault.totalAssets(), (11 * BTC_1) / 10);
        assertEq(vault.previewRedeem(shares), (11 * BTC_1) / 10);

        vm.prank(agent);
        uint256 out = vault.redeem(shares, agent, agent);
        assertEq(out, (11 * BTC_1) / 10);
    }

    function test_yieldVaultStrategyDeploy() public {
        vm.prank(owner);
        vault.setStrategy(address(strategy));
        vm.prank(agent);
        cirbtc.approve(address(vault), type(uint256).max);
        vm.prank(agent);
        vault.deposit(2 * BTC_1, agent);

        vm.prank(owner);
        vault.deployToStrategy(2 * BTC_1);
        assertEq(strategy.totalAssets(), 2 * BTC_1);
        assertEq(vault.totalAssets(), 2 * BTC_1); // counted via the strategy
    }
}
