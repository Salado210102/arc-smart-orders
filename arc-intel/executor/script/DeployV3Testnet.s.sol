// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Script.sol";
import "../src/ArcIntelExecutorV3.sol";

/// @notice Testnet convenience: deploy ArcIntelExecutorV3 with owner = the relayer (admin EOA) and
///         enable ALL pools in one shot. Removes the Safe step for testing. (Mainnet: owner = Safe.)
contract DeployV3Testnet is Script {
    function run() external {
        address poolManager = 0x8366a39CC670B4001A1121B8F6A443A643e40951;
        uint256 pk = vm.envUint("RELAYER_KEY");
        address admin = vm.addr(pk);

        vm.startBroadcast(pk);
        bytes32[] memory pools = new bytes32[](0);
        ArcIntelExecutorV3 ex = new ArcIntelExecutorV3(poolManager, admin, pools, true);
        ex.setAllowAllPools(true);
        vm.stopBroadcast();

        console2.log("ArcIntelExecutorV3 (owner=relayer, allowAll)", address(ex));
    }
}
