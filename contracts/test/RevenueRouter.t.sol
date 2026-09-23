// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {AgentCreditPool} from "../src/credit/AgentCreditPool.sol";
import {RevenueRouter} from "../src/credit/RevenueRouter.sol";
import {RevenueSplitter} from "../src/launchpad/RevenueSplitter.sol";
import {AgentStakingVault} from "../src/launchpad/AgentStakingVault.sol";
import {MockUSDC, MockERC20} from "../src/launchpad/mocks/Mocks.sol";

/// @notice Integration: an agent's revenue must FIRST repay the AgentCreditPool, THEN be split
///         70% to the staking vault / 30% to the treasury. Run:
///         forge test --match-contract RevenueRouterTest -vvv
contract RevenueRouterTest is Test {
    MockUSDC internal usdc;
    MockERC20 internal agentToken;
    AgentStakingVault internal vault;
    RevenueSplitter internal splitter;
    AgentCreditPool internal pool;
    RevenueRouter internal router;

    address internal owner = makeAddr("owner");
    address internal treasury = makeAddr("treasury");
    address internal risk = makeAddr("risk");
    address internal lp = makeAddr("lp");
    address internal agent = makeAddr("agent");
    address internal staker = makeAddr("staker");
    address internal revenueSrc = makeAddr("revenueSrc");

    uint256 internal constant USDC_1 = 1e6;

    function setUp() public {
        usdc = new MockUSDC();
        agentToken = new MockERC20("Agent", "AGT", 18);

        vault = new AgentStakingVault(address(agentToken), address(usdc), "Staked AGT", "sAGT");
        splitter = new RevenueSplitter(address(usdc), address(vault), treasury, 7000, owner);
        pool = new AgentCreditPool(address(usdc), owner, treasury, risk);
        router = new RevenueRouter(address(usdc), address(pool), address(splitter), owner);

        // whitelist + roles
        vm.startPrank(risk);
        pool.setLP(lp, true);
        pool.setAgent(agent, true);
        vm.stopPrank();

        // LP funds the pool
        usdc.mint(lp, 10_000 * USDC_1);
        vm.startPrank(lp);
        usdc.approve(address(pool), type(uint256).max);
        pool.deposit(1_000 * USDC_1);
        vm.stopPrank();

        // agent: bond + borrow
        usdc.mint(agent, 100 * USDC_1);
        vm.startPrank(agent);
        usdc.approve(address(pool), type(uint256).max);
        pool.depositBond(10 * USDC_1);
        pool.requestLoan(10 * USDC_1, 1 days);
        vm.stopPrank();

        // a staker holds vault shares so yield accrues to them
        agentToken.mint(staker, 100 ether);
        vm.startPrank(staker);
        agentToken.approve(address(vault), type(uint256).max);
        vault.deposit(100 ether, staker);
        vm.stopPrank();
    }

    function test_routeRepaysDebtBeforeSplitting() public {
        uint256 debt = pool.debtOf(agent);
        assertEq(debt, 10 * USDC_1 + (10 * USDC_1 * 100) / 10_000); // principal + 1% interest

        uint256 revenue = 20 * USDC_1;
        usdc.mint(revenueSrc, revenue);
        uint256 treasuryBefore = usdc.balanceOf(treasury);
        vm.startPrank(revenueSrc);
        usdc.approve(address(router), revenue);
        router.route(agent, revenue);
        vm.stopPrank();

        // 1) debt fully repaid to the pool
        assertEq(pool.debtOf(agent), 0);
        assertEq(pool.outstanding(), 0);

        // 2) remainder = revenue − debt, split 70/30; the pool also pays its 15% performance fee to treasury
        uint256 rest = revenue - debt;
        uint256 toTreasurySplit = rest - (rest * 7000) / 10_000;
        uint256 perf = (((10 * USDC_1 * 100) / 10_000) * 1500) / 10_000;
        assertEq(usdc.balanceOf(treasury), treasuryBefore + toTreasurySplit + perf);

        // staker earns the 70% of the remainder
        assertEq(vault.pendingRewards(staker), (rest * 7000) / 10_000);
    }

    function test_routeWithNoDebtForwardsAllToSplitter() public {
        // repay the loan first
        vm.prank(agent);
        pool.repay(0);
        assertEq(pool.debtOf(agent), 0);

        uint256 revenue = 5 * USDC_1;
        usdc.mint(revenueSrc, revenue);
        uint256 treasuryBefore = usdc.balanceOf(treasury);
        vm.startPrank(revenueSrc);
        usdc.approve(address(router), revenue);
        router.route(agent, revenue);
        vm.stopPrank();

        uint256 toTreasurySplit = revenue - (revenue * 7000) / 10_000;
        assertEq(usdc.balanceOf(treasury), treasuryBefore + toTreasurySplit);
        assertEq(vault.pendingRewards(staker), (revenue * 7000) / 10_000);
    }

    /// @dev Whole-loan settlement: if revenue < the full debt, no loan is settled and the amount is split.
    function test_partialRevenueBelowDebtIsSplitWhole() public {
        uint256 revenue = 3 * USDC_1;
        uint256 debtBefore = pool.debtOf(agent);
        usdc.mint(revenueSrc, revenue);
        uint256 treasuryBefore = usdc.balanceOf(treasury);
        vm.startPrank(revenueSrc);
        usdc.approve(address(router), revenue);
        router.route(agent, revenue);
        vm.stopPrank();

        assertEq(pool.debtOf(agent), debtBefore); // unchanged (no whole loan could be settled)
        uint256 toTreasurySplit = revenue - (revenue * 7000) / 10_000;
        assertEq(usdc.balanceOf(treasury), treasuryBefore + toTreasurySplit);
    }
}
