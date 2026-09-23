// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {OrderExecutor, IPermit2, IPermit2Allowance, IERC20Min} from "../src/OrderExecutor.sol";

contract MockERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amt) external {
        balanceOf[to] += amt;
    }

    function approve(address s, uint256 a) external returns (bool) {
        allowance[msg.sender][s] = a;
        return true;
    }

    function transfer(address to, uint256 a) external returns (bool) {
        balanceOf[msg.sender] -= a;
        balanceOf[to] += a;
        return true;
    }

    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        allowance[f][msg.sender] -= a;
        balanceOf[f] -= a;
        balanceOf[t] += a;
        return true;
    }
}

contract MockPermit2 {
    function permitTransferFrom(
        IPermit2.PermitTransferFrom calldata permit,
        IPermit2.SignatureTransferDetails calldata details,
        address owner,
        bytes calldata
    ) external {
        MockERC20(permit.permitted.token).transferFrom(owner, details.to, details.requestedAmount);
    }

    //  Variante con witness (la que usa el ejecutor): el mock ignora el witness y solo mueve fondos.
    function permitWitnessTransferFrom(
        IPermit2.PermitTransferFrom calldata permit,
        IPermit2.SignatureTransferDetails calldata details,
        address owner,
        bytes32,
        string calldata,
        bytes calldata
    ) external {
        MockERC20(permit.permitted.token).transferFrom(owner, details.to, details.requestedAmount);
    }

    //  AllowanceTransfer (DCA/TWAP): permit() no-op en el mock; transferFrom mueve la parte.
    function permit(address, IPermit2Allowance.PermitSingle calldata, bytes calldata) external {}

    function transferFrom(address from, address to, uint160 amount, address token) external {
        MockERC20(token).transferFrom(from, to, amount);
    }
}

contract MockSwap {
    function swap(address tokenIn, uint256 amountIn, address tokenOut, address recipient, uint256 amountOut) external {
        MockERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn);
        MockERC20(tokenOut).transfer(recipient, amountOut);
    }
}

