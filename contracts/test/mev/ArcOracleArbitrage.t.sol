// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {ArcOracleArbitrage} from "../../src/mev/ArcOracleArbitrage.sol";
import {MockUSDC, MockERC20} from "../../src/launchpad/mocks/Mocks.sol";

interface IERC20M {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IFlashCb {
    function uniswapV3FlashCallback(uint256 fee0, uint256 fee1, bytes calldata data) external;
}

interface ISwapA {
    struct ExactInputParams {
        bytes path;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }
}

/// @notice Uniswap v3 pool mock: lends tokens, calls back, then enforces the repayment (balance + fee).
contract MockV3Pool {
    IERC20M public token0;
    IERC20M public token1;
    uint256 public feePips; // Uniswap v3 fee units (500 = 0.05%); fee = amount * feePips / 1e6

    constructor(IERC20M token0_, IERC20M token1_, uint256 feePips_) {
        token0 = token0_;
        token1 = token1_;
        feePips = feePips_;
    }

    function flash(address recipient, uint256 amount0, uint256 amount1, bytes calldata data) external {
        uint256 b0 = token0.balanceOf(address(this));
        uint256 b1 = token1.balanceOf(address(this));
        if (amount0 > 0) token0.transfer(recipient, amount0);
        if (amount1 > 0) token1.transfer(recipient, amount1);
        uint256 f0 = (amount0 * feePips) / 1e6;
        uint256 f1 = (amount1 * feePips) / 1e6;
        IFlashCb(recipient).uniswapV3FlashCallback(f0, f1, data);
        require(token0.balanceOf(address(this)) >= b0 + f0, "repay0");
        require(token1.balanceOf(address(this)) >= b1 + f1, "repay1");
    }
}

/// @notice SwapRouter02 mock: pulls `tokenIn` and pays a configurable amount of USDC (the arb output).
contract MockSwapRouterA {
    address public tokenIn;
    MockUSDC public usdc;
    uint256 public outAmount;

    constructor(address tokenIn_, MockUSDC usdc_) {
        tokenIn = tokenIn_;
        usdc = usdc_;
    }

    function setOut(uint256 v) external {
        outAmount = v;
    }

    function exactInput(ISwapA.ExactInputParams calldata p) external payable returns (uint256) {
        IERC20M(tokenIn).transferFrom(msg.sender, address(this), p.amountIn);
        usdc.transfer(p.recipient, outAmount);
        return outAmount;
    }
}

contract ArcOracleArbitrageTest is Test {
    MockUSDC internal usdc;
    MockERC20 internal other; // the mispriced token (e.g. WETH)
    MockV3Pool internal pool;
    MockSwapRouterA internal router;
    ArcOracleArbitrage internal arb;

    address internal owner = address(0xA11CE);
    uint256 internal constant ONE_USDC = 1_000_000;
    uint24 internal constant FEE = 500; // 0.05%

    function setUp() public {
        usdc = new MockUSDC();
        other = new MockERC20("WETH", "WETH", 18);
        pool = new MockV3Pool(IERC20M(address(usdc)), IERC20M(address(other)), FEE); // token0 = USDC
        router = new MockSwapRouterA(address(usdc), usdc);
        arb = new ArcOracleArbitrage(address(usdc), address(router), owner);

        usdc.mint(address(pool), 1_000_000_000); // flash liquidity
        usdc.mint(address(router), 1_000_000_000); // USDC the arb route pays out
    }

    function _path() internal view returns (bytes memory) {
        // USDC -> WETH -> USDC (two legs; one leg is mispriced vs the oracle)
        return abi.encodePacked(address(usdc), FEE, address(other), FEE, address(usdc));
    }

    function _params(uint256 minProfit) internal view returns (ArcOracleArbitrage.ArbParams memory) {
        return ArcOracleArbitrage.ArbParams({
            flashPool: address(pool),
            path: _path(),
            amountIn: ONE_USDC,
            minProfit: minProfit
        });
    }

    /// @dev 1.5% discrepancy between the misaligned pool and the oracle => ~1.5% out on the route.
    function test_arbitrage_success_1p5pct() public {
        router.setOut(1_015_000); // 1.015 USDC out for 1 USDC in (1.5%)
        uint256 minProfit = 10_000; // 0.01 USDC

        vm.prank(owner);
        uint256 profit = arb.executeArbitrage(_params(minProfit));

        // owed = 1.000000 + 0.05% = 1.000500; profit = 1.015000 - 1.000500 = 0.014500
        assertEq(profit, 14_500, "net profit");
        assertEq(usdc.balanceOf(owner), 14_500, "profit -> owner (Safe)");
        assertEq(usdc.balanceOf(address(arb)), 0, "no funds stuck");
        assertEq(usdc.balanceOf(address(pool)), 1_000_000_000, "flash loan repaid (pool whole)");
    }

    function test_revert_when_not_profitable() public {
        router.setOut(1_001_000); // 1.001 USDC < owed 1.0005 + minProfit 0.01
        vm.prank(owner);
        vm.expectRevert(
            abi.encodeWithSelector(ArcOracleArbitrage.InsufficientProfit.selector, 1_001_000, 1_010_500)
        );
        arb.executeArbitrage(_params(10_000));
    }

    function test_onlyOwner() public {
        router.setOut(1_015_000);
        vm.prank(address(0xBAD));
        vm.expectRevert(ArcOracleArbitrage.NotOwner.selector);
        arb.executeArbitrage(_params(10_000));
    }

    function test_emergency_withdraw() public {
        usdc.mint(address(arb), 7_000_000);
        vm.prank(owner);
        arb.emergencyWithdraw(address(usdc), owner);
        assertEq(usdc.balanceOf(owner), 7_000_000);
    }
}
