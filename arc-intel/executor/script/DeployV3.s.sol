// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Script.sol";
import "../src/ArcIntelExecutorV3.sol";

/// @notice Deploy ArcIntelExecutorV3 on Arc testnet. Owner = the Safe; no pools pre-allowed
///         (owner sets policy with setAllowAllPools / setAllowedHook / setAllowedPool).
contract DeployV3 is Script {
    function run() external {
        address poolManager = 0x8366a39CC670B4001A1121B8F6A443A643e40951;
        address safeOwner = 0xe911D6F5f3a7D2f06dcD32006318ED5EF95986b7;
        uint256 pk = vm.envUint("RELAYER_KEY");

        vm.startBroadcast(pk);
        bytes32[] memory pools = new bytes32[](0);
        ArcIntelExecutorV3 v3 = new ArcIntelExecutorV3(poolManager, safeOwner, pools, false);
        vm.stopBroadcast();

        // B2: mainnet MUST NOT have allowAllPools (policy = allowedHooks per launchpad + allowedPools).
        require(!v3.isTestnet(), "mainnet deploy must be isTestnet=false");
        require(!v3.allowAllPools(), "allowAllPools MUST be false on mainnet");
        require(v3.owner() == safeOwner, "owner must be the Safe");

        console2.log("ArcIntelExecutorV3", address(v3));
        console2.log("isTestnet", v3.isTestnet());
        console2.log("allowAllPools", v3.allowAllPools());
    }
}
