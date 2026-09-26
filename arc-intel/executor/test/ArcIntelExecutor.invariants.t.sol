// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Test.sol";
import "forge-std/StdInvariant.sol";
import "forge-std/console2.sol";
import "../src/ArcIntelExecutor.sol";
import "./mocks/Mocks.sol";

/// @dev Stateful fuzzing harness. Besides happy-path fills, it ACTIVELY attempts actions that MUST
///      fail (expired deadline, minOut too high, execute while paused, pool not allowed) and counts
///      them separately. `unexpectedSuccess` must stay 0 (a must-fail action that succeeded).
contract Handler {
    ArcIntelExecutor public exec;
    MockERC20 public immutable tokenA;
    MockERC20 public immutable tokenB;
    IPoolManager.PoolKey public key;
    bytes32 public immutable poolId;
    address public immutable user;

    uint256 public pulledIn; // cumulative tokenIn pulled on successful fills
    uint256 public receivedOut; // cumulative tokenOut received by the recipient
    uint256 public successFills;
    uint256 public fillsWhilePaused;
    uint256 public fillsWhileDisallowed;
    bool public doubleFillDetected;
    mapping(uint256 => uint256) public nonceCount;

    // must-fail accounting
    uint256 public unexpectedSuccess; // must-fail action that SUCCEEDED (invariant must stay 0)
    uint256 public expiredTried;
    uint256 public minOutTried;
    uint256 public pausedTried;
    uint256 public disallowedTried;

    constructor(MockERC20 a, MockERC20 b, IPoolManager.PoolKey memory k, bytes32 pid, address u) {
        tokenA = a;
        tokenB = b;
        key = k;
        poolId = pid;
        user = u;
    }

    function setExecutor(ArcIntelExecutor e) external {
        exec = e;
    }

    // ------------------------------------------------------------------ fuzzed entrypoints

    function executeValidA(uint256 amountInSeed, uint256 minOutSeed, uint256 nonceSeed) external {
        _valid(true, amountInSeed, minOutSeed, nonceSeed);
    }

    function executeValidB(uint256 amountInSeed, uint256 minOutSeed, uint256 nonceSeed) external {
        _valid(false, amountInSeed, minOutSeed, nonceSeed);
    }

    /// @dev MUST revert (OrderExpired).
    function executeExpired(uint256 amountInSeed, uint256 nonceSeed) external {
        if (block.timestamp == 0) return;
        (uint256 amountIn,) = _bounds(true, amountInSeed);
        if (amountIn == 0) return;
        bool ok = _attempt(true, amountIn, 0, nonceSeed % 1000, block.timestamp - 1);
        expiredTried++;
        if (ok) unexpectedSuccess++;
    }

    /// @dev MUST revert (InsufficientOutput): asks for more than the pool can give.
    function executeMinOutTooHigh(uint256 amountInSeed, uint256 nonceSeed, uint256 extraSeed) external {
        (uint256 amountIn, uint256 expectedOut) = _bounds(true, amountInSeed);
        if (amountIn == 0) return;
        uint256 minOut = expectedOut + 1 + (extraSeed % 1e18);
        bool ok = _attempt(true, amountIn, minOut, nonceSeed % 1000, block.timestamp + 1000);
        minOutTried++;
        if (ok) unexpectedSuccess++;
    }

    /// @dev MUST revert (Paused): execute while the contract is paused.
    function executeWhilePaused(uint256 amountInSeed, uint256 nonceSeed) external {
        (uint256 amountIn,) = _bounds(true, amountInSeed);
        if (amountIn == 0) return;
        bool prev = exec.paused();
        exec.setPaused(true);
        bool ok = _attempt(true, amountIn, 0, nonceSeed % 1000, block.timestamp + 1000);
        pausedTried++;
        if (ok) {
            unexpectedSuccess++;
            fillsWhilePaused++;
        }
        exec.setPaused(prev);
    }

    /// @dev MUST revert (PoolNotAllowed): execute while the pool is not allowlisted.
    function executeDisallowed(uint256 amountInSeed, uint256 nonceSeed) external {
        (uint256 amountIn,) = _bounds(true, amountInSeed);
        if (amountIn == 0) return;
        bool prev = exec.allowedPools(poolId);
        exec.setAllowedPool(poolId, false);
        bool ok = _attempt(true, amountIn, 0, nonceSeed % 1000, block.timestamp + 1000);
        disallowedTried++;
        if (ok) {
            unexpectedSuccess++;
            fillsWhileDisallowed++;
        }
        exec.setAllowedPool(poolId, prev);
    }

    function setPaused(bool p) external {
        exec.setPaused(p);
    }

    function setPoolAllowed(bool a) external {
        exec.setAllowedPool(poolId, a);
    }

    // ------------------------------------------------------------------ internals

    function _bounds(bool sellA, uint256 seed) internal view returns (uint256 amountIn, uint256 expectedOut) {
        address tokenIn = sellA ? address(tokenA) : address(tokenB);
        uint256 bal = MockERC20(tokenIn).balanceOf(user);
        amountIn = bal == 0 ? 0 : seed % (bal + 1);
        expectedOut = amountIn; // pool rate is 1:1 in this campaign
    }

    function _valid(bool sellA, uint256 amountInSeed, uint256 minOutSeed, uint256 nonceSeed) internal {
        (uint256 amountIn, uint256 expectedOut) = _bounds(sellA, amountInSeed);
        if (amountIn == 0) return;
        uint256 minOut = minOutSeed % (expectedOut + 1);
        _attempt(sellA, amountIn, minOut, nonceSeed % 1000, block.timestamp + 1000);
    }

    function _attempt(bool sellA, uint256 amountIn, uint256 minOut, uint256 nonce, uint256 deadline)
        internal
        returns (bool ok)
    {
        address tokenIn = sellA ? address(tokenA) : address(tokenB);
        address tokenOut = sellA ? address(tokenB) : address(tokenA);
        bool zeroForOne = (key.currency0 == tokenIn);

        IPermit2.PermitTransferFrom memory permit = IPermit2.PermitTransferFrom({
            permitted: IPermit2.TokenPermissions({token: tokenIn, amount: amountIn}),
            nonce: nonce,
            deadline: deadline
        });
        ArcIntelExecutor.Order memory o = ArcIntelExecutor.Order({
            key: key,
            zeroForOne: zeroForOne,
            minOut: minOut,
            recipient: user,
            orderNonce: nonce,
            deadline: deadline
        });

        uint256 beforeBal = MockERC20(tokenOut).balanceOf(user);
        try exec.execute(permit, user, o, "") {
            uint256 got = MockERC20(tokenOut).balanceOf(user) - beforeBal;
            successFills++;
            pulledIn += amountIn;
            receivedOut += got;
            if (nonceCount[nonce] > 0) doubleFillDetected = true;
            nonceCount[nonce]++;
            return true;
        } catch {
            return false;
        }
    }
}

