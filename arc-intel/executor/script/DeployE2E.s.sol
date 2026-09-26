// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Script.sol";
import "../src/ArcIntelExecutor.sol";
import "../src/testonly/TestERC20.sol";
import "../src/testonly/PoolSeeder.sol";

/// @dev TEST-ONLY deployment + pool seeding for the Arc testnet E2E.
contract DeployE2E is Script {
    uint160 internal constant SQRT_PRICE_1_1 = 79228162514264337593543950336; // 2^96

    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address user = vm.addr(pk);
        address pm = vm.envAddress("POOL_MANAGER");

        uint256 amountIn = vm.envOr("AMOUNT_IN", uint256(1e15));
        uint256 minOut = vm.envOr("MIN_OUT", uint256(9e14));
        uint256 permitNonce = vm.envOr("PERMIT_NONCE", uint256(1));
        uint256 orderNonce = vm.envOr("ORDER_NONCE", uint256(1));
        uint256 deadline = block.timestamp + 3600;

        vm.startBroadcast(pk);

        TestERC20 a = new TestERC20("ArcIntel Test A", "TKA");
        TestERC20 b = new TestERC20("ArcIntel Test B", "TKB");
        (address c0, address c1) = address(a) < address(b) ? (address(a), address(b)) : (address(b), address(a));

        IPoolManagerTest.PoolKey memory key = IPoolManagerTest.PoolKey(c0, c1, 3000, 60, address(0));
        bytes32 poolId = keccak256(abi.encode(key));

        bytes32[] memory pools = new bytes32[](1);
        pools[0] = poolId;
        ArcIntelExecutor exec = new ArcIntelExecutor(pm, user, pools);
        PoolSeeder seeder = new PoolSeeder(pm);

        a.mint(address(seeder), 1e22);
        b.mint(address(seeder), 1e22);
        a.mint(user, 1e18);
        b.mint(user, 1e18);

        IPoolManagerTest(pm).initialize(key, SQRT_PRICE_1_1);
        seeder.seed(key, -600, 600, 1e18);

        // user authorizes Permit2 (ERC20-level) so the executor can pull via the signed permit
        TestERC20(c0).approve(exec.PERMIT2(), type(uint256).max);

        vm.stopBroadcast();

        // sell currency0 -> currency1
        string memory json = string.concat(
            "{",
            '"poolManager":"', vm.toString(pm), '",',
            '"executor":"', vm.toString(address(exec)), '",',
            '"user":"', vm.toString(user), '",',
            '"tokenIn":"', vm.toString(c0), '",',
            '"tokenOut":"', vm.toString(c1), '",',
            '"fee":3000,"tickSpacing":60,"hooks":"', vm.toString(address(0)), '",',
            '"zeroForOne":true,',
            '"amountIn":"', vm.toString(amountIn), '",',
            '"minOut":"', vm.toString(minOut), '",',
            '"recipient":"', vm.toString(user), '",',
            '"permitNonce":"', vm.toString(permitNonce), '",',
            '"orderNonce":"', vm.toString(orderNonce), '",',
            '"deadline":"', vm.toString(deadline), '",',
            '"poolId":"', vm.toString(poolId), '"',
            "}"
        );
        vm.writeFile("./deployments.json", json);

        console2.log("executor", address(exec));
        console2.log("token0", c0);
        console2.log("token1", c1);
        console2.log("deadline", deadline);
    }
}
