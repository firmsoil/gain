"""GAIN Engineering Intelligence Agent package."""

from gain.agent.gain_mcp_client import GainMcpClient
from gain.agent.gateway import AgentGateway
from gain.agent.github_mcp_client import GitHubMcpClient, GitHubMcpUnavailableError
from gain.agent.llm import DeterministicReasoningProvider, LLMGateway, ReasoningProvider
from gain.agent.models import (
    AgentResponse,
    Claim,
    ClaimType,
    InvestigationContext,
    InvestigationPlan,
    PlanStep,
    PlanStepStatus,
)
from gain.agent.orchestrator import EngineeringIntelligenceAgent
from gain.agent.planner import InvestigationPlanner
from gain.agent.policy import PolicyGuard, SecurityPolicyViolationError
from gain.agent.router import GainMcpUnavailableError, ToolRouter
from gain.agent.synthesizer import EvidenceSynthesizer

__all__ = [
    "AgentGateway",
    "AgentResponse",
    "Claim",
    "ClaimType",
    "DeterministicReasoningProvider",
    "EngineeringIntelligenceAgent",
    "EvidenceSynthesizer",
    "GainMcpClient",
    "GainMcpUnavailableError",
    "GitHubMcpClient",
    "GitHubMcpUnavailableError",
    "InvestigationContext",
    "InvestigationPlan",
    "InvestigationPlanner",
    "LLMGateway",
    "PlanStep",
    "PlanStepStatus",
    "PolicyGuard",
    "ReasoningProvider",
    "SecurityPolicyViolationError",
    "ToolRouter",
]
