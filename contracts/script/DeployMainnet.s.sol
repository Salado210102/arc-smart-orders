// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {OrderExecutor} from "../src/OrderExecutor.sol";
import {AgentFactory} from "../src/launchpad/AgentFactory.sol";
import {AgentRegistry} from "../src/launchpad/AgentRegistry.sol";
import {GraduationModule} from "../src/launchpad/GraduationModule.sol";
import {LiquidityLocker} from "../src/launchpad/LiquidityLocker.sol";

/// @notice Deterministic, sequential MAINNET deployment of the full Arc Smart Orders + Agent Launchpad.
/// @dev Safety gates:
///      - reverts unless `CONFIRM_MAINNET=1`;
///      - every external address (USDC / DEX / ERC-8004 / ERC-8183) is read from env and **must be a
///        deployed contract** — so the script refuses to run on mainnet until the real venues/registries
///        exist there;
///      - `owner` / `treasury` / `feeRecipient` **must be contracts** (i.e. the Safe), never an EOA.
///
/// Required env:
///   CONFIRM_MAINNET=1
///   USDC_MAINNET          USDC (ERC-20) address
///   DEX_ROUTER            real AMM / graduation venue on Arc
///   ORDERS_KEEPER         keeper EOA
/// Optional env (0x0/unset = skip):
///   ERC8004_REGISTRY      ERC-8004 IdentityRegistry — if 0, launches SKIP ERC-8004 (set later via Safe)
///   ERC8183_ESCROW        ERC-8183 AgenticCommerce (keeper-side) — validated only if provided
/// Optional env:
///   LAUNCHPAD_OWNER       default: the Arc Safe 2/2 (0x0FBFAF…7e93)
///   LAUNCHPAD_TREASURY    default: owner
///   ORDERS_FEE_RECIPIENT  default: treasury
///   ORDERS_FEE_BPS        default: 30 (0.30%), cap 1000
///   SOFT_LAUNCH_MAX_GRADUATION_USDC  default: 10000e6 ($10k) — policy guardrail (see note)
///   LAUNCHPAD_LOCK_SECONDS           default: 365 days
///
/// Arc mainnet:
///   forge script script/DeployMainnet.s.sol --rpc-url https://rpc.mainnet.arc.io \
///     --private-key $PK --broadcast --slow --verify
contract DeployMainnet is Script {
    /// @dev Default owner/treasury/feeRecipient (Arc Safe 2/2).
    address internal constant ARC_SAFE = 0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93;

    function run() external {
        require(vm.envOr("CONFIRM_MAINNET", uint256(0)) == 1, "DeployMainnet: set CONFIRM_MAINNET=1");

        //  ---- dynamic, validated addresses ----
        address usdc = _contractEnv("USDC_MAINNET");
        address dex = _contractEnv("DEX_ROUTER");
        //  Optional: 0x0 (or unset) = skip. If provided, must be a deployed contract.
        address identity = _optionalContractEnv("ERC8004_REGISTRY");
        address erc8183 = _optionalContractEnv("ERC8183_ESCROW");

        //  ---- roles (owner/treasury/feeRecipient MUST be contracts = the Safe) ----
        address owner = vm.envOr("LAUNCHPAD_OWNER", ARC_SAFE);
        address treasury = vm.envOr("LAUNCHPAD_TREASURY", owner);
        address feeRecipient = vm.envOr("ORDERS_FEE_RECIPIENT", treasury);
        address keeper = vm.envAddress("ORDERS_KEEPER");

        require(owner.code.length > 0, "LAUNCHPAD_OWNER must be a contract (Safe)");
        require(treasury.code.length > 0, "LAUNCHPAD_TREASURY must be a contract");
        require(feeRecipient.code.length > 0, "ORDERS_FEE_RECIPIENT must be a contract");
        require(keeper != address(0), "ORDERS_KEEPER = 0");

        //  ---- soft-launch policy ----
        uint256 feeBps = vm.envOr("ORDERS_FEE_BPS", uint256(30));
        uint256 softCapUsdc = vm.envOr("SOFT_LAUNCH_MAX_GRADUATION_USDC", uint256(10_000e6));
        uint64 lockSeconds = uint64(vm.envOr("LAUNCHPAD_LOCK_SECONDS", uint256(365 days)));
        require(feeBps <= 1000, "ORDERS_FEE_BPS > 10%");

        vm.startBroadcast();

        //  1) Liquidity locker (LP anti-rug).
        LiquidityLocker locker = new LiquidityLocker(owner);
        //  2) On-chain agent index.
        AgentRegistry registry = new AgentRegistry(owner);
        //  3) Graduation module (seeds DEX liquidity + locks LP).
        GraduationModule module = new GraduationModule(owner, usdc, dex, address(locker), lockSeconds);
        //  4) Factory (token + curve + ERC-8004 identity + registry).
        AgentFactory factory = new AgentFactory(usdc, identity, treasury, owner, address(registry), address(module));
        //  5) Non-custodial order engine (fee → treasury/splitter). Default feeBps = 30 in the ctor.
        OrderExecutor exec = new OrderExecutor(owner, keeper, dex, feeRecipient);

        vm.stopBroadcast();

        //  ---- post-deploy invariants: everything is owned by the Safe ----
        require(locker.owner() == owner, "locker owner != Safe");
        require(registry.owner() == owner, "registry owner != Safe");
        require(module.owner() == owner, "module owner != Safe");
        require(factory.owner() == owner, "factory owner != Safe");
        require(exec.owner() == owner, "executor owner != Safe");
        require(exec.feeBps() == 30, "executor feeBps != 30");
        require(exec.feeRecipient() == feeRecipient, "executor feeRecipient mismatch");
        require(factory.treasury() == treasury, "factory treasury mismatch");
        require(module.dex() == dex, "module dex mismatch");
        require(module.locker() == address(locker), "module locker mismatch");

        console2.log("=== Arc deployment ===");
        console2.log("LiquidityLocker :", address(locker));
        console2.log("AgentRegistry   :", address(registry));
        console2.log("GraduationModule:", address(module));
        console2.log("AgentFactory    :", address(factory));
        console2.log("OrderExecutor   :", address(exec));
        console2.log("owner/treasury  :", owner, treasury);
        console2.log("keeper          :", keeper);
        console2.log("dex             :", dex);
        console2.log("identity(8004)  :", identity);
        console2.log("escrow(8183)    :", erc8183);
        console2.log("feeRecipient    :", feeRecipient);
        console2.log("ORDS feeBps     :", feeBps);
        console2.log("soft-launch cap :", softCapUsdc, "USDC graduation/agent");

        //  ---- optional-infra warnings ----
        if (identity == address(0)) {
            console2.log("");
            console2.log("WARN: ERC8004_REGISTRY=0 -> launches SKIP ERC-8004; call setIdentity(Safe) once live");
        }
        if (erc8183 == address(0)) {
            console2.log("WARN: ERC8183_ESCROW=0 -> ERC-8183 jobs disabled (keeper-side); set before agentic jobs");
        }

        //  ---- Safe follow-up: registry.setFactory is onlyOwner (the deployer cannot call it) ----
        console2.log("");
        console2.log("!! The Safe MUST execute registry.setFactory(factory):");
        console2.log("   to       :", address(registry));
        console2.log("   function : setFactory(address)");
        console2.log("   arg      :", address(factory));
        console2.log("   helper   : node ops/safe-exec.mjs");

        //  ---- soft-launch policy notes ----
        console2.log("");
        console2.log("SOFT LAUNCH:");
        console2.log("  - fee fixed at 30 bps (Safe can change via setFee / setFeeDefaults).");
        console2.log("  - graduation cap is per-agent (AgentFactory.launch arg); the DApp defaults to the cap.");
        console2.log("  - EMERGENCY BRAKE (owner-only, no Pausable in contracts):");
        console2.log("      exec.setAllowedTarget(dex, false)  -> all swaps revert");
        console2.log("      factory.setGraduationModule(0)     -> graduation disabled");
        console2.log("      factory.setIdentity(0)             -> launches skip ERC-8004");
        console2.log("      exec.setKeeper(newKeeper)          -> rotate/neutralise the keeper");
    }

    /// @dev Reads a required address env var; reverts if missing/zero or if it has no code.
    function _contractEnv(string memory key) internal view returns (address a) {
        a = vm.envOr(key, address(0));
        require(a != address(0), string.concat(key, ": missing or zero"));
        require(a.code.length > 0, string.concat(key, ": no contract code at address"));
    }

    /// @dev Reads an optional address env var. 0x0/unset = skip. If set, it must have code.
    function _optionalContractEnv(string memory key) internal view returns (address a) {
        a = vm.envOr(key, address(0));
        if (a != address(0)) {
            require(a.code.length > 0, string.concat(key, ": no contract code at address"));
        }
    }
}
