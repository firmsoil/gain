"""Deterministic AI Economic ROI and multi-scenario sensitivity engine.

Incorporates Google Cloud DORA's 2026 two-ledger economic framework:
- Ledger A (Investment): Direct hard costs (licenses, usage, training, infra) + J-Curve tuition.
- Ledger B (Value): Reclaimed capacity (net of verification tax) + features + instability tax.
"""

from __future__ import annotations

from typing import Any

import structlog

from gain.config import Settings, get_settings
from gain.mcp.schemas.ai import ROIScenarioResult

logger = structlog.get_logger(__name__)

# Legacy benchmark defaults
DEFAULT_HOURLY_RATE = 85.00  # USD fully-loaded developer hourly rate
DEFAULT_MONTHLY_LICENSE = 19.00  # USD per user/month (GitHub Copilot Business)
DEFAULT_WEEKS_PER_YEAR = 48.0  # Working weeks per engineer year
DEFAULT_HOURS_SAVED_WEEKLY = 2.5  # Estimated hours saved weekly per active engineer

# DORA 2026 Reference Benchmark Defaults
DEFAULT_STAFF_SIZE = 500  # Technical FTEs
DEFAULT_LOADED_SALARY = 176000.00  # Fully loaded annual developer salary
DEFAULT_ANNUAL_LICENSE = 250.00  # Annual base license per user
DEFAULT_ANNUAL_ADDITIONAL_AI_COST = 80.00  # Variable tokens/API cost per user
DEFAULT_ANNUAL_TRAINING_COST = 9600.00  # Enablement & change management per user
DEFAULT_ANNUAL_INFRA_COST = 100000.00  # Supporting enterprise compute/monitoring
DEFAULT_J_CURVE_DROP = 0.15  # 15% adoption productivity dip
DEFAULT_J_CURVE_MONTHS = 3.0  # 3-month adoption learning curve
DEFAULT_NET_TIME_SAVED_PCT = 0.125  # 12.5% (~1 hour/day) net of verification tax


