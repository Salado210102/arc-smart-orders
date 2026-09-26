// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Test.sol";
import "../src/interfaces/IArcIntel.sol";

/// @dev Minimal swapper that exercises the REAL Arc PoolManager + a REAL Argus pool on a fork.
///      Bypasses Permit2 (canonical/audited) to isolate the v4 interface + hook tax, which is
///      the actual unknown before audit. Read-only: fork state only, no real funds.
contract ForkSwapper is IUnlockCallback {
    IPoolManager internal immutable pm;

    constructor(address pm_) {
        pm = IPoolManager(pm_);
    }

    function doSwap(IPoolManager.PoolKey memory key, bool zeroForOne, uint256 amountIn)
        external
        returns (uint256 out)
    {
        address tokenOut = zeroForOne ? key.currency1 : key.currency0;
        uint256 before = uint256(IERC20Min(tokenOut).balanceOf(address(this)));
        pm.unlock(abi.encode(key, zeroForOne, amountIn));
        out = uint256(IERC20Min(tokenOut).balanceOf(address(this))) - before;
    }

    function unlockCallback(bytes calldata data) external returns (bytes memory) {
        require(msg.sender == address(pm), "not pm");
        (IPoolManager.PoolKey memory key, bool zeroForOne, uint256 amountIn) =
            abi.decode(data, (IPoolManager.PoolKey, bool, uint256));

        int256 delta = pm.swap(
            key,
            IPoolManager.SwapParams({
                zeroForOne: zeroForOne,
                amountSpecified: -int256(amountIn),
                sqrtPriceLimitX96: zeroForOne ? uint160(4295128740) : uint160(1461446703485210103287273052203988822378723970341)
            }),
            ""
        );

        int128 amount0 = int128(delta >> 128);
        int128 amount1 = int128(delta);
        if (amount0 > 0) pm.take(key.currency0, address(this), uint128(amount0));
        if (amount1 > 0) pm.take(key.currency1, address(this), uint128(amount1));
        if (amount0 < 0) {
            pm.sync(key.currency0);
            IERC20Min(key.currency0).transfer(address(pm), uint128(-amount0));
            pm.settle();
        }
        if (amount1 < 0) {
            pm.sync(key.currency1);
            IERC20Min(key.currency1).transfer(address(pm), uint128(-amount1));
            pm.settle();
        }
        return "";
    }
}

contract ArcIntelForkTest is Test {
    address internal constant PM = 0x8366a39CC670B4001A1121B8F6A443A643e40951;
    address internal constant USDC = 0x3600000000000000000000000000000000000000;
    address internal constant LUNYA = 0xBF5c7958A9003f62D7a6a0Bdd5dE7D5F5659Ff53;
    address internal constant HOOK = 0xBEbE26760301c31d668E3AA4c3e3042A11856044;

    function _key() internal pure returns (IPoolManager.PoolKey memory) {
        // USDC (0x36..) < LUNYA (0xbf..) => currency0 = USDC, currency1 = LUNYA
        return IPoolManager.PoolKey(USDC, LUNYA, 10000, 200, HOOK);
    }

    function testForkRealPoolSellLunya() public {
        if (!vm.envOr("RUN_FORK", false)) {
            vm.skip(true);
        }
        vm.createSelectFork(vm.envOr("ARC_RPC", string("https://rpc.mainnet.arc.io")));

        ForkSwapper sw = new ForkSwapper(PM);
        deal(LUNYA, address(sw), 1e18);

        uint256 out = sw.doSwap(_key(), false, 1e18); // sell LUNYA -> USDC
        emit log_named_uint("usdc_out_for_1e18_lunya", out);
        assertGt(out, 0, "swap produced no output");
    }
}
