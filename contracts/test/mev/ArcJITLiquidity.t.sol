// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {ArcJITLiquidity} from "../../src/mev/ArcJITLiquidity.sol";
import {MockUSDC, MockERC20} from "../../src/launchpad/mocks/Mocks.sol";

interface IERC20JTest {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface INFPMTest {
    struct MintParams {
        address token0;
        address token1;
        uint24 fee;
        int24 tickLower;
        int24 tickUpper;
        uint256 amount0Desired;
        uint256 amount1Desired;
        uint256 amount0Min;
        uint256 amount1Min;
        address recipient;
        uint256 deadline;
    }

    struct DecreaseLiquidityParams {
        uint256 tokenId;
        uint128 liquidity;
        uint256 amount0Min;
        uint256 amount1Min;
        uint256 deadline;
    }

    struct CollectParams {
        uint256 tokenId;
        address recipient;
        uint128 amount0Max;
        uint128 amount1Max;
    }
}

/// @notice Minimal Uniswap v3 pool mock (only `slot0.tick` is used by the JIT contract).
contract MockPool {
    int24 public tick;

    constructor(int24 tick_) {
        tick = tick_;
    }

    function setTick(int24 t) external {
        tick = t;
    }

    function slot0()
        external
        view
        returns (uint160, int24, uint16, uint16, uint16, uint8, bool)
    {
        return (0, tick, 0, 0, 0, 0, true);
    }
}

/// @notice NonfungiblePositionManager mock: mint pulls capital, collect pays principal + fees, burn.
contract MockNFPM {
    MockUSDC public usdc;
    MockERC20 public token1;
    uint256 public collect0; // USDC paid on collect (principal + fees)
    uint256 public collect1; // token1 paid on collect
    uint256 public nextId = 1;

    constructor(MockUSDC usdc_, MockERC20 token1_) {
        usdc = usdc_;
        token1 = token1_;
    }

    function setCollect(uint256 c0, uint256 c1) external {
        collect0 = c0;
        collect1 = c1;
    }

    function mint(INFPMTest.MintParams calldata p)
        external
        payable
        returns (uint256 tokenId, uint128 liquidity, uint256 amount0, uint256 amount1)
    {
        IERC20JTest(p.token0).transferFrom(msg.sender, address(this), p.amount0Desired);
        IERC20JTest(p.token1).transferFrom(msg.sender, address(this), p.amount1Desired);
        tokenId = nextId++;
        liquidity = uint128(p.amount0Desired);
        amount0 = p.amount0Desired;
        amount1 = p.amount1Desired;
    }

    function decreaseLiquidity(INFPMTest.DecreaseLiquidityParams calldata) external payable returns (uint256, uint256) {
        return (0, 0);
    }

    function collect(INFPMTest.CollectParams calldata p) external payable returns (uint256, uint256) {
        usdc.transfer(p.recipient, collect0);
        token1.transfer(p.recipient, collect1);
        return (collect0, collect1);
    }

    function burn(uint256) external payable {}
}

/// @notice The "target swap": its execution is what pays fees to the JIT position (fees are pre-funded here).
contract MockSwapTarget {
    bool public called;

    function swap() external {
        called = true;
    }
}

contract ArcJITLiquidityTest is Test {
    MockUSDC internal usdc;
    MockERC20 internal weth;
    MockPool internal pool;
    MockNFPM internal nfpm;
    MockSwapTarget internal target;
    ArcJITLiquidity internal jit;

    address internal owner = address(0xA11CE);

    uint256 internal constant USDC_50K = 50_000_000_000; // 50,000 USDC
    uint256 internal constant WETH_20 = 20e18;
    uint256 internal constant PRICE = 2_500e6; // 1 WETH = 2500 USDC (USDC is 6-dec; token1 18-dec)
    int24 internal constant TICK = 100;

    function setUp() public {
        usdc = new MockUSDC();
        weth = new MockERC20("WETH", "WETH", 18);
        pool = new MockPool(TICK);
        nfpm = new MockNFPM(usdc, weth);
        target = new MockSwapTarget();
        jit = new ArcJITLiquidity(address(usdc), owner);

        // pre-fund the JIT contract with capital (owner's)
        usdc.mint(address(jit), USDC_50K);
        weth.mint(address(jit), WETH_20);
        // fund the mock NFPM so it can pay out principal + fees on collect
        usdc.mint(address(nfpm), 1_000_000_000); // extra USDC (fees)
    }

    function _params() internal view returns (ArcJITLiquidity.JITParams memory) {
        return ArcJITLiquidity.JITParams({
            pool: address(pool),
            nfpm: address(nfpm),
            token1: address(weth),
            poolFee: 500,
            tickLower: TICK,
            tickUpper: TICK + 1, // 1 single tick
            amount0Desired: USDC_50K,
            amount1Desired: WETH_20,
            amount0Min: 0,
            amount1Min: 0,
            swapTarget: address(target),
            swapData: abi.encodeWithSelector(MockSwapTarget.swap.selector),
            priceToken1InToken0: PRICE,
            gasCost: 1_000_000, // 1 USDC
            minProfit: 10_000_000, // 10 USDC
            deadline: block.timestamp + 600
        });
    }

    function test_jit_captures_fees_and_pays_owner() public {
        // collect returns principal (50,000 USDC + 20 WETH) + 100 USDC of fees
        nfpm.setCollect(USDC_50K + 100_000_000, WETH_20);

        vm.prank(owner);
        uint256 profit = jit.executeJIT(_params());

        // endValue = 50,100 + 20*2500 = 100,100 ; startValue = 100,000 ; profit = 100,100 - 100,000 - 1 = 99
        assertEq(profit, 99_000_000, "net profit (99 USDC)");
        assertEq(usdc.balanceOf(owner), USDC_50K + 100_000_000, "capital + fees -> owner Safe");
        assertEq(weth.balanceOf(owner), WETH_20, "token1 returned to owner");
        assertTrue(target.called(), "target swap executed");
    }

    function test_revert_when_not_profitable() public {
        // no fees -> endValue = 100,000 < 100,000 + 1 + 10
        nfpm.setCollect(USDC_50K, WETH_20);
        vm.prank(owner);
        vm.expectRevert(
            abi.encodeWithSelector(ArcJITLiquidity.InsufficientProfit.selector, 100_000_000_000, 100_011_000_000)
        );
        jit.executeJIT(_params());
    }

    function test_revert_when_range_misaligned() public {
        pool.setTick(9_999); // current tick outside [100, 101)
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(ArcJITLiquidity.TickOutOfRange.selector, int24(9_999), int24(100), int24(101)));
        jit.executeJIT(_params());
    }

    function test_onlyOwner() public {
        vm.prank(address(0xBAD));
        vm.expectRevert(ArcJITLiquidity.NotOwner.selector);
        jit.executeJIT(_params());
    }

    function test_emergency_withdraw() public {
        usdc.mint(address(jit), 1_000_000);
        vm.prank(owner);
        jit.emergencyWithdraw(address(usdc), owner);
        assertGt(usdc.balanceOf(owner), 0);
    }
}
