// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @title IPriceOracle — minimal price oracle interface for cirBTC/USDC collateral.
/// @notice Returns the USD price of **1 BTC** scaled by 1e18 (e.g. 60000e18 for $60k).
///         A real feed (Pyth / Chainlink) can be wrapped to implement this; `MockPriceOracle`
///         is used in tests. No public oracle address is assumed — the owner wires one via config.
interface IPriceOracle {
    function priceUsdPerBtc() external view returns (uint256);
}
