// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "../../src/interfaces/IArcIntel.sol";
import "../../src/ArcIntelExecutor.sol";

contract MockERC20 {
    string public name;
    uint8 public decimals = 18;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory n) {
        name = n;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "bal");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "bal");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @dev Pulls tokens and records the witness so tests can assert what was signed.
contract MockPermit2 {
    bytes32 public lastWitness;
    address public lastOwner;
    uint256 public lastAmount;

    function permitWitnessTransferFrom(
        IPermit2.PermitTransferFrom calldata permit,
        IPermit2.SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes32 witness,
        string calldata,
        bytes calldata
    ) external {
        lastWitness = witness;
        lastOwner = owner;
        lastAmount = permit.permitted.amount;
        MockERC20(permit.permitted.token).transferFrom(owner, transferDetails.to, transferDetails.requestedAmount);
    }
}

/// @dev Simulates just enough of the v4 PoolManager: unlock callback, swap delta, take/sync/settle.
///      `rate` emulates price/hook tax; `partialBps` emulates a partial fill (< 10000).
contract MockPoolManager {
    uint256 public rate = 1e18; // out = consumed * rate / 1e18
    uint256 public partialBps = 10_000; // fraction of amountIn actually consumed
    address public syncedCurrency;
    uint256 public syncedBalance;

    bool public lastZeroForOne;
    int256 public lastAmountSpecified;
    uint160 public lastLimit;

    address public swapHook;
    bool public strictSettle;

    error CurrencyNotSettled();

    function setRate(uint256 r) external {
        rate = r;
    }

    function setPartialBps(uint256 b) external {
        partialBps = b;
    }

    function setSwapHook(address h) external {
        swapHook = h;
    }

    /// @dev Emulates v4 flash accounting: settle() reverts if nothing was actually paid.
    function setStrictSettle(bool s) external {
        strictSettle = s;
    }

    function unlock(bytes calldata data) external returns (bytes memory) {
        return IUnlockCallback(msg.sender).unlockCallback(data);
    }

    function swap(IPoolManager.PoolKey memory, IPoolManager.SwapParams memory params, bytes calldata)
        external
        virtual
        returns (int256)
    {
        lastZeroForOne = params.zeroForOne;
        lastAmountSpecified = params.amountSpecified;
        lastLimit = params.sqrtPriceLimitX96;

        // emulates a v4 beforeSwap hook running inside the swap
        if (swapHook != address(0)) ISwapHook(swapHook).onSwap();

        uint256 amountIn = uint256(-params.amountSpecified);
        uint256 consumed = (amountIn * partialBps) / 10_000;
        uint256 out = (consumed * rate) / 1e18;
        if (params.zeroForOne) {
            return _pack(int128(-int256(consumed)), int128(int256(out)));
        } else {
            return _pack(int128(int256(out)), int128(-int256(consumed)));
        }
    }

    function take(address currency, address to, uint256 amount) external {
        MockERC20(currency).transfer(to, amount);
    }

    function sync(address currency) external {
        syncedCurrency = currency;
        syncedBalance = MockERC20(currency).balanceOf(address(this));
    }

    function settle() external payable returns (uint256 paid) {
        uint256 bal = MockERC20(syncedCurrency).balanceOf(address(this));
        paid = bal - syncedBalance;
        if (strictSettle && paid == 0) revert CurrencyNotSettled();
    }

    //  Mirrors v4 BalanceDelta: amount0 in the UPPER 128 bits, amount1 in the LOWER 128 bits.
    function _pack(int128 a0, int128 a1) internal pure returns (int256) {
        return int256((uint256(uint128(a0)) << 128) | uint256(uint128(a1)));
    }
}

/// @dev Pool manager whose swap reverts (e.g. a hostile/reverting hook). Used to assert atomicity.
contract RevertingPoolManager is MockPoolManager {
    function swap(IPoolManager.PoolKey memory, IPoolManager.SwapParams memory, bytes calldata)
        external
        override
        returns (int256)
    {
        revert("swap failed");
    }
}

/// @dev Malicious pool manager that tries to re-enter `execute` during the swap callback.
contract ReentrantPoolManager is MockPoolManager {
    address public target;

    function setTarget(address t) external {
        target = t;
    }

    function swap(IPoolManager.PoolKey memory, IPoolManager.SwapParams memory, bytes calldata)
        external
        override
        returns (int256)
    {
        IPoolManager.PoolKey memory k = IPoolManager.PoolKey(address(0), address(0), 0, 0, address(0));
        ArcIntelExecutor.Order memory o = ArcIntelExecutor.Order(k, false, 0, address(0), 0, 0);
        IPermit2.PermitTransferFrom memory p =
            IPermit2.PermitTransferFrom(IPermit2.TokenPermissions(address(0), 0), 0, 0);
        ArcIntelExecutor(target).execute(p, address(this), o, "");
        return 0; // unreachable if the reentrancy guard works
    }
}

interface ISwapHook {
    function onSwap() external;
}

interface IERC20From {
    function transferFrom(address, address, uint256) external returns (bool);
}

/// @dev ERC20 that returns `false` on transfer() WITHOUT reverting and does not move tokens —
///      exactly the case Slither's unchecked-transfer detector warns about.
contract FalseTransferERC20 {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address, uint256) external pure returns (bool) {
        return false; // silently "succeeds"
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "bal");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @dev ERC20 that ENFORCES allowance on transferFrom (so a malicious hook cannot move the
///      recipient's tokens without an approval).
contract StrictERC20 {
    string public name;
    uint8 public constant decimals = 18;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory n) {
        name = n;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "bal");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "bal");
        require(allowance[from][msg.sender] >= amount, "allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @dev Hook that, during the swap, (1) tries to re-enter `execute` and (2) tries to move the
///      recipient's output out. Both must fail (nonReentrant / no allowance).
contract MaliciousHook {
    ArcIntelExecutor public immutable target;
    address public immutable tokenOut;
    address public immutable recipient;
    bool public reentryBlocked;
    bool public stealFailed;

    constructor(address t, address tokenOut_, address recipient_) {
        target = ArcIntelExecutor(t);
        tokenOut = tokenOut_;
        recipient = recipient_;
    }

    function onSwap() external {
        IPoolManager.PoolKey memory k = IPoolManager.PoolKey(address(0), address(0), 0, 0, address(0));
        ArcIntelExecutor.Order memory o = ArcIntelExecutor.Order(k, false, 0, address(0), 0, 0);
        IPermit2.PermitTransferFrom memory p =
            IPermit2.PermitTransferFrom(IPermit2.TokenPermissions(address(0), 0), 0, 0);

        try target.execute(p, address(this), o, "") {
            // reentry succeeded (bad)
        } catch {
            reentryBlocked = true;
        }
        try IERC20From(tokenOut).transferFrom(recipient, address(this), 1) {
            // drain succeeded (bad)
        } catch {
            stealFailed = true;
        }
    }
}
