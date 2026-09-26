// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Test.sol";
import "../src/ArcIntelExecutor.sol";
import "./mocks/Mocks.sol";

contract ArcIntelExecutorTest is Test {
    ArcIntelExecutor internal exec;
    MockPoolManager internal pm;
    MockPermit2 internal permit2;
    MockERC20 internal usdc;
    MockERC20 internal tok;

    address internal safe = address(0x5AFE);
    address internal user = address(0xA11CE);

    IPoolManager.PoolKey internal key;
    bytes32 internal poolId;
    bool internal zeroForOne;

    function setUp() public {
        usdc = new MockERC20("USDC");
        tok = new MockERC20("TOK");
        (address c0, address c1) =
            address(tok) < address(usdc) ? (address(tok), address(usdc)) : (address(usdc), address(tok));
        zeroForOne = (c0 == address(tok)); // selling TOK -> tokenIn is TOK
        key = IPoolManager.PoolKey(c0, c1, 10000, 200, address(0xBEef));
        poolId = keccak256(abi.encode(key));

        pm = new MockPoolManager();
        bytes32[] memory pools = new bytes32[](1);
        pools[0] = poolId;
        exec = new ArcIntelExecutor(address(pm), safe, pools);

        //  Install the MockPermit2 code at the canonical Permit2 address the executor calls.
        permit2 = new MockPermit2();
        vm.etch(exec.PERMIT2(), address(permit2).code);

        tok.mint(user, 1_000e18);
        usdc.mint(address(pm), 1_000_000e18);
    }

    function _permit(address token, uint256 amount) internal view returns (IPermit2.PermitTransferFrom memory) {
        return IPermit2.PermitTransferFrom({
            permitted: IPermit2.TokenPermissions({token: token, amount: amount}),
            nonce: 1,
            deadline: block.timestamp + 100
        });
    }

    function _order(uint256 minOut, uint256 nonce, uint256 deadline)
        internal
        view
        returns (ArcIntelExecutor.Order memory)
    {
        return ArcIntelExecutor.Order({
            key: key,
            zeroForOne: zeroForOne,
            minOut: minOut,
            recipient: user,
            orderNonce: nonce,
            deadline: deadline
        });
    }

    function testFillsAndSendsOutputToRecipient() public {
        uint256 amountIn = 100e18;
        pm.setRate(0.98e18); // 2% effective cost (fees + hook tax)
        uint256 expectedOut = 98e18;

        uint256 before = usdc.balanceOf(user);
        exec.execute(_permit(address(tok), amountIn), user, _order(expectedOut, 1, block.timestamp + 100), "");

        assertEq(usdc.balanceOf(user) - before, expectedOut);
        assertEq(tok.balanceOf(address(exec)), 0, "no custody");
        assertEq(usdc.balanceOf(address(exec)), 0, "no custody of output");
        assertEq(tok.balanceOf(address(pm)), amountIn, "pool received input");
    }

    function testWitnessBindsSignedIntent() public {
        uint256 amountIn = 100e18;
        pm.setRate(1e18);
        bytes32 expectedWitness = keccak256(
            abi.encode(
                keccak256(
                    "ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,uint256 orderNonce)"
                ),
                poolId,
                zeroForOne,
                uint256(100e18),
                user,
                uint256(7)
            )
        );
        exec.execute(_permit(address(tok), amountIn), user, _order(100e18, 7, block.timestamp + 100), "");
        assertEq(MockPermit2(exec.PERMIT2()).lastWitness(), expectedWitness);
    }

    function testRevertWhenPaused() public {
        vm.prank(safe);
        exec.setPaused(true);
        vm.expectRevert(ArcIntelExecutor.Paused.selector);
        exec.execute(_permit(address(tok), 1e18), user, _order(0, 1, block.timestamp + 100), "");
    }

    function testRevertPoolNotAllowed() public {
        IPoolManager.PoolKey memory other =
            IPoolManager.PoolKey(key.currency0, key.currency1, 500, 10, address(0xBAD));
        ArcIntelExecutor.Order memory o = _order(0, 1, block.timestamp + 100);
        o.key = other;
        vm.expectRevert();
        exec.execute(_permit(address(tok), 1e18), user, o, "");
    }

    function testRevertExpired() public {
        vm.expectRevert(ArcIntelExecutor.OrderExpired.selector);
        exec.execute(_permit(address(tok), 1e18), user, _order(0, 1, block.timestamp - 1), "");
    }

    function testRevertNonceReuse() public {
        pm.setRate(1e18);
        exec.execute(_permit(address(tok), 10e18), user, _order(0, 3, block.timestamp + 100), "");
        vm.expectRevert(ArcIntelExecutor.NonceAlreadyUsed.selector);
        exec.execute(_permit(address(tok), 10e18), user, _order(0, 3, block.timestamp + 100), "");
    }

    function testRevertTokenMismatch() public {
        vm.expectRevert(ArcIntelExecutor.TokenMismatch.selector);
        // passing USDC as the input token although the signed direction expects TOK
        exec.execute(_permit(address(usdc), 1e18), user, _order(0, 1, block.timestamp + 100), "");
    }

    function testRevertMinOutNotMet() public {
        pm.setRate(1e18);
        vm.expectRevert(abi.encodeWithSelector(ArcIntelExecutor.InsufficientOutput.selector, 100e18, 101e18));
        exec.execute(_permit(address(tok), 100e18), user, _order(101e18, 1, block.timestamp + 100), "");
    }

    function testCancelBlocksFill() public {
        vm.prank(user);
        exec.cancelOrder(9);
        vm.expectRevert(ArcIntelExecutor.NonceAlreadyUsed.selector);
        exec.execute(_permit(address(tok), 1e18), user, _order(0, 9, block.timestamp + 100), "");
    }

    function testUnlockCallbackOnlyPoolManager() public {
        vm.expectRevert(ArcIntelExecutor.NotPoolManager.selector);
        exec.unlockCallback("");
    }

    function testOnlyOwnerCanPause() public {
        vm.prank(user);
        vm.expectRevert(ArcIntelExecutor.NotOwner.selector);
        exec.setPaused(true);
    }

    function testOnlyOwnerCanAllowPool() public {
        vm.prank(user);
        vm.expectRevert(ArcIntelExecutor.NotOwner.selector);
        exec.setAllowedPool(keccak256("x"), true);
    }

    function testPartialFillReturnsDustToUser() public {
        uint256 amountIn = 100e18;
        pm.setRate(1e18);
        pm.setPartialBps(4000); // only 40% of the input is consumed
        uint256 consumed = 40e18;
        uint256 before = tok.balanceOf(user);

        exec.execute(_permit(address(tok), amountIn), user, _order(consumed, 1, block.timestamp + 100), "");

        assertEq(tok.balanceOf(address(exec)), 0, "no dust retained");
        assertEq(tok.balanceOf(user), before - consumed, "dust returned to user");
        assertEq(tok.balanceOf(address(pm)), consumed, "pool received only the consumed amount");
    }

    function testReentrancyGuardBlocksNestedExecute() public {
        ReentrantPoolManager rpm = new ReentrantPoolManager();
        bytes32[] memory pools = new bytes32[](1);
        pools[0] = poolId;
        ArcIntelExecutor exec2 = new ArcIntelExecutor(address(rpm), safe, pools);
        vm.etch(exec2.PERMIT2(), address(permit2).code);
        rpm.setTarget(address(exec2));
        rpm.setRate(1e18);
        usdc.mint(address(rpm), 1_000_000e18);
        tok.mint(user, 1_000e18);

        vm.expectRevert(ArcIntelExecutor.Reentrancy.selector);
        exec2.execute(_permit(address(tok), 10e18), user, _order(0, 1, block.timestamp + 100), "");
    }

    function testFuzzMinOutBoundary(uint256 amountIn, uint256 rate) public {
        amountIn = bound(amountIn, 1e6, 500e18);
        rate = bound(rate, 0.5e18, 1e18);
        pm.setRate(rate);
        uint256 expectedOut = (amountIn * rate) / 1e18;

        uint256 before = usdc.balanceOf(user);
        exec.execute(_permit(address(tok), amountIn), user, _order(expectedOut, 1, block.timestamp + 100), "");
        assertEq(usdc.balanceOf(user) - before, expectedOut);
    }

    function testFuzzMinOutTooHighReverts(uint256 amountIn, uint256 rate) public {
        amountIn = bound(amountIn, 1e6, 500e18);
        rate = bound(rate, 0.5e18, 1e18);
        pm.setRate(rate);
        uint256 expectedOut = (amountIn * rate) / 1e18;

        vm.expectRevert(
            abi.encodeWithSelector(ArcIntelExecutor.InsufficientOutput.selector, expectedOut, expectedOut + 1)
        );
        exec.execute(_permit(address(tok), amountIn), user, _order(expectedOut + 1, 1, block.timestamp + 100), "");
    }

    function testFuzzNonceSingleUse(uint256 nonce) public {
        pm.setRate(1e18);
        exec.execute(_permit(address(tok), 1e18), user, _order(1e18, nonce, block.timestamp + 100), "");
        vm.expectRevert(ArcIntelExecutor.NonceAlreadyUsed.selector);
        exec.execute(_permit(address(tok), 1e18), user, _order(1e18, nonce, block.timestamp + 100), "");
    }

    function testNonceNotConsumedWhenSwapReverts() public {
        RevertingPoolManager rpm = new RevertingPoolManager();
        bytes32[] memory pools = new bytes32[](1);
        pools[0] = poolId;
        ArcIntelExecutor exec2 = new ArcIntelExecutor(address(rpm), safe, pools);
        vm.etch(exec2.PERMIT2(), address(permit2).code);
        tok.mint(user, 10e18);

        uint256 tokBefore = tok.balanceOf(user);
        vm.expectRevert();
        exec2.execute(_permit(address(tok), 10e18), user, _order(0, 42, block.timestamp + 100), "");

        assertFalse(exec2.orderNonceUsed(user, 42), "nonce must not be consumed when the swap reverts");
        assertEq(tok.balanceOf(user), tokBefore, "the Permit2 pull is reverted too");
    }

    function testOutputToDifferentRecipient() public {
        pm.setRate(1e18);
        address recipient = address(0xB0B);
        ArcIntelExecutor.Order memory o = _order(0, 1, block.timestamp + 100);
        o.recipient = recipient;

        exec.execute(_permit(address(tok), 10e18), user, o, "");
        assertEq(usdc.balanceOf(recipient), 10e18);
        assertEq(usdc.balanceOf(user), 0);
    }

    function testRevokedPoolBlocksFill() public {
        vm.prank(safe);
        exec.setAllowedPool(poolId, false);
        vm.expectRevert(abi.encodeWithSelector(ArcIntelExecutor.PoolNotAllowed.selector, poolId));
        exec.execute(_permit(address(tok), 1e18), user, _order(0, 1, block.timestamp + 100), "");
    }

    function testCancelOnlyAffectsOwnNonce() public {
        address user2 = address(0xBEEF);
        vm.prank(user2);
        exec.cancelOrder(1); // cancels user2's nonce 1, not the user's

        pm.setRate(1e18);
        exec.execute(_permit(address(tok), 1e18), user, _order(1e18, 1, block.timestamp + 100), "");
        assertEq(usdc.balanceOf(user), 1e18);
    }

    function testPriceLimitBoundsAndAmount() public {
        pm.setRate(1e18);
        exec.execute(_permit(address(tok), 1e18), user, _order(1e18, 1, block.timestamp + 100), "");

        uint160 expectedLimit = zeroForOne
            ? uint160(4295128739 + 1)
            : uint160(1461446703485210103287273052203988822378723970342 - 1);
        assertEq(pm.lastLimit(), expectedLimit);
        assertEq(pm.lastZeroForOne(), zeroForOne);
        assertEq(pm.lastAmountSpecified(), -int256(1e18));
    }
}
