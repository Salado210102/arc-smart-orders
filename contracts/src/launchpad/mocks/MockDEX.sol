// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC20Dex {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @notice Minimal AMM + LP token for tests. `addLiquidity` pulls both tokens and mints LP = amountA.
///         The contract itself is the LP token (ERC-20), so it can be locked in a LiquidityLocker.
contract MockDEX {
    string public name = "Mock LP Token";
    string public symbol = "MLP";
    uint8 public decimals = 18;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event LiquidityAdded(address indexed tokenA, address indexed tokenB, uint256 amountA, uint256 amountB, uint256 lp);

    function lpToken() external view returns (address) {
        return address(this);
    }

    function addLiquidity(address tokenA, address tokenB, uint256 amountA, uint256 amountB, address to)
        external
        returns (uint256 lpAmount)
    {
        require(IERC20Dex(tokenA).transferFrom(msg.sender, address(this), amountA), "pull A");
        require(IERC20Dex(tokenB).transferFrom(msg.sender, address(this), amountB), "pull B");
        lpAmount = amountA; // 1:1 on the agent token for simplicity
        balanceOf[to] += lpAmount;
        totalSupply += lpAmount;
        emit Transfer(address(0), to, lpAmount);
        emit LiquidityAdded(tokenA, tokenB, amountA, amountB, lpAmount);
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
        require(a >= amount, "allowance");
        if (a != type(uint256).max) allowance[from][msg.sender] = a - amount;
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) private {
        require(balanceOf[from] >= amount, "balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}
