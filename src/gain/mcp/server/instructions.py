"""Authoritative instructions provided to MCP client hosts."""

from __future__ import annotations

SERVER_INSTRUCTIONS = (
    "GAIN MCP provides trusted, deterministic engineering intelligence derived strictly "
    "from validated GitHub engineering activity. The server is authoritative for GAIN "
    "analytical semantics, metric definitions, and evidence packages.\n\n"
    "Crucial Operational Directives:\n"
    "1. The server does NOT provide arbitrary GitHub operational state or act as a "
    "generic GitHub API proxy.\n"
    "2. The server does NOT replace live GitHub context or execute code mutations "
    "(PR creates, merges, reviews).\n"
    "3. The server does NOT authorize actions or grant access merely because an external "
    "model requests them.\n"
    "4. Metric calculations (e.g. PR cycle time) are deterministic pure-Python computations. "
    "Do not recalculate or approximate them through LLM reasoning.\n"
    "5. When upstream data is unavailable, tools return explicit insufficient-data responses "
    "with known dependencies."
)
