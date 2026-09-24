// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {ArcMorphoLiquidator} from "../src/mev/ArcMorphoLiquidator.sol";

/// @notice Deploy ArcMorphoLiquidator with owner = Safe.
/// Env: MORPHO, USDC, SWAP_ROUTER, OWNER (Safe), MAX_FLASH_USDC (optional; default 5 for a pilot).
/// The script reverts if MORPHO/SWAP_ROUTER have no code or OWNER is not a contract (Safe).
contract DeployMorphoLiquidator is Script {
    function run() external {
        address morpho = vm.envAddress("MORPHO");
        address usdc = vm.envAddress("USDC");
        address router = vm.envAddress("SWAP_ROUTER");
        address owner = vm.envAddress("OWNER");
        uint256 maxFlashUsdc = vm.envOr("MAX_FLASH_USDC", uint256(5));

        require(morpho.code.length > 0, "MORPHO has no code");
        require(router.code.length > 0, "SWAP_ROUTER has no code");
        require(owner.code.length > 0, "OWNER must be a contract (Safe)");

        vm.startBroadcast();
        ArcMorphoLiquidator keeper = new ArcMorphoLiquidator(morpho, usdc, router, owner);
        if (maxFlashUsdc > 0) keeper.setMaxFlashAmount(maxFlashUsdc * 1e6); // USDC 6 dec
        vm.stopBroadcast();

        console2.log("ArcMorphoLiquidator:", address(keeper));
        console2.log("morpho          :", morpho);
        console2.log("usdc            :", usdc);
        console2.log("swapRouter      :", router);
        console2.log("owner (Safe)    :", owner);
        console2.log("maxFlashAmount  :", keeper.maxFlashAmount());
    }
}
