// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {OrderExecutor} from "../src/OrderExecutor.sol";
import {AgentFactory} from "../src/launchpad/AgentFactory.sol";
import {AgentRegistry} from "../src/launchpad/AgentRegistry.sol";
import {GraduationModule} from "../src/launchpad/GraduationModule.sol";
import {LiquidityLocker} from "../src/launchpad/LiquidityLocker.sol";

/// @notice Deterministic, sequential MAINNET deployment of the full Arc Smart Orders + Agent Launchpad.
/// @dev Safety gate: reverts unless `CONFIRM_MAINNET=1`. Per-agent vaults/splitters are deployed on
///      demand by the operator (see docs/MAINNET_RUNBOOK.md). Idempotent ordering; verify after each.
///
/// Required env:
///   CONFIRM_MAINNET=1
///   LAUNCHPAD_OWNER     (Safe)
///   ORDERS_KEEPER       (keeper EOA)
///   DEX                 (real AMM / graduation venue on Arc)
/// Optional env:
///   LAUNCHPAD_TREASURY  (default: owner)
///   ORDERS_FEE_RECIPIENT(default: treasury — or an agent RevenueSplitter)
///   LAUNCHPAD_LOCK_SECONDS (default: 365 days)
///
/// Arc mainnet:
///   forge script script/DeployMainnet.s.sol --rpc-url https://rpc.mainnet.arc.io \
///     --private-key $PK --broadcast --slow --verify
contract DeployMainnet is Script {
    address internal constant USDC = 0x3600000000000000000000000000000000000000;
    address internal constant IDENTITY = 0x8004A818BFB912233c491871b3d84c89A494BD9e;

    function run() external {
        require(vm.envOr("CONFIRM_MAINNET", uint256(0)) == 1, "DeployMainnet: set CONFIRM_MAINNET=1");

        address owner = vm.envAddress("LAUNCHPAD_OWNER");
        address treasury = vm.envOr("LAUNCHPAD_TREASURY", owner);
        address keeper = vm.envAddress("ORDERS_KEEPER");
        address dex = vm.envAddress("DEX");
        address feeRecipient = vm.envOr("ORDERS_FEE_RECIPIENT", treasury);
        uint64 lockSeconds = uint64(vm.envOr("LAUNCHPAD_LOCK_SECONDS", uint256(365 days)));

        vm.startBroadcast();

        //  1) Liquidity locker (LP anti-rug).
        LiquidityLocker locker = new LiquidityLocker(owner);
        //  2) On-chain agent index.
        AgentRegistry registry = new AgentRegistry(owner);
        //  3) Graduation module (seeds DEX liquidity + locks LP).
        GraduationModule module = new GraduationModule(owner, USDC, dex, address(locker), lockSeconds);
        //  4) Factory (token + curve + ERC-8004 identity + registry).
        AgentFactory factory = new AgentFactory(USDC, IDENTITY, treasury, owner, address(registry), address(module));
        //  5) Wire the registry's factory. `setFactory` is onlyOwner: if the owner is a contract
        //     (Safe), the deployer EOA is NOT authorized — the Safe must execute this after deploy.
        if (owner.code.length == 0) {
            registry.setFactory(address(factory));
        } else {
            console2.log("!! owner is a contract: the Safe MUST call registry.setFactory(factory)");
            console2.log("   to       :", address(registry));
            console2.log("   function : setFactory(address)");
            console2.log("   arg      :", address(factory));
        }
        //  6) Non-custodial order engine (fee → treasury/splitter).
        OrderExecutor exec = new OrderExecutor(owner, keeper, dex, feeRecipient);

        vm.stopBroadcast();

        console2.log("=== Arc Mainnet deployment ===");
        console2.log("LiquidityLocker :", address(locker));
        console2.log("AgentRegistry   :", address(registry));
        console2.log("GraduationModule:", address(module));
        console2.log("AgentFactory    :", address(factory));
        console2.log("OrderExecutor   :", address(exec));
        console2.log("owner/treasury  :", owner, treasury);
        console2.log("keeper          :", keeper);
        console2.log("dex             :", dex);
        console2.log("feeRecipient    :", feeRecipient);
        console2.log("");
        console2.log("NEXT: verify sources, then deploy per-agent AgentStakingVault + RevenueSplitter on demand.");
    }
}
