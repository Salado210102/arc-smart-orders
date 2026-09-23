// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

interface IERC165 {
    function supportsInterface(bytes4 interfaceId) external view returns (bool);
}

/// @notice ERC-8183 Agentic Commerce (job escrow + evaluator attestation), ref impl on Arc testnet:
///         0x0747EEf0706327138c69792bF28Cd525089e4583
interface IAgenticCommerce {
    enum JobStatus {
        Open,
        Funded,
        Submitted,
        Completed,
        Rejected,
        Expired
    }

    struct Job {
        uint256 id;
        address client;
        address provider;
        address evaluator;
        string description;
        uint256 budget;
        uint256 expiredAt;
        JobStatus status;
        address hook;
    }

    function createJob(address provider, address evaluator, uint256 expiredAt, string calldata description, address hook)
        external
        returns (uint256 jobId);
    function setProvider(uint256 jobId, address provider) external;
    function setBudget(uint256 jobId, uint256 amount, bytes calldata optParams) external;
    function fund(uint256 jobId, bytes calldata optParams) external;
    function submit(uint256 jobId, bytes32 deliverable, bytes calldata optParams) external;
    function complete(uint256 jobId, bytes32 reason, bytes calldata optParams) external;
    function reject(uint256 jobId, bytes32 reason, bytes calldata optParams) external;
    function claimRefund(uint256 jobId) external;
    function getJob(uint256 jobId) external view returns (Job memory);
    function paymentToken() external view returns (address);
}

/// @notice Optional ERC-8183 hook. NOTE: ACP hooks must be WHITELISTED by the ACP admin
///         (`setHookWhitelist`), so a custom hook can only be used if approved. The default
///         (non-hooked) path needs no hook.
interface IACPHook is IERC165 {
    function beforeAction(uint256 jobId, bytes4 selector, bytes calldata data) external;
    function afterAction(uint256 jobId, bytes4 selector, bytes calldata data) external;
}
