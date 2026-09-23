// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {AgentStakingVault} from "../src/launchpad/AgentStakingVault.sol";
import {RevenueSplitter} from "../src/launchpad/RevenueSplitter.sol";

/// @notice Deploys the staking vault + revenue splitter for an agent token.
/// Env: STAKING_TOKEN (required, the AgentToken) / STAKING_OWNER / STAKING_TREASURY / STAKING_STAKER_BPS
contract DeployStaking is Script {
    address internal constant USDC = 0x3600000000000000000000000000000000000000;

    function run() external {
        address owner = vm.envOr("STAKING_OWNER", msg.sender);
        address treasury = vm.envOr("STAKING_TREASURY", owner);
        address token = vm.envAddress("STAKING_TOKEN");
        uint16 stakerBps = uint16(vm.envOr("STAKING_STAKER_BPS", uint256(7000)));

        vm.startBroadcast();
        AgentStakingVault vault = new AgentStakingVault(token, USDC, "Staked Agent", "sAGT");
        RevenueSplitter splitter = new RevenueSplitter(USDC, address(vault), treasury, stakerBps, owner);
        vm.stopBroadcast();

        console2.log("AgentStakingVault:", address(vault));
        console2.log("RevenueSplitter :", address(splitter));
        console2.log("asset token     :", token);
        console2.log("owner/treasury  :", owner, treasury);
        console2.log("stakerShareBps  :", stakerBps);
    }
}
