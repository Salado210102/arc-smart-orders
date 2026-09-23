// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC20R {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IStakingVault {
    function notifyReward(uint256 amount) external;
}

/// @notice Receives the agent's USDC revenue and splits it between stakers (via the vault) and the
///         protocol treasury. Pulls USDC from the caller (approve this contract first).
contract RevenueSplitter {
    IERC20R public immutable usdc;
    address public vault; // AgentStakingVault (stakers)
    address public treasury; // protocol/Safe
    uint16 public stakerShareBps; // e.g. 7000 = 70% to stakers
    address public owner;

    event Distributed(uint256 amount, uint256 toStakers, uint256 toTreasury);
    event ConfigUpdated(address vault, address treasury, uint16 stakerShareBps);
    event OwnershipTransferred(address indexed previous, address indexed current);

    error NotOwner();
    error ZeroAmount();
    error BadConfig();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address usdc_, address vault_, address treasury_, uint16 stakerShareBps_, address owner_) {
        if (usdc_ == address(0) || owner_ == address(0)) revert BadConfig();
        if (vault_ == address(0) || treasury_ == address(0) || stakerShareBps_ > 10_000) revert BadConfig();
        usdc = IERC20R(usdc_);
        vault = vault_;
        treasury = treasury_;
        stakerShareBps = stakerShareBps_;
        owner = owner_;
    }

    /// @notice Pulls `amount` USDC from the caller and distributes it.
    function distribute(uint256 amount) external {
        if (amount == 0) revert ZeroAmount();
        if (!usdc.transferFrom(msg.sender, address(this), amount)) revert TransferFailed();

        uint256 toStakers = (amount * stakerShareBps) / 10_000;
        uint256 toTreasury = amount - toStakers;

        if (toStakers > 0) {
            usdc.approve(vault, toStakers); // vault pulls it via notifyReward
            IStakingVault(vault).notifyReward(toStakers);
        }
        if (toTreasury > 0) {
            if (!usdc.transfer(treasury, toTreasury)) revert TransferFailed();
        }
        emit Distributed(amount, toStakers, toTreasury);
    }

    /// @notice Distributes the USDC already held by this contract.
    function distributeBalance() external {
        uint256 bal = usdc.balanceOf(address(this));
        if (bal == 0) revert ZeroAmount();
        uint256 toStakers = (bal * stakerShareBps) / 10_000;
        uint256 toTreasury = bal - toStakers;
        if (toStakers > 0) {
            usdc.approve(vault, toStakers);
            IStakingVault(vault).notifyReward(toStakers);
        }
        if (toTreasury > 0) {
            if (!usdc.transfer(treasury, toTreasury)) revert TransferFailed();
        }
        emit Distributed(bal, toStakers, toTreasury);
    }

    function setConfig(address vault_, address treasury_, uint16 stakerShareBps_) external onlyOwner {
        if (vault_ == address(0) || treasury_ == address(0) || stakerShareBps_ > 10_000) revert BadConfig();
        vault = vault_;
        treasury = treasury_;
        stakerShareBps = stakerShareBps_;
        emit ConfigUpdated(vault_, treasury_, stakerShareBps_);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert BadConfig();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
