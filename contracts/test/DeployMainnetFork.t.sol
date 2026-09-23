// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {DeployMainnet} from "../script/DeployMainnet.s.sol";
import {MockDEX} from "../src/launchpad/mocks/MockDEX.sol";
import {MockIdentityRegistry} from "../src/launchpad/mocks/Mocks.sol";

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

/// @notice Final pre-audit dry-run of `DeployMainnet.s.sol` against a **fork of Arc mainnet**.
///
///         The real ERC-8004 / ERC-8183 registries are not deployed on Arc mainnet yet, so this test
///         *simulates their future presence* by etching the mock runtime code at the canonical
///         addresses, then runs the exact mainnet script and lets its post-deploy `require`s assert
///         the whole wiring (owner==Safe, feeBps==30, treasury/feeRecipient/dex/locker).
///
///         Run with the environment the script expects (see `.env.example`):
///         ```bash
///         CONFIRM_MAINNET=1 USDC_MAINNET=0x3600…0000 DEX_ROUTER=0x…D3 \
///         ERC8004_REGISTRY=0x8004A818…BD9e ERC8183_ESCROW=0x0747…4583 \
///         ORDERS_KEEPER=0x327f…50bC LAUNCHPAD_OWNER=0x0FBFAF…7e93 \
///         forge test --match-test test_FullDeployOnFork -vv
///         ```
contract DeployMainnetForkTest is Test {
    address internal constant USDC = 0x3600000000000000000000000000000000000000;
    address internal constant DEX = 0x00000000000000000000000000000000000000D3; // fixed ether for the etched venue
    address internal constant IDENTITY = 0x8004A818BFB912233c491871b3d84c89A494BD9e; // canonical (no code on mainnet yet)
    address internal constant ESCROW = 0x0747EEf0706327138c69792bF28Cd525089e4583; // canonical (no code on mainnet yet)

    address internal constant SAFE_FACTORY = 0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67;
    address internal constant SINGLETON = 0x41675C099F32341bf84BFc5382aF534df5C7461a;
    address internal constant FALLBACK = 0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99;
    address internal constant ARC_SAFE = 0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93;
    address internal constant SIGNER_1 = 0x3df362854B3981b1367aC2DFa41533386628c977;
    address internal constant SIGNER_2 = 0xE34AA475d6F606671DB886fE9db3baFA428a1279;

    /// @dev Full deploy on the mainnet fork; reverts if any post-deploy invariant fails.
    ///      Skipped (no RPC hit) unless CONFIRM_MAINNET=1 + the env vars are provided.
    function test_FullDeployOnFork_InvariantsPass() public {
        if (vm.envOr("CONFIRM_MAINNET", uint256(0)) != 1) {
            vm.skip(true);
            return;
        }

        string memory rpc = vm.envOr("ARC_MAINNET_RPC", string("https://rpc.mainnet.arc.io"));
        vm.createSelectFork(rpc);

        //  Simulate the future mainnet infra with mocks at the addresses the script will read.
        vm.etch(DEX, address(new MockDEX()).code);
        vm.etch(IDENTITY, address(new MockIdentityRegistry()).code);
        vm.etch(ESCROW, address(new MockDEX()).code);

        //  Deploy the real Safe 2/2 on the fork and confirm its deterministic address.
        address[] memory owners = new address[](2);
        owners[0] = SIGNER_1;
        owners[1] = SIGNER_2;
        bytes memory data =
            abi.encodeCall(ISafeSetup.setup, (owners, 2, address(0), "", FALLBACK, address(0), 0, address(0)));
        address safe = ISafeProxyFactory(SAFE_FACTORY).createProxyWithNonce(SINGLETON, data, 0);
        assertEq(safe, ARC_SAFE, "Safe address != deterministic 0x0FBFAF...7e93");

        new DeployMainnet().run();
    }
}
