// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @title AgentCreditPool — DRAFT (NOT audited)
/// @notice Peer-to-contract micro-credit for AI agents on Arc: LPs deposit USDC to earn yield;
///         approved agents borrow micro-loans (e.g. $5–$50) to pay for API/gas, and auto-repay.
/// @dev This is a DESIGN SKELETON. Security-critical parts (risk model, liquidation, interest math)
///      are marked TODO and must be specified + audited before any mainnet use.
///
/// Model: $0 protocol capital (LPs fund), $0 marketing (B2B/B2Agent organic).
/// Fee: 15% performance fee on interest -> treasury (Safe).
contract AgentCreditPool {
    // ---- deps ----
    // USDC (ERC-20 interface, 6 dec) on Arc: 0x3600000000000000000000000000000000000000
    address public immutable usdc;

    // ---- roles (Safe in production) ----
    address public owner; // Safe
    address public treasury; // Safe — receives the performance fee
    address public riskManager; // allowlisted ops (can approve agents / pause)

    // ---- economics ----
    uint16 public constant MAX_PERFORMANCE_FEE_BPS = 3000; // hard cap 30%
    uint16 public performanceFeeBps = 1500; // 15% of interest -> treasury
    uint16 public interestBps = 200; // simple interest per loan term (draft: 2%)

    // ---- LP accounting (shares = pro-rata of pool NAV) ----
    uint256 public totalShares;
    mapping(address => uint256) public shares;
    uint256 public idle; // USDC available to lend
    uint256 public outstanding; // principal currently lent out
    uint256 public reserve; // first-loss buffer (funded by part of the fee)

    // ---- credit policy ----
    uint256 public minLoan = 5e6; // 5 USDC
    uint256 public maxLoan = 50e6; // 50 USDC
    uint64 public maxTerm = 7 days;
    uint256 public epochOutstandingCap; // max total principal outstanding per epoch (0 = unlimited)
    mapping(address => bool) public approvedAgent; // MVP risk gate (see docs)
    mapping(address => uint256) public agentOutstanding; // per-agent exposure

    struct Loan {
        address borrower;
        uint256 principal; // USDC lent
        uint256 owed; // principal + interest (recomputed at repay)
        uint64 dueAt;
        bool active;
    }
    Loan[] public loans;

    event Deposited(address indexed lp, uint256 amount, uint256 shares);
    event Withdrawn(address indexed lp, uint256 shares, uint256 amount);
    event AgentApproved(address indexed agent, bool ok);
    event Loaned(uint256 indexed loanId, address indexed agent, uint256 principal, uint64 dueAt);
    event Repaid(uint256 indexed loanId, address indexed agent, uint256 principal, uint256 interest, uint256 performanceFee);
    event PolicyUpdated(uint256 minLoan, uint256 maxLoan, uint64 maxTerm, uint256 epochCap);
    event Defaulted(uint256 indexed loanId, address indexed agent, uint256 lossBps);
    event OwnershipTransferred(address indexed from, address indexed to);

    error NotOwner();
    error NotRiskManager();
    error NotApprovedAgent();
    error ZeroAmount();
    error BadAmount();
    error InsufficientLiquidity();
    error NotActive();
    error NotDue();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }
    modifier onlyRisk() {
        if (msg.sender != riskManager && msg.sender != owner) revert NotRiskManager();
        _;
    }

    constructor(address usdc_, address owner_, address treasury_, address riskManager_) {
        require(usdc_ != address(0) && owner_ != address(0) && treasury_ != address(0), "zero");
        usdc = usdc_;
        owner = owner_;
        treasury = treasury_;
        riskManager = riskManager_;
    }

    // ============================================================ LP side
    /// @notice Deposit USDC to earn yield. TODO: ERC-4626-style share math with pending interest.
    function deposit(uint256 amount) external returns (uint256 minted) {
        if (amount == 0) revert ZeroAmount();
        // TODO: pull USDC, mint shares proportional to (idle + outstanding - reserve)
        revert("TODO: deposit");
    }

    /// @notice Withdraw by burning shares. TODO: respect that funds may be outstanding.
    function withdraw(uint256 shareAmount) external returns (uint256 amount) {
        // TODO: burn shares, transfer pro-rata, revert if not enough idle
        revert("TODO: withdraw");
    }

    // ============================================================ Borrow side
    /// @notice An approved AI agent requests a micro-loan. Draft: fixed interest per term.
    /// @dev MVP gate = `approvedAgent`. Post-ERC-8004: gate by on-chain identity/reputation.
    function requestLoan(uint256 amount, uint64 termSeconds) external returns (uint256 loanId) {
        if (!approvedAgent[msg.sender]) revert NotApprovedAgent();
        if (amount < minLoan || amount > maxLoan) revert BadAmount();
        if (termSeconds == 0 || termSeconds > maxTerm) revert BadAmount();
        if (amount > idle) revert InsufficientLiquidity();
        // TODO: epoch cap + per-agent cap + reserve checks
        revert("TODO: requestLoan");
    }

    /// @notice Repay principal + interest; 15% of the interest goes to treasury, rest to LPs.
    function repay(uint256 loanId) external {
        Loan storage l = loans[loanId];
        if (!l.active) revert NotActive();
        // TODO: compute interest, split performance fee -> treasury (+ reserve), return the rest to the pool
        revert("TODO: repay");
    }

    /// @notice Mark a loan as defaulted and socialize/recover the loss. TODO: bond/reputation slash.
    function markDefault(uint256 loanId) external onlyRisk {
        // TODO: use agent bond (if any) -> reserve -> LP loss; record for off-chain reputation
        revert("TODO: default");
    }

    // ============================================================ Admin (Safe)
    function setAgent(address agent, bool ok) external onlyRisk {
        approvedAgent[agent] = ok;
        emit AgentApproved(agent, ok);
    }

    function setPolicy(uint256 minLoan_, uint256 maxLoan_, uint64 maxTerm_, uint256 epochCap_)
        external
        onlyOwner
    {
        minLoan = minLoan_;
        maxLoan = maxLoan_;
        maxTerm = maxTerm_;
        epochOutstandingCap = epochCap_;
        emit PolicyUpdated(minLoan_, maxLoan_, maxTerm_, epochCap_);
    }

    function setFee(uint16 performanceFeeBps_, uint16 interestBps_) external onlyOwner {
        require(performanceFeeBps_ <= MAX_PERFORMANCE_FEE_BPS, "fee too high");
        performanceFeeBps = performanceFeeBps_;
        interestBps = interestBps_;
    }

    function transferOwnership(address to) external onlyOwner {
        require(to != address(0), "zero");
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    // ---- views ----
    function loanCount() external view returns (uint256) {
        return loans.length;
    }
}