class AIROIService:
    """Calculates deterministic economic ROI scenarios and sensitivity intervals.

    Supports Google Cloud DORA 2026 two-ledger modeling and legacy estimation.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def calculate_roi_scenario(
        self,
        population: str,
        time_period: str = "annual",
        developer_count: int | None = None,
        hourly_rate: float | None = None,
        monthly_license_cost: float | None = None,
        hours_saved_weekly: float | None = None,
        investment_cost: float | None = None,
        # DORA 2026 Two-Ledger Parameters:
        staff_size: int = DEFAULT_STAFF_SIZE,
        salary: float = DEFAULT_LOADED_SALARY,
        annual_license_per_user: float = DEFAULT_ANNUAL_LICENSE,
        annual_additional_ai_cost_per_user: float = DEFAULT_ANNUAL_ADDITIONAL_AI_COST,
        annual_training_cost_per_user: float = DEFAULT_ANNUAL_TRAINING_COST,
        annual_infra_cost: float = DEFAULT_ANNUAL_INFRA_COST,
        j_curve_drop: float = DEFAULT_J_CURVE_DROP,
        j_curve_months: float = DEFAULT_J_CURVE_MONTHS,
        net_time_saved_pct: float = DEFAULT_NET_TIME_SAVED_PCT,
        # Baseline & Target DORA metrics for Instability Tax:
        current_deploys: int = 50,
        target_deploys: int = 56,
        current_cfr: float = 0.05,
        target_cfr: float = 0.06,
        fdrt_hours: float = 4.0,
        downtime_cost_per_hour: float = 100000.0,
        # Feature acceleration & optionality:
        current_features: int = 50,
        target_features: int = 56,
        idea_success_rate: float = 0.33,
        revenue_impact_per_feature: float = 0.005,
        portfolio_revenue: float = 100000000.0,
        use_dora_model: bool | None = None,
    ) -> ROIScenarioResult:
        """Compute multi-tier ROI scenario and sensitivity bounds deterministically."""
        is_legacy = not use_dora_model and (
            developer_count is not None
            or hourly_rate is not None
            or monthly_license_cost is not None
            or hours_saved_weekly is not None
        )

        if is_legacy:
            return self._calculate_legacy_roi(
                population=population,
                time_period=time_period,
                developer_count=developer_count or 25,
                hourly_rate=hourly_rate or DEFAULT_HOURLY_RATE,
                monthly_license_cost=monthly_license_cost or DEFAULT_MONTHLY_LICENSE,
                hours_saved_weekly=hours_saved_weekly or DEFAULT_HOURS_SAVED_WEEKLY,
                investment_cost=investment_cost,
            )

        return self._calculate_dora_2026_roi(
            population=population,
            time_period=time_period,
            staff_size=staff_size,
            salary=salary,
            annual_license_per_user=annual_license_per_user,
            annual_additional_ai_cost_per_user=annual_additional_ai_cost_per_user,
            annual_training_cost_per_user=annual_training_cost_per_user,
            annual_infra_cost=annual_infra_cost,
            j_curve_drop=j_curve_drop,
            j_curve_months=j_curve_months,
            net_time_saved_pct=net_time_saved_pct,
            current_deploys=current_deploys,
            target_deploys=target_deploys,
            current_cfr=current_cfr,
            target_cfr=target_cfr,
            fdrt_hours=fdrt_hours,
            downtime_cost_per_hour=downtime_cost_per_hour,
            current_features=current_features,
            target_features=target_features,
            idea_success_rate=idea_success_rate,
            revenue_impact_per_feature=revenue_impact_per_feature,
            portfolio_revenue=portfolio_revenue,
        )

    def _calculate_dora_2026_roi(
        self,
        population: str,
        time_period: str,
        staff_size: int,
        salary: float,
        annual_license_per_user: float,
        annual_additional_ai_cost_per_user: float,
        annual_training_cost_per_user: float,
        annual_infra_cost: float,
        j_curve_drop: float,
        j_curve_months: float,
        net_time_saved_pct: float,
        current_deploys: int,
        target_deploys: int,
        current_cfr: float,
        target_cfr: float,
        fdrt_hours: float,
        downtime_cost_per_hour: float,
        current_features: int,
        target_features: int,
        idea_success_rate: float,
        revenue_impact_per_feature: float,
        portfolio_revenue: float,
    ) -> ROIScenarioResult:
        """DORA 2026 comprehensive two-ledger economic return computation."""
        n_fte = max(1, staff_size)
        loaded_salary = max(1000.0, salary)

        # Ledger A: Total Investment
        # 1. Direct Hard Costs = ((License + Additional AI + Training) * Staff) + Infra
        per_user_tooling = (
            annual_license_per_user
            + annual_additional_ai_cost_per_user
            + annual_training_cost_per_user
        )
        direct_hard_costs = round((per_user_tooling * n_fte) + annual_infra_cost, 2)

        # 2. J-Curve Tuition Cost = Staff * Salary * Drop * (Duration / 12)
        j_curve_cost = round(
            n_fte * loaded_salary * j_curve_drop * (max(0.0, j_curve_months) / 12.0), 2
        )

        total_first_year_investment = round(direct_hard_costs + j_curve_cost, 2)

        # Ledger B: Total Annual Value
        # 1. Headcount Reinvestment Capacity (Net of Verification Tax)
        headcount_reinvestment_value = round(n_fte * loaded_salary * net_time_saved_pct, 2)

        # 2. Revenue from Accelerated Feature Deployments / Optionality
        delta_features = max(0, target_features - current_features)
        feature_revenue_lift = round(
            delta_features * idea_success_rate * revenue_impact_per_feature * portfolio_revenue,
            2,
        )

        # 3. Downtime Impact (Instability Tax from delta CFR / FDRT)
        baseline_downtime = current_deploys * current_cfr * fdrt_hours * downtime_cost_per_hour
        target_downtime = target_deploys * target_cfr * fdrt_hours * downtime_cost_per_hour
        instability_impact = round(baseline_downtime - target_downtime, 2)

        total_annual_value = round(
            headcount_reinvestment_value + feature_revenue_lift + instability_impact, 2
        )

        # Financial Synthesis
        first_year_benefit = round(total_annual_value - total_first_year_investment, 2)
        roi_percentage = (
            round((first_year_benefit / total_first_year_investment) * 100.0, 1)
            if total_first_year_investment > 0
            else 0.0
        )
        payback_period_years = (
            round(total_first_year_investment / total_annual_value, 2)
            if total_annual_value > 0
            else None
        )

        # Scenario Multipliers (DORA 2026 Page 37)
        # Conservative: 0.8x Value, 1.5x Cost
        # Expected: 1.0x Value, 1.0x Cost
        # Optimistic: 1.2x Value, 0.8x Cost
        scenarios: dict[str, dict[str, Any]] = {}
        multipliers = {
            "conservative": {"value_mult": 0.8, "cost_mult": 1.5},
            "expected": {"value_mult": 1.0, "cost_mult": 1.0},
            "optimistic": {"value_mult": 1.2, "cost_mult": 0.8},
        }

        for tier, mults in multipliers.items():
            adj_val = round(total_annual_value * mults["value_mult"], 2)
            adj_cost = round(total_first_year_investment * mults["cost_mult"], 2)
            adj_net = round(adj_val - adj_cost, 2)
            adj_roi = round((adj_net / adj_cost) * 100.0, 1) if adj_cost > 0 else 0.0
            scenarios[tier] = {
                "value_multiplier": mults["value_mult"],
                "cost_multiplier": mults["cost_mult"],
                "total_investment": adj_cost,
                "gross_economic_value": adj_val,
                "net_benefit": adj_net,
                "roi_percentage": adj_roi,
            }

        assumptions = [
            (
                f"Technical staff size: {n_fte} FTEs with average fully loaded salary "
                f"${loaded_salary:,.2f}."
            ),
            (
                f"Direct hard costs: licenses (${annual_license_per_user}/user), AI usage "
                f"(${annual_additional_ai_cost_per_user}/user), training "
                f"(${annual_training_cost_per_user}/user), infra (${annual_infra_cost:,.2f})."
            ),
            (
                f"J-Curve tuition cost assumes {j_curve_drop * 100:.1f}% productivity dip across "
                f"{j_curve_months:.1f} months."
            ),
            f"Net productivity boost: {net_time_saved_pct * 100:.1f}% net of verification tax.",
            (
                f"Instability tax models CFR shifting from {current_cfr * 100:.1f}% to "
                f"{target_cfr * 100:.1f}% at ${downtime_cost_per_hour:,.2f}/hr downtime."
            ),
            (
                "Capacity gains represent headcount reinvestment (innovation headroom), "
                "not payroll reductions."
            ),
        ]

        logger.info(
            "dora_ai_roi_calculated",
            population=population,
            total_investment=total_first_year_investment,
            total_annual_value=total_annual_value,
            net_benefit=first_year_benefit,
            roi_percentage=roi_percentage,
        )

        return ROIScenarioResult(
            status="available",
            is_modeled=True,
            model_version="gain-dora-roi-v2026.1",
            time_period=time_period,
            population=population,
            investment_cost=total_first_year_investment,
            hard_costs=direct_hard_costs,
            j_curve_cost=j_curve_cost,
            economic_value_components={
                "direct_hard_costs": direct_hard_costs,
                "j_curve_cost": j_curve_cost,
                "total_investment": total_first_year_investment,
                "headcount_reinvestment_value": headcount_reinvestment_value,
                "feature_revenue_lift": feature_revenue_lift,
                "instability_impact": instability_impact,
                "total_annual_value": total_annual_value,
            },
            headcount_reinvestment_value=headcount_reinvestment_value,
            feature_revenue_lift=feature_revenue_lift,
            instability_impact=instability_impact,
            total_annual_value=total_annual_value,
            net_benefit=first_year_benefit,
            roi_percentage=roi_percentage,
            payback_period_years=payback_period_years,
            assumptions=assumptions,
            attribution_basis=(
                "Google Cloud DORA 2026 Two-Ledger Economic Framework (CC BY-NC-SA 4.0)"
            ),
            sensitivity_analysis=scenarios,
            uncertainty_range={
                "min_roi_percentage": scenarios["conservative"]["roi_percentage"],
                "max_roi_percentage": scenarios["optimistic"]["roi_percentage"],
            },
            limitations=[
                (
                    "Financial projections represent modeled scenario assumptions, "
                    "not audited accounting records."
                ),
                (
                    "Assumes engineering capacity freed by AI is reinvested in "
                    "high-value feature development."
                ),
                (
                    "Negative instability tax will compound if delivery pipelines "
                    "lack automated test guardrails."
                ),
            ],
        )

    def _calculate_legacy_roi(
        self,
        population: str,
        time_period: str,
        developer_count: int,
        hourly_rate: float,
        monthly_license_cost: float,
        hours_saved_weekly: float,
        investment_cost: float | None,
    ) -> ROIScenarioResult:
        """Legacy single-multiplier calculation for backward compatibility."""
        dev_count = max(1, developer_count)
        rate = max(1.0, hourly_rate)
        license_mo = (
            monthly_license_cost
            if investment_cost is None
            else (investment_cost / (dev_count * 12.0))
        )

        annual_investment = (
            investment_cost
            if investment_cost is not None
            else round(dev_count * license_mo * 12.0, 2)
        )

        expected_annual_hours = round(dev_count * hours_saved_weekly * DEFAULT_WEEKS_PER_YEAR, 1)
        expected_gross_value = round(expected_annual_hours * rate, 2)
        expected_net_benefit = round(expected_gross_value - annual_investment, 2)
        expected_roi = (
            round((expected_net_benefit / annual_investment) * 100.0, 1)
            if annual_investment > 0
            else 0.0
        )

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
