// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {AgentToken} from "./AgentToken.sol";
import {AgentBondingCurve} from "./AgentBondingCurve.sol";

/// @notice Orchestrates an Agent launch: deploys the ERC-20 + USDC bonding curve, wires them,
///         registers the agent identity (ERC-8004) and hands ownership to the Safe.
/// @dev identity == address(0) skips ERC-8004 registration (e.g. local tests).
contract AgentFactory {
    address public immutable usdc;
    address public identity; // ERC-8004 IdentityRegistry (0 = skip)
    address public treasury; // protocol/Safe fee receiver
    address public owner; // Safe

    //  protocol defaults
    uint16 public feeBps = 100; // 1%
    uint16 public treasuryShareBps = 5000; // 50% of the fee to the protocol treasury
    uint16 public sniperFeeBps = 500; // 5% during the sniper window
    uint64 public sniperWindow = 30; // seconds

    event AgentCreated(
        address indexed token,
        address indexed curve,
        address indexed creator,
        uint256 supply,
        uint256 graduationUsdc,
        string metadataURI
    );
    event FeeDefaultsUpdated(uint16 feeBps, uint16 treasuryShareBps, uint16 sniperFeeBps, uint64 sniperWindow);
    event IdentityUpdated(address identity);
    event TreasuryUpdated(address treasury);

    error NotOwner();
    error ZeroAddress();
    error BadParams();
    error IdentityFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address usdc_, address identity_, address treasury_, address owner_) {
        if (usdc_ == address(0) || treasury_ == address(0) || owner_ == address(0)) revert ZeroAddress();
        usdc = usdc_;
        identity = identity_;
        treasury = treasury_;
        owner = owner_;
    }

    function launch(
        string calldata name_,
        string calldata symbol_,
        uint256 supply_, // = y0 (virtual token reserve)
        uint256 x0_, // virtual USDC reserve
        uint256 graduationUsdc_,
        uint256 maxWallet_,
        uint256 maxTx_,
        string calldata metadataURI_
    ) external returns (address tokenAddr, address curveAddr) {
        if (supply_ == 0 || x0_ == 0 || graduationUsdc_ == 0) revert BadParams();
        if (maxWallet_ != 0 && maxWallet_ < maxTx_) revert BadParams();

        //  Token: owner = this factory until the curve is wired, then -> Safe.
        AgentToken token = new AgentToken(name_, symbol_, supply_, address(this), maxWallet_, maxTx_);

        AgentBondingCurve curve = new AgentBondingCurve(
            usdc,
            address(token),
            x0_,
            supply_,
            graduationUsdc_,
            owner,
            treasury,
            msg.sender, // agent treasury = creator
            feeBps,
            treasuryShareBps,
            sniperFeeBps,
            sniperWindow
        );

        token.setCurve(address(curve));
        //  Move the whole supply into the curve (the factory minted it).
        require(token.transfer(address(curve), supply_), "supply_transfer_failed");
        token.transferOwnership(owner); // hand control to the Safe

        if (identity != address(0)) {
            (bool ok, ) = identity.call(abi.encodeWithSignature("register(string)", metadataURI_));
            if (!ok) revert IdentityFailed();
        }

        tokenAddr = address(token);
        curveAddr = address(curve);
        emit AgentCreated(tokenAddr, curveAddr, msg.sender, supply_, graduationUsdc_, metadataURI_);
    }

    //  ---- admin ----

    /// @dev Accept ERC-721 identity NFTs (ERC-8004 registers via safeMint to this factory).
    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return 0x150b7a02; // IERC721Receiver.onERC721Received.selector
    }

    function setFeeDefaults(uint16 feeBps_, uint16 treasuryShareBps_, uint16 sniperFeeBps_, uint64 sniperWindow_)
        external
        onlyOwner
    {
        require(feeBps_ <= 1000 && treasuryShareBps_ <= 10_000 && sniperFeeBps_ <= 2000, "bad_fee");
        feeBps = feeBps_;
        treasuryShareBps = treasuryShareBps_;
        sniperFeeBps = sniperFeeBps_;
        sniperWindow = sniperWindow_;
        emit FeeDefaultsUpdated(feeBps_, treasuryShareBps_, sniperFeeBps_, sniperWindow_);
    }

    function setIdentity(address identity_) external onlyOwner {
        identity = identity_;
        emit IdentityUpdated(identity_);
    }

    function setTreasury(address treasury_) external onlyOwner {
        if (treasury_ == address(0)) revert ZeroAddress();
        treasury = treasury_;
        emit TreasuryUpdated(treasury_);
    }
}
