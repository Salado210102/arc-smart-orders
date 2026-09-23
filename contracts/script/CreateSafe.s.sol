// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";

interface ISafeProxyFactory {
    function createProxyWithNonce(address _singleton, bytes memory initializer, uint256 saltNonce)
        external
        returns (address proxy);
}

interface ISafeSetup {
    function setup(
        address[] calldata _owners,
        uint256 _threshold,
        address to,
        bytes calldata data,
        address fallbackHandler,
        address paymentToken,
        uint256 payment,
        address paymentReceiver
    ) external;
}

/// @notice Creates a 2/2 Safe (multisig) on Arc — the treasury / owner for OrderExecutor v2.
///         Safe v1.4.1 is already deployed on Arc mainnet & testnet (verified).
/// Env:
///   SAFE_OWNER_1 (required)  signer #1
///   SAFE_OWNER_2 (required)  signer #2
///   SAFE_SALT    (optional)  salt nonce (default 0)
/// Run (Arc mainnet):
///   forge script script/CreateSafe.s.sol --rpc-url https://rpc.mainnet.arc.io --broadcast
contract CreateSafe is Script {
    // Safe v1.4.1 (same on Arc mainnet & testnet)
    address internal constant PROXY_FACTORY = 0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67;
    address internal constant SINGLETON = 0x41675C099F32341bf84BFc5382aF534df5C7461a;
    address internal constant FALLBACK_HANDLER = 0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99;

    function run() external {
        address owner1 = vm.envAddress("SAFE_OWNER_1");
        address owner2 = vm.envAddress("SAFE_OWNER_2");
        uint256 salt = vm.envOr("SAFE_SALT", uint256(0));

        address[] memory owners = new address[](2);
        owners[0] = owner1;
        owners[1] = owner2;

        bytes memory setupData = abi.encodeCall(
            ISafeSetup.setup,
            (owners, 2, address(0), "", FALLBACK_HANDLER, address(0), 0, address(0))
        );

        vm.startBroadcast();
        address safe = ISafeProxyFactory(PROXY_FACTORY).createProxyWithNonce(SINGLETON, setupData, salt);
        vm.stopBroadcast();

        console2.log("Safe 2/2:", safe);
        console2.log("owner1  :", owner1);
        console2.log("owner2  :", owner2);
    }
}
