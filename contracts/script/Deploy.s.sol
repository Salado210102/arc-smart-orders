// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {OrderExecutor} from "../src/OrderExecutor.sol";

/// @notice Deploy del OrderExecutor en Arc.
///   EXECUTOR_OWNER  (multisig/owner)   def. msg.sender
///   EXECUTOR_KEEPER (keeper EOA)       requerido
///   EXECUTOR_TARGET (router/venue)     opcional (se puede autorizar luego con setAllowedTarget)
///
/// Arc testnet: forge script script/Deploy.s.sol --rpc-url https://rpc.testnet.arc.io --broadcast
contract Deploy is Script {
    function run() external {
        address owner = vm.envOr("EXECUTOR_OWNER", msg.sender);
        address keeper = vm.envAddress("EXECUTOR_KEEPER");
        address target = vm.envOr("EXECUTOR_TARGET", address(0));

        vm.startBroadcast();
        OrderExecutor exec = new OrderExecutor(owner, keeper, target);
        vm.stopBroadcast();

        console2.log("OrderExecutor:", address(exec));
        console2.log("owner:", owner);
        console2.log("keeper:", keeper);
        console2.log("swapTarget:", target);
    }
}
