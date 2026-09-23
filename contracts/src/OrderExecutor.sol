// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

//  OrderExecutor: ejecucion ATOMICA de ordenes inteligentes de BasePump (una sola tx).
//  Flujo:
//    1) El usuario firma un Permit2 `PermitTransferFrom` one-shot (importe EXACTO, spender = este contrato).
//    2) El keeper llama `executeOrder(...)`: el contrato tira del tokenIn del usuario via Permit2,
//       lo aprueba al router del swap y ejecuta el swap (calldata construida off-chain con
//       recipient = usuario y comision -> tesoreria).
//    3) Se garantiza que el usuario recibe >= minOut del tokenOut (el keeper no puede desviar el output).
//  El contrato NO guarda fondos en reposo.

interface IERC20Min {
    function balanceOf(address) external view returns (uint256);
    function approve(address, uint256) external returns (bool);
    function transfer(address, uint256) external returns (bool);
}

interface IPermit2 {
    struct TokenPermissions {
        address token;
        uint256 amount;
    }
    struct PermitTransferFrom {
        TokenPermissions permitted;
        uint256 nonce;
        uint256 deadline;
    }
    struct SignatureTransferDetails {
        address to;
        uint256 requestedAmount;
    }

    function permitTransferFrom(
        PermitTransferFrom calldata permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external;

    function permitWitnessTransferFrom(
        PermitTransferFrom calldata permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes32 witness,
        string calldata witnessTypeString,
        bytes calldata signature
    ) external;
}

//  Permit2 AllowanceTransfer: una firma autoriza un allowance con expiracion que el spender
//  puede consumir en VARIAS transferencias (necesario para DCA/TWAP).
interface IPermit2Allowance {
    struct PermitDetails {
        address token;
        uint160 amount;
        uint48 expiration;
        uint48 nonce;
    }
    struct PermitSingle {
        PermitDetails details;
        address spender;
        uint256 sigDeadline;
    }

    function permit(address owner, PermitSingle calldata permitSingle, bytes calldata signature) external;

