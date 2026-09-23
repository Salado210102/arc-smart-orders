"""arc-agent-treasury — treasury & micro-credit client for AI agents on Arc.

    from arc_agent_treasury import AgentTreasuryClient

    tr = AgentTreasuryClient(
        rpc_url="https://rpc.mainnet.arc.io",
        pool_address="0x...AgentCreditPool",
        agent_address="0x...myAgent",
        private_key=os.environ["AGENT_PK"],
    )
    tx = tr.ensure_credit(amount_usdc=10, term_seconds=86_400)  # borrow 10 USDC if low
"""
from .client import AgentTreasuryClient, LoanTerms, USDC

# Backward-compatible alias (earlier drafts used `ArcAgentTreasury`).
ArcAgentTreasury = AgentTreasuryClient

__all__ = ["AgentTreasuryClient", "ArcAgentTreasury", "LoanTerms", "USDC"]
