// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "../interfaces/IArcIntel.sol";

/// @dev TEST-ONLY minimal view of the v4 PoolManager for initializing + seeding a pool.
///      Not part of the audit scope.
interface IPoolManagerTest {
    struct PoolKey {
        address currency0;
        address currency1;
        uint24 fee;
        int24 tickSpacing;
        address hooks;
    }
    struct ModifyLiquidityParams {
        int24 tickLower;
        int24 tickUpper;
        int256 liquidityDelta;
        bytes32 salt;
    }

    function unlock(bytes calldata data) external returns (bytes memory);
    function initialize(PoolKey memory key, uint160 sqrtPriceX96) external returns (int24);
    function modifyLiquidity(PoolKey memory key, ModifyLiquidityParams memory params, bytes calldata hookData)
        external
        returns (int256 callerDelta, int256 feesAccrued);
    function sync(address currency) external;
    function settle() external payable returns (uint256);
    function take(address currency, address to, uint256 amount) external;
}

/// @dev TEST-ONLY helper that seeds a v4 pool (adds liquidity) via the unlock callback.
contract PoolSeeder is IUnlockCallback {
    IPoolManagerTest internal immutable pm;

    constructor(address pm_) {
        pm = IPoolManagerTest(pm_);
    }

    function seed(IPoolManagerTest.PoolKey calldata key, int24 lower, int24 upper, int128 liquidity) external {
        pm.unlock(abi.encode(key, lower, upper, liquidity));
    }

    function unlockCallback(bytes calldata data) external returns (bytes memory) {
        require(msg.sender == address(pm), "not pm");
        (IPoolManagerTest.PoolKey memory key, int24 lower, int24 upper, int128 liquidity) =
            abi.decode(data, (IPoolManagerTest.PoolKey, int24, int24, int128));

        (int256 delta,) =
            pm.modifyLiquidity(key, IPoolManagerTest.ModifyLiquidityParams(lower, upper, int256(liquidity), bytes32(0)), "");

        int128 amount0 = int128(delta >> 128);
        int128 amount1 = int128(delta);

        if (amount0 < 0) {
            pm.sync(key.currency0);
            IERC20Min(key.currency0).transfer(address(pm), uint128(-amount0));
            pm.settle();
        } else if (amount0 > 0) {
            pm.take(key.currency0, address(this), uint128(amount0));
        }
        if (amount1 < 0) {
            pm.sync(key.currency1);
            IERC20Min(key.currency1).transfer(address(pm), uint128(-amount1));
            pm.settle();
        } else if (amount1 > 0) {
            pm.take(key.currency1, address(this), uint128(amount1));
        }
        return "";
    }
}
