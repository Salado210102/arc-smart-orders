// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "forge-std/Test.sol";
import "forge-std/StdInvariant.sol";
import "../src/ArcIntelExecutor.sol";
import "./mocks/Mocks.sol";

/// @dev Stateful fuzzing harness. Every function here is called with random inputs by Foundry's
///      invariant fuzzer; it records cumulative outcomes that the invariants then assert on.
contract Handler {
    ArcIntelExecutor public exec;
    MockERC20 public immutable tokenA;
    MockERC20 public immutable tokenB;
    IPoolManager.PoolKey public key;
    bytes32 public immutable poolId;
    address public immutable user;

    uint256 public pulledIn; // cumulative tokenIn actually pulled via Permit2 (successful fills)
    uint256 public receivedOut; // cumulative tokenOut received by the recipient
    uint256 public successFills;
    uint256 public fillsWhilePaused;
    uint256 public fillsWhileDisallowed;
    bool public doubleFillDetected;
    mapping(uint256 => uint256) public nonceCount; // user is fixed -> per nonce

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

    function executeSellA(uint256 amountIn, uint256 minOut, uint256 nonce) external {
        _fill(true, amountIn, minOut, nonce);
    }

    function executeSellB(uint256 amountIn, uint256 minOut, uint256 nonce) external {
        _fill(false, amountIn, minOut, nonce);
    }

    function setPaused(bool p) external {
        exec.setPaused(p);
    }

    function setPoolAllowed(bool a) external {
        exec.setAllowedPool(poolId, a);
    }

    function _fill(bool sellA, uint256 amountInSeed, uint256 minOutSeed, uint256 nonceSeed) internal {
        address tokenIn = sellA ? address(tokenA) : address(tokenB);
        address tokenOut = sellA ? address(tokenB) : address(tokenA);
        bool zeroForOne = (key.currency0 == tokenIn);

        uint256 bal = MockERC20(tokenIn).balanceOf(user);
        if (bal == 0) return;
        uint256 amountIn = amountInSeed % (bal + 1);
        if (amountIn == 0) return;
        uint256 expectedOut = amountIn; // pool rate is 1:1 in this campaign
        uint256 minOut = minOutSeed % (expectedOut + 1);
        uint256 orderNonce = nonceSeed % 1000;

        bool wasPaused = exec.paused();
        bool wasDisallowed = !exec.allowedPools(poolId);

        IPermit2.PermitTransferFrom memory permit = IPermit2.PermitTransferFrom({
            permitted: IPermit2.TokenPermissions({token: tokenIn, amount: amountIn}),
            nonce: orderNonce,
            deadline: block.timestamp + 1000
        });
        ArcIntelExecutor.Order memory o = ArcIntelExecutor.Order({
            key: key,
            zeroForOne: zeroForOne,
            minOut: minOut,
            recipient: user,
            orderNonce: orderNonce,
            deadline: block.timestamp + 1000
        });

        uint256 before = MockERC20(tokenOut).balanceOf(user);
        try exec.execute(permit, user, o, "") {
            uint256 got = MockERC20(tokenOut).balanceOf(user) - before;
            successFills++;
            pulledIn += amountIn;
            receivedOut += got;
            if (wasPaused) fillsWhilePaused++;
            if (wasDisallowed) fillsWhileDisallowed++;
            if (nonceCount[orderNonce] > 0) doubleFillDetected = true;
            nonceCount[orderNonce]++;
        } catch {}
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
        // owner = handler, so the fuzzer can also exercise pause()/allowlist
        exec = new ArcIntelExecutor(address(pm), address(handler), pools);
        handler.setExecutor(exec);

        // install mock Permit2 at the canonical address the executor calls
        permit2 = new MockPermit2();
        vm.etch(exec.PERMIT2(), address(permit2).code);

        // large seed balances so the campaign does not drain (no minting during the campaign)
        tokenA.mint(user, 1e30);
        tokenB.mint(user, 1e30);
        tokenA.mint(address(pm), 1e30);
        tokenB.mint(address(pm), 1e30);

        // Fuzz ONLY the handler entrypoints. Explicitly exclude tokens / pool manager / executor so
        // the campaign cannot mint tokens or change the pool rate (harness-only actions).
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

    /// @dev One intent -> at most one fill. A second fill on the same nonce must be impossible.
    function invariant_noDoubleFill() public view {
        assertFalse(handler.doubleFillDetected(), "same (user,nonce) filled twice");
    }

    /// @dev No custody at rest: after every interaction the executor holds zero of both tokens.
    function invariant_noCustody() public view {
        assertEq(tokenA.balanceOf(address(exec)), 0, "executor holds tokenA");
        assertEq(tokenB.balanceOf(address(exec)), 0, "executor holds tokenB");
    }

    /// @dev Conservation of value: total received by recipients never exceeds total pulled.
    function invariant_noValueCreated() public view {
        assertLe(handler.receivedOut(), handler.pulledIn(), "more value out than in");
    }

    /// @dev pause() is absolute: no fill can succeed while paused, under any input.
    function invariant_pauseAbsolute() public view {
        assertEq(handler.fillsWhilePaused(), 0, "a fill succeeded while paused");
    }

    /// @dev Fail-closed: with the pool not allowlisted, no fill can succeed.
    function invariant_emptyAllowlistNoFill() public view {
        assertEq(handler.fillsWhileDisallowed(), 0, "a fill succeeded while pool disallowed");
    }
}
