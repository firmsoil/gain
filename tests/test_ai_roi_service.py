"""Tests for deterministic AIROIService supporting both DORA 2026 and legacy calculations."""

from gain.services.ai_roi import AIROIService


def test_ai_roi_service_legacy_calculations() -> None:
    """Ensure backward-compatibility with legacy single-multiplier parameters."""
    service = AIROIService()

    # 10 developers, $100/hr, $20/seat/mo, 2.0 hrs saved weekly, 48 weeks/yr
    # Investment = 10 * 20 * 12 = $2,400.00
    # Annual Hours = 10 * 2.0 * 48 = 960 hrs
    # Gross Value = 960 * 100 = $96,000.00
    # Net Benefit = 96,000 - 2,400 = $93,600.00
    # ROI % = (93,600 / 2,400) * 100 = 3,900.0%
    result = service.calculate_roi_scenario(
        population="test-team",
        developer_count=10,
        hourly_rate=100.0,
        monthly_license_cost=20.0,
        hours_saved_weekly=2.0,
    )

    assert result.status == "available"
    assert result.is_modeled is True
    assert result.investment_cost == 2400.0
    assert result.net_benefit == 93600.0
    assert result.roi_percentage == 3900.0

    # Test sensitivity analysis
    scenarios = result.sensitivity_analysis
    assert "conservative" in scenarios
    assert "expected" in scenarios
    assert "optimistic" in scenarios

    # Conservative (0.5x hours -> 480 hrs * 100 = 48,000; net: 45,600; roi: 1900.0%)
    assert scenarios["conservative"]["annual_hours_saved"] == 480.0
    assert scenarios["conservative"]["net_benefit"] == 45600.0
    assert scenarios["conservative"]["roi_percentage"] == 1900.0

    # Optimistic (1.5x hours -> 1440 hrs * 100 = 144,000; net: 141,600; roi: 5900.0%)
    assert scenarios["optimistic"]["annual_hours_saved"] == 1440.0
    assert scenarios["optimistic"]["net_benefit"] == 141600.0
    assert scenarios["optimistic"]["roi_percentage"] == 5900.0


def test_ai_roi_service_dora_2026_reference_benchmark() -> None:
    """Verify exact numerical reproduction of the Google Cloud DORA 2026 reference calculator.

    Reference: DORA 'The ROI of AI-assisted Software Development' (v. 2026.1), Pages 57-58.
    """
    service = AIROIService()

    result = service.calculate_roi_scenario(
        population="fortune-100-eng",
        staff_size=500,
        salary=176000.00,
        annual_license_per_user=250.00,
        annual_additional_ai_cost_per_user=80.00,
        annual_training_cost_per_user=9600.00,
        annual_infra_cost=100000.00,
        j_curve_drop=0.15,
        j_curve_months=3.0,
        net_time_saved_pct=0.125,
        current_deploys=50,
        target_deploys=56,
        current_cfr=0.05,
        target_cfr=0.06,
        fdrt_hours=4.0,
        downtime_cost_per_hour=100000.00,
        current_features=50,
        target_features=56,
        idea_success_rate=0.33,
        revenue_impact_per_feature=0.005,
        portfolio_revenue=100000000.00,
        use_dora_model=True,
    )

    assert result.status == "available"
    assert result.model_version == "gain-dora-roi-v2026.1"

    # Ledger A: Investment Verification
    # Hard costs = ((250 + 80 + 9600) * 500) + 100,000 = $5,065,000.00
    assert result.hard_costs == 5065000.00
    # J-Curve cost = 500 * 176,000 * 0.15 * (3 / 12) = $3,300,000.00
    assert result.j_curve_cost == 3300000.00
    # Total Investment = 5,065,000 + 3,300,000 = $8,365,000.00
    assert result.investment_cost == 8365000.00

    # Ledger B: Value Verification
    # Headcount reinvestment = 500 * 176,000 * 0.125 = $11,000,000.00
    assert result.headcount_reinvestment_value == 11000000.00
    # Feature revenue = 6 * 0.33 * 0.005 * 100,000,000 = $990,000.00
    assert result.feature_revenue_lift == 990000.00
    # Downtime impact = (50 * 0.05 * 4 * 100k) - (56 * 0.06 * 4 * 100k) = -$344,000.00
    assert result.instability_impact == -344000.00
    # Total Annual Value = 11,000,000 + 990,000 - 344,000 = $11,646,000.00
    assert result.total_annual_value == 11646000.00

    # Synthesis Verification
    # First year benefit = 11,646,000 - 8,365,000 = $3,281,000.00
    assert result.net_benefit == 3281000.00
    # ROI % = (3,281,000 / 8,365,000) * 100 = 39.2% (rounds to 39% in DORA report)
    assert result.roi_percentage == 39.2
    # Payback period = 8,365,000 / 11,646,000 = 0.72 years (~8.6 months)
    assert result.payback_period_years == 0.72

    # Asymmetric Scenario Verification (Page 37)
    scenarios = result.sensitivity_analysis
    assert "conservative" in scenarios
    assert "expected" in scenarios
    assert "optimistic" in scenarios

    # Conservative: 0.8x Value, 1.5x Cost
    assert scenarios["conservative"]["total_investment"] == 12547500.00
    assert scenarios["conservative"]["gross_economic_value"] == 9316800.00
    assert scenarios["conservative"]["net_benefit"] == -3230700.00
    assert scenarios["conservative"]["roi_percentage"] == -25.7

    # Optimistic: 1.2x Value, 0.8x Cost
    assert scenarios["optimistic"]["total_investment"] == 6692000.00
    assert scenarios["optimistic"]["gross_economic_value"] == 13975200.00
    assert scenarios["optimistic"]["net_benefit"] == 7283200.00
    assert scenarios["optimistic"]["roi_percentage"] == 108.8
