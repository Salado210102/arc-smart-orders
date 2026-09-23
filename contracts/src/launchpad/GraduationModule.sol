// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {LiquidityLocker} from "./LiquidityLocker.sol";

interface IERC20G {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IDEX {
    /// @notice Adds liquidity for the pair and mints LP to `to`. Returns the LP amount minted.
    function addLiquidity(address tokenA, address tokenB, uint256 amountA, uint256 amountB, address to)
        external
        returns (uint256 lpAmount);
    function lpToken() external view returns (address);
}

interface ICurveGrad {
    function pullForGraduation(address to) external;
}

/// @notice On graduation: pulls the raised USDC + remaining tokens from the curve, adds the initial
///         liquidity to a DEX, and locks the resulting LP in a LiquidityLocker (anti-rug).
contract GraduationModule {
    address public owner;
    address public immutable usdc;
    address public dex;
    address public locker;
    uint64 public lockSeconds; // LP lock duration from graduation

    mapping(address => bool) public graduated; // curve -> done

    event Graduated(
        address indexed token,
        address indexed curve,
        address lpToken,
        uint256 lpAmount,
        address beneficiary,
        uint64 unlockAt
    );
    event ConfigUpdated(address dex, address locker, uint64 lockSeconds);
    event OwnershipTransferred(address indexed previous, address indexed current);

    error NotOwner();
    error ZeroAddress();
    error AlreadyGraduated();
    error NoLiquidity();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address owner_, address usdc_, address dex_, address locker_, uint64 lockSeconds_) {
        if (owner_ == address(0) || usdc_ == address(0) || dex_ == address(0) || locker_ == address(0)) revert ZeroAddress();
        owner = owner_;
        usdc = usdc_;
        dex = dex_;
        locker = locker_;
        lockSeconds = lockSeconds_;
    }

    function setConfig(address dex_, address locker_, uint64 lockSeconds_) external onlyOwner {
        if (dex_ == address(0) || locker_ == address(0)) revert ZeroAddress();
        dex = dex_;
        locker = locker_;
        lockSeconds = lockSeconds_;
        emit ConfigUpdated(dex_, locker_, lockSeconds_);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    /// @notice Permissionless: anyone can trigger graduation once the curve flags `graduated`.
    /// @param beneficiary the entity that can withdraw the LP after the lock (usually the creator).
    function graduate(address token, address curve, address beneficiary)
        external
        returns (address lpToken, uint256 lpAmount)
    {
        if (graduated[curve]) revert AlreadyGraduated();
        graduated[curve] = true;

        //  Pull the curve's real USDC + remaining tokens into this module.
        ICurveGrad(curve).pullForGraduation(address(this));

        uint256 tokAmt = IERC20G(token).balanceOf(address(this));
        uint256 usdcAmt = IERC20G(usdc).balanceOf(address(this));
        if (tokAmt == 0 || usdcAmt == 0) revert NoLiquidity();

        IERC20G(token).approve(dex, 0);
        IERC20G(token).approve(dex, tokAmt);
        IERC20G(usdc).approve(dex, 0);
        IERC20G(usdc).approve(dex, usdcAmt);

        lpAmount = IDEX(dex).addLiquidity(token, usdc, tokAmt, usdcAmt, address(this));
        lpToken = IDEX(dex).lpToken();

        IERC20G(lpToken).approve(locker, 0);
        IERC20G(lpToken).approve(locker, lpAmount);
        uint64 unlockAt = uint64(block.timestamp) + lockSeconds;
        LiquidityLocker(locker).lock(lpToken, beneficiary, lpAmount, unlockAt);

        emit Graduated(token, curve, lpToken, lpAmount, beneficiary, unlockAt);
    }
}
