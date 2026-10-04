"""Domain Curriculum Engineering Taxonomy for Engineering Intelligence (FM.next).

Implements hierarchical domain knowledge modeling (knowledge, foundational skills,
and composition skills) inspired by IBM InstructLab and IEEE SWEBOK to eliminate
unstructured training inefficiencies (Hassan et al. 2026).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TaxonomyNode:
    """A node in the hierarchical curriculum taxonomy representing knowledge or skills."""

    node_id: str
    name: str
    node_type: str  # "knowledge" | "foundational_skill" | "composition_skill"
    domain: str  # "flow_metrics" | "causal_attribution" | "code_quality" | "delivery_stability"
    principles: list[str]
    verifiable_rules: list[str]
    few_shot_exemplars: list[dict[str, Any]] = field(default_factory=list)


class DomainCurriculum:
    """Curriculum engineering taxonomy manager for software engineering intelligence."""

    def __init__(
        self,
        curriculum_version: str = "1.0.0",
        title: str = "GAIN SE 3.0 Curriculum",
    ) -> None:
        self.curriculum_version = curriculum_version
        self.title = title
        self.nodes: dict[str, TaxonomyNode] = {}

    def register_node(self, node: TaxonomyNode) -> None:
        """Register a taxonomy node in the curriculum."""
        self.nodes[node.node_id] = node

    def match_skills(self, intent_text: str) -> list[TaxonomyNode]:
        """Match relevant curriculum nodes based on keywords in the intent text."""
        q = intent_text.lower()
        domain_triggers = {
            "flow_metrics": ["cycle time", "lead time", "pr", "pull request", "duration"],
            "causal_attribution": ["ai", "copilot", "cause", "velocity", "impact", "attribution"],
            "code_quality": ["bloat", "refactor", "churn", "clean", "additions", "deletions"],
            "delivery_stability": ["dora", "deployment", "cfr", "fail rate", "incident"],
        }

        matched: list[TaxonomyNode] = []
        for node in self.nodes.values():
            triggers = domain_triggers.get(node.domain, [])
            if any(k in q for k in triggers):
                matched.append(node)

        return matched

    def compile_grounding_prompt(self, intent_text: str) -> str:
        """Compile matched curriculum rules into a structured instruction context."""
        matched_nodes = self.match_skills(intent_text)
        if not matched_nodes:
            # Fall back to base domain principles
            matched_nodes = [n for n in self.nodes.values() if n.node_type == "knowledge"]

        sections: list[str] = [
            f"### Authoritative SE Curriculum Grounding [v{self.curriculum_version}]",
            "Evaluate this inquiry strictly adhering to the following domain rules:",
        ]

        for node in matched_nodes:
            sections.append(f"\n#### [{node.node_type.upper()}] {node.name}:")
            for p in node.principles:
                sections.append(f"- Principle: {p}")
            for r in node.verifiable_rules:
                sections.append(f"- Verifiable Rule: {r}")

        return "\n".join(sections)

    @classmethod
    def load_default_curriculum(cls) -> DomainCurriculum:
        """Construct the canonical GAIN engineering intelligence curriculum."""
        curriculum = cls()

        # 1. Knowledge: Flow Metrics Foundation (SWEBOK / DORA)
        curriculum.register_node(
            TaxonomyNode(
                node_id="KNOW-FLOW-01",
                name="PR Lifecycle & Flow Measurement",
                node_type="knowledge",
                domain="flow_metrics",
                principles=[
                    (
                        "PR cycle time measures duration between creation and merge, "
                        "strictly excluding prior author coding time."
                    ),
                    (
                        "Flow speed distributions are skewed; linear rank percentiles "
                        "(p50, p75, p90) must be preferred over arithmetic means."
                    ),
                ],
                verifiable_rules=[
                    "Unmerged PRs must be excluded from cycle time duration statistics.",
                    (
                        "Gaming risk: PR cycle time must never be used as a proxy for "
                        "individual engineer effort."
                    ),
                ],
            )
        )

        # 2. Foundational Skill: Confounder Isolation & Epistemic Attribution
        curriculum.register_node(
            TaxonomyNode(
                node_id="SKILL-CONFOUND-01",
                name="Confounder Isolation & Epistemic Bounding",
                node_type="foundational_skill",
                domain="causal_attribution",
                principles=[
                    (
                        "AI developer tool adoption cannot be inferred from generic commit volume "
                        "without authoritative author telemetry."
                    ),
                    (
                        "Differences between cohorts reflect statistical association by default; "
                        "causal attribution requires controlled experimental isolation."
                    ),
                ],
                verifiable_rules=[
                    "Tag all non-randomized cohort comparisons as ClaimType.ASSOCIATED.",
                    (
                        "Flag PR size disparity (>25% lines difference) as an active "
                        "confounding variable."
                    ),
                ],
            )
        )

        # 3. Foundational Skill: Code Bloat & Additive Churn Defense (SE 3.0)
        curriculum.register_node(
            TaxonomyNode(
                node_id="SKILL-BLOAT-01",
                name="Additive Bias & Code Bloat Mitigation",
                node_type="foundational_skill",
                domain="code_quality",
                principles=[
                    (
                        "AI coding assistants bias toward additive code generation, "
                        "increasing maintainability drag (Hassan et al. 2026)."
                    ),
                    (
                        "High developer velocity accompanied by plunging refactoring ratios "
                        "signifies technical debt accumulation."
                    ),
                ],
                verifiable_rules=[
                    "Evaluate Refactoring Ratio (GAIN-QUAL-003): deletions / total churn.",
                    (
                        "Flag Code Bloat Index (GAIN-QUAL-004) when net additions per file "
                        "exceed 100 lines/file."
                    ),
                ],
            )
        )

        # 4. Composition Skill: Multi-Dimensional Flow & Stability Assessment
        curriculum.register_node(
            TaxonomyNode(
                node_id="COMP-STABILITY-01",
                name="Delivery Velocity & Stability Balance",
                node_type="composition_skill",
                domain="delivery_stability",
                principles=[
                    (
                        "Speedups in delivery flow must be cross-referenced against change failure "
                        "rates to evaluate instability taxes."
                    ),
                    (
                        "Higher PR velocity coupled with elevated review latency indicates "
                        "verification tax bottlenecks."
                    ),
                ],
                verifiable_rules=[
                    (
                        "Incorporate DORA Change Failure Rate alongside PR throughput in "
                        "delivery assessments."
                    ),
                    (
                        "Surface verification tax when AI cohort cycle time exceeds baseline "
                        "despite faster initial PR creation."
                    ),
                ],
            )
        )

        return curriculum
