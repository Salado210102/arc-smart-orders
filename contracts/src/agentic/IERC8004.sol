// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @notice Minimal interfaces for the ERC-8004 registries deployed on Arc.
///         Arc testnet:
///           IdentityRegistry   0x8004A818BFB912233c491871b3d84c89A494BD9e
///           ReputationRegistry 0x8004B663056A597Dffe9eCcC1965A193B7388713
///           ValidationRegistry 0x8004Cb1BF31DAf7788923b405b754f57acEB4272
interface IIdentityRegistry {
    /// @dev Mints an identity NFT for the agent; ownerOf(tokenId) is the agent owner.
    ///      The tokenId (agentId) is found via the Transfer event (register returns nothing).
    function register(string calldata metadataURI) external;
    function ownerOf(uint256 agentId) external view returns (address);
    function tokenURI(uint256 agentId) external view returns (string memory);
}

interface IReputationRegistry {
    /// @dev Per ERC-8004, the agent OWNER cannot record reputation for its own agent (anti self-dealing).
    function giveFeedback(
        uint256 agentId,
        int128 score,
        uint8 feedbackType,
        string calldata tag,
        string calldata evidenceURI,
        string calldata context,
        string calldata extra,
        bytes32 feedbackHash
    ) external;
}

interface IValidationRegistry {
    function validationRequest(address validator, uint256 agentId, string calldata requestURI, bytes32 requestHash)
        external;
    function validationResponse(
        bytes32 requestHash,
        uint8 response,
        string calldata responseURI,
        bytes32 responseHash,
        string calldata tag
    ) external;
    function getValidationStatus(bytes32 requestHash)
        external
        view
        returns (address validator, uint256 agentId, uint8 response, bytes32 responseHash, string memory tag, uint256 lastUpdate);
}
