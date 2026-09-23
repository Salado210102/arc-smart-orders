// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @title AgentCreditPool — invite-only USDC micro-credit for AI agents on Arc
/// @notice LPs (whitelisted) deposit USDC to earn yield; approved agents take short micro-loans
///         ($5–$50) to pay for API/gas, ideally auto-repaid from an ERC-8183 job escrow.
/// @dev MVP design (audit pending):
///      - INVITE-ONLY: both LPs and agents are whitelisted (no public deposit/borrow).
///      - HYBRID collateral: a small USDC bond + (off-chain) ERC-8004 reputation / slashing.
///      - Interest: FLAT per loan (`interestBps`), split into a 15% performance fee -> treasury,
///        a slice -> first-loss reserve, the rest -> LPs.
///      - Caps: per-agent, per-epoch, and a max utilization so LPs can always withdraw.
///      - Pause: blocks deposit/loan; withdraw/repay always work.
///      - Auto-repay: `keeper` (or anyone) can settle a loan via `repayFrom` once ERC-8183 pays out.
contract AgentCreditPool {
    // --------------------------------------------------------------------- deps
    interface IERC20 {
        function transfer(address to, uint256 amount) external returns (bool);
        function transferFrom(address from, address to, uint256 amount) external returns (bool);
        function balanceOf(address account) external view returns (uint256);
    }

    IERC20 public immutable usdc; // Arc ERC-20 (6 dec): 0x3600...0000

    // --------------------------------------------------------------------- roles
    address public owner; // Safe
    address public treasury; // Safe — performance fee
    address public riskManager; // whitelisting / defaults / pause
    address public keeper; // ERC-8183 auto-repay

    bool public paused;

    // --------------------------------------------------------------------- fees (caps are constants)
    uint16 public constant MAX_PERFORMANCE_FEE_BPS = 3000; // 30%
    uint16 public constant MAX_INTEREST_BPS = 2000; // 20% flat per loan
    uint16 public constant MAX_RESERVE_BPS = 3000; // 30% of interest -> reserve

    uint16 public performanceFeeBps = 1500; // 15% of interest -> treasury
    uint16 public interestBps = 100; // 1% flat interest per loan
    uint16 public reserveShareBps = 2000; // 20% of interest -> first-loss reserve

    // --------------------------------------------------------------------- LP accounting
    uint256 public totalShares;
    mapping(address => uint256) public shares;
    uint256 public idle; // USDC available to lend / withdraw (excludes reserve + bonds)
    uint256 public outstanding; // principal currently lent
    uint256 public reserve; // first-loss buffer (USDC held by the pool, not LP-owned)

    // --------------------------------------------------------------------- whitelist
    mapping(address => bool) public approvedLP;
    mapping(address => bool) public approvedAgent;

    // --------------------------------------------------------------------- policy
    uint256 public minLoan = 5e6; // 5 USDC
    uint256 public maxLoan = 50e6; // 50 USDC
    uint64 public maxTerm = 7 days;
    uint256 public maxPerAgent = 50e6; // max principal outstanding per agent
    uint256 public epochCap = 500e6; // max principal originated per epoch
    uint64 public epochDuration = 1 days;
    uint64 public epochStart;
    uint256 public epochOutstanding;
    uint16 public maxUtilizationBps = 8000; // 80% of TVL can be outstanding

    // --------------------------------------------------------------------- hybrid bond
    uint256 public minBond = 10e6; // 10 USDC required to borrow
    mapping(address => uint256) public bond;

    // --------------------------------------------------------------------- loans
    struct Loan {
        address borrower;
        uint256 principal;
        uint64 dueAt;
        bool active;
        bool defaulted;
    }
    Loan[] public loans;
    mapping(address => uint256) public agentOutstanding;
    mapping(address => uint256[]) internal agentLoans; // loan ids per agent (for repayOnBehalf)

    uint256 private _locked;

    // --------------------------------------------------------------------- events
    event Deposited(address indexed lp, uint256 amount, uint256 mintedShares);
    event Withdrawn(address indexed lp, uint256 amount, uint256 burnedShares);
    event Whitelisted(address indexed who, bool isLP, bool ok);
    event BondDeposited(address indexed agent, uint256 amount);
    event BondWithdrawn(address indexed agent, uint256 amount);
    event Loaned(uint256 indexed loanId, address indexed agent, uint256 principal, uint64 dueAt);
    event Repaid(
        uint256 indexed loanId, address indexed payer, address indexed agent, uint256 principal, uint256 interest, uint256 performanceFee, uint256 toReserve
    );
    event Defaulted(uint256 indexed loanId, address indexed agent, uint256 principal, uint256 bondSlashed, uint256 reserveUsed, uint256 lpLoss);
    event PolicyUpdated(uint256 minLoan, uint256 maxLoan, uint64 maxTerm, uint256 maxPerAgent, uint256 epochCap, uint64 epochDuration, uint16 maxUtilizationBps);
    event FeesUpdated(uint16 performanceFeeBps, uint16 interestBps, uint16 reserveShareBps);
    event PausedSet(bool paused);
    event RolesUpdated(address riskManager, address keeper);
    event OwnershipTransferred(address indexed from, address indexed to);

    // --------------------------------------------------------------------- errors
    error NotOwner();
    error NotRisk();
    error NotWhitelistedLP();
    error NotWhitelistedAgent();
    error ZeroAmount();
    error BadParams();
    error Paused();
    error InsufficientLiquidity();
    error UtilizationTooHigh();
    error EpochCapExceeded();
    error AgentCapExceeded();
    error BondTooLow();
    error NoActiveLoan();
    error HasActiveLoans();
    error NotDue();
    error TransferFailed();
    error Reentrancy();

    // --------------------------------------------------------------------- modifiers
    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }
    modifier onlyRisk() {
        if (msg.sender != riskManager && msg.sender != owner) revert NotRisk();
        _;
    }
    modifier nonReentrant() {
        if (_locked) revert Reentrancy();
        _locked = true;
        _;
        _locked = false;
    }

    constructor(address usdc_, address owner_, address treasury_, address riskManager_) {
        if (usdc_ == address(0) || owner_ == address(0) || treasury_ == address(0)) revert BadParams();
        usdc = IERC20(usdc_);
        owner = owner_;
        treasury = treasury_;
        riskManager = riskManager_;
        epochStart = uint64(block.timestamp);
    }

    // ===================================================================== views
    /// @notice LP net asset value = idle + outstanding principal (excludes reserve + agent bonds).
    function poolAssets() public view returns (uint256) {
        return idle + outstanding;
    }

    /// @notice Value of one share (scaled 1e18). Returns 1e18 when empty.
    function sharePrice() public view returns (uint256) {
        return totalShares == 0 ? 1e18 : (poolAssets() * 1e18) / totalShares;
    }

    function loanCount() external view returns (uint256) {
        return loans.length;
    }

    /// @notice Interest owed on a loan if repaid now (flat per-loan).
    function pendingInterest(uint256 loanId) public view returns (uint256) {
        Loan storage l = loans[loanId];
        return (l.principal * interestBps) / 10_000;
    }

    function currentEpochOutstanding() public view returns (uint256) {
        if (block.timestamp >= epochStart + epochDuration) return 0; // resets next write
        return epochOutstanding;
    }

    /// @notice Total (principal + interest) this agent would need to repay to clear its active loans.
    function debtOf(address agent) public view returns (uint256 total) {
        uint256[] storage ids = agentLoans[agent];
        for (uint256 i = 0; i < ids.length; i++) {
            Loan storage l = loans[ids[i]];
            if (l.active) total += l.principal + (l.principal * interestBps) / 10_000;
        }
    }

    // ===================================================================== LP side
    function deposit(uint256 amount) external nonReentrant returns (uint256 mintedShares) {
        if (paused) revert Paused();
        if (!approvedLP[msg.sender]) revert NotWhitelistedLP();
        if (amount == 0) revert ZeroAmount();

        uint256 assets = poolAssets();
        mintedShares = totalShares == 0 ? amount : (amount * totalShares) / assets;
        if (mintedShares == 0) revert BadParams();

        totalShares += mintedShares;
        shares[msg.sender] += mintedShares;
        idle += amount;

        if (!usdc.transferFrom(msg.sender, address(this), amount)) revert TransferFailed();
        emit Deposited(msg.sender, amount, mintedShares);
    }

    function withdraw(uint256 shareAmount) external nonReentrant returns (uint256 amount) {
        if (shareAmount == 0) revert ZeroAmount();
        if (shares[msg.sender] < shareAmount) revert BadParams();

        amount = (shareAmount * poolAssets()) / totalShares;
        if (amount > idle) revert InsufficientLiquidity(); // funds are lent out

        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        idle -= amount;

        if (!usdc.transfer(msg.sender, amount)) revert TransferFailed();
        emit Withdrawn(msg.sender, amount, shareAmount);
    }

    // ===================================================================== bond
    function depositBond(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        bond[msg.sender] += amount;
        if (!usdc.transferFrom(msg.sender, address(this), amount)) revert TransferFailed();
        emit BondDeposited(msg.sender, amount);
    }

    function withdrawBond(uint256 amount) external nonReentrant {
        if (agentOutstanding[msg.sender] != 0) revert HasActiveLoans();
        if (amount == 0 || amount > bond[msg.sender]) revert BadParams();
        bond[msg.sender] -= amount;
        if (!usdc.transfer(msg.sender, amount)) revert TransferFailed();
        emit BondWithdrawn(msg.sender, amount);
    }

    // ===================================================================== borrow side
    function requestLoan(uint256 amount, uint64 termSeconds) external nonReentrant returns (uint256 loanId) {
        if (paused) revert Paused();
        if (!approvedAgent[msg.sender]) revert NotWhitelistedAgent();
        if (bond[msg.sender] < minBond) revert BondTooLow();
        if (amount < minLoan || amount > maxLoan) revert BadParams();
        if (termSeconds == 0 || termSeconds > maxTerm) revert BadParams();
        if (amount > idle) revert InsufficientLiquidity();

        _touchEpoch();
        if (epochOutstanding + amount > epochCap) revert EpochCapExceeded();
        if (agentOutstanding[msg.sender] + amount > maxPerAgent) revert AgentCapExceeded();

        uint256 tvl = poolAssets();
        if (outstanding + amount > (tvl * maxUtilizationBps) / 10_000) revert UtilizationTooHigh();

        loanId = loans.length;
        loans.push(Loan({ borrower: msg.sender, principal: amount, dueAt: uint64(block.timestamp) + termSeconds, active: true, defaulted: false }));
        agentLoans[msg.sender].push(loanId);

        outstanding += amount;
        idle -= amount;
        agentOutstanding[msg.sender] += amount;
        epochOutstanding += amount;

        if (!usdc.transfer(msg.sender, amount)) revert TransferFailed();
        emit Loaned(loanId, msg.sender, amount, uint64(block.timestamp) + termSeconds);
    }

    /// @notice Repay pulling USDC from the borrower (they must have approved the pool).
    function repay(uint256 loanId) external nonReentrant {
        _settle(loanId, loans[loanId].borrower);
    }

    /// @notice Repay pulling USDC from msg.sender — for the keeper / ERC-8183 escrow auto-repay.
    function repayFrom(uint256 loanId) external nonReentrant {
        _settle(loanId, msg.sender);
    }

    /// @notice Repay an agent's active loans from msg.sender's funds (used by the RevenueRouter / keeper
    ///         to GUARANTEE debt is settled BEFORE revenue is split). Settles whole loans in order while
    ///         `maxAmount` allows; returns the amount actually used.
    function repayOnBehalf(address agent, uint256 maxAmount) external nonReentrant returns (uint256 used) {
        uint256[] storage ids = agentLoans[agent];
        for (uint256 i = 0; i < ids.length && used < maxAmount; i++) {
            Loan storage l = loans[ids[i]];
            if (!l.active) continue;
            uint256 owed = l.principal + (l.principal * interestBps) / 10_000;
            if (used + owed > maxAmount) continue; // cannot fully settle this loan with the funds available
            _settle(ids[i], msg.sender);
            used += owed;
        }
    }

    function _settle(uint256 loanId, address payer) internal {
        Loan storage l = loans[loanId];
        if (!l.active) revert NoActiveLoan();

        uint256 principal = l.principal;
        uint256 interest = (principal * interestBps) / 10_000;
        uint256 owed = principal + interest;
        uint256 perf = (interest * performanceFeeBps) / 10_000;
        uint256 toReserve = (interest * reserveShareBps) / 10_000;
        uint256 toLPs = principal + interest - perf - toReserve;

        l.active = false;
        outstanding -= principal;
        agentOutstanding[l.borrower] -= principal;

        idle += toLPs;
        reserve += toReserve;

        if (!usdc.transferFrom(payer, address(this), owed)) revert TransferFailed();
        if (perf > 0 && !usdc.transfer(treasury, perf)) revert TransferFailed();

        emit Repaid(loanId, payer, l.borrower, principal, interest, perf, toReserve);
    }

    /// @notice Mark a loan as defaulted: slash the agent's bond, use the reserve to cover the rest,
    ///         and socialize any remaining loss to LPs (NAV drops). ERC-8004 reputation is slashed off-chain.
    function markDefault(uint256 loanId) external onlyRisk nonReentrant {
        Loan storage l = loans[loanId];
        if (!l.active) revert NoActiveLoan();
        if (block.timestamp < l.dueAt) revert NotDue(); // only after due (or via risk override below)

        address b = l.borrower;
        uint256 principal = l.principal;

        // 1) slash the bond toward the principal
        uint256 slashed = bond[b] >= principal ? principal : bond[b];
        bond[b] -= slashed;
        idle += slashed;

        // 2) first-loss reserve covers the remainder
        uint256 loss = principal - slashed;
        uint256 reserveUsed = 0;
        if (loss > 0) {
            reserveUsed = reserve >= loss ? loss : reserve;
            reserve -= reserveUsed;
            idle += reserveUsed;
            loss -= reserveUsed;
        }

        l.active = false;
        l.defaulted = true;
        outstanding -= principal;
        agentOutstanding[b] -= principal;

        emit Defaulted(loanId, b, principal, slashed, reserveUsed, loss);
    }

    // ===================================================================== admin
    function setPaused(bool p) external onlyRisk {
        paused = p;
        emit PausedSet(p);
    }

    /// @notice Emergency stop. Blocks deposit/loan; withdraw/repay always work.
    function pause() external onlyRisk {
        paused = true;
        emit PausedSet(true);
    }

    function unpause() external onlyRisk {
        paused = false;
        emit PausedSet(false);
    }

    function setLP(address who, bool ok) external onlyRisk {
        approvedLP[who] = ok;
        emit Whitelisted(who, true, ok);
    }

    function setAgent(address who, bool ok) external onlyRisk {
        approvedAgent[who] = ok;
        emit Whitelisted(who, false, ok);
    }

    function setPolicy(
        uint256 minLoan_,
        uint256 maxLoan_,
        uint64 maxTerm_,
        uint256 maxPerAgent_,
        uint256 epochCap_,
        uint64 epochDuration_,
        uint16 maxUtilizationBps_
    ) external onlyOwner {
        if (minLoan_ == 0 || maxLoan_ < minLoan_ || maxTerm_ == 0) revert BadParams();
        if (maxPerAgent_ < maxLoan_ || maxUtilizationBps_ > 10_000 || epochDuration_ == 0) revert BadParams();
        minLoan = minLoan_;
        maxLoan = maxLoan_;
        maxTerm = maxTerm_;
        maxPerAgent = maxPerAgent_;
        epochCap = epochCap_;
        epochDuration = epochDuration_;
        maxUtilizationBps = maxUtilizationBps_;
        emit PolicyUpdated(minLoan_, maxLoan_, maxTerm_, maxPerAgent_, epochCap_, epochDuration_, maxUtilizationBps_);
    }

    function setFees(uint16 performanceFeeBps_, uint16 interestBps_, uint16 reserveShareBps_) external onlyOwner {
        if (performanceFeeBps_ > MAX_PERFORMANCE_FEE_BPS || interestBps_ > MAX_INTEREST_BPS || reserveShareBps_ > MAX_RESERVE_BPS) {
            revert BadParams();
        }
        performanceFeeBps = performanceFeeBps_;
        interestBps = interestBps_;
        reserveShareBps = reserveShareBps_;
        emit FeesUpdated(performanceFeeBps_, interestBps_, reserveShareBps_);
    }

    function setBondMin(uint256 minBond_) external onlyOwner {
        minBond = minBond_;
    }

    function setRoles(address riskManager_, address keeper_) external onlyOwner {
        riskManager = riskManager_;
        keeper = keeper_;
        emit RolesUpdated(riskManager_, keeper_);
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert BadParams();
        emit OwnershipTransferred(owner, to);
        owner = to;
    }

    // ===================================================================== internal
    function _touchEpoch() internal {
        if (block.timestamp >= epochStart + epochDuration) {
            epochStart = uint64(block.timestamp);
            epochOutstanding = 0;
        }
    }
}
