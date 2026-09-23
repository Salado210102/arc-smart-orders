// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {AgentToken} from "./AgentToken.sol";

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @notice USDC bonding curve (constant product with virtual reserves) for an Agent token.
///         k = x*y ; price = x/y (USDC per token). Buys add real USDC to the reserve, sells remove it.
///         Fees are taken in USDC and split between the protocol treasury and the agent treasury.
///         Graduates (stops trading) once the raised USDC reaches `graduationUsdc`.
contract AgentBondingCurve {
    IERC20 public immutable usdc;
    AgentToken public immutable token;

    uint256 public immutable x0; // virtual USDC reserve (6 dec)
    uint256 public immutable y0; // virtual token reserve (= totalSupply)
    uint256 public immutable k; // x0 * y0

    uint256 public x; // current virtual USDC reserve
    uint256 public y; // current virtual token reserve

    uint16 public feeBps; // curve fee (e.g. 100 = 1%)
    uint16 public treasuryShareBps; // share of the fee to the protocol treasury
    uint16 public sniperFeeBps; // higher fee during the sniper window
    uint64 public immutable launchTs;
    uint64 public sniperWindow; // seconds

    uint256 public graduationUsdc; // raised-USDC threshold
    bool public graduated;

    address public owner;
    address public treasury; // protocol/Safe
    address public agentTreasury; // agent ops (creator)

    event Bought(address indexed buyer, uint256 usdcIn, uint256 fee, uint256 tokensOut);
    event Sold(address indexed seller, uint256 tokensIn, uint256 usdcOut, uint256 fee);
    event FeeDistributed(uint256 toTreasury, uint256 toAgent);
    event Graduated(uint256 raisedUsdc, uint256 tokensSold);
    event FeeUpdated(uint16 feeBps, uint16 treasuryShareBps, uint16 sniperFeeBps);
    event AgentTreasuryUpdated(address agentTreasury);
    event GraduationUsdcUpdated(uint256 graduationUsdc);

    error NotOwner();
    error TradingDisabled();
    error Slippage();
    error CurveEmpty();
    error ZeroAmount();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(
        address usdc_,
        address token_,
        uint256 x0_,
        uint256 y0_,
        uint256 graduationUsdc_,
        address owner_,
        address treasury_,
        address agentTreasury_,
        uint16 feeBps_,
        uint16 treasuryShareBps_,
        uint16 sniperFeeBps_,
        uint64 sniperWindow_
    ) {
        usdc = IERC20(usdc_);
        token = AgentToken(token_);
        x0 = x0_;
        y0 = y0_;
        k = x0_ * y0_;
        x = x0_;
        y = y0_;
        graduationUsdc = graduationUsdc_;
        owner = owner_;
        treasury = treasury_;
        agentTreasury = agentTreasury_;
        feeBps = feeBps_;
        treasuryShareBps = treasuryShareBps_;
        sniperFeeBps = sniperFeeBps_;
        sniperWindow = sniperWindow_;
        launchTs = uint64(block.timestamp);
    }

    //  ---- views ----

    /// @notice Price in USDC (6 dec) per 1 token base unit (18 dec) * 1e18, i.e. price scaled by 1e18.
    function price() public view returns (uint256) {
        return (x * 1e18) / y;
    }

    function raisedUsdc() public view returns (uint256) {
        return x - x0;
    }

    function buyQuote(uint256 usdcIn) public view returns (uint256 tokensOut, uint256 fee) {
        uint256 effBps = _effFeeBps();
        fee = (usdcIn * effBps) / 10_000;
        uint256 netU = usdcIn - fee;
        tokensOut = y - (k / (x + netU));
    }

    function sellQuote(uint256 tokensIn) public view returns (uint256 usdcOut, uint256 fee, uint256 gross) {
        gross = x - (k / (y + tokensIn));
        uint256 effBps = _effFeeBps();
        fee = (gross * effBps) / 10_000;
        usdcOut = gross - fee;
    }

    //  ---- trading ----

    function buy(uint256 usdcIn, uint256 minTokensOut) external returns (uint256 tokensOut) {
        if (graduated) revert TradingDisabled();
        if (usdcIn == 0) revert ZeroAmount();

        uint256 effBps = _effFeeBps();
        uint256 fee = (usdcIn * effBps) / 10_000;
        uint256 netU = usdcIn - fee;

        tokensOut = y - (k / (x + netU));
        if (tokensOut == 0 || tokensOut >= y) revert CurveEmpty();
        if (tokensOut < minTokensOut) revert Slippage();

        x = x + netU;
        y = y - tokensOut;

        if (!usdc.transferFrom(msg.sender, address(this), usdcIn)) revert TransferFailed();
        _distributeFee(fee);
        if (!token.transfer(msg.sender, tokensOut)) revert TransferFailed();

        emit Bought(msg.sender, usdcIn, fee, tokensOut);

        if (raisedUsdc() >= graduationUsdc) {
            graduated = true;
            emit Graduated(raisedUsdc(), y0 - y);
        }
    }

    function sell(uint256 tokensIn, uint256 minUsdcOut) external returns (uint256 usdcOut) {
        if (graduated) revert TradingDisabled();
        if (tokensIn == 0) revert ZeroAmount();

        uint256 gross = x - (k / (y + tokensIn));
        uint256 effBps = _effFeeBps();
        uint256 fee = (gross * effBps) / 10_000;
        usdcOut = gross - fee;
        if (usdcOut < minUsdcOut) revert Slippage();
        if (usdcOut >= x) revert CurveEmpty(); // cannot drain the virtual reserve

        if (!token.transferFrom(msg.sender, address(this), tokensIn)) revert TransferFailed();

        x = x - gross;
        y = y + tokensIn;

        _distributeFee(fee);
        if (!usdc.transfer(msg.sender, usdcOut)) revert TransferFailed();

        emit Sold(msg.sender, tokensIn, usdcOut, fee);
    }

    //  ---- internal ----

    function _effFeeBps() internal view returns (uint256) {
        return block.timestamp < launchTs + sniperWindow ? sniperFeeBps : feeBps;
    }

    function _distributeFee(uint256 fee) internal {
        if (fee == 0) return;
        uint256 toTreasury = (fee * treasuryShareBps) / 10_000;
        uint256 toAgent = fee - toTreasury;
        if (toTreasury > 0 && !usdc.transfer(treasury, toTreasury)) revert TransferFailed();
        if (toAgent > 0 && !usdc.transfer(agentTreasury, toAgent)) revert TransferFailed();
        emit FeeDistributed(toTreasury, toAgent);
    }

    //  ---- admin (owner = Safe in production) ----

    function setFee(uint16 feeBps_, uint16 treasuryShareBps_, uint16 sniperFeeBps_) external onlyOwner {
        require(feeBps_ <= 1000 && treasuryShareBps_ <= 10_000 && sniperFeeBps_ <= 2000, "bad_fee");
        feeBps = feeBps_;
        treasuryShareBps = treasuryShareBps_;
        sniperFeeBps = sniperFeeBps_;
        emit FeeUpdated(feeBps_, treasuryShareBps_, sniperFeeBps_);
    }

    function setAgentTreasury(address agentTreasury_) external onlyOwner {
        agentTreasury = agentTreasury_;
        emit AgentTreasuryUpdated(agentTreasury_);
    }

    function setGraduationUsdc(uint256 graduationUsdc_) external onlyOwner {
        graduationUsdc = graduationUsdc_;
        emit GraduationUsdcUpdated(graduationUsdc_);
    }
}