    function transferFrom(address from, address to, uint160 amount, address token) external;
}

//  EIP-1271 minimo (smart wallets / Safe) para validar la firma de la intencion.
interface IERC1271_MIN {
    function isValidSignature(bytes32 hash, bytes calldata signature) external view returns (bytes4);
}

contract OrderExecutor {
    //  Permit2 canonico (misma direccion en Base).
    address public constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    //  Witness firmado por el usuario: compromete tokenOut + minOut de la intencion completa.
    bytes32 private constant ORDER_INTENT_TYPEHASH = keccak256("OrderIntent(address tokenOut,uint256 minOut)");
    //  Type string que Permit2 concatena al STUB para recomputar el typehash del witness.
    string public constant WITNESS_TYPE_STRING =
        "OrderIntent witness)OrderIntent(address tokenOut,uint256 minOut)TokenPermissions(address token,uint256 amount)";

    //  STUB canonico de Permit2 (prefijo del typehash). Publica para verificar en tests.
    string public constant PERMIT2_WITNESS_STUB =
        "PermitWitnessTransferFrom(TokenPermissions permitted,address spender,uint256 nonce,uint256 deadline,";

    //  ---- Intencion firmada para DCA/GRID/COPY ----
    //  Permit2 AllowanceTransfer (permit/permitBatch) NO tiene variante con witness, asi que para estos
    //  tipos el usuario firma una INTENCION propia (EIP-712, dominio BasePump) que el contrato verifica
    //  en CADA parte: compromete tokenOut + minRate + maxAmountIn + deadline. El keeper no puede ni
    //  desviar el output a otro token ni llenar por debajo del precio firmado.
    bytes32 private constant DCA_INTENT_TYPEHASH = keccak256(
        "DcaIntent(address owner,address tokenIn,address tokenOut,uint256 maxAmountIn,uint256 minRate,uint256 deadline)"
    );
    bytes32 private constant EIP712_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant EIP712_NAME_HASH = keccak256("ArcSmartOrders");
    bytes32 private constant EIP712_VERSION_HASH = keccak256("1");

    //  minRate = minimo de tokenOut (unidades base) por 1e18 de tokenIn (unidades base).
    struct DcaIntent {
        address owner;
        address tokenIn;
        address tokenOut;
        uint256 maxAmountIn;
        uint256 minRate;
        uint256 deadline;
    }

    address public owner; // Safe (multisig) de BasePump.
    address public keeper; // wallet del keeper autorizada a ejecutar ordenes.

    //  Whitelist de routers/contratos a los que el ejecutor puede llamar (gestionada por el Safe).
    mapping(address => bool) public allowedTargets;

    bool private _locked;

    error NotKeeper();
    error NotOwner();
    error ZeroAddr();
    error SwapFailed(bytes reason);
    error InsufficientOutput(uint256 got, uint256 minOut);
    error Reentrancy();
    error TargetNotAllowed(address target);
    error BadIntent();
    error IntentExpired();
    error IntentAmountTooHigh();
    error IntentRateTooLow();
    error BadIntentSignature();

    event OrderExecuted(
        address indexed orderOwner,
        address indexed tokenIn,
        address indexed tokenOut,
        address swapTarget,
        uint256 amountIn,
        uint256 amountOut
    );
    event KeeperUpdated(address keeper);
    event TargetAllowed(address target, bool allowed);

    modifier onlyKeeper() {
        if (msg.sender != keeper) revert NotKeeper();
        _;
    }

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

    constructor(address owner_, address keeper_, address initialTarget) {
        if (owner_ == address(0) || keeper_ == address(0)) revert ZeroAddr();
        owner = owner_;
        keeper = keeper_;
        if (initialTarget != address(0)) {
            allowedTargets[initialTarget] = true;
            emit TargetAllowed(initialTarget, true);
        }
    }

    function setKeeper(address k) external onlyOwner {
        if (k == address(0)) revert ZeroAddr();
        keeper = k;
        emit KeeperUpdated(k);
    }

    /// @notice Autoriza/revoca un swapTarget (router DEX) al que el ejecutor puede llamar.
    function setAllowedTarget(address target, bool allowed) external onlyOwner {
        if (target == address(0)) revert ZeroAddr();
        allowedTargets[target] = allowed;
        emit TargetAllowed(target, allowed);
    }

    /**
     * @notice Ejecuta la orden firmada por `orderOwner`: pull del tokenIn + swap atomico.
     * @param permit          Datos del Permit2 (token+importe, nonce, deadline) firmados por el usuario.
     * @param orderOwner      Wallet del usuario (owner del permit).
     * @param permitSignature Firma EIP-712 del usuario (spender = este contrato).
     * @param swapTarget      Router del swap (calldata construida off-chain).
     * @param swapData        Calldata del swap (debe enviar el output a orderOwner y la comision a tesoreria).
     * @param tokenOut        Token que se espera recibir (para verificar el minimo).
     * @param minOut          Minimo de tokenOut que debe recibir orderOwner.
     */
    function executeOrder(
        IPermit2.PermitTransferFrom calldata permit,
        address orderOwner,
        bytes calldata permitSignature,
        address swapTarget,
        bytes calldata swapData,
        address tokenOut,
        uint256 minOut
    ) external onlyKeeper nonReentrant {
        if (!allowedTargets[swapTarget]) revert TargetNotAllowed(swapTarget);
        address tokenIn = permit.permitted.token;
        uint256 amountIn = permit.permitted.amount;
        uint256 outBefore = IERC20Min(tokenOut).balanceOf(orderOwner);

        //  1) Traer el tokenIn del usuario a este contrato.
        //     Permit2 exige que msg.sender == spender firmado => el usuario firmo spender = address(this).
        //     El witness (tokenOut + minOut) lo RECALCULA el contrato: si el keeper pasara otros valores,
        //     la firma del usuario no validaria on-chain.
        bytes32 witness = keccak256(abi.encode(ORDER_INTENT_TYPEHASH, tokenOut, minOut));
        IPermit2(PERMIT2).permitWitnessTransferFrom(
            permit,
            IPermit2.SignatureTransferDetails({to: address(this), requestedAmount: amountIn}),
            orderOwner,
            witness,
            WITNESS_TYPE_STRING,
            permitSignature
        );

        //  2) Aprobar al router exacto y ejecutar el swap.
        _forceApprove(tokenIn, swapTarget, amountIn);
        (bool ok, bytes memory ret) = swapTarget.call(swapData);
        if (!ok) revert SwapFailed(ret);
        _forceApprove(tokenIn, swapTarget, 0);

        //  3) Devolver cualquier resto del tokenIn al usuario.
        uint256 leftover = IERC20Min(tokenIn).balanceOf(address(this));
        if (leftover > 0) IERC20Min(tokenIn).transfer(orderOwner, leftover);

        //  4) Verificar que el usuario recibio al menos minOut del tokenOut.
        uint256 outAfter = IERC20Min(tokenOut).balanceOf(orderOwner);
        uint256 received = outAfter > outBefore ? outAfter - outBefore : 0;
        if (received < minOut) revert InsufficientOutput(received, minOut);

        emit OrderExecuted(orderOwner, tokenIn, tokenOut, swapTarget, amountIn, received);
    }

    /**
     * @notice Ejecuta UNA parte de una orden DCA/TWAP (Permit2 AllowanceTransfer).
     * @dev La primera vez se registra el allowance firmado (permitSignature no vacia); despues basta
     *      con `transferFrom` hasta agotar `amount` o expirar. Cada parte se aprueba y consume exacta.
     */
    function executeDca(
        IPermit2Allowance.PermitSingle calldata permitSingle,
        bytes calldata permitSignature,
        address orderOwner,
        uint256 partAmount,
        address swapTarget,
        bytes calldata swapData,
        address tokenOut,
        uint256 minOut,
        DcaIntent calldata intent,
        bytes calldata intentSignature
    ) external onlyKeeper nonReentrant {
        if (!allowedTargets[swapTarget]) revert TargetNotAllowed(swapTarget);
        address tokenIn = permitSingle.details.token;

        //  Verifica la intencion firmada por el usuario (tokenOut + minRate + maxAmountIn + deadline).
        _verifyDcaIntent(orderOwner, tokenIn, tokenOut, partAmount, minOut, intent, intentSignature);

        uint256 outBefore = IERC20Min(tokenOut).balanceOf(orderOwner);

        //  Registra el allowance a partir de la firma (solo en la primera parte).
        if (permitSignature.length > 0) {
            IPermit2Allowance(PERMIT2).permit(orderOwner, permitSingle, permitSignature);
        }
        //  Tira de UNA parte del tokenIn (Permit2 descuenta del allowance firmado).
        IPermit2Allowance(PERMIT2).transferFrom(orderOwner, address(this), uint160(partAmount), tokenIn);

        _forceApprove(tokenIn, swapTarget, partAmount);
        (bool ok, bytes memory ret) = swapTarget.call(swapData);
        if (!ok) revert SwapFailed(ret);
        _forceApprove(tokenIn, swapTarget, 0);

        uint256 leftover = IERC20Min(tokenIn).balanceOf(address(this));
        if (leftover > 0) IERC20Min(tokenIn).transfer(orderOwner, leftover);

        uint256 outAfter = IERC20Min(tokenOut).balanceOf(orderOwner);
        uint256 received = outAfter > outBefore ? outAfter - outBefore : 0;
        if (received < minOut) revert InsufficientOutput(received, minOut);

        emit OrderExecuted(orderOwner, tokenIn, tokenOut, swapTarget, partAmount, received);
    }

    /// @dev Verifica la intencion firmada de DCA/GRID/COPY y que el minOut respete el precio firmado.
    function _verifyDcaIntent(
        address orderOwner,
        address tokenIn,
        address tokenOut,
        uint256 partAmount,
        uint256 minOut,
        DcaIntent calldata intent,
        bytes calldata intentSignature
    ) private view {
        if (intent.owner != orderOwner || intent.tokenIn != tokenIn || intent.tokenOut != tokenOut) revert BadIntent();
        if (block.timestamp > intent.deadline) revert IntentExpired();
        if (partAmount > intent.maxAmountIn) revert IntentAmountTooHigh();
        //  minOut >= partAmount * minRate / 1e18: el keeper no puede llenar por debajo del minimo firmado.
        if (minOut < (partAmount * intent.minRate) / 1e18) revert IntentRateTooLow();
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), _hashDcaIntent(intent)));
        if (!_verifyIntentSignature(orderOwner, digest, intentSignature)) revert BadIntentSignature();
    }

    function _domainSeparator() private view returns (bytes32) {
        return
            keccak256(
                abi.encode(EIP712_DOMAIN_TYPEHASH, EIP712_NAME_HASH, EIP712_VERSION_HASH, block.chainid, address(this))
            );
    }

    function _hashDcaIntent(DcaIntent calldata i) private pure returns (bytes32) {
        return
            keccak256(
                abi.encode(DCA_INTENT_TYPEHASH, i.owner, i.tokenIn, i.tokenOut, i.maxAmountIn, i.minRate, i.deadline)
            );
    }

    /// @dev ECDSA (EOA) o EIP-1271 (smart wallet / Safe).
    function _verifyIntentSignature(address signer, bytes32 digest, bytes calldata sig) private view returns (bool) {
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
            address rec = ecrecover(digest, v, r, s);
            return rec != address(0) && rec == signer;
        }
        (bool ok, bytes memory ret) = signer.staticcall(
            abi.encodeWithSelector(IERC1271_MIN.isValidSignature.selector, digest, sig)
        );
        return ok && ret.length >= 32 && abi.decode(ret, (bytes4)) == IERC1271_MIN.isValidSignature.selector;
    }

    /// @dev Aprueba con soporte para tokens tipo USDT (exige poner 0 antes).
    function _forceApprove(address token, address spender, uint256 amount) private {
        (bool ok0, ) = token.call(abi.encodeWithSelector(IERC20Min.approve.selector, spender, 0));
        ok0; // best-effort
        (bool ok1, bytes memory r) = token.call(abi.encodeWithSelector(IERC20Min.approve.selector, spender, amount));
        require(ok1 && (r.length == 0 || abi.decode(r, (bool))), "approve failed");
    }
}
