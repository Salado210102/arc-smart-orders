// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {AgentCreditPool} from "../src/credit/AgentCreditPool.sol";
import {MockUSDC} from "../src/launchpad/mocks/Mocks.sol";

/// @notice Foundry tests for the AgentCreditPool (invite-only USDC micro-credit).
///         Run:  forge test --match-contract AgentCreditPoolTest -vvv
contract AgentCreditPoolTest is Test {
    MockUSDC internal usdc;
    AgentCreditPool internal pool;

    address internal owner = makeAddr("owner");
    address internal treasury = makeAddr("treasury");
    address internal risk = makeAddr("risk");
    address internal keeper = makeAddr("keeper");
    address internal lp = makeAddr("lp");
    address internal lp2 = makeAddr("lp2");
    address internal agent = makeAddr("agent");

    uint256 internal constant USDC_1 = 1e6; // 1 USDC (6 dec)

    function setUp() public {
        usdc = new MockUSDC();
        pool = new AgentCreditPool(address(usdc), owner, treasury, risk);

        // whitelist (invite-only)
        vm.startPrank(risk);
        pool.setLP(lp, true);
        pool.setLP(lp2, true);
        pool.setAgent(agent, true);
        pool.setRoles(risk, keeper);
        vm.stopPrank();

        // fund + approve LP
        usdc.mint(lp, 10_000 * USDC_1);
        vm.prank(lp);
        usdc.approve(address(pool), type(uint256).max);

        // fund + approve agent (for the bond)
        usdc.mint(agent, 1_000 * USDC_1);
        vm.prank(agent);
        usdc.approve(address(pool), type(uint256).max);

        // fund keeper (for repayFrom)
        usdc.mint(keeper, 1_000 * USDC_1);
        vm.prank(keeper);
        usdc.approve(address(pool), type(uint256).max);
    }

    // ---------------------------------------------------------------- helpers
    function _lpDeposit(uint256 amount) internal {
        vm.prank(lp);
        pool.deposit(amount);
    }

    function _bond(uint256 amount) internal {
        vm.prank(agent);
        pool.depositBond(amount);
    }

    function _borrow(uint256 amount, uint64 term) internal returns (uint256 id) {
        vm.prank(agent);
        id = pool.requestLoan(amount, term);
    }

    // ---------------------------------------------------------------- LP / shares
    function test_depositMintsSharesAndFixesSharePrice() public {
        _lpDeposit(500 * USDC_1);
        assertEq(pool.totalShares(), 500 * USDC_1);
        assertEq(pool.poolAssets(), 500 * USDC_1);
        assertEq(pool.sharePrice(), 1e18);
    }

    function test_withdrawReturnsProRata() public {
        _lpDeposit(500 * USDC_1);
        vm.prank(lp);
        uint256 out = pool.withdraw(200 * USDC_1);
        assertEq(out, 200 * USDC_1);
        assertEq(usdc.balanceOf(lp), 10_000 * USDC_1 - 500 * USDC_1 + 200 * USDC_1);
    }

    function test_depositRequiresWhitelist() public {
        address stranger = makeAddr("stranger");
        usdc.mint(stranger, 100 * USDC_1);
        vm.startPrank(stranger);
        usdc.approve(address(pool), type(uint256).max);
        vm.expectRevert(AgentCreditPool.NotWhitelistedLP.selector);
        pool.deposit(100 * USDC_1);
        vm.stopPrank();
    }

    // ---------------------------------------------------------------- borrow gates
    function test_requestLoanRequiresWhitelist() public {
        address rogue = makeAddr("rogue");
        usdc.mint(rogue, 100 * USDC_1);
        vm.startPrank(rogue);
        usdc.approve(address(pool), type(uint256).max);
        vm.expectRevert(AgentCreditPool.NotWhitelistedAgent.selector);
        pool.requestLoan(10 * USDC_1, 1 days);
        vm.stopPrank();
    }

    function test_requestLoanRequiresBond() public {
        _lpDeposit(500 * USDC_1);
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.BondTooLow.selector);
        pool.requestLoan(10 * USDC_1, 1 days);
    }

    function test_requestLoanHappyPath() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        uint256 balBefore = usdc.balanceOf(agent);
        uint256 id = _borrow(10 * USDC_1, 1 days);
        assertEq(usdc.balanceOf(agent), balBefore + 10 * USDC_1);
        assertEq(pool.outstanding(), 10 * USDC_1);
        assertEq(pool.agentOutstanding(agent), 10 * USDC_1);
        (, , , bool active, ) = pool.loans(id);
        assertTrue(active);
    }

    function test_requestLoanRespectsAmountBounds() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.BadParams.selector);
        pool.requestLoan(1 * USDC_1, 1 days); // < minLoan
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.BadParams.selector);
        pool.requestLoan(100 * USDC_1, 1 days); // > maxLoan
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.BadParams.selector);
        pool.requestLoan(10 * USDC_1, 8 days); // > maxTerm
    }

    function test_epochCapEnforcedAndResets() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        // tiny epoch cap (15 USDC) so the 2nd loan of 10 within the same epoch reverts
        vm.prank(owner);
        pool.setPolicy(5 * USDC_1, 50 * USDC_1, 7 days, 1000 * USDC_1, 15 * USDC_1, 1 days, 10_000);

        _borrow(10 * USDC_1, 1 days); // epoch outstanding = 10
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.EpochCapExceeded.selector);
        pool.requestLoan(10 * USDC_1, 1 days); // 20 > 15

        vm.warp(block.timestamp + 1 days + 1); // new epoch
        _borrow(10 * USDC_1, 1 days); // ok again
    }

    function test_utilizationCap() public {
        _lpDeposit(50 * USDC_1); // small TVL
        _bond(10 * USDC_1);
        vm.prank(owner);
        // maxUtilization 80% → max outstanding = 40 USDC; 30 ok, then +20 → 50 > 40 reverts
        pool.setPolicy(5 * USDC_1, 50 * USDC_1, 7 days, 1000 * USDC_1, 1000 * USDC_1, 1 days, 8000);
        _borrow(30 * USDC_1, 1 days);
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.UtilizationTooHigh.selector);
        pool.requestLoan(20 * USDC_1, 1 days);
    }

    // ---------------------------------------------------------------- repay / fees
    function test_repaySplitsInterestTreasuryReserveAndLPs() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        uint256 id = _borrow(10 * USDC_1, 1 days);

        // interestBps = 100 (1%) → interest = 0.1 USDC
        uint256 interest = (10 * USDC_1 * 100) / 10_000;
        uint256 perf = (interest * 1500) / 10_000; // 15%
        uint256 toReserve = (interest * 2000) / 10_000; // 20%

        uint256 treasuryBefore = usdc.balanceOf(treasury);
        vm.prank(agent);
        pool.repay(id);

        assertEq(usdc.balanceOf(treasury), treasuryBefore + perf);
        assertEq(pool.reserve(), toReserve);
        assertEq(pool.outstanding(), 0);
        // pool assets grew by interest − perf − reserve
        assertEq(pool.idle(), 500 * USDC_1 + interest - perf - toReserve);
    }

    function test_repayFromLetsKeeperPayFromOwnFunds() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        uint256 id = _borrow(10 * USDC_1, 1 days);

        uint256 keeperBefore = usdc.balanceOf(keeper);
        vm.prank(keeper);
        pool.repayFrom(id);
        uint256 owed = 10 * USDC_1 + (10 * USDC_1 * 100) / 10_000;
        assertEq(usdc.balanceOf(keeper), keeperBefore - owed);
        assertEq(pool.outstanding(), 0);
    }

    // ---------------------------------------------------------------- default
    function test_markDefaultSlashesBond() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1); // bond == principal
        uint256 id = _borrow(10 * USDC_1, 1 days);

        vm.warp(block.timestamp + 1 days + 1);
        vm.prank(risk);
        pool.markDefault(id);

        assertEq(pool.bond(agent), 0);
        assertEq(pool.outstanding(), 0);
        assertEq(pool.idle(), 500 * USDC_1); // bond recovered the full principal
    }

    function test_markDefaultUsesReserveThenLPs() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1); // bond only 10
        uint256 id = _borrow(40 * USDC_1, 1 days); // borrow 40 > bond

        // seed some reserve via an earlier repaid loan
        uint256 id2 = _borrow(10 * USDC_1, 1 days);
        vm.prank(agent);
        pool.repay(id2);
        uint256 reserveBefore = pool.reserve();
        assertGt(reserveBefore, 0);

        vm.warp(block.timestamp + 1 days + 1);
        uint256 navBefore = pool.poolAssets();
        vm.prank(risk);
        pool.markDefault(id);

        // bond (10) slashed, reserve used up to loss (30), rest is LP loss
        assertLt(pool.poolAssets(), navBefore); // LPs socialized the remainder
        assertEq(pool.bond(agent), 0);
    }

    function test_markDefaultOnlyAfterDue() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        uint256 id = _borrow(10 * USDC_1, 1 days);
        vm.prank(risk);
        vm.expectRevert(AgentCreditPool.NotDue.selector);
        pool.markDefault(id);
    }

    // ---------------------------------------------------------------- pause
    function test_pauseBlocksDepositAndLoanButAllowsWithdrawAndRepay() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        uint256 id = _borrow(10 * USDC_1, 1 days);

        vm.prank(risk);
        pool.setPaused(true);

        // deposit blocked
        usdc.mint(lp, 100 * USDC_1);
        vm.prank(lp);
        vm.expectRevert(AgentCreditPool.Paused.selector);
        pool.deposit(100 * USDC_1);

        // loan blocked
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.Paused.selector);
        pool.requestLoan(5 * USDC_1, 1 days);

        // withdraw allowed
        vm.prank(lp);
        pool.withdraw(100 * USDC_1);

        // repay allowed
        vm.prank(agent);
        pool.repay(id);
    }

    // ---------------------------------------------------------------- access control
    function test_onlyOwnerSetters() public {
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.NotOwner.selector);
        pool.setFees(100, 100, 100);

        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.NotOwner.selector);
        pool.setPolicy(1, 2, 1, 1, 1, 1, 1);
    }

    function test_onlyRiskWhitelists() public {
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.NotRisk.selector);
        pool.setAgent(makeAddr("x"), true);

        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.NotRisk.selector);
        pool.setLP(makeAddr("y"), true);
    }

    function test_bondCannotBeWithdrawnWithActiveLoan() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        _borrow(10 * USDC_1, 1 days);
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.HasActiveLoans.selector);
        pool.withdrawBond(5 * USDC_1);
    }

    // ---------------------------------------------------------------- pause alias + repayOnBehalf
    function test_pauseAliasBlocksThenUnpauseRestores() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        vm.prank(risk);
        pool.pause();
        assertTrue(pool.paused());
        vm.prank(agent);
        vm.expectRevert(AgentCreditPool.Paused.selector);
        pool.requestLoan(5 * USDC_1, 1 days);
        vm.prank(risk);
        pool.unpause();
        assertFalse(pool.paused());
        _borrow(5 * USDC_1, 1 days);
    }

    function test_repayOnBehalfClearsAgentDebt() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        _borrow(10 * USDC_1, 1 days);
        uint256 debt = pool.debtOf(agent);
        assertGt(debt, 10 * USDC_1); // principal + interest

        vm.prank(keeper);
        uint256 used = pool.repayOnBehalf(agent, debt);
        assertEq(used, debt);
        assertEq(pool.debtOf(agent), 0);
        assertEq(pool.outstanding(), 0);
    }

    function test_debtOfIncludesInterest() public {
        _lpDeposit(500 * USDC_1);
        _bond(10 * USDC_1);
        uint256 id = _borrow(10 * USDC_1, 1 days);
        assertEq(pool.debtOf(agent), pool.pendingInterest(id) + 10 * USDC_1);
    }
}
