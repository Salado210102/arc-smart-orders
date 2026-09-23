// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC20X {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IERC1271X {
    function isValidSignature(bytes32 hash, bytes calldata signature) external view returns (bytes4);
}

/// @title CrossChainOrderExecutor — DRAFT (not audited)
/// @notice Executes a **cross-chain** smart order on Arc: an intent signed on a **source** chain is
///         delivered by the Arc Interop / CCTP message and filled atomically here (destination).
///
/// @dev Design notes (read before use):
///      - **Does NOT inherit `OrderExecutor.sol`** (kept frozen/verified) — it reimplements the same
///        EIP-712 + ECDSA/EIP-1271 verification pattern, self-contained.
///      - **Not Permit2**: Permit2 signatures are chain-bound (the domain includes `chainId`), so a
///        signature made on Base Sepolia would not validate against Arc's Permit2. Instead the order is
///        a signed **`CrossChainIntent`**, and the input tokens are delivered to this executor by the
///        interop/bridge (the swap happens atomically on arrival).
///      - **Anti-replay**: the standard EIP-712 domain commits the **destination** `chainId` (so a
///        signature can't be reused on another chain), and the signed intent commits **both**
///        `sourceChainId` + `destinationChainId` (checked on execution) plus a single-use nonce.
///      - The input-side platform fee (default 0.30%) is retained from the delivered `tokenIn` before
///        the swap, and `minOut` is enforced on the **net**.
contract CrossChainOrderExecutor {
    IERC20X public immutable usdc;

    address public owner;
    address public keeper; // authorized to submit/deliver the fill
    address public interop; // authorized interop/CCTP message source (0 = any keeper)
    address public feeRecipient;

    uint256 public feeBps = 30; // 0.30%
    uint256 public constant MAX_FEE_BPS = 1000;

    uint256 public immutable sourceChainId; // allowed origin chain
    uint256 public immutable destinationChainId; // this chain (set to block.chainid at deploy)

    mapping(address => bool) public allowedTargets;
    mapping(bytes32 => bool) public usedIntent; // intentHash -> consumed

    bytes32 internal constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 internal constant INTENT_TYPEHASH = keccak256(
        "CrossChainIntent(address owner,address tokenIn,address tokenOut,uint256 amountIn,uint256 minOut,uint256 sourceChainId,uint256 destinationChainId,uint256 nonce,uint256 deadline)"
    );
    bytes32 internal constant NAME_HASH = keccak256("ArcCrossChainOrders");
    bytes32 internal constant VERSION_HASH = keccak256("1");

    struct CrossChainIntent {
        address owner; // order author (signer)
        address tokenIn; // delivered token (e.g. USDC)
        address tokenOut; // desired output
        uint256 amountIn; // gross input (base units)
        uint256 minOut; // minimum output on the NET (after fee)
        uint256 sourceChainId; // origin chain
        uint256 destinationChainId; // execution chain (must equal block.chainid)
        uint256 nonce;
        uint256 deadline;
    }

    bool private _locked;

    event CrossChainFilled(
        address indexed owner, uint256 sourceChainId, address tokenIn, address tokenOut, uint256 amountIn, uint256 netAmountIn, uint256 fee, uint256 amountOut
    );
    event KeeperUpdated(address keeper);
    event InteropUpdated(address interop);
    event TargetAllowed(address target, bool allowed);
    event FeeUpdated(uint256 feeBps, address feeRecipient);
    event OwnershipTransferred(address indexed from, address indexed to);

    error NotOwner();
    error NotKeeper();
    error NotInterop();
    error ZeroAddr();
    error TargetNotAllowed();
    error WrongSource();
    error WrongDestination();
    error IntentExpired();
    error IntentUsed();
    error BadSignature();
    error InsufficientInput();
    error SwapFailed(bytes reason);
    error InsufficientOutput(uint256 got, uint256 minOut);
    error FeeTooHigh();
    error Reentrancy();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }
    modifier onlyKeeper() {
        if (msg.sender != keeper) revert NotKeeper();
        _;
    }
    modifier nonReentrant() {
        if (_locked) revert Reentrancy();
        _locked = true;
        _;
        _locked = false;
    }

    constructor(
        address usdc_,
        address owner_,
        address keeper_,
        address interop_,
        address feeRecipient_,
        uint256 sourceChainId_
    ) {
        if (usdc_ == address(0) || owner_ == address(0) || keeper_ == address(0)) revert ZeroAddr();
        usdc = IERC20X(usdc_);
        owner = owner_;
        keeper = keeper_;
        interop = interop_;
        feeRecipient = feeRecipient_ == address(0) ? owner_ : feeRecipient_;
        sourceChainId = sourceChainId_;
        destinationChainId = block.chainid;
    }

    // --------------------------------------------------------------- EIP-712
    /// @dev Standard 4-field domain (viem/wallet compatible). Anti-replay comes from `chainId`
    ///      (= destination), the signed intent's `sourceChainId`/`destinationChainId`, and the nonce.
    function domainSeparator() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, destinationChainId, address(this)));
    }

    function hashIntent(CrossChainIntent calldata intent) public pure returns (bytes32) {
        return keccak256(
            abi.encode(
                INTENT_TYPEHASH,
                intent.owner,
                intent.tokenIn,
                intent.tokenOut,
                intent.amountIn,
                intent.minOut,
                intent.sourceChainId,
                intent.destinationChainId,
                intent.nonce,
                intent.deadline
            )
        );
    }

    function digest(CrossChainIntent calldata intent) public view returns (bytes32) {
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), hashIntent(intent)));
    }

    // --------------------------------------------------------------- execution
    /// @notice Fill a cross-chain order. The `tokenIn` must already be held by this executor (delivered
    ///         by the interop/CCTP message). `swapData` must send `tokenOut` to `intent.owner`.
    function executeCrossChain(
        CrossChainIntent calldata intent,
        bytes calldata signature,
        address swapTarget,
        bytes calldata swapData
    ) external nonReentrant {
        // only an authorized keeper, and — if configured — only via the interop source.
        if (msg.sender != keeper) revert NotKeeper();
        if (interop != address(0) && msg.sender != interop) revert NotInterop();

        if (intent.sourceChainId != sourceChainId) revert WrongSource();
        if (intent.destinationChainId != destinationChainId) revert WrongDestination();
        if (block.timestamp > intent.deadline) revert IntentExpired();
        if (!allowedTargets[swapTarget]) revert TargetNotAllowed();

        bytes32 ih = hashIntent(intent);
        if (usedIntent[ih]) revert IntentUsed();
        if (!_verify(intent.owner, digest(intent), signature)) revert BadSignature();
        usedIntent[ih] = true;

        if (intent.tokenIn != address(usdc)) revert InsufficientInput(); // MVP: input is USDC
        uint256 amountIn = intent.amountIn;
        if (usdc.balanceOf(address(this)) < amountIn) revert InsufficientInput();

        // input-side platform fee (retained from the delivered tokenIn)
        uint256 fee = feeRecipient == address(0) ? 0 : (amountIn * feeBps) / 10_000;
        uint256 net = amountIn - fee;
        if (fee > 0 && !usdc.transfer(feeRecipient, fee)) revert SwapFailed("fee");

        // approve the whitelisted venue for the NET and call it
        _forceApprove(address(usdc), swapTarget, net);
        uint256 outBefore = IERC20X(intent.tokenOut).balanceOf(intent.owner);
        (bool ok, bytes memory ret) = swapTarget.call(swapData);
        if (!ok) revert SwapFailed(ret);
        _forceApprove(address(usdc), swapTarget, 0);

        // enforce minOut on the NET-received output
        uint256 outAfter = IERC20X(intent.tokenOut).balanceOf(intent.owner);
        uint256 received = outAfter > outBefore ? outAfter - outBefore : 0;
        if (received < intent.minOut) revert InsufficientOutput(received, intent.minOut);

        emit CrossChainFilled(intent.owner, intent.sourceChainId, intent.tokenIn, intent.tokenOut, amountIn, net, fee, received);
    }

    // --------------------------------------------------------------- admin (owner)
    function setKeeper(address k) external onlyOwner {
        if (k == address(0)) revert ZeroAddr();
        keeper = k;
        emit KeeperUpdated(k);
    }

    function setInterop(address i) external onlyOwner {
        interop = i;
        emit InteropUpdated(i);
    }

    function setAllowedTarget(address target, bool allowed) external onlyOwner {
        if (target == address(0)) revert ZeroAddr();
        allowedTargets[target] = allowed;
        emit TargetAllowed(target, allowed);
    }

    function setFee(uint256 feeBps_, address feeRecipient_) external onlyOwner {
        if (feeBps_ > MAX_FEE_BPS) revert FeeTooHigh();
        feeBps = feeBps_;
        feeRecipient = feeRecipient_;
        emit FeeUpdated(feeBps_, feeRecipient_);
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert ZeroAddr();
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    // --------------------------------------------------------------- internal
    function _verify(address signer, bytes32 d, bytes calldata sig) internal view returns (bool) {
        if (signer.code.length == 0) {
            if (sig.length != 65) return false;
            bytes32 r;
            bytes32 s;
            uint8 v;
            assembly {
                r := calldataload(sig.offset)
                s := calldataload(add(sig.offset, 32))
                v := byte(0, calldataload(add(sig.offset, 64)))
            }
            if (v < 27) v += 27;
            if (v != 27 && v != 28) return false;
            address rec = ecrecover(d, v, r, s);
            return rec != address(0) && rec == signer;
        }
        (bool ok, bytes memory ret) = signer.staticcall(abi.encodeWithSelector(IERC1271X.isValidSignature.selector, d, sig));
        return ok && ret.length >= 32 && abi.decode(ret, (bytes4)) == IERC1271X.isValidSignature.selector;
    }

    function _forceApprove(address token, address spender, uint256 amount) internal {
        (bool ok0, ) = token.call(abi.encodeWithSelector(IERC20X.approve.selector, spender, 0));
        ok0;
        (bool ok1, bytes memory r) = token.call(abi.encodeWithSelector(IERC20X.approve.selector, spender, amount));
        require(ok1 && (r.length == 0 || abi.decode(r, (bool))), "approve failed");
    }
}
