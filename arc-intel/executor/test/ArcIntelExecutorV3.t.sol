// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Test.sol";
import "../src/ArcIntelExecutorV3.sol";
import "./mocks/Mocks.sol";

contract ArcIntelExecutorV3Test is Test {
    ArcIntelExecutorV3 internal exec;
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
    bool internal buyZeroForOne;

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
        buyZeroForOne = (c0 == address(usdc));
        key = IPoolManager.PoolKey(c0, c1, 10000, 200, address(0xBEEF)); // a custom hook
        poolId = keccak256(abi.encode(key));

        pm = new MockPoolManager();
        bytes32[] memory pools = new bytes32[](0); // no pools pre-allowed
        exec = new ArcIntelExecutorV3(address(pm), safe, pools);   // chainid 31337 != 5042 -> isTestnet()

        permit2 = new MockPermit2();
        vm.etch(exec.PERMIT2(), address(permit2).code);

        usdc.mint(user, 1_000_000e18);
        usdc.mint(address(pm), 1_000_000e18);
        tok.mint(address(pm), 1_000_000e18);
    }

    function _authorize() internal {
        vm.prank(user);
        exec.authorizeSession(sessionKey, poolId, address(usdc), 1000e18, 1000e18, 0,
                              uint64(block.timestamp + 1 days));
    }

    function _order(uint256 amountIn, uint256 minOut, uint256 nonce)
        internal
        view
        returns (ArcIntelExecutorV3.SessionOrder memory)
    {
        return ArcIntelExecutorV3.SessionOrder({
            user: user, key: key, zeroForOne: buyZeroForOne, amountIn: amountIn, minOut: minOut,
            recipient: user, orderNonce: nonce, deadline: block.timestamp + 100
        });
    }

    function _digest(ArcIntelExecutorV3.SessionOrder memory o) internal view returns (bytes32) {
        bytes32 keyHash = keccak256(
            abi.encode(POOLKEY_TYPEHASH, o.key.currency0, o.key.currency1, o.key.fee, o.key.tickSpacing, o.key.hooks)
        );
        bytes32 sh = keccak256(
            abi.encode(SESSION_ORDER_TYPEHASH, o.user, keyHash, o.zeroForOne, o.amountIn, o.minOut, o.recipient,
                       o.orderNonce, o.deadline)
        );
        return keccak256(abi.encodePacked("\x19\x01", exec.DOMAIN_SEPARATOR(), sh));
    }

    function _sign(ArcIntelExecutorV3.SessionOrder memory o) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(skPk, _digest(o));
        return abi.encodePacked(r, s, v);
    }

    function testPoolNotAllowedByDefault() public {
        _authorize();
        ArcIntelExecutorV3.SessionOrder memory o = _order(100e18, 0, 1);
        bytes memory sig = _sign(o);
        vm.expectRevert(abi.encodeWithSelector(ArcIntelExecutorV3.PoolNotAllowed.selector, poolId));
        exec.executeWithSession(o, sig);
    }

    function testAllowAllPools() public {
        _authorize();
        vm.prank(safe);
        exec.setAllowAllPools(true);
        ArcIntelExecutorV3.SessionOrder memory o = _order(100e18, 0, 1);
        uint256 before = tok.balanceOf(user);
        exec.executeWithSession(o, _sign(o));
        assertEq(tok.balanceOf(user) - before, 100e18);
    }

    function testAllowedHookCoversPool() public {
        _authorize();
        vm.prank(safe);
        exec.setAllowedHook(key.hooks, true);
        ArcIntelExecutorV3.SessionOrder memory o = _order(100e18, 0, 1);
        uint256 before = tok.balanceOf(user);
        exec.executeWithSession(o, _sign(o));
        assertEq(tok.balanceOf(user) - before, 100e18);
    }

    function testOnlyOwnerCanSetPolicy() public {
        vm.expectRevert(ArcIntelExecutorV3.NotOwner.selector);
        exec.setAllowAllPools(true);
        vm.expectRevert(ArcIntelExecutorV3.NotOwner.selector);
        exec.setAllowedHook(key.hooks, true);
    }

    function testRevertZeroRecipientV1() public {
        IPermit2.PermitTransferFrom memory permit = IPermit2.PermitTransferFrom({
            permitted: IPermit2.TokenPermissions({token: address(usdc), amount: 1e18}),
            nonce: 1,
            deadline: uint256(block.timestamp + 100)
        });
        ArcIntelExecutorV3.Order memory o = ArcIntelExecutorV3.Order({
            key: key, zeroForOne: buyZeroForOne, minOut: 0, recipient: address(0),
            orderNonce: 1, deadline: uint256(block.timestamp + 100)
        });
        vm.expectRevert(ArcIntelExecutorV3.BadRecipient.selector);
        exec.execute(permit, user, o, "");
    }

    function testWitnessBindsDeadline() public view {
        string memory expected =
            "ArcIntelOrder witness)ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,uint256 orderNonce,uint256 deadline)TokenPermissions(address token,uint256 amount)";
        assertEq(keccak256(bytes(exec.WITNESS_TYPE_STRING())), keccak256(bytes(expected)));
    }

    function testMainnetCannotAllowAll() public {
        vm.chainId(5042);   // simulate Arc mainnet
        bytes32[] memory pools = new bytes32[](0);
        ArcIntelExecutorV3 mainnetExec = new ArcIntelExecutorV3(address(pm), safe, pools);
        assertFalse(mainnetExec.isTestnet());
        vm.prank(safe);
        vm.expectRevert(ArcIntelExecutorV3.AllowAllNotAllowed.selector);
        mainnetExec.setAllowAllPools(true);
        // explicit policy still works on mainnet
        vm.prank(safe);
        mainnetExec.setAllowedHook(key.hooks, true);
        assertTrue(mainnetExec.allowedHooks(key.hooks));
    }

    function testHookRevokedBlocks() public {
        _authorize();
        vm.prank(safe);
        exec.setAllowedHook(key.hooks, true);   // allow
        vm.prank(safe);
        exec.setAllowedHook(key.hooks, false);  // revoke
        ArcIntelExecutorV3.SessionOrder memory o = _order(100e18, 0, 1);
        bytes memory sig = _sign(o);
        vm.expectRevert(abi.encodeWithSelector(ArcIntelExecutorV3.PoolNotAllowed.selector, poolId));
        exec.executeWithSession(o, sig);
    }

    function testAllowedHookOnlyCoversItsOwnHook() public {
        vm.prank(safe);
        exec.setAllowedHook(address(0xDEAD), true); // a different hook
        _authorize();
        ArcIntelExecutorV3.SessionOrder memory o = _order(100e18, 0, 1);
        bytes memory sig = _sign(o);
        vm.expectRevert(abi.encodeWithSelector(ArcIntelExecutorV3.PoolNotAllowed.selector, poolId));
        exec.executeWithSession(o, sig);
    }

    function testAllowAllPoolsPermitsArbitraryPool() public {
        vm.prank(safe);
        exec.setAllowAllPools(true);
        _authorize();
        pm.setRate(1e18);
        ArcIntelExecutorV3.SessionOrder memory o = _order(100e18, 0, 1);
        uint256 before = tok.balanceOf(user);
        exec.executeWithSession(o, _sign(o));
        assertEq(tok.balanceOf(user) - before, 100e18);
    }

    function testHostileAllowedHookIsContained() public {
        MaliciousHook hook = new MaliciousHook(address(exec), address(tok), user);
        IPoolManager.PoolKey memory k2 =
            IPoolManager.PoolKey(key.currency0, key.currency1, 10000, 200, address(hook));
        bytes32 pid2 = keccak256(abi.encode(k2));
        vm.prank(safe);
        exec.setAllowedHook(address(hook), true);
        vm.prank(user);
        exec.authorizeSession(sessionKey, pid2, address(usdc), type(uint256).max, type(uint256).max, 0,
                              uint64(block.timestamp + 1 days));
        pm.setSwapHook(address(hook));
        pm.setRate(1e18);
        ArcIntelExecutorV3.SessionOrder memory o = ArcIntelExecutorV3.SessionOrder({
            user: user, key: k2, zeroForOne: buyZeroForOne, amountIn: 100e18, minOut: 0, recipient: user,
            orderNonce: 1, deadline: block.timestamp + 100
        });
        uint256 before = tok.balanceOf(user);
        exec.executeWithSession(o, _sign(o));
        assertEq(tok.balanceOf(user) - before, 100e18);
        assertTrue(hook.reentryBlocked(), "reentry via hook not blocked");
    }
}
