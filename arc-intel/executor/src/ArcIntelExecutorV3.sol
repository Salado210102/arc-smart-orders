// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "./interfaces/IArcIntel.sol";

/// @title ArcIntelExecutorV3
/// @notice V2 (sessions) + a flexible pool policy: allow by **pool**, by **hook** (a whole
///         launchpad at once), or a global **allowAllPools** toggle. So enabling trading is a
///         one-time owner action, not per-token.
/// @dev Same non-custodial guarantees: no withdraw, owner only pauses / edits the policy, user
///      sessions are hard-scoped on-chain.
contract ArcIntelExecutorV3 is IUnlockCallback {
    address public constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    uint160 private constant MIN_SQRT_RATIO = 4295128739;
    uint160 private constant MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342;

    IPoolManager public immutable poolManager;
    address public immutable owner;
    bool public immutable isTestnet;   // when false, `allowAllPools` cannot be enabled (B3)

    //  EIP-712 domain: cached at deploy, recomputed if the chain id changes (fork-safe).
    bytes32 private immutable _DOMAIN_SEPARATOR;
    uint256 private immutable _CHAIN_ID;

    bytes32 private constant ORDER_TYPEHASH = keccak256(
        "ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,uint256 orderNonce,uint256 deadline)"
    );
    string public constant WITNESS_TYPE_STRING =
        "ArcIntelOrder witness)ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,uint256 orderNonce,uint256 deadline)TokenPermissions(address token,uint256 amount)";

    bytes32 private constant SESSION_ORDER_TYPEHASH = keccak256(
        "ArcIntelSessionOrder(address user,PoolKey key,bool zeroForOne,uint256 amountIn,uint256 minOut,address recipient,uint256 orderNonce,uint256 deadline)PoolKey(address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks)"
    );
    bytes32 private constant POOLKEY_TYPEHASH =
        keccak256("PoolKey(address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks)");

    struct Order {
        IPoolManager.PoolKey key;
        bool zeroForOne;
        uint256 minOut;
        address recipient;
        uint256 orderNonce;
        uint256 deadline;
    }

    struct SessionOrder {
        address user;
        IPoolManager.PoolKey key;
        bool zeroForOne;
        uint256 amountIn;
        uint256 minOut;
        address recipient;
        uint256 orderNonce;
        uint256 deadline;
    }

    struct Session {
        bool exists;
        bool revoked;
        bytes32 poolId;
        address tokenIn;
        uint256 maxPerOrder;
        uint256 maxTotal;
        uint256 spent;
        uint256 minOutFloor;
        uint64 expiry;
    }

    mapping(bytes32 => bool) public allowedPools;
    mapping(address => bool) public allowedHooks;
    bool public allowAllPools;
    mapping(address => mapping(uint256 => bool)) public orderNonceUsed;
    mapping(address => mapping(address => Session)) public sessions;
    bool public paused;

    bool private _locked;

    error NotOwner();
    error ZeroAddr();
    error Paused();
    error PoolNotAllowed(bytes32 poolId);
    error OrderExpired();
    error NonceAlreadyUsed();
    error TokenMismatch();
    error InsufficientOutput(uint256 got, uint256 minOut);
    error NotPoolManager();
    error Reentrancy();
    error BadSignature();
    error SessionInvalid();
    error SessionExpired();
    error SessionPoolMismatch();
    error SessionOverPerOrder();
    error SessionOverTotal();
    error SessionMinOutTooLow();
    error BadRecipient();
    error BadExpiry();
    error AllowAllNotAllowed();

    event Filled(
        address indexed user, bytes32 indexed poolId, uint256 amountIn, uint256 amountOut, uint256 orderNonce
    );
    event SessionFilled(
        address indexed user, address indexed sessionKey, bytes32 indexed poolId, uint256 amountIn,
        uint256 amountOut, uint256 orderNonce
    );
    event Cancelled(address indexed user, uint256 orderNonce);
    event SessionAuthorized(
        address indexed user, address indexed sessionKey, bytes32 poolId, address tokenIn, uint64 expiry
    );
    event SessionRevoked(address indexed user, address indexed sessionKey);
    event PausedSet(bool paused);
    event PoolAllowed(bytes32 indexed poolId, bool allowed);
    event HookAllowed(address indexed hook, bool allowed);
    event AllowAllSet(bool allowAll);

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier nonReentrant() {
        if (_locked) revert Reentrancy();
        _locked = true;
        _;
        _locked = false;
    }

    constructor(address poolManager_, address owner_, bytes32[] memory initialPools, bool testnet_) {
        if (poolManager_ == address(0) || owner_ == address(0)) revert ZeroAddr();
        poolManager = IPoolManager(poolManager_);
        owner = owner_;
        isTestnet = testnet_;
        _CHAIN_ID = block.chainid;
        _DOMAIN_SEPARATOR = _computeDomainSeparator();
        for (uint256 i = 0; i < initialPools.length; i++) {
            allowedPools[initialPools[i]] = true;
            emit PoolAllowed(initialPools[i], true);
        }
    }

    function _computeDomainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("ArcIntelExecutor"),
                keccak256("2"),
                block.chainid,
                address(this)
            )
        );
    }

    /// @notice EIP-712 domain separator; recomputed if `block.chainid` changed (fork-safe).
    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return block.chainid == _CHAIN_ID ? _DOMAIN_SEPARATOR : _computeDomainSeparator();
    }

    // --------------------------------------------------------------------- admin

    function setPaused(bool p) external onlyOwner {
        paused = p;
        emit PausedSet(p);
    }

    function setAllowedPool(bytes32 poolId, bool allowed) external onlyOwner {
        allowedPools[poolId] = allowed;
        emit PoolAllowed(poolId, allowed);
    }

    function setAllowedHook(address hook, bool allowed) external onlyOwner {
        allowedHooks[hook] = allowed;
        emit HookAllowed(hook, allowed);
    }

    function setAllowAllPools(bool allowAll) external onlyOwner {
        if (allowAll && !isTestnet) revert AllowAllNotAllowed();   // B3: mainnet keeps pool/hook policy
        allowAllPools = allowAll;
        emit AllowAllSet(allowAll);
    }

    function _checkPool(bytes32 poolId, address hook) private view {
        if (allowAllPools) return;
        if (allowedPools[poolId]) return;
        if (hook != address(0) && allowedHooks[hook]) return;
        revert PoolNotAllowed(poolId);
    }

    // --------------------------------------------------------------------- sessions

    function authorizeSession(
        address sessionKey,
        bytes32 poolId,
        address tokenIn,
        uint256 maxPerOrder,
        uint256 maxTotal,
        uint256 minOutFloor,
        uint64 expiry
    ) external {
        if (sessionKey == address(0) || tokenIn == address(0)) revert ZeroAddr();
        if (expiry <= block.timestamp) revert BadExpiry();
        Session storage s = sessions[msg.sender][sessionKey];
        s.exists = true;
        s.revoked = false;
        s.poolId = poolId;
        s.tokenIn = tokenIn;
        s.maxPerOrder = maxPerOrder;
        s.maxTotal = maxTotal;
        s.spent = 0;
        s.minOutFloor = minOutFloor;
        s.expiry = expiry;
        emit SessionAuthorized(msg.sender, sessionKey, poolId, tokenIn, expiry);
    }

    function revokeSession(address sessionKey) external {
        sessions[msg.sender][sessionKey].revoked = true;
        emit SessionRevoked(msg.sender, sessionKey);
    }

    // --------------------------------------------------------------------- user

    function cancelOrder(uint256 orderNonce) external {
        orderNonceUsed[msg.sender][orderNonce] = true;
        emit Cancelled(msg.sender, orderNonce);
    }

    // --------------------------------------------------------------------- execution

    function execute(
        IPermit2.PermitTransferFrom calldata permit,
        address user,
        Order calldata order,
        bytes calldata signature
    ) external nonReentrant returns (uint256 amountOut) {
        if (paused) revert Paused();
        if (block.timestamp > order.deadline) revert OrderExpired();
        if (order.recipient == address(0)) revert BadRecipient();
        bytes32 poolId = keccak256(abi.encode(order.key));
        _checkPool(poolId, order.key.hooks);
        if (orderNonceUsed[user][order.orderNonce]) revert NonceAlreadyUsed();
        orderNonceUsed[user][order.orderNonce] = true;

        address tokenIn = permit.permitted.token;
        uint256 amountIn = permit.permitted.amount;
        address expectedIn = order.zeroForOne ? order.key.currency0 : order.key.currency1;
        if (tokenIn != expectedIn) revert TokenMismatch();

        bytes32 witness = keccak256(
            abi.encode(
                ORDER_TYPEHASH, poolId, order.zeroForOne, order.minOut, order.recipient, order.orderNonce,
                order.deadline
            )
        );
        IPermit2(PERMIT2).permitWitnessTransferFrom(
            permit,
            IPermit2.SignatureTransferDetails({to: address(this), requestedAmount: amountIn}),
            user,
            witness,
            WITNESS_TYPE_STRING,
            signature
        );

        amountOut = _swapAndSettle(order.key, order.zeroForOne, amountIn, order.recipient, order.minOut);
        uint256 leftover = IERC20Min(tokenIn).balanceOf(address(this));
        if (leftover > 0) IERC20Min(tokenIn).transfer(user, leftover);
        emit Filled(user, poolId, amountIn, amountOut, order.orderNonce);
    }

    function executeWithSession(SessionOrder calldata o, bytes calldata sig)
        external
        nonReentrant
        returns (uint256 amountOut)
    {
        if (paused) revert Paused();
        if (block.timestamp > o.deadline) revert OrderExpired();

        address sessionKey = _recover(_sessionDigest(o), sig);
        Session storage s = sessions[o.user][sessionKey];
        if (!s.exists || s.revoked) revert SessionInvalid();
        if (block.timestamp > s.expiry) revert SessionExpired();

        bytes32 poolId = keccak256(abi.encode(o.key));
        if (poolId != s.poolId) revert SessionPoolMismatch();
        _checkPool(poolId, o.key.hooks);
        if (o.amountIn == 0 || o.amountIn > s.maxPerOrder) revert SessionOverPerOrder();
        if (s.spent + o.amountIn > s.maxTotal) revert SessionOverTotal();
        if (o.minOut < s.minOutFloor) revert SessionMinOutTooLow();
        if (o.recipient != o.user) revert BadRecipient();
        if (orderNonceUsed[o.user][o.orderNonce]) revert NonceAlreadyUsed();

        address tokenIn = o.zeroForOne ? o.key.currency0 : o.key.currency1;
        if (tokenIn != s.tokenIn) revert TokenMismatch();

        orderNonceUsed[o.user][o.orderNonce] = true;
        s.spent += o.amountIn;

        IPermit2(PERMIT2).transferFrom(o.user, address(this), uint160(o.amountIn), tokenIn);

        amountOut = _swapAndSettle(o.key, o.zeroForOne, o.amountIn, o.recipient, o.minOut);
        uint256 leftover = IERC20Min(tokenIn).balanceOf(address(this));
        if (leftover > 0) IERC20Min(tokenIn).transfer(o.user, leftover);
        emit SessionFilled(o.user, sessionKey, poolId, o.amountIn, amountOut, o.orderNonce);
    }

    // --------------------------------------------------------------------- internals

    function _swapAndSettle(
        IPoolManager.PoolKey memory key,
        bool zeroForOne,
        uint256 amountIn,
        address recipient,
        uint256 minOut
    ) private returns (uint256 amountOut) {
        address tokenOut = zeroForOne ? key.currency1 : key.currency0;
        uint256 outBefore = IERC20Min(tokenOut).balanceOf(recipient);
        poolManager.unlock(abi.encode(key, zeroForOne, amountIn, recipient));
        uint256 outAfter = IERC20Min(tokenOut).balanceOf(recipient);
        amountOut = outAfter > outBefore ? outAfter - outBefore : 0;
        if (amountOut < minOut) revert InsufficientOutput(amountOut, minOut);
    }

    function _sessionDigest(SessionOrder calldata o) internal view returns (bytes32) {
        bytes32 keyHash = keccak256(
            abi.encode(POOLKEY_TYPEHASH, o.key.currency0, o.key.currency1, o.key.fee, o.key.tickSpacing, o.key.hooks)
        );
        bytes32 structHash = keccak256(
            abi.encode(
                SESSION_ORDER_TYPEHASH, o.user, keyHash, o.zeroForOne, o.amountIn, o.minOut, o.recipient,
                o.orderNonce, o.deadline
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
    }

    function _recover(bytes32 digest, bytes calldata sig) internal pure returns (address) {
        if (sig.length != 65) revert BadSignature();
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
        if (v < 27) v += 27;
        if (v != 27 && v != 28) revert BadSignature();
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            revert BadSignature();
        }
        address signer = ecrecover(digest, v, r, s);
        if (signer == address(0)) revert BadSignature();
        return signer;
    }

    // --------------------------------------------------------------------- v4 callback

    function unlockCallback(bytes calldata data) external returns (bytes memory) {
        if (msg.sender != address(poolManager)) revert NotPoolManager();
        (IPoolManager.PoolKey memory key, bool zeroForOne, uint256 amountIn, address recipient) =
            abi.decode(data, (IPoolManager.PoolKey, bool, uint256, address));

        int256 delta = poolManager.swap(
            key,
            IPoolManager.SwapParams({
                zeroForOne: zeroForOne,
                amountSpecified: -int256(amountIn),
                sqrtPriceLimitX96: zeroForOne ? MIN_SQRT_RATIO + 1 : MAX_SQRT_RATIO - 1
            }),
            ""
        );

        int128 amount0 = int128(delta >> 128);
        int128 amount1 = int128(delta);

        if (amount0 > 0) poolManager.take(key.currency0, recipient, uint128(amount0));
        if (amount1 > 0) poolManager.take(key.currency1, recipient, uint128(amount1));
        if (amount0 < 0) _settle(key.currency0, uint128(-amount0));
        if (amount1 < 0) _settle(key.currency1, uint128(-amount1));
        return "";
    }

    function _settle(address currency, uint256 amount) private {
        poolManager.sync(currency);
        IERC20Min(currency).transfer(address(poolManager), amount);
        poolManager.settle();
    }
}
