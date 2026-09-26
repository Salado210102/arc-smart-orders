// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "./interfaces/IArcIntel.sol";

/// @title ArcIntelExecutor
/// @notice Minimal, non-custodial v4 executor for arc-intel. One signed order -> one fill.
/// @dev No custody at rest: funds are pulled via Permit2, swapped on the Uniswap v4
///      PoolManager, and the output is sent straight to the recipient inside the same tx.
///      There is deliberately no rescue/withdraw function (there is nothing to rescue).
///      The owner (a Safe) can only pause and edit the pool allowlist; it can never move
///      user funds or alter a user-signed order.
contract ArcIntelExecutor is IUnlockCallback {
    //  Canonical Permit2 (same address on every chain).
    address public constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    //  v4 price-limit sentinels (SwapMath constants) used when no explicit limit is set.
    uint160 private constant MIN_SQRT_RATIO = 4295128739;
    uint160 private constant MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342;

    IPoolManager public immutable poolManager;
    address public immutable owner;

    //  The user signs ONE Permit2 `PermitWitnessTransferFrom` message. Its EIP-712 domain is
    //  Permit2's own domain (name "Permit2", chainId, verifyingContract = the canonical Permit2),
    //  so the signature is bound to this chain and to Permit2 -> not replayable elsewhere.
    //  The order-specifics are bound via the `witness` below, and `spender` == this executor.
    //  (No custom domain here on purpose: the signature is validated by Permit2, not by us.)

    //  Witness signed by the user; binds the swap-specifics. The pulled token+amount live in
    //  the Permit2 permit itself, so one signature covers both the transfer and the swap.
    bytes32 private constant ORDER_TYPEHASH =
        keccak256("ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,uint256 orderNonce)");
    string public constant WITNESS_TYPE_STRING =
        "ArcIntelOrder witness)ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,uint256 orderNonce)TokenPermissions(address token,uint256 amount)";

    struct Order {
        IPoolManager.PoolKey key;
        bool zeroForOne;
        uint256 minOut;
        address recipient;
        uint256 orderNonce;
        uint256 deadline;
    }

    /// @notice poolId -> allowed. Empty allowlist means nothing can execute (fail-closed).
    mapping(bytes32 => bool) public allowedPools;
    /// @notice user -> orderNonce -> used (single-use; also used for user-side cancellation).
    mapping(address => mapping(uint256 => bool)) public orderNonceUsed;
    /// @notice Emergency stop for NEW fills only.
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

    event Filled(
        address indexed user,
        bytes32 indexed poolId,
        uint256 amountIn,
        uint256 amountOut,
        uint256 orderNonce
    );
    event Cancelled(address indexed user, uint256 orderNonce);
    event PausedSet(bool paused);
    event PoolAllowed(bytes32 indexed poolId, bool allowed);

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

    constructor(address poolManager_, address owner_, bytes32[] memory initialPools) {
        if (poolManager_ == address(0) || owner_ == address(0)) revert ZeroAddr();
        poolManager = IPoolManager(poolManager_);
        owner = owner_;
        for (uint256 i = 0; i < initialPools.length; i++) {
            allowedPools[initialPools[i]] = true;
            emit PoolAllowed(initialPools[i], true);
        }
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

    // --------------------------------------------------------------------- user

    /// @notice Revoke a pending order before it is filled. Only the signer can cancel their own.
    function cancelOrder(uint256 orderNonce) external {
        orderNonceUsed[msg.sender][orderNonce] = true;
        emit Cancelled(msg.sender, orderNonce);
    }

    // --------------------------------------------------------------------- keepers

    /// @notice Execute a user-signed order. Callable by anyone (permissionless keeper/relayer):
    ///         the signed terms make submission harmless, so the worst a submitter can do is
    ///         censor (not submit), never steal or alter terms.
    /// @param permit    Permit2 data signed by `user` (spender = this contract).
    /// @param user      The signer / order owner.
    /// @param order     The swap the user signed (witness).
    /// @param signature The single EIP-712 signature over permit + witness.
    function execute(
        IPermit2.PermitTransferFrom calldata permit,
        address user,
        Order calldata order,
        bytes calldata signature
    ) external nonReentrant returns (uint256 amountOut) {
        if (paused) revert Paused();
        if (block.timestamp > order.deadline) revert OrderExpired();

        bytes32 poolId = keccak256(abi.encode(order.key));
        if (!allowedPools[poolId]) revert PoolNotAllowed(poolId);
        if (orderNonceUsed[user][order.orderNonce]) revert NonceAlreadyUsed();
        orderNonceUsed[user][order.orderNonce] = true;

        address tokenIn = permit.permitted.token;
        uint256 amountIn = permit.permitted.amount;
        address tokenOut = order.zeroForOne ? order.key.currency1 : order.key.currency0;
        // The pulled token must be the pool's input side for the signed direction.
        address expectedIn = order.zeroForOne ? order.key.currency0 : order.key.currency1;
        if (tokenIn != expectedIn) revert TokenMismatch();

        //  Pull the exact input straight into this contract. The witness recomputes the intent;
        //  a keeper passing different values makes the user's signature fail to validate.
        bytes32 witness = keccak256(
            abi.encode(ORDER_TYPEHASH, poolId, order.zeroForOne, order.minOut, order.recipient, order.orderNonce)
        );
        IPermit2(PERMIT2).permitWitnessTransferFrom(
            permit,
            IPermit2.SignatureTransferDetails({to: address(this), requestedAmount: amountIn}),
            user,
            witness,
            WITNESS_TYPE_STRING,
            signature
        );

        uint256 outBefore = IERC20Min(tokenOut).balanceOf(order.recipient);

        //  Perform the v4 swap (exact input -> output), same tx.
        poolManager.unlock(abi.encode(order, amountIn));

        uint256 outAfter = IERC20Min(tokenOut).balanceOf(order.recipient);
        amountOut = outAfter > outBefore ? outAfter - outBefore : 0;
        if (amountOut < order.minOut) revert InsufficientOutput(amountOut, order.minOut);

        //  Return any input dust left unspent (e.g. partial fill) to the user.
        uint256 leftover = IERC20Min(tokenIn).balanceOf(address(this));
        if (leftover > 0) IERC20Min(tokenIn).transfer(user, leftover);

        emit Filled(user, poolId, amountIn, amountOut, order.orderNonce);
    }

    // --------------------------------------------------------------------- v4 callback

    /// @inheritdoc IUnlockCallback
    function unlockCallback(bytes calldata data) external returns (bytes memory) {
        if (msg.sender != address(poolManager)) revert NotPoolManager();

        (Order memory order, uint256 amountIn) = abi.decode(data, (Order, uint256));

        int256 delta = poolManager.swap(
            order.key,
            IPoolManager.SwapParams({
                zeroForOne: order.zeroForOne,
                amountSpecified: -int256(amountIn),
                sqrtPriceLimitX96: order.zeroForOne ? MIN_SQRT_RATIO + 1 : MAX_SQRT_RATIO - 1
            }),
            ""
        );

        //  v4 BalanceDelta: amount0 is the UPPER 128 bits, amount1 is the LOWER 128 bits.
        int128 amount0 = int128(delta >> 128);
        int128 amount1 = int128(delta);

        //  Output side (positive delta) -> send straight to the recipient.
        if (amount0 > 0) poolManager.take(order.key.currency0, order.recipient, uint128(amount0));
        if (amount1 > 0) poolManager.take(order.key.currency1, order.recipient, uint128(amount1));

        //  Input side (negative delta) -> pay the pool from the funds pulled via Permit2.
        if (amount0 < 0) _settle(order.key.currency0, uint128(-amount0));
        if (amount1 < 0) _settle(order.key.currency1, uint128(-amount1));

        return "";
    }

    /// @dev Pay the pool for one currency: snapshot the pool's balance, send the tokens, then settle.
    function _settle(address currency, uint256 amount) private {
        poolManager.sync(currency);
        IERC20Min(currency).transfer(address(poolManager), amount);
        poolManager.settle();
    }
}