contract ArcIntelExecutorInvariants is StdInvariant, Test {
    ArcIntelExecutor internal exec;
    MockPoolManager internal pm;
    MockPermit2 internal permit2;
    MockERC20 internal tokenA;
    MockERC20 internal tokenB;
    Handler internal handler;

    address internal user = address(0xA11CE);
    IPoolManager.PoolKey internal key;

    function setUp() public {
        tokenA = new MockERC20("A");
        tokenB = new MockERC20("B");
        (address c0, address c1) =
            address(tokenA) < address(tokenB) ? (address(tokenA), address(tokenB)) : (address(tokenB), address(tokenA));
        key = IPoolManager.PoolKey(c0, c1, 3000, 60, address(0));
        bytes32 poolId = keccak256(abi.encode(key));

        pm = new MockPoolManager(); // rate = 1:1

        handler = new Handler(tokenA, tokenB, key, poolId, user);

        bytes32[] memory pools = new bytes32[](1);
        pools[0] = poolId;
        exec = new ArcIntelExecutor(address(pm), address(handler), pools); // owner = handler
        handler.setExecutor(exec);

        permit2 = new MockPermit2();
        vm.etch(exec.PERMIT2(), address(permit2).code);

        tokenA.mint(user, 1e30);
        tokenB.mint(user, 1e30);
        tokenA.mint(address(pm), 1e30);
        tokenB.mint(address(pm), 1e30);

        targetContract(address(handler));
        bytes4[] memory excluded = new bytes4[](1);
        excluded[0] = Handler.setExecutor.selector;
        excludeSelector(FuzzSelector({addr: address(handler), selectors: excluded}));
        excludeContract(address(tokenA));
        excludeContract(address(tokenB));
        excludeContract(address(pm));
        excludeContract(address(permit2));
        excludeContract(address(exec));
    }

    /// @dev One intent -> at most one fill.
    function invariant_noDoubleFill() public view {
        assertFalse(handler.doubleFillDetected(), "same (user,nonce) filled twice");
    }

    /// @dev No custody at rest.
    function invariant_noCustody() public view {
        assertEq(tokenA.balanceOf(address(exec)), 0, "executor holds tokenA");
        assertEq(tokenB.balanceOf(address(exec)), 0, "executor holds tokenB");
    }

    /// @dev Conservation of value: received never exceeds pulled.
    function invariant_noValueCreated() public view {
        assertLe(handler.receivedOut(), handler.pulledIn(), "more value out than in");
    }

    /// @dev pause() is absolute.
    function invariant_pauseAbsolute() public view {
        assertEq(handler.fillsWhilePaused(), 0, "a fill succeeded while paused");
    }

    /// @dev Fail-closed allowlist.
    function invariant_emptyAllowlistNoFill() public view {
        assertEq(handler.fillsWhileDisallowed(), 0, "a fill succeeded while pool disallowed");
    }

    /// @dev No must-fail action ever succeeded (expired / minOut-too-high / paused / disallowed).
    function invariant_noUnexpectedSuccess() public view {
        assertEq(handler.unexpectedSuccess(), 0, "a must-fail action unexpectedly succeeded");
    }

    /// @dev Report must-fail coverage so we can see the campaign actually tried to break things.
    function afterInvariant() public view {
        console2.log("validFills", handler.successFills());
        console2.log("expiredTried", handler.expiredTried());
        console2.log("minOutTried", handler.minOutTried());
        console2.log("pausedTried", handler.pausedTried());
        console2.log("disallowedTried", handler.disallowedTried());
    }
}
