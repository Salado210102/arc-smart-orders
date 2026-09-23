// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {AgentStakingVault} from "../src/launchpad/AgentStakingVault.sol";
import {RevenueSplitter} from "../src/launchpad/RevenueSplitter.sol";
import {MockUSDC, MockERC20} from "../src/launchpad/mocks/Mocks.sol";

contract StakingTest is Test {
    MockUSDC usdc;
    MockERC20 token;
    AgentStakingVault vault;
    RevenueSplitter splitter;

    address constant OWNER = address(0xA11CE);
    address constant TREASURY = address(0x7EA5);
    address constant ALICE = address(0xA1);
    address constant BOB = address(0xB0);

    function setUp() public {
        usdc = new MockUSDC();
        token = new MockERC20("Agent", "AGT", 18);
        vault = new AgentStakingVault(address(token), address(usdc), "Staked AGT", "sAGT");
        splitter = new RevenueSplitter(address(usdc), address(vault), TREASURY, 7000, OWNER);

        token.mint(ALICE, 1_000e18);
        token.mint(BOB, 1_000e18);
        vm.prank(ALICE);
        token.approve(address(vault), type(uint256).max);
        vm.prank(BOB);
        token.approve(address(vault), type(uint256).max);
    }

    function test_deposit() public {
        vm.prank(ALICE);
        uint256 sh = vault.deposit(100e18, ALICE);
        assertEq(sh, 100e18, "shares 1:1");
        assertEq(vault.balanceOf(ALICE), 100e18);
        assertEq(vault.totalAssets(), 100e18);
        assertEq(token.balanceOf(address(vault)), 100e18, "principal held");
    }

    function test_yieldViaSplitter() public {
        vm.prank(ALICE);
        vault.deposit(100e18, ALICE);

        //  Agent earns 1,000 USDC -> 70% stakers, 30% treasury.
        usdc.mint(address(this), 1_000e6);
        usdc.approve(address(splitter), 1_000e6);
        splitter.distribute(1_000e6);

        assertEq(usdc.balanceOf(address(vault)), 700e6, "vault holds the staker share");
        assertEq(usdc.balanceOf(TREASURY), 300e6, "treasury share");
        assertEq(vault.pendingRewards(ALICE), 700e6, "pending");

        vm.prank(ALICE);
        uint256 p = vault.claim();
        assertEq(p, 700e6);
        assertEq(usdc.balanceOf(ALICE), 700e6, "claimed");
        assertEq(vault.pendingRewards(ALICE), 0, "settled");
    }

    function test_proportional_noPrecisionLoss() public {
        vm.prank(ALICE);
        vault.deposit(100e18, ALICE);
        vm.prank(BOB);
        vault.deposit(300e18, BOB);

        usdc.mint(address(this), 400e6);
        usdc.approve(address(splitter), 400e6);
        splitter.distribute(400e6); // 70% = 280 USDC to stakers

        assertEq(vault.pendingRewards(ALICE), 70e6, "alice 100/400 of 280");
        assertEq(vault.pendingRewards(BOB), 210e6, "bob 300/400 of 280");
        assertEq(vault.pendingRewards(ALICE) + vault.pendingRewards(BOB), 280e6, "sum = 100%");

        //  Withdraw returns the principal exactly and pays the accrued reward.
        uint256 before = token.balanceOf(ALICE);
        vm.prank(ALICE);
        vault.withdraw(100e18, ALICE, ALICE);
        assertEq(token.balanceOf(ALICE), before + 100e18, "principal exact");
        assertEq(usdc.balanceOf(ALICE), 70e6, "pending paid on withdraw");
        assertEq(vault.balanceOf(ALICE), 0);
        assertEq(vault.pendingRewards(BOB), 210e6, "bob untouched");
    }

    function test_poolAllocatedOnFirstDeposit() public {
        //  Reward injected before any staker is held in `pool`, then allocated on first deposit.
        usdc.mint(address(this), 70e6);
        usdc.approve(address(splitter), 70e6);
        splitter.distribute(70e6); // 70% = 49 USDC held (no shares yet)
        assertEq(usdc.balanceOf(address(vault)), 49e6);

        vm.prank(ALICE);
        vault.deposit(100e18, ALICE);
        assertEq(vault.pendingRewards(ALICE), 49e6, "pool allocated to first staker");
    }

    function test_secondYieldAccruesToExistingStakers() public {
        vm.prank(ALICE);
        vault.deposit(100e18, ALICE);
        usdc.mint(address(this), 100e6);
        usdc.approve(address(splitter), 100e6);
        splitter.distribute(100e6); // 70 USDC
        assertEq(vault.pendingRewards(ALICE), 70e6);

        //  Bob joins after the first yield; a second yield splits on the new total.
        vm.prank(BOB);
        vault.deposit(300e18, BOB);
        assertEq(vault.pendingRewards(ALICE), 70e6, "alice keeps her prior yield");

        usdc.mint(address(this), 400e6);
        usdc.approve(address(splitter), 400e6);
        splitter.distribute(400e6); // 280 USDC over 400 shares
        assertEq(vault.pendingRewards(ALICE) - 70e6, 70e6, "alice +70");
        assertEq(vault.pendingRewards(BOB), 210e6, "bob 210");
    }
}
