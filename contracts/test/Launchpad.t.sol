// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {AgentToken} from "../src/launchpad/AgentToken.sol";
import {AgentBondingCurve} from "../src/launchpad/AgentBondingCurve.sol";
import {AgentFactory} from "../src/launchpad/AgentFactory.sol";
import {MockUSDC, MockIdentityRegistry} from "../src/launchpad/mocks/Mocks.sol";

contract LaunchpadTest is Test {
    MockUSDC usdc;
    MockIdentityRegistry identity;
    AgentFactory factory;
    AgentToken token;
    AgentBondingCurve curve;

    address constant OWNER = address(0xA11CE); // Safe
    address constant TREASURY = address(0x7EA5); // protocol treasury
    address constant CREATOR = address(0xC0FFEE); // agent treasury
    address constant BUYER = address(0xB0B);

    uint256 constant SUPPLY = 1_000_000e18; // y0
    uint256 constant X0 = 5_000e6; // virtual USDC (5,000)
    uint256 constant MAXW = 100_000e18; // max wallet
    uint256 constant MAXTX = 100_000e18; // max tx

    function setUp() public {
        usdc = new MockUSDC();
        identity = new MockIdentityRegistry();
        factory = new AgentFactory(address(usdc), address(identity), TREASURY, OWNER, address(0), address(0));

        vm.prank(CREATOR);
        (address t, address c) = factory.launch(
            "Alpha Agent", "ALPHA", SUPPLY, X0, 1_000_000e6 /*large*/, MAXW, MAXTX, "ipfs://meta"
        );
        token = AgentToken(t);
        curve = AgentBondingCurve(c);

        usdc.mint(BUYER, 1_000_000e6);
        vm.startPrank(BUYER);
        usdc.approve(address(curve), type(uint256).max);
        token.approve(address(curve), type(uint256).max);
        vm.stopPrank();
    }

    function test_factory_wiresAndRegisters() public {
        assertEq(token.owner(), OWNER, "token owner = Safe");
        assertEq(token.curve(), address(curve), "curve set");
        assertEq(curve.owner(), OWNER, "curve owner = Safe");
        assertEq(curve.agentTreasury(), CREATOR, "agent treasury = creator");
        assertEq(identity.registerCount(), 1, "ERC-8004 identity registered");
        assertEq(token.balanceOf(address(curve)), SUPPLY, "curve holds the supply");
    }

    function test_buySell_slippage() public {
        vm.warp(block.timestamp + 60); // past the sniper window
        uint256 usdcIn = 100e6;
        (uint256 quotedOut, uint256 fee) = curve.buyQuote(usdcIn);
        assertEq(fee, (usdcIn * 100) / 10_000, "1% fee");

        vm.prank(BUYER);
        curve.buy(usdcIn, quotedOut);
        assertEq(token.balanceOf(BUYER), quotedOut, "bought tokens");

        // slippage on buy
        vm.prank(BUYER);
        vm.expectRevert(AgentBondingCurve.Slippage.selector);
        curve.buy(usdcIn, quotedOut + 1);

        // sell
        (uint256 usdcOut,,) = curve.sellQuote(quotedOut);
        uint256 before = usdc.balanceOf(BUYER);
        vm.prank(BUYER);
        curve.sell(quotedOut, usdcOut);
        assertEq(usdc.balanceOf(BUYER) - before, usdcOut, "sold for USDC");

        // slippage on sell
        vm.prank(BUYER);
        curve.buy(usdcIn, 0);
        vm.prank(BUYER);
        vm.expectRevert(AgentBondingCurve.Slippage.selector);
        curve.sell(quotedOut, type(uint256).max);
    }

    function test_feeGoesToTreasuryAndAgent() public {
        vm.warp(block.timestamp + 60);
        uint256 usdcIn = 100e6;
        (, uint256 fee) = curve.buyQuote(usdcIn); // 1e6
        uint256 toTreasury = (fee * 5000) / 10_000;
        uint256 toAgent = fee - toTreasury;

        uint256 tBefore = usdc.balanceOf(TREASURY);
        uint256 cBefore = usdc.balanceOf(CREATOR);
        vm.prank(BUYER);
        curve.buy(usdcIn, 0);

        assertEq(usdc.balanceOf(TREASURY) - tBefore, toTreasury, "protocol treasury fee");
        assertEq(usdc.balanceOf(CREATOR) - cBefore, toAgent, "agent treasury fee");
    }

    function test_graduation_event() public {
        vm.prank(CREATOR);
        (address t2, address c2) = factory.launch(
            "Grad Agent", "GRAD", SUPPLY, X0, 50e6 /* small threshold */, MAXW, MAXTX, "ipfs://m2"
        );
        AgentToken token2 = AgentToken(t2);
        AgentBondingCurve curve2 = AgentBondingCurve(c2);
        vm.prank(BUYER);
        token2.approve(address(curve2), type(uint256).max);
        vm.prank(BUYER);
        usdc.approve(address(curve2), type(uint256).max);

        vm.warp(block.timestamp + 60);
        vm.expectEmit(true, true, true, false, address(curve2));
        emit AgentBondingCurve.Graduated(0, 0); // values checked below

        vm.prank(BUYER);
        curve2.buy(100e6, 0);
        assertTrue(curve2.graduated(), "graduated");
        assertGe(curve2.raisedUsdc(), 50e6, "raised >= threshold");

        vm.prank(BUYER);
        vm.expectRevert(AgentBondingCurve.TradingDisabled.selector);
        curve2.buy(1e6, 0);
    }

    function test_antiSniper_fee() public {
        // Immediately after launch -> within the sniper window (5%).
        (, uint256 fee) = curve.buyQuote(100e6);
        assertEq(fee, (100e6 * 500) / 10_000, "5% sniper fee");
        // After the window -> 1%.
        vm.warp(block.timestamp + 60);
        (, uint256 fee2) = curve.buyQuote(100e6);
        assertEq(fee2, (100e6 * 100) / 10_000, "1% normal fee");
    }

    function test_maxWalletLimit() public {
        vm.warp(block.timestamp + 60);
        // Buying ~600 USDC yields > 100,000 tokens -> MaxWalletExceeded on transfer.
        vm.prank(BUYER);
        vm.expectRevert(AgentToken.MaxWalletExceeded.selector);
        curve.buy(600e6, 0);
    }

    function test_maxTxLimit() public {
        vm.warp(block.timestamp + 60);
        vm.prank(BUYER);
        curve.buy(100e6, 0);
        // Owner tightens maxTx; a transfer above it reverts.
        vm.prank(OWNER);
        token.setLimits(0, 1_000e18, true);
        vm.prank(BUYER);
        vm.expectRevert(AgentToken.MaxTxExceeded.selector);
        token.transfer(address(0xDEAD), 5_000e18);
    }

    function test_onlyOwnerLimits() public {
        vm.prank(BUYER);
        vm.expectRevert(AgentToken.NotOwner.selector);
        token.setLimits(0, 0, false);
        vm.prank(BUYER);
        vm.expectRevert(AgentBondingCurve.NotOwner.selector);
        curve.setFee(1, 1, 1);
    }
}
