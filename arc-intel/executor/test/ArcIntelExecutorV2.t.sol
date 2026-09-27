// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Test.sol";
import "../src/ArcIntelExecutorV2.sol";
import "./mocks/Mocks.sol";

contract ArcIntelExecutorV2Test is Test {
    ArcIntelExecutorV2 internal exec;
    MockPoolManager internal pm;
    MockPermit2 internal permit2;
    MockERC20 internal usdc;
    MockERC20 internal tok;

    address internal safe = address(0x5AFE);
    address internal user = address(0xA11CE);

    uint256 internal skPk = 0xB0B;
    address internal sessionKey;

    IPoolManager.PoolKey internal key;
    bytes32 internal poolId;
    bool internal zeroForOne; // sell TOK
    bool internal buyZeroForOne; // buy with USDC

    bytes32 internal constant SESSION_ORDER_TYPEHASH = keccak256(
        "ArcIntelSessionOrder(address user,PoolKey key,bool zeroForOne,uint256 amountIn,uint256 minOut,address recipient,uint256 orderNonce,uint256 deadline)PoolKey(address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks)"
    );
    bytes32 internal constant POOLKEY_TYPEHASH =
        keccak256("PoolKey(address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks)");

    function setUp() public {
        sessionKey = vm.addr(skPk);
        usdc = new MockERC20("USDC");
        tok = new MockERC20("TOK");
        (address c0, address c1) =
            address(tok) < address(usdc) ? (address(tok), address(usdc)) : (address(usdc), address(tok));
        zeroForOne = (c0 == address(tok));
        buyZeroForOne = (c0 == address(usdc));
        key = IPoolManager.PoolKey(c0, c1, 10000, 200, address(0xBEef));
        poolId = keccak256(abi.encode(key));

        pm = new MockPoolManager();
        bytes32[] memory pools = new bytes32[](1);
        pools[0] = poolId;
        exec = new ArcIntelExecutorV2(address(pm), safe, pools);

        permit2 = new MockPermit2();
        vm.etch(exec.PERMIT2(), address(permit2).code);

        tok.mint(user, 1_000_000e18);
        usdc.mint(user, 1_000_000e18);
        tok.mint(address(pm), 1_000_000e18);
        usdc.mint(address(pm), 1_000_000e18);
    }

    //  All tests use the BUY direction (pay USDC -> get TOK).
    function _tokenIn() internal pure returns (address) {
        return address(0); // replaced in tests below via _buyIn
    }

    function _buyIn() internal view returns (address) {
        return address(usdc);
    }

    function _buyOut() internal view returns (address) {
        return address(tok);
    }

    function _authorize(address tokenIn, uint256 perOrder, uint256 total, uint256 minFloor, uint64 expiry)
        internal
    {
        vm.prank(user);
        exec.authorizeSession(sessionKey, poolId, tokenIn, perOrder, total, minFloor, expiry);
    }

    function _order(bool z4o, uint256 amountIn, uint256 minOut, address recipient, uint256 nonce, uint256 deadline)
        internal
        view
        returns (ArcIntelExecutorV2.SessionOrder memory)
    {
        return ArcIntelExecutorV2.SessionOrder({
            user: user,
            key: key,
            zeroForOne: z4o,
            amountIn: amountIn,
            minOut: minOut,
            recipient: recipient,
            orderNonce: nonce,
            deadline: deadline
        });
    }

    function _digest(ArcIntelExecutorV2.SessionOrder memory o) internal view returns (bytes32) {
        bytes32 keyHash = keccak256(
            abi.encode(POOLKEY_TYPEHASH, o.key.currency0, o.key.currency1, o.key.fee, o.key.tickSpacing, o.key.hooks)
        );
        bytes32 sh = keccak256(
            abi.encode(
                SESSION_ORDER_TYPEHASH, o.user, keyHash, o.zeroForOne, o.amountIn, o.minOut, o.recipient,
                o.orderNonce, o.deadline
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", exec.DOMAIN_SEPARATOR(), sh));
    }

    function _sign(ArcIntelExecutorV2.SessionOrder memory o) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(skPk, _digest(o));
        return abi.encodePacked(r, s, v);
    }

    function _signWith(uint256 pk, ArcIntelExecutorV2.SessionOrder memory o) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, _digest(o));
        return abi.encodePacked(r, s, v);
    }

    function testExecuteWithSessionBuy() public {
        pm.setRate(1e18);
        uint256 amountIn = 100e18;
        _authorize(_buyIn(), 200e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o =
            _order(buyZeroForOne, amountIn, 100e18, user, 1, block.timestamp + 100);

        uint256 before = IERC20Min(_buyOut()).balanceOf(user);
        exec.executeWithSession(o, _sign(o));
        assertEq(IERC20Min(_buyOut()).balanceOf(user) - before, amountIn);

        (, , , , , , uint256 spent, , ) = exec.sessions(user, sessionKey);
        assertEq(spent, amountIn);
        assertEq(tok.balanceOf(address(exec)), 0, "no custody");
        assertEq(usdc.balanceOf(address(exec)), 0, "no custody");
    }

    function testOverPerOrder() public {
        _authorize(_buyIn(), 50e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.SessionOverPerOrder.selector);
        exec.executeWithSession(o, sig);
    }

    function testOverTotal() public {
        _authorize(_buyIn(), 100e18, 150e18, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o1 = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        exec.executeWithSession(o1, _sign(o1));
        ArcIntelExecutorV2.SessionOrder memory o2 = _order(buyZeroForOne, 100e18, 0, user, 2, block.timestamp + 100);
        bytes memory sig2 = _sign(o2);
        vm.expectRevert(ArcIntelExecutorV2.SessionOverTotal.selector);
        exec.executeWithSession(o2, sig2);
    }

    function testRevoked() public {
        _authorize(_buyIn(), 200e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        vm.prank(user);
        exec.revokeSession(sessionKey);
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.SessionInvalid.selector);
        exec.executeWithSession(o, sig);
    }

    function testExpiredSession() public {
        _authorize(_buyIn(), 200e18, 1000e18, 0, uint64(block.timestamp + 10));
        vm.warp(block.timestamp + 20);
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.SessionExpired.selector);
        exec.executeWithSession(o, sig);
    }

    function testBadExpiryOnAuthorize() public {
        vm.prank(user);
        vm.expectRevert(ArcIntelExecutorV2.BadExpiry.selector);
        exec.authorizeSession(sessionKey, poolId, _buyIn(), 1, 1, 0, uint64(block.timestamp));
    }

    function testWrongPool() public {
        bytes32 other = keccak256("other");
        vm.prank(user);
        exec.authorizeSession(sessionKey, other, _buyIn(), 1000e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.SessionPoolMismatch.selector);
        exec.executeWithSession(o, sig);
    }

    function testWrongTokenIn() public {
        _authorize(address(tok), 1e30, 1e30, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.TokenMismatch.selector);
        exec.executeWithSession(o, sig);
    }

    function testMinOutFloor() public {
        _authorize(_buyIn(), 200e18, 1000e18, 100e18, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 90e18, user, 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.SessionMinOutTooLow.selector);
        exec.executeWithSession(o, sig);
    }

    function testRecipientMustBeUser() public {
        _authorize(_buyIn(), 200e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o =
            _order(buyZeroForOne, 100e18, 0, address(0xBAD), 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.BadRecipient.selector);
        exec.executeWithSession(o, sig);
    }

    function testBadSignatureNotAuthorized() public {
        _authorize(_buyIn(), 200e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        bytes memory sig = _signWith(0xDEAD, o);
        vm.expectRevert(ArcIntelExecutorV2.SessionInvalid.selector);
        exec.executeWithSession(o, sig);
    }

    function testNonceReuse() public {
        _authorize(_buyIn(), 200e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 7, block.timestamp + 100);
        bytes memory sig = _sign(o);
        exec.executeWithSession(o, sig);
        vm.expectRevert(ArcIntelExecutorV2.NonceAlreadyUsed.selector);
        exec.executeWithSession(o, sig);
    }

    function testPausedBlocksSession() public {
        _authorize(_buyIn(), 200e18, 1000e18, 0, uint64(block.timestamp + 1 days));
        vm.prank(safe);
        exec.setPaused(true);
        ArcIntelExecutorV2.SessionOrder memory o = _order(buyZeroForOne, 100e18, 0, user, 1, block.timestamp + 100);
        bytes memory sig = _sign(o);
        vm.expectRevert(ArcIntelExecutorV2.Paused.selector);
        exec.executeWithSession(o, sig);
    }
}
