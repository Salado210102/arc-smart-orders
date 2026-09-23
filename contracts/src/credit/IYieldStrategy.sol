// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @title IYieldStrategy — pluggable deployment target for `AgentYieldVault`.
/// @notice The vault holds cirBTC; a strategy (e.g. a Uniswap v4 / Arc AMM concentrated-liquidity
///         position manager) can deploy idle funds to earn fees. No public AMM exists on Arc yet, so a
///         `MockYieldStrategy` is used until a real venue is wired.
interface IYieldStrategy {
    /// @return the cirBTC base units (asset) currently managed by the strategy
    function totalAssets() external view returns (uint256);

    /// @notice deploy `amount` of the asset from the vault into the strategy
    function deploy(uint256 amount) external;

    /// @notice return `amount` of the asset from the strategy to the vault
    function recall(uint256 amount) external;
}