contract OrderExecutorTest is Test {
    OrderExecutor exec;
    MockERC20 tokenIn;
    MockERC20 tokenOut;
    MockSwap router;

    address constant SAFE = address(0x5AFE);
    address constant KEEPER = address(0xFEED);
    address constant TREASURY = address(0x7EA5);
    uint256 constant USER_PK = 0xA11CE;
    address USER;

    function setUp() public {
        USER = vm.addr(USER_PK);
        //  Permit2 mock en la direccion canonica.
        MockPermit2 p2 = new MockPermit2();
        vm.etch(0x000000000022D473030F116dDEE9F6B43aC78BA3, address(p2).code);

        tokenIn = new MockERC20();
        tokenOut = new MockERC20();
        router = new MockSwap();
        exec = new OrderExecutor(SAFE, KEEPER, address(0), TREASURY);
        vm.prank(SAFE);
        exec.setAllowedTarget(address(router), true);
        //  Fee a 0 por defecto en los tests base (los tests de fee lo suben).
        vm.prank(SAFE);
        exec.setFee(0, TREASURY);

        tokenIn.mint(USER, 1_000e6);
        tokenOut.mint(address(router), 1_000e18);
        vm.prank(USER);
        tokenIn.approve(0x000000000022D473030F116dDEE9F6B43aC78BA3, type(uint256).max);
    }

    function _permit(uint256 amount) internal view returns (IPermit2.PermitTransferFrom memory) {
        return IPermit2.PermitTransferFrom({
            permitted: IPermit2.TokenPermissions({token: address(tokenIn), amount: amount}),
            nonce: 1,
            deadline: block.timestamp + 1 hours
        });
    }

    //  ---- DcaIntent helpers (DCA/GRID/COPY) ----
    function _intent(uint256 maxAmountIn, uint256 minRate, address tokenOut_, uint256 deadline)
        internal
        view
        returns (OrderExecutor.DcaIntent memory it, bytes memory sig)
    {
        it = OrderExecutor.DcaIntent({
            owner: USER,
            tokenIn: address(tokenIn),
            tokenOut: tokenOut_,
            maxAmountIn: maxAmountIn,
            minRate: minRate,
            deadline: deadline
        });
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(USER_PK, _intentDigest(it));
        sig = abi.encodePacked(r, s, v);
    }

    function _intentDigest(OrderExecutor.DcaIntent memory it) internal view returns (bytes32) {
        bytes32 dom = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("ArcSmartOrders"),
                keccak256("1"),
                block.chainid,
                address(exec)
            )
        );
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256(
                    "DcaIntent(address owner,address tokenIn,address tokenOut,uint256 maxAmountIn,uint256 minRate,uint256 deadline)"
                ),
                it.owner,
                it.tokenIn,
                it.tokenOut,
                it.maxAmountIn,
                it.minRate,
                it.deadline
            )
        );
        return keccak256(abi.encodePacked(hex"1901", dom, structHash));
    }

    function test_executeOrder_pullYSwapAtomico() public {
        uint256 amountIn = 10e6;
        uint256 amountOut = 5e18;
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), amountIn, address(tokenOut), USER, amountOut));

        vm.prank(KEEPER);
        exec.executeOrder(_permit(amountIn), USER, "", address(router), data, address(tokenOut), amountOut);

        assertEq(tokenOut.balanceOf(USER), amountOut, "usuario recibe tokenOut");
        assertEq(tokenIn.balanceOf(USER), 1_000e6 - amountIn, "usuario paga tokenIn");
        assertEq(tokenIn.balanceOf(address(exec)), 0, "executor sin fondos en reposo");
        assertEq(tokenIn.allowance(address(exec), address(router)), 0, "aprobacion reseteada");
    }

    function test_targetNoAutorizado() public {
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), 1e6, address(tokenOut), USER, 1e18));
        vm.prank(KEEPER);
        vm.expectRevert(abi.encodeWithSelector(OrderExecutor.TargetNotAllowed.selector, address(0xBEEF)));
        exec.executeOrder(_permit(1e6), USER, "", address(0xBEEF), data, address(tokenOut), 1e18);
    }

    function test_soloKeeper() public {
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), 1e6, address(tokenOut), USER, 1e18));
        vm.prank(USER);
        vm.expectRevert(OrderExecutor.NotKeeper.selector);
        exec.executeOrder(_permit(1e6), USER, "", address(router), data, address(tokenOut), 1e18);
    }

    function test_executeDca_unaParte() public {
        uint256 partAmount = 5e6;
        uint256 amountOut = 2e18;
        IPermit2Allowance.PermitSingle memory ps = IPermit2Allowance.PermitSingle({
            details: IPermit2Allowance.PermitDetails({
                token: address(tokenIn),
                amount: 20e6,
                expiration: uint48(block.timestamp + 7 days),
                nonce: 1
            }),
            spender: address(exec),
            sigDeadline: block.timestamp + 1 hours
        });
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), partAmount, address(tokenOut), USER, amountOut));

        //  Intencion firmada (minRate justo = amountOut/partAmount) reutilizable en las 2 partes.
        uint256 minRate = (amountOut * 1e18) / partAmount;
        (OrderExecutor.DcaIntent memory it, bytes memory isig) =
            _intent(20e6, minRate, address(tokenOut), block.timestamp + 7 days);

        //  Primera parte con firma (registra allowance) y segunda parte sin firma (reusa allowance).
        vm.prank(KEEPER);
        exec.executeDca(ps, hex"01", USER, partAmount, address(router), data, address(tokenOut), amountOut, it, isig);
        vm.prank(KEEPER);
        exec.executeDca(ps, "", USER, partAmount, address(router), data, address(tokenOut), amountOut, it, isig);

        assertEq(tokenOut.balanceOf(USER), amountOut * 2, "recibe el output de las 2 partes");
        assertEq(tokenIn.balanceOf(USER), 1_000e6 - 2 * partAmount, "paga las 2 partes");
        assertEq(tokenIn.balanceOf(address(exec)), 0, "executor sin fondos en reposo");
    }

    function _dcaSetup(uint256 partAmount, uint256 amountOut)
        internal
        view
        returns (IPermit2Allowance.PermitSingle memory ps, bytes memory data)
    {
        ps = IPermit2Allowance.PermitSingle({
            details: IPermit2Allowance.PermitDetails({
                token: address(tokenIn),
                amount: 20e6,
                expiration: uint48(block.timestamp + 7 days),
                nonce: 1
            }),
            spender: address(exec),
            sigDeadline: block.timestamp + 1 hours
        });
        data = abi.encodeCall(MockSwap.swap, (address(tokenIn), partAmount, address(tokenOut), USER, amountOut));
    }

    function test_dcaIntent_tokenOutDistinto_revierte() public {
        uint256 partAmount = 5e6;
        uint256 amountOut = 2e18;
        (IPermit2Allowance.PermitSingle memory ps, bytes memory data) = _dcaSetup(partAmount, amountOut);
        //  Intencion firmada para OTRO tokenOut -> BadIntent.
        (OrderExecutor.DcaIntent memory it, bytes memory isig) =
            _intent(20e6, (amountOut * 1e18) / partAmount, address(0xBEEF), block.timestamp + 7 days);
        vm.prank(KEEPER);
        vm.expectRevert(OrderExecutor.BadIntent.selector);
        exec.executeDca(ps, hex"01", USER, partAmount, address(router), data, address(tokenOut), amountOut, it, isig);
    }

    function test_dcaIntent_minOutBajo_revierte() public {
        uint256 partAmount = 5e6;
        uint256 amountOut = 2e18;
        (IPermit2Allowance.PermitSingle memory ps, bytes memory data) = _dcaSetup(partAmount, amountOut);
        //  minRate exige el DOBLE de lo que el swap entrega -> IntentRateTooLow.
        (OrderExecutor.DcaIntent memory it, bytes memory isig) =
            _intent(20e6, (amountOut * 2 * 1e18) / partAmount, address(tokenOut), block.timestamp + 7 days);
        vm.prank(KEEPER);
        vm.expectRevert(OrderExecutor.IntentRateTooLow.selector);
        exec.executeDca(ps, hex"01", USER, partAmount, address(router), data, address(tokenOut), amountOut, it, isig);
    }

    function test_dcaIntent_firmaAjena_revierte() public {
        uint256 partAmount = 5e6;
        uint256 amountOut = 2e18;
        (IPermit2Allowance.PermitSingle memory ps, bytes memory data) = _dcaSetup(partAmount, amountOut);
        (OrderExecutor.DcaIntent memory it,) =
            _intent(20e6, (amountOut * 1e18) / partAmount, address(tokenOut), block.timestamp + 7 days);
        //  Firma con OTRA clave -> BadIntentSignature.
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xB0B, _intentDigest(it));
        vm.prank(KEEPER);
        vm.expectRevert(OrderExecutor.BadIntentSignature.selector);
        exec.executeDca(
            ps, hex"01", USER, partAmount, address(router), data, address(tokenOut), amountOut, it, abi.encodePacked(r, s, v)
        );
    }

    function test_dcaIntent_caducada_revierte() public {
        uint256 partAmount = 5e6;
        uint256 amountOut = 2e18;
        (IPermit2Allowance.PermitSingle memory ps, bytes memory data) = _dcaSetup(partAmount, amountOut);
        (OrderExecutor.DcaIntent memory it, bytes memory isig) =
            _intent(20e6, (amountOut * 1e18) / partAmount, address(tokenOut), block.timestamp - 1);
        vm.prank(KEEPER);
        vm.expectRevert(OrderExecutor.IntentExpired.selector);
        exec.executeDca(ps, hex"01", USER, partAmount, address(router), data, address(tokenOut), amountOut, it, isig);
    }

    function test_witnessTypehashCanonico() public {
        //  El typehash que Permit2 recalcula DEBE coincidir con la cadena canonica EIP-712
        //  (tipos referenciados ordenados alfabeticamente: OrderIntent < TokenPermissions).
        bytes32 expected = keccak256(
            "PermitWitnessTransferFrom(TokenPermissions permitted,address spender,uint256 nonce,uint256 deadline,OrderIntent witness)OrderIntent(address tokenOut,uint256 minOut)TokenPermissions(address token,uint256 amount)"
        );
        assertEq(
            keccak256(abi.encodePacked(exec.PERMIT2_WITNESS_STUB(), exec.WITNESS_TYPE_STRING())),
            expected,
            "witnessTypeString no canonico"
        );
    }

    function test_minOutRevierte() public {
        uint256 amountIn = 10e6;
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), amountIn, address(tokenOut), USER, 5e18));
        vm.prank(KEEPER);
        //  pedimos minOut mayor que lo que entrega el swap -> revierte (todo atomico, sin fondos movidos)
        vm.expectRevert(abi.encodeWithSelector(OrderExecutor.InsufficientOutput.selector, 5e18, 6e18));
        exec.executeOrder(_permit(amountIn), USER, "", address(router), data, address(tokenOut), 6e18);
    }

    function test_setKeeperSoloOwner() public {
        vm.prank(KEEPER);
        vm.expectRevert(OrderExecutor.NotOwner.selector);
        exec.setKeeper(KEEPER);
        vm.prank(SAFE);
        exec.setKeeper(address(0xBEEF));
        assertEq(exec.keeper(), address(0xBEEF));
    }

    //  ---- Fee (input-side) ----

    function test_fee_defaultEs30() public {
        OrderExecutor fresh = new OrderExecutor(SAFE, KEEPER, address(0), TREASURY);
        assertEq(fresh.feeBps(), 30, "default 30 bps");
        assertEq(fresh.feeRecipient(), TREASURY);
        OrderExecutor fresh2 = new OrderExecutor(SAFE, KEEPER, address(0), address(0));
        assertEq(fresh2.feeRecipient(), SAFE, "recipient 0 -> owner");
    }

    function test_setFee_soloOwner_yCap() public {
        vm.prank(KEEPER);
        vm.expectRevert(OrderExecutor.NotOwner.selector);
        exec.setFee(50, TREASURY);

        vm.prank(SAFE);
        vm.expectRevert(abi.encodeWithSelector(OrderExecutor.FeeTooHigh.selector, 1001));
        exec.setFee(1001, TREASURY);

        vm.prank(SAFE);
        exec.setFee(50, address(0xBEEF));
        assertEq(exec.feeBps(), 50);
        assertEq(exec.feeRecipient(), address(0xBEEF));
    }

    function test_feeOrder_inputSide() public {
        vm.prank(SAFE);
        exec.setFee(300, TREASURY); // 3%

        uint256 amountIn = 10e6;
        uint256 fee = (amountIn * 300) / 10_000; // 0.3e6
        uint256 swapAmount = amountIn - fee; // 9.7e6
        uint256 amountOut = 5e18;

        //  El keeper construye el swap para el importe NETO.
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), swapAmount, address(tokenOut), USER, amountOut));
        uint256 beforeIn = tokenIn.balanceOf(USER);

        vm.prank(KEEPER);
        exec.executeOrder(_permit(amountIn), USER, "", address(router), data, address(tokenOut), amountOut);

        assertEq(tokenIn.balanceOf(TREASURY), fee, "tesoreria recibe el fee en tokenIn");
        assertEq(beforeIn - tokenIn.balanceOf(USER), amountIn, "el usuario paga el bruto");
        assertEq(tokenOut.balanceOf(USER), amountOut, "el usuario recibe el output (minOut sobre el neto)");
        assertEq(tokenIn.balanceOf(address(exec)), 0, "executor sin fondos");
        assertEq(tokenIn.balanceOf(address(router)), swapAmount, "el router recibe el neto");
    }

    function test_feeOrder_sinRecipient_noCobra() public {
        vm.prank(SAFE);
        exec.setFee(300, address(0)); // sin recipient -> no cobra

        uint256 amountIn = 10e6;
        uint256 amountOut = 5e18;
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), amountIn, address(tokenOut), USER, amountOut));

        vm.prank(KEEPER);
        exec.executeOrder(_permit(amountIn), USER, "", address(router), data, address(tokenOut), amountOut);

        assertEq(tokenIn.balanceOf(TREASURY), 0, "sin fee");
        assertEq(tokenIn.balanceOf(address(router)), amountIn, "swap con el bruto completo");
    }

    function test_feeOrder_minOutNeto_revierte() public {
        vm.prank(SAFE);
        exec.setFee(300, TREASURY);

        uint256 amountIn = 10e6;
        uint256 fee = (amountIn * 300) / 10_000;
        uint256 swapAmount = amountIn - fee;
        //  El swap entrega 5e18, pero pedimos 6e18 -> revierte (fee ya retenido, todo atomico).
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), swapAmount, address(tokenOut), USER, 5e18));
        vm.prank(KEEPER);
        vm.expectRevert(abi.encodeWithSelector(OrderExecutor.InsufficientOutput.selector, 5e18, 6e18));
        exec.executeOrder(_permit(amountIn), USER, "", address(router), data, address(tokenOut), 6e18);
    }

    function test_feeDca_inputSide() public {
        vm.prank(SAFE);
        exec.setFee(300, TREASURY);

        uint256 partAmount = 5e6;
        uint256 fee = (partAmount * 300) / 10_000;
        uint256 swapAmount = partAmount - fee;
        uint256 amountOut = 2e18;

        (IPermit2Allowance.PermitSingle memory ps,) = _dcaSetup(partAmount, amountOut);
        bytes memory data = abi.encodeCall(MockSwap.swap, (address(tokenIn), swapAmount, address(tokenOut), USER, amountOut));
        uint256 minRate = (amountOut * 1e18) / partAmount; // required == amountOut
        (OrderExecutor.DcaIntent memory it, bytes memory isig) =
            _intent(20e6, minRate, address(tokenOut), block.timestamp + 7 days);

        vm.prank(KEEPER);
        exec.executeDca(ps, hex"01", USER, partAmount, address(router), data, address(tokenOut), amountOut, it, isig);

        assertEq(tokenIn.balanceOf(TREASURY), fee, "fee DCA en tokenIn");
        assertEq(tokenOut.balanceOf(USER), amountOut, "output DCA");
        assertEq(tokenIn.balanceOf(address(exec)), 0, "executor sin fondos");
    }
}
