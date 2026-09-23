// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @notice Minimal ERC-20 for an Agent token: fixed supply, no mint, no tax, no proxy.
///         Enforces max-wallet / max-tx while the bonding curve is active (anti-sniper).
/// @dev The whole supply is minted to the bonding curve; the curve is exempt from limits.
contract AgentToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    address public owner;
    address public curve; // bonding curve (exempt from limits)
    mapping(address => bool) public exempt; // addresses exempt from the limits (curve, module, owner)
    uint256 public maxWallet; // base units; 0 = no limit
    uint256 public maxTx; // base units; 0 = no limit
    bool public limitsActive = true;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event LimitsUpdated(uint256 maxWallet, uint256 maxTx, bool active);
    event CurveSet(address curve);
    event OwnershipTransferred(address indexed previous, address indexed current);

    error NotOwner();
    error ZeroAddress();
    error MaxWalletExceeded();
    error MaxTxExceeded();
    error InsufficientBalance();
    error InsufficientAllowance();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(string memory name_, string memory symbol_, uint256 supply_, address owner_, uint256 maxWallet_, uint256 maxTx_) {
        if (owner_ == address(0)) revert ZeroAddress();
        name = name_;
        symbol = symbol_;
        owner = owner_;
        maxWallet = maxWallet_;
        maxTx = maxTx_;
        totalSupply = supply_;
        balanceOf[msg.sender] = supply_; // minted to the deployer (the curve)
        exempt[owner_] = true;
        emit Transfer(address(0), msg.sender, supply_);
    }

    /// @notice The curve must be set once so it is exempt from the limits.
    function setCurve(address curve_) external onlyOwner {
        if (curve_ == address(0)) revert ZeroAddress();
        curve = curve_;
        exempt[curve_] = true;
        emit CurveSet(curve_);
    }

    function setExempt(address account, bool isExempt) external onlyOwner {
        exempt[account] = isExempt;
    }

    function setLimits(uint256 maxWallet_, uint256 maxTx_, bool active_) external onlyOwner {
        maxWallet = maxWallet_;
        maxTx = maxTx_;
        limitsActive = active_;
        emit LimitsUpdated(maxWallet_, maxTx_, active_);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        if (a < amount) revert InsufficientAllowance();
        if (a != type(uint256).max) allowance[from][msg.sender] = a - amount;
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) private {
        if (to == address(0)) revert ZeroAddress();
        if (balanceOf[from] < amount) revert InsufficientBalance();
        //  Anti-sniper limits only while the curve is active and not yet graduated.
        if (limitsActive && !_curveGraduated()) {
            if (!exempt[to] && maxWallet > 0 && balanceOf[to] + amount > maxWallet) revert MaxWalletExceeded();
            if (!exempt[from] && maxTx > 0 && amount > maxTx) revert MaxTxExceeded();
        }
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }

    /// @dev True once the bonding curve has graduated (limits are lifted -> DEX trading).
    function _curveGraduated() private view returns (bool) {
        if (curve == address(0)) return false;
        (bool ok, bytes memory ret) = curve.staticcall(abi.encodeWithSignature("graduated()"));
        return ok && ret.length >= 32 && abi.decode(ret, (bool));
    }
}
