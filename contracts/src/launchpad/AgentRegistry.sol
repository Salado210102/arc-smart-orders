// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @notice On-chain index of launched agents: agentId <-> AgentToken <-> curve <-> creator.
contract AgentRegistry {
    struct Agent {
        uint256 agentId; // ERC-8004 identity (0 if not registered)
        address token; // AgentToken
        address curve; // AgentBondingCurve
        address creator;
        string metadataURI;
        uint64 createdAt;
    }

    Agent[] private _agents;
    mapping(address => uint256) public tokenIndex; // token -> index + 1

    address public owner;
    address public factory;

    event AgentRegistered(
        uint256 indexed agentId,
        address indexed token,
        address indexed curve,
        address creator,
        string metadataURI
    );
    event FactoryUpdated(address factory);

    error NotOwner();
    error NotFactory();
    error AlreadyRegistered();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }
    modifier onlyFactory() {
        if (msg.sender != factory) revert NotFactory();
        _;
    }

    constructor(address owner_) {
        owner = owner_;
        factory = owner_; // set to the real factory right after deploy
    }

    function setFactory(address factory_) external onlyOwner {
        factory = factory_;
        emit FactoryUpdated(factory_);
    }

    function register(uint256 agentId, address token, address curve, address creator, string calldata metadataURI)
        external
        onlyFactory
        returns (uint256 index)
    {
        if (tokenIndex[token] != 0) revert AlreadyRegistered();
        _agents.push(Agent(agentId, token, curve, creator, metadataURI, uint64(block.timestamp)));
        index = _agents.length - 1;
        tokenIndex[token] = index + 1;
        emit AgentRegistered(agentId, token, curve, creator, metadataURI);
    }

    function count() external view returns (uint256) {
        return _agents.length;
    }

    function agentAt(uint256 index) external view returns (Agent memory) {
        return _agents[index];
    }

    function all() external view returns (Agent[] memory) {
        return _agents;
    }

    function byToken(address token) external view returns (Agent memory) {
        return _agents[tokenIndex[token] - 1];
    }
}
