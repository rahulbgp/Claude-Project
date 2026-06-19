"""
Context window management for multi-turn agent conversations.

Implements:
- Summary memory: keeps a compressed summary of older history
- Recent prompt window: always retains the last N prompts verbatim
- Token budget: trims content to stay within a max token estimate

Strategy (per capstone Step 8):
  - Summary: ≤12-15% of the total context corpus
  - Recent prompts: last 8-10 messages kept verbatim
  - Everything between summary and recent window is discarded after
    the summary is generated.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Approximate tokens: 1 token ≈ 4 chars
CHARS_PER_TOKEN = 4

# Context window budget (conservative — leave room for tools and response)
MAX_CONTEXT_TOKENS = 60_000

# Max % of context budget to use for summary
SUMMARY_BUDGET_RATIO = 0.13  # 13% — within the 12-15% requirement

# Number of recent message pairs to keep verbatim (each pair = 1 user + 1 assistant turn)
RECENT_TURNS_TO_KEEP = 5  # = 10 messages = last 8-10 prompts per spec


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _estimate_messages_tokens(messages: list) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += _estimate_tokens(str(block.get("text", block.get("content", ""))))
    return total


def trim_messages(
    messages: list,
    system_summary: Optional[str] = None,
    max_tokens: int = MAX_CONTEXT_TOKENS,
) -> tuple[list, str]:
    """
    Trim a messages list to fit within the token budget.

    Strategy:
    1. Always keep the last RECENT_TURNS_TO_KEEP * 2 messages verbatim.
    2. Represent older messages as a compressed summary injected as the
       first user message.
    3. If even the recent messages exceed the budget, truncate from the
       oldest of the recent set.

    Args:
        messages: Full message history list (role/content dicts).
        system_summary: Existing summary from a previous trim round.
        max_tokens: Hard token ceiling.

    Returns:
        (trimmed_messages, updated_summary) tuple.
    """
    if not messages:
        return messages, system_summary or ""

    # How many messages to keep verbatim at the tail
    keep_count = min(RECENT_TURNS_TO_KEEP * 2, len(messages))
    recent_msgs = messages[-keep_count:]
    old_msgs = messages[:-keep_count]

    if not old_msgs:
        return messages, system_summary or ""

    # Build or extend the summary
    old_summary = system_summary or ""
    new_summary_parts = []
    if old_summary:
        new_summary_parts.append(old_summary)

    for msg in old_msgs:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            # Keep only the first 150 chars per old message for the summary
            snippet = content[:150].replace("\n", " ")
            new_summary_parts.append(f"[{role}]: {snippet}…")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    snippet = block.get("text", "")[:100].replace("\n", " ")
                    new_summary_parts.append(f"[{role}]: {snippet}…")
                    break

    updated_summary = " | ".join(new_summary_parts)

    # Enforce summary budget
    summary_token_budget = int(max_tokens * SUMMARY_BUDGET_RATIO)
    while _estimate_tokens(updated_summary) > summary_token_budget and len(new_summary_parts) > 1:
        # Drop the oldest summary entry
        new_summary_parts.pop(0)
        updated_summary = " | ".join(new_summary_parts)

    # Build the trimmed message list: [summary injection] + recent
    summary_injection = {
        "role": "user",
        "content": f"[CONTEXT SUMMARY — older turns compressed]\n{updated_summary}",
    }
    trimmed = [summary_injection] + recent_msgs

    total_tokens = _estimate_messages_tokens(trimmed)
    if total_tokens > max_tokens:
        # Emergency trim: drop from the oldest of the recent set (not the summary)
        while len(trimmed) > 2 and _estimate_messages_tokens(trimmed) > max_tokens:
            trimmed.pop(1)  # pop oldest recent message (index 1, after summary)

    logger.debug(
        "Context trimmed",
        extra={
            "original_messages": len(messages),
            "trimmed_messages": len(trimmed),
            "summary_tokens": _estimate_tokens(updated_summary),
        },
    )

    return trimmed, updated_summary


class ContextWindowManager:
    """
    Stateful context manager for a single agent conversation.
    Maintains the rolling summary and enforces the recent-window policy.
    """

    def __init__(self, max_tokens: int = MAX_CONTEXT_TOKENS):
        self._max_tokens = max_tokens
        self._summary = ""
        self._full_history: list = []

    def add(self, message: dict) -> None:
        """Append a message to the full history."""
        self._full_history.append(message)

    def get_trimmed(self) -> list:
        """Return the trimmed message list ready to send to the API."""
        trimmed, self._summary = trim_messages(
            self._full_history, self._summary, self._max_tokens
        )
        return trimmed

    @property
    def summary(self) -> str:
        return self._summary

    @property
    def full_history(self) -> list:
        return self._full_history

    def reset(self) -> None:
        self._summary = ""
        self._full_history = []
