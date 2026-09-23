// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC20Lock {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @notice Locks LP tokens for a beneficiary until a timestamp (anti-rug). LP can only be withdrawn
///         by the beneficiary after `unlockTime`. Owner (Safe) is informational only — no unlock.
contract LiquidityLocker {
    struct Lock {
        address lpToken;
        address beneficiary;
        uint256 amount;
        uint64 unlockTime;
        bool withdrawn;
    }

    address public owner;
    Lock[] public locks;
    mapping(address => uint256) public lockedBalance; // lpToken -> locked amount

    event Locked(uint256 indexed id, address indexed lpToken, address indexed beneficiary, uint256 amount, uint64 unlockTime);
    event Withdrawn(uint256 indexed id, address indexed to, uint256 amount);
    event OwnershipTransferred(address indexed previous, address indexed current);

    error ZeroAddress();
    error NotOwner();
    error UnlockInPast();
    error NotBeneficiary();
    error StillLocked();
    error AlreadyWithdrawn();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address owner_) {
        if (owner_ == address(0)) revert ZeroAddress();
        owner = owner_;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    /// @notice Locks `amount` of `lpToken` for `beneficiary` until `unlockTime`. Pulls from msg.sender.
    function lock(address lpToken, address beneficiary, uint256 amount, uint64 unlockTime)
        external
        returns (uint256 id)
    {
        if (lpToken == address(0) || beneficiary == address(0) || amount == 0) revert ZeroAddress();
        if (unlockTime <= block.timestamp) revert UnlockInPast();
        if (!IERC20Lock(lpToken).transferFrom(msg.sender, address(this), amount)) revert TransferFailed();

        locks.push(Lock(lpToken, beneficiary, amount, unlockTime, false));
        id = locks.length - 1;
        lockedBalance[lpToken] += amount;
        emit Locked(id, lpToken, beneficiary, amount, unlockTime);
    }

    function withdraw(uint256 id) external {
        Lock storage l = locks[id];
        if (l.withdrawn) revert AlreadyWithdrawn();
        if (msg.sender != l.beneficiary) revert NotBeneficiary();
        if (block.timestamp < l.unlockTime) revert StillLocked();

        l.withdrawn = true;
        lockedBalance[l.lpToken] -= l.amount;
        if (!IERC20Lock(l.lpToken).transfer(l.beneficiary, l.amount)) revert TransferFailed();
        emit Withdrawn(id, l.beneficiary, l.amount);
    }

    function lockCount() external view returns (uint256) {
        return locks.length;
    }
}
