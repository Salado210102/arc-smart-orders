// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Script.sol";
import "../src/ArcIntelExecutorV2.sol";

/// @notice Deploy ArcIntelExecutorV2 on Arc testnet. Owner = the Safe; no pools pre-allowed
///         (the Safe allowlists pools with setAllowedPool after deployment).
contract DeployV2 is Script {
    function run() external {
        address poolManager = 0x8366a39CC670B4001A1121B8F6A443A643e40951;
        address safeOwner = 0xe911D6F5f3a7D2f06dcD32006318ED5EF95986b7;
        uint256 pk = vm.envUint("RELAYER_KEY");

        vm.startBroadcast(pk);
        bytes32[] memory pools = new bytes32[](0);
        ArcIntelExecutorV2 v2 = new ArcIntelExecutorV2(poolManager, safeOwner, pools);
        vm.stopBroadcast();

        console2.log("ArcIntelExecutorV2", address(v2));
    }
}
