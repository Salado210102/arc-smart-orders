// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {OrderExecutor} from "../src/OrderExecutor.sol";
import {MockStableRouter} from "../src/mocks/MockStableRouter.sol";

/// @notice Deploys the OrderExecutor on Arc (and optionally the test router).
/// Env:
///   EXECUTOR_OWNER        (owner/multisig)   default: msg.sender
///   EXECUTOR_KEEPER       (keeper EOA)       required
///   EXECUTOR_TARGET       (swap target)      optional; if DEPLOY_MOCK_ROUTER=1 this is set to the mock
///   DEPLOY_MOCK_ROUTER    (bool)             optional; deploys MockStableRouter(USDC, EURC) and whitelists it
///
/// Arc testnet:
///   forge script script/Deploy.s.sol --rpc-url https://rpc.testnet.arc.io --broadcast
contract Deploy is Script {
    // Arc testnet addresses (lowercase = no checksum requirement).
    address internal constant USDC = 0x3600000000000000000000000000000000000000;
    address internal constant EURC_TESTNET = 0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a;

    function run() external {
        address owner = vm.envOr("EXECUTOR_OWNER", msg.sender);
        address keeper = vm.envAddress("EXECUTOR_KEEPER");
        address feeRecipient = vm.envOr("EXECUTOR_FEE_RECIPIENT", owner);
        bool deployMock = vm.envOr("DEPLOY_MOCK_ROUTER", false);
        address target = vm.envOr("EXECUTOR_TARGET", address(0));

        vm.startBroadcast();

        if (deployMock) {
            MockStableRouter mock = new MockStableRouter(USDC, EURC_TESTNET);
            target = address(mock);
            console2.log("MockStableRouter:", target);
        }

        OrderExecutor exec = new OrderExecutor(owner, keeper, target, feeRecipient);

        vm.stopBroadcast();

        console2.log("OrderExecutor:", address(exec));
        console2.log("owner       :", owner);
        console2.log("keeper      :", keeper);
        console2.log("swapTarget  :", target);
        console2.log("feeRecipient:", feeRecipient);
        console2.log("");
        console2.log("NEXT:");
        console2.log("  1) Fund the mock router with testnet EURC (so it can pay swaps).");
        console2.log("  2) The user approves Permit2 for USDC once (sdk.ensurePermit2Approval).");
        console2.log("  3) Put EXECUTOR + ROUTER in keeper/.env and `npm start`.");
    }
}
