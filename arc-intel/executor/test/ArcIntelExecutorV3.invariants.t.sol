// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Test.sol";
import "forge-std/StdInvariant.sol";
import "forge-std/console2.sol";
import "../src/ArcIntelExecutorV3.sol";
import "./mocks/Mocks.sol";

/// @dev Stateful fuzzing harness for V3. Besides valid session fills it ACTIVELY attempts actions that
///      MUST fail (paused, revoked session, expired session, wrong recipient, wrong pool/token,
///      over per-order/total caps). `unexpectedSuccess` must stay 0.
contract HandlerV3 {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    ArcIntelExecutorV3 public exec;
    MockERC20 public immutable usdc;
    MockERC20 public immutable tok;
    IPoolManager.PoolKey public key;
    bytes32 public immutable poolId;
    address public immutable user;
    address public immutable sessionKey;

    uint256 public successFills;
    uint256 public fillsWhilePaused;
    uint256 public revokedFills;
    uint256 public expiredFills;
    uint256 public recipientViolations;
    uint256 public poolTokenViolations;
    bool public doubleFillDetected;
    uint256 public unexpectedSuccess;
    mapping(uint256 => uint256) public nonceCount;

    uint256 public lastMaxTotal;

    bytes32 internal constant SESSION_ORDER_TYPEHASH = keccak256(
        "ArcIntelSessionOrder(address user,PoolKey key,bool zeroForOne,uint256 amountIn,uint256 minOut,address recipient,uint256 orderNonce,uint256 deadline)PoolKey(address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks)"
    );
    bytes32 internal constant POOLKEY_TYPEHASH =
        keccak256("PoolKey(address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks)");
    uint256 internal immutable skPk;

    constructor(MockERC20 u, MockERC20 t, IPoolManager.PoolKey memory k, bytes32 pid, address usr,
                address sk, uint256 pk) {
        usdc = u;
        tok = t;
        key = k;
        poolId = pid;
        user = usr;
        sessionKey = sk;
        skPk = pk;
    }

    function setExecutor(ArcIntelExecutorV3 e) external {
        exec = e;
    }

    function authorize(uint64 expiry, uint256 perOrder, uint256 total) external {
        lastMaxTotal = total;
        vm.prank(user);
        exec.authorizeSession(sessionKey, poolId, address(usdc), perOrder, total, 0, expiry);
    }

    function revoke() external {
        vm.prank(user);
        exec.revokeSession(sessionKey);
    }

    function setPaused(bool p) external {
        exec.setPaused(p);
    }

    function setHookAllowed(bool a) external {
        exec.setAllowedHook(key.hooks, a);
    }

    function setAllowAll(bool a) external {
        exec.setAllowAllPools(a);
    }

    function warp(uint256 dt) external {
        vm.warp(block.timestamp + (dt % 30 days));
    }

    // ---------------------------------------------------------------- fuzzed entrypoints

    function executeValid(uint256 amtSeed, uint256 nonceSeed) external {
        _attempt(amtSeed, nonceSeed, user, true, true);
    }

    function executeWhilePaused(uint256 amtSeed, uint256 nonceSeed) external {
        bool prev = exec.paused();
        exec.setPaused(true);
        bool ok = _attempt(amtSeed, nonceSeed, user, true, true);
        if (ok) {
            unexpectedSuccess++;
            fillsWhilePaused++;
        }
        exec.setPaused(prev);
    }

    function executeWhileRevoked(uint256 amtSeed, uint256 nonceSeed) external {
        vm.prank(user);
        exec.revokeSession(sessionKey);
        bool ok = _attempt(amtSeed, nonceSeed, user, true, true);
        if (ok) {
            unexpectedSuccess++;
            revokedFills++;
        }
        vm.prank(user);
        exec.authorizeSession(sessionKey, poolId, address(usdc), type(uint256).max, type(uint256).max, 0,
                              uint64(block.timestamp + 1 days));
        lastMaxTotal = type(uint256).max;
    }

    function executeExpiredSession(uint256 amtSeed, uint256 nonceSeed) external {
        vm.prank(user);
        exec.authorizeSession(sessionKey, poolId, address(usdc), type(uint256).max, type(uint256).max, 0,
                              uint64(block.timestamp + 1));
        vm.warp(block.timestamp + 2);
        bool ok = _attempt(amtSeed, nonceSeed, user, true, true);
        if (ok) {
            unexpectedSuccess++;
            expiredFills++;
        }
        vm.prank(user);
        exec.authorizeSession(sessionKey, poolId, address(usdc), type(uint256).max, type(uint256).max, 0,
                              uint64(block.timestamp + 1 days));
        lastMaxTotal = type(uint256).max;
    }

    function executeWrongRecipient(uint256 amtSeed, uint256 nonceSeed) external {
        bool ok = _attempt(amtSeed, nonceSeed, address(0xBADD), true, true);
        if (ok) {
            unexpectedSuccess++;
            recipientViolations++;
        }
    }

    function executeWrongPool(uint256 amtSeed, uint256 nonceSeed) external {
        bool ok = _attempt(amtSeed, nonceSeed, user, false, false);
        if (ok) {
            unexpectedSuccess++;
            poolTokenViolations++;
        }
    }

    // ---------------------------------------------------------------- internals

    function _attempt(uint256 amtSeed, uint256 nonceSeed, address recipient, bool correctPool,
                      bool correctToken) internal returns (bool ok) {
        uint256 bal = usdc.balanceOf(user);
        uint256 amountIn = bal == 0 ? 0 : (amtSeed % (bal + 1));
        if (amountIn == 0) return false;
        uint256 nonce = nonceSeed % 1e6;

        IPoolManager.PoolKey memory k = key;
        bool z4o = (k.currency0 == address(usdc));
        if (!correctPool) {
            // a different pool id (different fee) but the SAME tokenIn
            k = IPoolManager.PoolKey(k.currency0, k.currency1, 3001, 60, address(0));
        }
        if (!correctToken) {
            z4o = !z4o; // tokenIn becomes the other currency -> TokenMismatch
        }
        ArcIntelExecutorV3.SessionOrder memory o = ArcIntelExecutorV3.SessionOrder({
            user: user,
            key: k,
            zeroForOne: z4o,
            amountIn: amountIn,
            minOut: 0,
            recipient: recipient,
            orderNonce: nonce,
            deadline: block.timestamp + 1000
        });
        bytes memory sig = _sign(o);

        try exec.executeWithSession(o, sig) {
            successFills++;
            if (nonceCount[nonce] > 0) doubleFillDetected = true;
            nonceCount[nonce]++;
            return true;
        } catch {
            return false;
        }
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
}

contract ArcIntelExecutorV3Invariants is StdInvariant, Test {
    ArcIntelExecutorV3 internal exec;
    MockPoolManager internal pm;
    MockPermit2 internal permit2;
    MockERC20 internal usdc;
    MockERC20 internal tok;
    HandlerV3 internal handler;

    address internal user = address(0xA11CE);
    uint256 internal skPk = 0xB0B;
    address internal sessionKey;
    IPoolManager.PoolKey internal key;

    function setUp() public {
        sessionKey = vm.addr(skPk);
        usdc = new MockERC20("USDC");
        tok = new MockERC20("TOK");
        (address c0, address c1) =
            address(tok) < address(usdc) ? (address(tok), address(usdc)) : (address(usdc), address(tok));
        key = IPoolManager.PoolKey(c0, c1, 10000, 200, address(0xBEEF));
        bytes32 poolId = keccak256(abi.encode(key));

        pm = new MockPoolManager();
        handler = new HandlerV3(usdc, tok, key, poolId, user, sessionKey, skPk);

        bytes32[] memory pools = new bytes32[](1);
        pools[0] = poolId;
        exec = new ArcIntelExecutorV3(address(pm), address(handler), pools, true); // owner=handler, testnet
        handler.setExecutor(exec);

        permit2 = new MockPermit2();
        vm.etch(exec.PERMIT2(), address(permit2).code);

        usdc.mint(user, 1e30);
        tok.mint(user, 1e30);
        usdc.mint(address(pm), 1e30);
        tok.mint(address(pm), 1e30);

        handler.authorize(uint64(block.timestamp + 1 days), type(uint256).max, type(uint256).max);

        targetContract(address(handler));
        bytes4[] memory excluded = new bytes4[](1);
        excluded[0] = HandlerV3.setExecutor.selector;
        excludeSelector(FuzzSelector({addr: address(handler), selectors: excluded}));
        excludeContract(address(usdc));
        excludeContract(address(tok));
        excludeContract(address(pm));
        excludeContract(address(permit2));
        excludeContract(address(exec));
    }

    /// spent <= maxTotal.
    function invariant_spentLeMaxTotal() public view {
        (,,,,, uint256 maxTotal, uint256 spent,,) = exec.sessions(user, sessionKey);
        assertLe(spent, maxTotal, "spent > maxTotal");
    }

    /// revoked / expired sessions never fill.
    function invariant_revokedExpiredNoFill() public view {
        assertEq(handler.revokedFills(), 0, "fill succeeded on a revoked session");
        assertEq(handler.expiredFills(), 0, "fill succeeded on an expired session");
    }

    /// recipient is always the user.
    function invariant_recipientIsUser() public view {
        assertEq(handler.recipientViolations(), 0, "a fill had recipient != user");
    }

    /// a session only touches its poolId and tokenIn.
    function invariant_sessionScope() public view {
        assertEq(handler.poolTokenViolations(), 0, "a session touched another pool/token");
    }

    /// one intent -> at most one fill.
    function invariant_noDoubleFill() public view {
        assertFalse(handler.doubleFillDetected(), "same (user,nonce) filled twice");
    }

    /// no custody at rest.
    function invariant_noCustody() public view {
        assertEq(usdc.balanceOf(address(exec)), 0, "executor holds usdc");
        assertEq(tok.balanceOf(address(exec)), 0, "executor holds tok");
    }

    /// pause is absolute.
    function invariant_pauseAbsolute() public view {
        assertEq(handler.fillsWhilePaused(), 0, "a fill succeeded while paused");
    }

    /// no must-fail action ever succeeded.
    function invariant_noUnexpectedSuccess() public view {
        assertEq(handler.unexpectedSuccess(), 0, "a must-fail action unexpectedly succeeded");
    }

    function afterInvariant() public view {
        console2.log("successFills", handler.successFills());
    }
}
