# GAIN AI Economic ROI Model

**Author:** Lead Implementation Architect  
**Status:** Approved & Implemented (Gate 8)  
**Authoritative References:** `docs/MASTER_SPEC.md` Section 12, `docs/REFERENCE_ARCHITECTURE.md`, `docs/adr/0031-ai-economic-roi-and-sensitivity-scenarios.md`  

---

## 1. Economic Framework & Separation of Concerns

GAIN strictly separates economic return modeling into four distinct stages:

$$\text{Measurement} \longrightarrow \text{Attribution} \longrightarrow \text{Economic Modeling} \longrightarrow \text{Scenario Analysis}$$

1. **Measurement**: Observable, empirical delivery flow metrics (PR cycle time, throughput) derived from canonical telemetry.
2. **Attribution**: The fraction of measured efficiency change legitimately linked to the AI developer tool (excluding natural speedups, seasonal lulls, or team shifts).
3. **Economic Modeling**: Transformation of attributed engineering time savings into monetary equivalents using explicit cost parameters.
4. **Scenario Analysis**: Multi-tier sensitivity bounds (`conservative`, `expected`, `optimistic`) providing executive leadership with realistic risk envelopes rather than single-point forecasts.

All financial outputs must be explicitly classified as **`Modeled`** claims.

---

## 2. Mathematical Formulations

### 2.1 Annual Investment Cost
$$\text{Investment Cost} = N_{\text{devs}} \times C_{\text{seat\_monthly}} \times 12$$
where:
- $N_{\text{devs}}$: Number of licensed active developers.
- $C_{\text{seat\_monthly}}$: Monthly license cost per seat (e.g. $19/seat for GitHub Copilot Business, $39/seat for GitHub Copilot Enterprise).

### 2.2 Annual Time Savings
$$\text{Annual Hours Saved} = N_{\text{devs}} \times H_{\text{saved\_weekly}} \times W_{\text{weeks\_per\_year}}$$
where:
- $H_{\text{saved\_weekly}}$: Attributed engineering hours saved per developer per week.
- $W_{\text{weeks\_per\_year}}$: Working weeks per year (default $48.0$).

### 2.3 Gross Economic Value
$$\text{Gross Economic Value} = \text{Annual Hours Saved} \times R_{\text{hourly}}$$
where:
- $R_{\text{hourly}}$: Blended fully-loaded engineering hourly cost (salary, benefits, infrastructure; default benchmark: $85.00/hr).

### 2.4 Net Benefit & Return on Investment (ROI)
$$\text{Net Benefit} = \text{Gross Economic Value} - \text{Investment Cost}$$

$$\text{ROI (\%)} = \left(\frac{\text{Net Benefit}}{\text{Investment Cost}}\right) \times 100\%$$

---

## 3. Sensitivity Analysis & Uncertainty Matrix

To prevent misleading precision, GAIN computes three distinct sensitivity scenarios:
1. **Conservative Scenario ($0.5\times$ efficiency multiplier)**: Accounts for adoption friction, hallucination debugging, and increased review latency from larger code volume.
2. **Expected Scenario ($1.0\times$ efficiency multiplier)**: Standard operational baseline derived from empirical cohort delta.
3. **Optimistic Scenario ($1.5\times$ efficiency multiplier)**: Assumes high prompt proficiency, automated test generation, and streamlined code reviews.

Every scenario output reports:
- Time savings range
- Gross value range
- Net benefit range
- ROI percentage range
- Explicit assumptions and parameter benchmarks
