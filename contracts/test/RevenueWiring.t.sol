// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {OrderExecutor, IPermit2, IERC20Min} from "../src/OrderExecutor.sol";
import {AgentStakingVault} from "../src/launchpad/AgentStakingVault.sol";
import {RevenueSplitter} from "../src/launchpad/RevenueSplitter.sol";
import {MockUSDC, MockERC20} from "../src/launchpad/mocks/Mocks.sol";

//  Minimal Permit2 + router mocks for the integration test.
contract MockPermit2 {
    function permitWitnessTransferFrom(
        IPermit2.PermitTransferFrom calldata permit,
        IPermit2.SignatureTransferDetails calldata details,
        address owner,
        bytes32,
        string calldata,
        bytes calldata
    ) external {
        MockERC20(permit.permitted.token).transferFrom(owner, details.to, details.requestedAmount);
    }
}

contract MockSwap {
    function swap(address tokenIn, uint256 amountIn, address tokenOut, address recipient, uint256 amountOut) external {
        MockERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn);
        MockERC20(tokenOut).transfer(recipient, amountOut);
    }
}

/// @dev Integration: a keeper fills an order through OrderExecutor v2 (input-side fee) → the fee lands
///      in the agent's RevenueSplitter → 70% is pushed to the AgentStakingVault as USDC yield.
contract RevenueWiringTest is Test {
    MockUSDC usdc;
    MockERC20 agent;
    AgentStakingVault vault;
    RevenueSplitter splitter;
    OrderExecutor exec;
    MockSwap router;

    address constant OWNER = address(0xA11CE); // Safe
    address constant KEEPER = address(0xFEED);
    address constant TREASURY = address(0x7EA5);
    address constant STAKER = address(0x5A4C3);
    address constant USER = address(0xB0B);

    function setUp() public {
        usdc = new MockUSDC();
        agent = new MockERC20("Agent", "AGT", 18);
        vault = new AgentStakingVault(address(agent), address(usdc), "Staked AGT", "sAGT");
        splitter = new RevenueSplitter(address(usdc), address(vault), TREASURY, 7000, OWNER);

        //  Permit2 mock at the canonical address.
        MockPermit2 p2 = new MockPermit2();
        vm.etch(0x000000000022D473030F116dDEE9F6B43aC78BA3, address(p2).code);

        router = new MockSwap();
        //  feeRecipient = the agent's RevenueSplitter; default feeBps = 30 (0.30%).
        exec = new OrderExecutor(OWNER, KEEPER, address(router), address(splitter));
        vm.prank(OWNER);
        exec.setAllowedTarget(address(router), true);
        assertEq(exec.feeBps(), 30);
        assertEq(exec.feeRecipient(), address(splitter));

        usdc.mint(USER, 1_000_000e6);
        vm.prank(USER);
        usdc.approve(0x000000000022D473030F116dDEE9F6B43aC78BA3, type(uint256).max);
        agent.mint(address(router), 1_000_000e18);
    }

    function _permit(uint256 amount) internal view returns (IPermit2.PermitTransferFrom memory) {
        return IPermit2.PermitTransferFrom({
            permitted: IPermit2.TokenPermissions({token: address(usdc), amount: amount}),
            nonce: 1,
            deadline: block.timestamp + 1 hours
        });
    }

    function test_orderFee_flowsToStakers() public {
        //  1) A staker deposits the agent token into the vault.
        agent.mint(STAKER, 1_000e18);
        vm.startPrank(STAKER);
        agent.approve(address(vault), type(uint256).max);
        vault.deposit(1_000e18, STAKER);
        vm.stopPrank();

        //  2) The keeper fills a LIMIT order (USDC -> AGENT) through OrderExecutor v2.
        uint256 amountIn = 1_000e6;
        uint256 fee = (amountIn * 30) / 10_000; // 3 USDC
        uint256 swapAmount = amountIn - fee; // 997 USDC
        uint256 out = 1_000e18;
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(usdc), swapAmount, address(agent), USER, out));

        vm.prank(KEEPER);
        exec.executeOrder(_permit(amountIn), USER, "", address(router), data, address(agent), out);

        //  Fee landed in the splitter; the swap got the net.
        assertEq(usdc.balanceOf(address(splitter)), fee, "order fee -> splitter");
        assertEq(usdc.balanceOf(address(router)), swapAmount, "net -> swap");

        //  3) Distribute: 70% to the vault (stakers), 30% to treasury.
        splitter.distributeBalance();
        uint256 toStakers = (fee * 7000) / 10_000; // 2.1 USDC
        uint256 toTreasury = fee - toStakers; // 0.9 USDC
        assertEq(usdc.balanceOf(address(vault)), toStakers, "vault got 70%");
        assertEq(usdc.balanceOf(TREASURY), toTreasury, "treasury got 30%");

        //  4) The staker's USDC yield accrued and is claimable.
        assertEq(vault.pendingRewards(STAKER), toStakers, "staker pending");
        vm.prank(STAKER);
        uint256 p = vault.claim();
        assertEq(p, toStakers);
        assertEq(usdc.balanceOf(STAKER), toStakers, "claimed USDC");
    }
}
