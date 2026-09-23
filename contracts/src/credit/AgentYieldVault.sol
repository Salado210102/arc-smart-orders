// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {IYieldStrategy} from "./IYieldStrategy.sol";

interface IERC20V {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function decimals() external view returns (uint8);
}

/// @title AgentYieldVault — ERC-4626-style vault on **cirBTC** with a pluggable yield strategy.
/// @notice Depositors get shares of a cirBTC pool. Idle funds can be deployed into a strategy
///         (e.g. concentrated liquidity on Uniswap v4 / an Arc AMM) to earn fees; `totalAssets()`
///         tracks vault + strategy. Also serves as the yield/liquidity backstop for agent credit.
/// @dev DRAFT (not audited). Shares use the same decimals as the asset. No OZ dependency.
contract AgentYieldVault {
    IERC20V public immutable asset; // cirBTC
    IYieldStrategy public strategy;

    address public owner;
    address public manager; // keeper: deploy/recall

    string public name;
    string public symbol;
    uint8 public immutable decimals;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Deposit(address indexed caller, address indexed owner, uint256 assets, uint256 shares);
    event Withdraw(address indexed caller, address indexed receiver, address indexed owner, uint256 assets, uint256 shares);
    event StrategyUpdated(address strategy);
    event Deployed(uint256 amount);
    event Recalled(uint256 amount);
    event RolesUpdated(address owner, address manager);

    error NotOwner();
    error NotManager();
    error ZeroAmount();
    error BadParams();
    error Insufficient();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }
    modifier onlyManager() {
        if (msg.sender != manager && msg.sender != owner) revert NotManager();
        _;
    }

    constructor(address asset_, address owner_, string memory name_, string memory symbol_) {
        if (asset_ == address(0) || owner_ == address(0)) revert BadParams();
        asset = IERC20V(asset_);
        owner = owner_;
        manager = owner_;
        name = name_;
        symbol = symbol_;
        decimals = IERC20V(asset_).decimals();
    }

    // ------------------------------------------------------------- ERC-4626 views
    function totalAssets() public view returns (uint256) {
        uint256 bal = asset.balanceOf(address(this));
        if (address(strategy) != address(0)) bal += strategy.totalAssets();
        return bal;
    }

    function convertToShares(uint256 assets) public view returns (uint256) {
        uint256 ts = totalSupply;
        return ts == 0 ? assets : (assets * ts) / totalAssets();
    }

    function convertToAssets(uint256 shares) public view returns (uint256) {
        uint256 ts = totalSupply;
        return ts == 0 ? shares : (shares * totalAssets()) / ts;
    }

    function previewDeposit(uint256 assets) external view returns (uint256) {
        return convertToShares(assets);
    }

    function previewRedeem(uint256 shares) external view returns (uint256) {
        return convertToAssets(shares);
    }

    // ------------------------------------------------------------- ERC-20 share token
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _move(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        if (a != type(uint256).max) {
            if (a < amount) revert Insufficient();
            allowance[from][msg.sender] = a - amount;
        }
        _move(from, to, amount);
        return true;
    }

    function _move(address from, address to, uint256 amount) internal {
        if (to == address(0)) revert BadParams();
        if (balanceOf[from] < amount) revert Insufficient();
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }

    // ------------------------------------------------------------- ERC-4626 core
    function deposit(uint256 assets, address receiver) external returns (uint256 shares) {
        if (assets == 0) revert ZeroAmount();
        shares = convertToShares(assets);
        if (shares == 0) revert BadParams();

        totalSupply += shares;
        balanceOf[receiver] += shares;
        if (!asset.transferFrom(msg.sender, address(this), assets)) revert TransferFailed();

        emit Transfer(address(0), receiver, shares);
        emit Deposit(msg.sender, receiver, assets, shares);
    }

    function withdraw(uint256 assets, address receiver, address owner_) external returns (uint256 shares) {
        if (assets == 0) revert ZeroAmount();
        shares = convertToShares(assets);
        _burnAndPay(shares, assets, receiver, owner_);
    }

    function redeem(uint256 shares, address receiver, address owner_) external returns (uint256 assets) {
        if (shares == 0) revert ZeroAmount();
        assets = convertToAssets(shares);
        _burnAndPay(shares, assets, receiver, owner_);
    }

    function _burnAndPay(uint256 shares, uint256 assets, address receiver, address owner_) internal {
        if (msg.sender != owner_) {
            uint256 a = allowance[owner_][msg.sender];
            if (a < shares) revert Insufficient();
            if (a != type(uint256).max) allowance[owner_][msg.sender] = a - shares;
        }
        if (balanceOf[owner_] < shares) revert Insufficient();

        balanceOf[owner_] -= shares;
        totalSupply -= shares;

        // pull from strategy if the vault is short
        uint256 bal = asset.balanceOf(address(this));
        if (bal < assets && address(strategy) != address(0)) {
            uint256 need = assets - bal;
            uint256 st = strategy.totalAssets();
            strategy.recall(need > st ? st : need);
        }
        if (!asset.transfer(receiver, assets)) revert TransferFailed();

        emit Transfer(owner_, address(0), shares);
        emit Withdraw(msg.sender, receiver, owner_, assets, shares);
    }

    // ------------------------------------------------------------- strategy ops (manager)
    function setStrategy(address strategy_) external onlyOwner {
        strategy = IYieldStrategy(strategy_);
        emit StrategyUpdated(strategy_);
    }

    function deployToStrategy(uint256 amount) external onlyManager {
        if (amount == 0) revert ZeroAmount();
        asset.approve(address(strategy), amount);
        strategy.deploy(amount);
        emit Deployed(amount);
    }

    function recallFromStrategy(uint256 amount) external onlyManager {
        strategy.recall(amount);
        emit Recalled(amount);
    }

    function setRoles(address owner_, address manager_) external onlyOwner {
        require(owner_ != address(0), "owner=0");
        owner = owner_;
        manager = manager_;
        emit RolesUpdated(owner_, manager_);
    }
}
