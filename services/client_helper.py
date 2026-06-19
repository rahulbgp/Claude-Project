"""
Helper for connecting Claude agents to the MCP servers.
Builds the mcp_servers list used in client.messages.create() calls.
"""

from config import MCP_LOAN_RULES_URL, MCP_AUDIT_URL


def get_mcp_servers() -> list:
    """
    Return the mcp_servers configuration for Anthropic SDK calls.
    Claude can call MCP tools directly when these are passed in.
    """
    return [
        {
            "type": "url",
            "name": "loan-rules",
            "url": MCP_LOAN_RULES_URL,
        },
        {
            "type": "url",
            "name": "audit-db",
            "url": MCP_AUDIT_URL,
        },
    ]


def get_loan_rules_server() -> dict:
    """Return only the loan rules MCP server config."""
    return {
        "type": "url",
        "name": "loan-rules",
        "url": MCP_LOAN_RULES_URL,
    }
