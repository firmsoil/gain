"""Tests for deterministic AIROIService."""

from gain.services.ai_roi import AIROIService


def test_ai_roi_service_deterministic_calculations() -> None:
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

    # Uncertainty range
    assert result.uncertainty_range["min_roi_percentage"] == 1900.0
    assert result.uncertainty_range["max_roi_percentage"] == 5900.0
