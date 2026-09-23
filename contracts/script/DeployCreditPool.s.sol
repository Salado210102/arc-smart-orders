// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {AgentCreditPool} from "../src/credit/AgentCreditPool.sol";

/// @notice Deterministic deploy of the AgentCreditPool (invite-only USDC micro-credit on Arc).
/// @dev Safety gates:
///      - reverts unless `CONFIRM_DEPLOY=1`;
///      - `USDC_ADDRESS` and `SAFE_ADDRESS` must be deployed **contracts**;
///      - owner + treasury = the Safe (never an EOA).
///      Owner-only follow-ups (setRoles/whitelist/policy) are executed **by the Safe** — printed here.
///
/// Required env:
///   CONFIRM_DEPLOY=1
///   USDC_ADDRESS   USDC (ERC-20, 6 dec) on Arc — 0x3600...0000
///   SAFE_ADDRESS   Safe 2/2 -> owner AND treasury
/// Optional env:
///   RISK_MANAGER   default: SAFE_ADDRESS
///   KEEPER         default: SAFE_ADDRESS (auto-repay via ERC-8183)
///
/// Run:
///   forge script script/DeployCreditPool.s.sol --rpc-url <arc> --private-key $PK --broadcast
contract DeployCreditPool is Script {
    function run() external {
        require(vm.envOr("CONFIRM_DEPLOY", uint256(0)) == 1, "DeployCreditPool: set CONFIRM_DEPLOY=1");

        address usdc = _contractEnv("USDC_ADDRESS");
        address safe = _contractEnv("SAFE_ADDRESS"); // owner + treasury
        address riskManager = vm.envOr("RISK_MANAGER", safe);
        address keeper = vm.envOr("KEEPER", safe);

        require(riskManager != address(0), "RISK_MANAGER = 0");
        require(keeper != address(0), "KEEPER = 0");

        vm.startBroadcast();
        AgentCreditPool pool = new AgentCreditPool(usdc, safe, safe, riskManager);
        vm.stopBroadcast();

        // ---- post-deploy invariants ----
        require(address(pool.usdc()) == usdc, "usdc mismatch");
        require(pool.owner() == safe, "owner != Safe");
        require(pool.treasury() == safe, "treasury != Safe");
        require(pool.riskManager() == riskManager, "riskManager mismatch");
        require(pool.paused() == false, "paused on deploy");

        console2.log("=== AgentCreditPool deployment ===");
        console2.log("pool            :", address(pool));
        console2.log("usdc            :", usdc);
        console2.log("owner/treasury  :", safe);
        console2.log("riskManager     :", riskManager);
        console2.log("keeper          :", keeper);
        console2.log("minBond (USDC)  :", pool.minBond());
        console2.log("interestBps     :", pool.interestBps());
        console2.log("perfFeeBps      :", pool.performanceFeeBps());

        // ---- Safe follow-ups (owner is the Safe; the deployer EOA cannot call these) ----
        if (safe.code.length == 0) {
            // testnet/EOA-owner convenience — production uses the Safe (branch below)
            pool.setRoles(riskManager, keeper);
        } else {
            console2.log("");
            console2.log("!! The Safe MUST execute:");
            console2.log("   setRoles(riskManager, keeper)");
            console2.log("   setLP(<lp>, true)            // whitelist LPs");
            console2.log("   setAgent(<agent>, true)      // whitelist agents");
            console2.log("   setPolicy(minLoan, maxLoan, maxTerm, maxPerAgent, epochCap, epochDuration, maxUtilBps)");
            console2.log("   helper: node ops/safe-exec.mjs");
        }
    }

    /// @dev Reads a required address env var; reverts if missing/zero or if it has no code.
    function _contractEnv(string memory key) internal view returns (address a) {
        a = vm.envOr(key, address(0));
        require(a != address(0), string.concat(key, ": missing or zero"));
        require(a.code.length > 0, string.concat(key, ": no contract code at address"));
    }
}
