// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {AgentToken} from "../src/launchpad/AgentToken.sol";
import {AgentBondingCurve} from "../src/launchpad/AgentBondingCurve.sol";
import {AgentFactory} from "../src/launchpad/AgentFactory.sol";
import {AgentRegistry} from "../src/launchpad/AgentRegistry.sol";
import {GraduationModule} from "../src/launchpad/GraduationModule.sol";
import {LiquidityLocker} from "../src/launchpad/LiquidityLocker.sol";
import {MockUSDC, MockIdentityRegistry} from "../src/launchpad/mocks/Mocks.sol";
import {MockDEX} from "../src/launchpad/mocks/MockDEX.sol";

contract LaunchpadGraduationTest is Test {
    MockUSDC usdc;
    MockIdentityRegistry identity;
    AgentRegistry registry;
    LiquidityLocker locker;
    MockDEX dex;
    GraduationModule module;
    AgentFactory factory;

    address constant OWNER = address(0xA11CE); // Safe
    address constant TREASURY = address(0x7EA5);
    address constant CREATOR = address(0xC0FFEE);
    address constant BUYER = address(0xB0B);

    uint256 constant SUPPLY = 1_000_000e18;
    uint256 constant X0 = 5_000e6;
    uint256 constant GRAD_USDC = 1_000e6; // graduate after ~1,000 USDC raised
    uint64 constant LOCK_SECONDS = 365 days;

    function setUp() public {
        usdc = new MockUSDC();
        identity = new MockIdentityRegistry();
        registry = new AgentRegistry(OWNER);
        locker = new LiquidityLocker(OWNER);
        dex = new MockDEX();
        module = new GraduationModule(OWNER, address(usdc), address(dex), address(locker), LOCK_SECONDS);
        factory = new AgentFactory(address(usdc), address(identity), TREASURY, OWNER, address(registry), address(module));

        vm.prank(OWNER);
        registry.setFactory(address(factory));
    }

    function _launch() internal returns (AgentToken token, AgentBondingCurve curve) {
        vm.prank(CREATOR);
        (address t, address c) =
            factory.launch("Grad Agent", "GRAD", SUPPLY, X0, GRAD_USDC, 500_000e18, 500_000e18, "ipfs://meta");
        token = AgentToken(t);
        curve = AgentBondingCurve(c);
    }

    function test_fullCycle_graduation_locksLP() public {
        (AgentToken token, AgentBondingCurve curve) = _launch();

        //  Registry indexed the agent.
        assertEq(registry.count(), 1, "registry count");
        AgentRegistry.Agent memory a = registry.agentAt(0);
        assertEq(a.token, address(token), "registry token");
        assertEq(a.curve, address(curve), "registry curve");
        assertEq(a.creator, CREATOR, "registry creator");

        //  The curve is wired to the graduation module.
        assertEq(curve.graduationModule(), address(module), "module wired");

        //  Buy up to (and past) the graduation threshold.
        usdc.mint(BUYER, 100_000e6);
        vm.startPrank(BUYER);
        usdc.approve(address(curve), type(uint256).max);
        token.approve(address(curve), type(uint256).max);
        vm.stopPrank();

        vm.warp(block.timestamp + 60); // past sniper
        vm.prank(BUYER);
        curve.buy(1_100e6, 0);
        assertTrue(curve.graduated(), "graduated");
        assertGe(curve.raisedUsdc(), GRAD_USDC, "raised >= threshold");

        uint256 raised = usdc.balanceOf(address(curve));
        uint256 tokensLeft = token.balanceOf(address(curve));

        //  Graduation: any caller can trigger it; LP is locked for the creator.
        vm.expectEmit(true, true, true, false, address(module));
        emit GraduationModule.Graduated(address(token), address(curve), address(dex), 0, CREATOR, 0);
        module.graduate(address(token), address(curve), CREATOR);

        //  LP moved to the locker.
        assertEq(locker.lockCount(), 1, "one lock");
        assertEq(locker.lockedBalance(address(dex)), tokensLeft, "LP locked = tokens seeded");
        assertEq(dex.balanceOf(address(locker)), tokensLeft, "locker holds the LP");
        assertEq(usdc.balanceOf(address(curve)), 0, "curve emptied USDC");
        assertEq(token.balanceOf(address(curve)), 0, "curve emptied tokens");
        assertEq(dex.balanceOf(address(BUYER)), 0, "buyer has no LP");

        //  Cannot graduate twice.
        vm.expectRevert(GraduationModule.AlreadyGraduated.selector);
        module.graduate(address(token), address(curve), CREATOR);

        //  LP cannot be withdrawn before unlock.
        (,,, uint64 unlockTime,) = locker.locks(0);
        assertEq(unlockTime, uint64(block.timestamp) + LOCK_SECONDS, "unlock time");
        vm.prank(CREATOR);
        vm.expectRevert(LiquidityLocker.StillLocked.selector);
        locker.withdraw(0);

        //  After the lock expires, the creator can withdraw.
        vm.warp(unlockTime + 1);
        vm.prank(CREATOR);
        locker.withdraw(0);
        assertEq(dex.balanceOf(CREATOR), tokensLeft, "creator withdrew LP");
        assertEq(raised > 0, true);
    }

    function test_pullForGraduation_onlyModule() public {
        (, AgentBondingCurve curve) = _launch();
        vm.prank(BUYER);
        vm.expectRevert(bytes("only_module"));
        curve.pullForGraduation(BUYER);
    }

    function test_registry_onlyFactory() public {
        (AgentToken token,) = _launch();
        vm.prank(BUYER);
        vm.expectRevert(AgentRegistry.NotFactory.selector);
        registry.register(0, address(token), address(0), BUYER, "x");
    }
}
