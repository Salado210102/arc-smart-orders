// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {AgentFactory} from "../src/launchpad/AgentFactory.sol";
import {AgentRegistry} from "../src/launchpad/AgentRegistry.sol";
import {GraduationModule} from "../src/launchpad/GraduationModule.sol";
import {LiquidityLocker} from "../src/launchpad/LiquidityLocker.sol";
import {MockDEX} from "../src/launchpad/mocks/MockDEX.sol";

/// @notice Deploys the full Agent Launchpad on Arc (P2) and optionally launches a demo agent.
/// Env: LAUNCHPAD_OWNER (Safe) / LAUNCHPAD_TREASURY / LAUNCHPAD_IDENTITY / LAUNCHPAD_LOCK_SECONDS / LAUNCHPAD_LAUNCH_DEMO
contract DeployLaunchpad is Script {
    address internal constant USDC = 0x3600000000000000000000000000000000000000;
    address internal constant IDENTITY = 0x8004A818BFB912233c491871b3d84c89A494BD9e;

    function run() external {
        address owner = vm.envOr("LAUNCHPAD_OWNER", msg.sender);
        address treasury = vm.envOr("LAUNCHPAD_TREASURY", owner);
        address identity = vm.envOr("LAUNCHPAD_IDENTITY", IDENTITY);
        uint64 lockSeconds = uint64(vm.envOr("LAUNCHPAD_LOCK_SECONDS", uint256(365 days)));
        bool launchDemo = vm.envOr("LAUNCHPAD_LAUNCH_DEMO", false);

        vm.startBroadcast();

        LiquidityLocker locker = new LiquidityLocker(owner);
        AgentRegistry registry = new AgentRegistry(owner);
        MockDEX dex = new MockDEX(); //  testnet AMM (mainnet: real DEX, TBD)
        GraduationModule module = new GraduationModule(owner, USDC, address(dex), address(locker), lockSeconds);
        AgentFactory factory = new AgentFactory(USDC, identity, treasury, owner, address(registry), address(module));
        registry.setFactory(address(factory));

        address token;
        address curve;
        if (launchDemo) {
            (token, curve) = factory.launch(
                "Demo Agent",
                "DEMO",
                1_000_000e18,
                5_000e6,
                1_000_000e6,
                1_000_000e18, // maxWallet (large)
                1_000_000e18,
                "ipfs://bafkreibdi6623n3xpf7ymk62ckb4bo75o3qemwkpfvp5i25j66itxvsoei"
            );
        }

        vm.stopBroadcast();

        console2.log("AgentFactory     :", address(factory));
        console2.log("AgentRegistry    :", address(registry));
        console2.log("GraduationModule :", address(module));
        console2.log("LiquidityLocker  :", address(locker));
        console2.log("MockDEX (LP)     :", address(dex));
        console2.log("owner/treasury   :", owner, treasury);
        if (launchDemo) {
            console2.log("Demo token       :", token);
            console2.log("Demo curve       :", curve);
        }
    }
}
