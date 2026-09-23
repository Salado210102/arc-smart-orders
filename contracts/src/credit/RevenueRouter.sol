// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC20Router {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IAgentCreditPool {
    function debtOf(address agent) external view returns (uint256);
    function repayOnBehalf(address agent, uint256 maxAmount) external returns (uint256 used);
}

interface IRevenueSplitter {
    function distribute(uint256 amount) external;
}

/// @title RevenueRouter — enforces the Phase-2 economic flow: **repay credit BEFORE splitting revenue**.
/// @notice An agent's USDC revenue is routed here: the router first clears the agent's outstanding
///         AgentCreditPool debt (`repayOnBehalf`), and only the remainder is forwarded to the
///         RevenueSplitter (70% stakers / 30% treasury). Atomic — the split can't happen before repayment.
contract RevenueRouter {
    IERC20Router public immutable usdc;
    address public pool; // AgentCreditPool
    address public splitter; // RevenueSplitter
    address public owner;

    event Routed(address indexed agent, uint256 amount, uint256 toPool, uint256 toSplitter);
    event ConfigUpdated(address pool, address splitter);
    event OwnershipTransferred(address indexed from, address indexed to);

    error NotOwner();
    error ZeroAmount();
    error BadConfig();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address usdc_, address pool_, address splitter_, address owner_) {
        if (usdc_ == address(0) || owner_ == address(0)) revert BadConfig();
        usdc = IERC20Router(usdc_);
        pool = pool_;
        splitter = splitter_;
        owner = owner_;
    }

    /// @notice Pull `amount` USDC from the caller (an agent/keeper), repay the agent's debt first,
    ///         then split the remainder.
    function route(address agent, uint256 amount) external {
        if (amount == 0) revert ZeroAmount();
        if (!usdc.transferFrom(msg.sender, address(this), amount)) revert TransferFailed();
        _route(agent, amount);
    }

    /// @notice Route the USDC already held by this router (e.g. after a receive()).
    function routeBalance(address agent) external {
        uint256 bal = usdc.balanceOf(address(this));
        if (bal == 0) revert ZeroAmount();
        _route(agent, bal);
    }

    function _route(address agent, uint256 amount) internal {
        uint256 used = 0;
        if (pool != address(0)) {
            uint256 debt = IAgentCreditPool(pool).debtOf(agent);
            if (debt > 0) {
                uint256 pay = debt < amount ? debt : amount;
                usdc.approve(pool, pay);
                used = IAgentCreditPool(pool).repayOnBehalf(agent, pay);
                usdc.approve(pool, 0); // reset leftover allowance
            }
        }

        uint256 rest = amount - used;
        if (rest > 0 && splitter != address(0)) {
            usdc.approve(splitter, rest);
            IRevenueSplitter(splitter).distribute(rest);
        } else if (rest > 0) {
            // no splitter configured -> return the remainder to the caller
            if (!usdc.transfer(msg.sender, rest)) revert TransferFailed();
        }

        emit Routed(agent, amount, used, rest);
    }

    function setConfig(address pool_, address splitter_) external onlyOwner {
        pool = pool_;
        splitter = splitter_;
        emit ConfigUpdated(pool_, splitter_);
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert BadConfig();
        emit OwnershipTransferred(owner, to);
        owner = to;
    }
}
