// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC20Like {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @notice Router de PRUEBA para Arc: cambia USDC<->EURC a una tasa fija (6 decimales).
/// @dev Solo testnet/local. En produccion se sustituye por el venue real (App Kit Swap / router),
///      que se autoriza en el OrderExecutor vía `setAllowedTarget`. La firma `swap(...)` imita la
///      calldata que el keeper construye off-chain.
contract MockStableRouter {
    IERC20Like public immutable usdc;
    IERC20Like public immutable eurc;
    //  EURC out per USDC in, escalado 1e18 (p.ej. 0.92e18 = 0.92 EURC por 1 USDC).
    uint256 public rateEurcPerUsdc = 0.92e18;

    error PairNotSupported();
    error MinOut();

    constructor(address usdc_, address eurc_) {
        usdc = IERC20Like(usdc_);
        eurc = IERC20Like(eurc_);
    }

    function setRate(uint256 r) external {
        rateEurcPerUsdc = r;
    }

    /// @param tokenIn  debe ser USDC (ERC-20, 6 dec)
    /// @param tokenOut debe ser EURC (6 dec)
    /// @param minOut   minimo que debe recibir `recipient` (lo valida tambien el OrderExecutor)
    function swap(address tokenIn, uint256 amountIn, address tokenOut, address recipient, uint256 minOut)
        external
        returns (uint256 out)
    {
        if (tokenIn != address(usdc) || tokenOut != address(eurc)) revert PairNotSupported();
        require(usdc.transferFrom(msg.sender, address(this), amountIn), "PULL");
        out = (amountIn * rateEurcPerUsdc) / 1e18;
        if (out < minOut) revert MinOut();
        require(eurc.transfer(recipient, out), "SEND");
    }
}
