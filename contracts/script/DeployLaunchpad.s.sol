// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {AgentFactory} from "../src/launchpad/AgentFactory.sol";

/// @notice Deploys the AgentFactory (Agent Launchpad) on Arc, and optionally launches a demo agent.
/// Env:
///   LAUNCHPAD_OWNER      (Safe)        default: msg.sender
///   LAUNCHPAD_TREASURY   (Safe)        default: owner
///   LAUNCHPAD_LAUNCH_DEMO (bool)       optional: launch a demo agent
///   LAUNCHPAD_IDENTITY   (registry)    default: ERC-8004 IdentityRegistry (Arc)
/// Arc testnet/mainnet:
///   forge script script/DeployLaunchpad.s.sol --rpc-url https://rpc.testnet.arc.io --broadcast
contract DeployLaunchpad is Script {
    //  Arc (same addresses on mainnet & testnet)
    address internal constant USDC = 0x3600000000000000000000000000000000000000;
    address internal constant IDENTITY = 0x8004A818BFB912233c491871b3d84c89A494BD9e;

    function run() external {
        address owner = vm.envOr("LAUNCHPAD_OWNER", msg.sender);
        address treasury = vm.envOr("LAUNCHPAD_TREASURY", owner);
        address identity = vm.envOr("LAUNCHPAD_IDENTITY", IDENTITY);
        bool launchDemo = vm.envOr("LAUNCHPAD_LAUNCH_DEMO", false);

        vm.startBroadcast();
        AgentFactory factory = new AgentFactory(USDC, identity, treasury, owner);

        address token;
        address curve;
        if (launchDemo) {
            (token, curve) = factory.launch(
                "Demo Agent",
                "DEMO",
                1_000_000e18, // supply = y0
                5_000e6, // x0 virtual USDC
                1_000_000e6, // graduation threshold
                100_000e18, // maxWallet
                100_000e18, // maxTx
                "ipfs://bafkreibdi6623n3xpf7ymk62ckb4bo75o3qemwkpfvp5i25j66itxvsoei"
            );
        }
        vm.stopBroadcast();

        console2.log("AgentFactory:", address(factory));
        console2.log("owner       :", owner);
        console2.log("treasury    :", treasury);
        console2.log("identity    :", identity);
        if (launchDemo) {
            console2.log("Demo token  :", token);
            console2.log("Demo curve  :", curve);
        }
    }
}
