// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {ArcMorphoLiquidator} from "../src/mev/ArcMorphoLiquidator.sol";

/// @notice Deploy ArcMorphoLiquidator with owner = Safe and a low-privilege keeper hot key.
/// Env: MORPHO, USDC, SWAP_ROUTER, OWNER (Safe), KEEPER (hot key), MAX_FLASH_USDC (optional; default 5).
/// The script reverts if MORPHO/SWAP_ROUTER have no code or OWNER is not a contract (Safe).
contract DeployMorphoLiquidator is Script {
    function run() external {
        address morpho = vm.envAddress("MORPHO");
        address usdc = vm.envAddress("USDC");
        address router = vm.envAddress("SWAP_ROUTER");
        address owner = vm.envAddress("OWNER");
        address keeperHot = vm.envAddress("KEEPER");
        uint256 maxFlashUsdc = vm.envOr("MAX_FLASH_USDC", uint256(5));

        require(morpho.code.length > 0, "MORPHO has no code");
        require(router.code.length > 0, "SWAP_ROUTER has no code");
        require(owner.code.length > 0, "OWNER must be a contract (Safe)");

        vm.startBroadcast();
        ArcMorphoLiquidator keeper = new ArcMorphoLiquidator(morpho, usdc, router, owner, keeperHot);
        vm.stopBroadcast();

        console2.log("ArcMorphoLiquidator:", address(keeper));
        console2.log("morpho          :", morpho);
        console2.log("usdc            :", usdc);
        console2.log("swapRouter      :", router);
        console2.log("owner (Safe)    :", owner);
        console2.log("keeper          :", keeperHot);
        if (maxFlashUsdc > 0) {
            uint256 cap = maxFlashUsdc * 1e6; // USDC 6 dec
            if (owner.code.length == 0) {
                // owner is an EOA (deployer) -> set the cap directly
                vm.startBroadcast();
                keeper.setMaxFlashAmount(cap);
                vm.stopBroadcast();
                console2.log("maxFlashAmount  :", keeper.maxFlashAmount());
            } else {
                // owner is a contract (Safe) -> the Safe must execute setMaxFlashAmount(cap)
                console2.log("owner is a contract (Safe): execute this via the Safe:");
                console2.logBytes(abi.encodeWithSignature("setMaxFlashAmount(uint256)", cap));
            }
        }
    }
}
