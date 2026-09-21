"""Deterministic AI Economic ROI and multi-scenario sensitivity engine."""

from __future__ import annotations

from typing import Any

import structlog

from gain.config import Settings, get_settings
from gain.mcp.schemas.ai import ROIScenarioResult

logger = structlog.get_logger(__name__)

# Default benchmark parameters
DEFAULT_HOURLY_RATE = 85.00  # USD fully-loaded developer hourly rate
DEFAULT_MONTHLY_LICENSE = 19.00  # USD per user/month (GitHub Copilot Business)
DEFAULT_WEEKS_PER_YEAR = 48.0  # Working weeks per engineer year
DEFAULT_HOURS_SAVED_WEEKLY = 2.5  # Estimated hours saved weekly per active engineer


class AIROIService:
    """Calculates deterministic economic ROI scenarios and sensitivity intervals."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def calculate_roi_scenario(
        self,
        population: str,
        time_period: str = "annual",
        developer_count: int = 25,
        hourly_rate: float = DEFAULT_HOURLY_RATE,
        monthly_license_cost: float = DEFAULT_MONTHLY_LICENSE,
        hours_saved_weekly: float = DEFAULT_HOURS_SAVED_WEEKLY,
        investment_cost: float | None = None,
    ) -> ROIScenarioResult:
        """Compute multi-tier ROI scenario and sensitivity bounds deterministically."""
        dev_count = max(1, developer_count)
        rate = max(1.0, hourly_rate)
        license_mo = (
            monthly_license_cost
            if investment_cost is None
            else (investment_cost / (dev_count * 12.0))
        )

        # 1. Total annual tool investment
        annual_investment = (
            investment_cost
            if investment_cost is not None
            else round(dev_count * license_mo * 12.0, 2)
        )

        # 2. Expected base scenario (1.0x multiplier)
        expected_annual_hours = round(dev_count * hours_saved_weekly * DEFAULT_WEEKS_PER_YEAR, 1)
        expected_gross_value = round(expected_annual_hours * rate, 2)
        expected_net_benefit = round(expected_gross_value - annual_investment, 2)
        expected_roi = (
            round((expected_net_benefit / annual_investment) * 100.0, 1)
            if annual_investment > 0
            else 0.0
        )

        # 3. Sensitivity scenarios
        scenarios: dict[str, dict[str, Any]] = {}
        multipliers = {
            "conservative": 0.5,
            "expected": 1.0,
            "optimistic": 1.5,
        }

        for tier, mult in multipliers.items():
            hrs = round(expected_annual_hours * mult, 1)
            gross = round(hrs * rate, 2)
            net = round(gross - annual_investment, 2)
            roi = round((net / annual_investment) * 100.0, 1) if annual_investment > 0 else 0.0

            scenarios[tier] = {
                "efficiency_multiplier": mult,
                "annual_hours_saved": hrs,
                "gross_economic_value": gross,
                "net_benefit": net,
                "roi_percentage": roi,
            }

        logger.info(
            "ai_roi_calculated",
            population=population,
            annual_investment=annual_investment,
            expected_net_benefit=expected_net_benefit,
            expected_roi=expected_roi,
        )

        return ROIScenarioResult(
            status="available",
            is_modeled=True,
            model_version="gain-roi-v1.0",
            time_period=time_period,
            population=population,
            investment_cost=annual_investment,
            economic_value_components={
                "annual_investment": annual_investment,
                "developer_count": float(dev_count),
                "blended_hourly_rate": rate,
                "annual_hours_saved": expected_annual_hours,
                "gross_economic_value": expected_gross_value,
            },
            net_benefit=expected_net_benefit,
            roi_percentage=expected_roi,
            assumptions=[
                f"Blended developer hourly cost benchmark is ${rate:.2f}/hr.",
                f"Work year assumes {DEFAULT_WEEKS_PER_YEAR:.0f} weeks per developer.",
                f"Tool cost assumes ${license_mo:.2f}/seat/month across {dev_count} developers.",
                (
                    "All financial figures represent modeled scenario projections, "
                    "not historical accounting facts."
                ),
            ],
            attribution_basis=(
                f"{hours_saved_weekly:.1f} hours/dev/week attributed to AI workflow acceleration."
            ),
            sensitivity_analysis=scenarios,
            uncertainty_range={
                "min_roi_percentage": scenarios["conservative"]["roi_percentage"],
                "max_roi_percentage": scenarios["optimistic"]["roi_percentage"],
            },
            limitations=[
                "Model excludes secondary reviewer latency increases if code volume expands.",
                "Projections assume sustained developer adoption and tool availability.",
            ],
        )
