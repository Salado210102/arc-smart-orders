// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {IPriceOracle} from "../IPriceOracle.sol";
import {IYieldStrategy} from "../IYieldStrategy.sol";

/// @notice Test/dev price oracle: USD per BTC scaled 1e18 (default $60k). Set via `setPrice`.
contract MockPriceOracle is IPriceOracle {
    uint256 public price = 60_000e18;

    function setPrice(uint256 p) external {
        price = p;
    }

    function priceUsdPerBtc() external view returns (uint256) {
        return price;
    }
}

interface IERC20M {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @notice Test/dev yield strategy: simply holds the asset. Mint the asset to this address to simulate
///         fees/yield (totalAssets grows). A real CL position manager would replace it.
contract MockYieldStrategy is IYieldStrategy {
    IERC20M public immutable asset;

    constructor(address asset_) {
        asset = IERC20M(asset_);
    }

    function totalAssets() external view returns (uint256) {
        return asset.balanceOf(address(this));
    }

    function deploy(uint256 amount) external {
        require(asset.transferFrom(msg.sender, address(this), amount), "pull");
    }

    function recall(uint256 amount) external {
        require(asset.transfer(msg.sender, amount), "push");
    }
}
