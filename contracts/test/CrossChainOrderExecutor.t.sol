// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {CrossChainOrderExecutor} from "../src/CrossChainOrderExecutor.sol";
import {MockUSDC, MockERC20} from "../src/launchpad/mocks/Mocks.sol";

interface IERC20T {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @notice Minimal fixed-output swap venue (pulls tokenIn, pays `outAmount` of tokenOut to recipient).
contract MockSwap {
    address public immutable out;
    uint256 public immutable outAmount;

    constructor(address out_, uint256 outAmount_) {
        out = out_;
        outAmount = outAmount_;
    }

    function swap(address tokenIn, uint256 amountIn, address tokenOut, address recipient, uint256 minOut)
        external
        returns (uint256)
    {
        require(IERC20T(tokenIn).transferFrom(msg.sender, address(this), amountIn), "pull");
        require(outAmount >= minOut, "slippage");
        require(IERC20T(tokenOut).transfer(recipient, outAmount), "push");
        return outAmount;
    }
}

/// @notice Cross-chain executor tests. Run:
///         forge test --match-contract CrossChainOrderExecutorTest -vvv
contract CrossChainOrderExecutorTest is Test {
    MockUSDC internal usdc;
    MockERC20 internal eurc;
    MockSwap internal swap;
    CrossChainOrderExecutor internal exec;

    uint256 internal constant SOURCE = 84532; // Base Sepolia (origin)
    uint256 internal constant USDC_1 = 1e6;
    uint256 internal ownerPk = 0xA11CE;
    address internal owner;
    address internal keeper = address(0xB0B);
    address internal feeRecipient = address(0xFEE);

    function setUp() public {
        owner = vm.addr(ownerPk);
        usdc = new MockUSDC();
        eurc = new MockERC20("EURC", "EURC", 6);
        swap = new MockSwap(address(eurc), 950000); // pays 0.95 EURC per fill

        exec = new CrossChainOrderExecutor(address(usdc), owner, keeper, address(0), feeRecipient, SOURCE);
        vm.prank(owner);
        exec.setAllowedTarget(address(swap), true);

        // simulate funds delivered to the executor by the interop/CCTP message + fund the venue
        usdc.mint(address(exec), 100 * USDC_1);
        eurc.mint(address(swap), 100 * USDC_1);
    }

    function _build(uint256 source, uint256 dest, uint256 amountIn, uint256 minOut, uint256 nonce)
        internal
        view
        returns (CrossChainOrderExecutor.CrossChainIntent memory it, bytes memory sig, bytes memory swapData)
    {
        it = CrossChainOrderExecutor.CrossChainIntent({
            owner: owner,
            tokenIn: address(usdc),
            tokenOut: address(eurc),
            amountIn: amountIn,
            minOut: minOut,
            sourceChainId: source,
            destinationChainId: dest,
            nonce: nonce,
            deadline: block.timestamp + 3600
        });
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerPk, exec.digest(it));
        sig = abi.encodePacked(r, s, v);

        uint256 fee = (amountIn * 30) / 10_000; // 0.30%
        uint256 net = amountIn - fee;
        swapData = abi.encodeWithSelector(MockSwap.swap.selector, address(usdc), net, address(eurc), owner, minOut);
    }

    function test_crossChainFill_retainsInputSideFee() public {
        (CrossChainOrderExecutor.CrossChainIntent memory it, bytes memory sig, bytes memory swapData) =
            _build(SOURCE, block.chainid, 1 * USDC_1, 900000, 1);

        uint256 feeBefore = usdc.balanceOf(feeRecipient);
        vm.prank(keeper);
        exec.executeCrossChain(it, sig, address(swap), swapData);

        assertEq(eurc.balanceOf(owner), 950000); // output delivered (>= minOut)
        assertEq(usdc.balanceOf(feeRecipient), feeBefore + 3000); // 0.30% of 1 USDC
    }

    function test_wrongSourceChain_rejected() public {
        (CrossChainOrderExecutor.CrossChainIntent memory it, bytes memory sig, bytes memory swapData) =
            _build(1, block.chainid, 1 * USDC_1, 900000, 2);
        vm.prank(keeper);
        vm.expectRevert(CrossChainOrderExecutor.WrongSource.selector);
        exec.executeCrossChain(it, sig, address(swap), swapData);
    }

    function test_wrongDestinationChain_rejected() public {
        (CrossChainOrderExecutor.CrossChainIntent memory it, bytes memory sig, bytes memory swapData) =
            _build(SOURCE, 999, 1 * USDC_1, 900000, 3);
        vm.prank(keeper);
        vm.expectRevert(CrossChainOrderExecutor.WrongDestination.selector);
        exec.executeCrossChain(it, sig, address(swap), swapData);
    }

    function test_replay_rejected() public {
        (CrossChainOrderExecutor.CrossChainIntent memory it, bytes memory sig, bytes memory swapData) =
            _build(SOURCE, block.chainid, 1 * USDC_1, 900000, 4);
        vm.prank(keeper);
        exec.executeCrossChain(it, sig, address(swap), swapData);
        vm.prank(keeper);
        vm.expectRevert(CrossChainOrderExecutor.IntentUsed.selector);
        exec.executeCrossChain(it, sig, address(swap), swapData);
    }

    function test_badSignature_rejected() public {
        (CrossChainOrderExecutor.CrossChainIntent memory it, bytes memory sig, bytes memory swapData) =
            _build(SOURCE, block.chainid, 1 * USDC_1, 900000, 5);
        it.owner = address(0xDEAD); // not the signer
        vm.prank(keeper);
        vm.expectRevert(CrossChainOrderExecutor.BadSignature.selector);
        exec.executeCrossChain(it, sig, address(swap), swapData);
    }

    function test_onlyKeeper() public {
        (CrossChainOrderExecutor.CrossChainIntent memory it, bytes memory sig, bytes memory swapData) =
            _build(SOURCE, block.chainid, 1 * USDC_1, 900000, 6);
        vm.expectRevert(CrossChainOrderExecutor.NotKeeper.selector);
        exec.executeCrossChain(it, sig, address(swap), swapData);
    }
}
