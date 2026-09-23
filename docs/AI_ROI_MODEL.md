# GAIN AI Economic ROI Model

**Author:** Lead Implementation Architect & AI Analytics Specialist  
**Status:** Approved & Implemented (DORA 2026 Specification Alignment)  
**Authoritative References:** `docs/MASTER_SPEC.md` Section 12, `docs/REFERENCE_ARCHITECTURE.md`, Google Cloud DORA *The ROI of AI-assisted Software Development* (v. 2026.1)

---

## 1. Economic Framework & Separation of Concerns

GAIN strictly separates economic return modeling into four distinct stages:

$$\text{Measurement} \longrightarrow \text{Attribution} \longrightarrow \text{Economic Modeling} \longrightarrow \text{Scenario Analysis}$$

1. **Measurement**: Observable, empirical delivery flow metrics (PR cycle time, throughput, CFR, FDRT) derived from canonical telemetry.
2. **Attribution**: The fraction of measured efficiency change legitimately linked to the AI developer tool (excluding natural speedups, seasonal lulls, or team shifts).
3. **Economic Modeling**: Transformation of attributed engineering capacity, feature optionality, and stability impacts into monetary equivalents using explicit cost parameters.
4. **Scenario Analysis**: Multi-tier sensitivity bounds (`conservative`, `expected`, `optimistic`) providing executive leadership with realistic risk envelopes rather than single-point forecasts.

All financial outputs must be explicitly classified as **`Modeled`** claims (`ClaimClassification.MODELED`).

---

## 2. DORA 2026 Two-Ledger Economic Architecture

GAIN implements the Google Cloud DORA 2026 two-ledger framework, accounting for direct tooling expenses, adoption disruption costs, reclaimed innovation capacity, accelerated feature value, and production instability drag.

### Ledger A: Total First-Year Investment ($I_{\text{total}}$)

$$I_{\text{total}} = I_{\text{hard}} + I_{\text{j\_curve}}$$

#### 2.1 Direct Hard Costs ($I_{\text{hard}}$)
$$I_{\text{hard}} = \Big(\big(C_{\text{license}} + C_{\text{tokens}} + C_{\text{training}}\big) \times N_{\text{FTE}}\Big) + C_{\text{infra}}$$
- $N_{\text{FTE}}$: Technical staff size in full-time employees.
- $C_{\text{license}}$: Annual base license cost per user (benchmark: \$250/yr).
- $C_{\text{tokens}}$: Additional variable token/API usage per user (benchmark: \$80/yr).
- $C_{\text{training}}$: Enablement, onboarding, and context engineering training per user (benchmark: \$9,600/yr).
- $C_{\text{infra}}$: Enterprise infrastructure and monitoring support (benchmark: \$100,000/yr).

#### 2.2 J-Curve Tuition Cost ($I_{\text{j\_curve}}$)
Adopting AI introduces temporary workflow disruption, learning friction, and code review adjustment:
$$I_{\text{j\_curve}} = N_{\text{FTE}} \times S_{\text{loaded}} \times \delta_{\text{drop}} \times \left(\frac{M_{\text{duration}}}{12}\right)$$
- $S_{\text{loaded}}$: Average fully loaded annual engineer salary (benchmark: \$176,000).
- $\delta_{\text{drop}}$: Temporary productivity drop percentage (benchmark: 15%).
- $M_{\text{duration}}$: Expected learning phase timeline in months (benchmark: 3 months).

---

### Ledger B: Total Annual Gross Value ($V_{\text{total}}$)

$$V_{\text{total}} = V_{\text{capacity}} + V_{\text{features}} + V_{\text{stability}}$$

#### 2.3 Headcount Reinvestment Capacity ($V_{\text{capacity}}$)
Capacity freed by AI is modeled as *headcount reinvestment* for innovation (avoided hiring), **never** as payroll cost-cutting:
$$V_{\text{capacity}} = N_{\text{FTE}} \times S_{\text{loaded}} \times \tau_{\text{net\_saved}}$$
- $\tau_{\text{net\_saved}}$: Net productivity gain per developer, strictly net of the **Verification Tax** (benchmark: 12.5% or ~1 hr/day).

#### 2.4 Accelerated Feature Innovation Lift ($V_{\text{features}}$)
Captures the financial optionality created by lower prototyping friction:
$$V_{\text{features}} = \Delta F \times R_{\text{success}} \times \Delta R_{\text{impact}} \times P_{\text{revenue}}$$
- $\Delta F$: Incremental user features deployed per year ($F_{\text{target}} - F_{\text{current}}$).
- $R_{\text{success}}$: Idea success rate (benchmark: 33%).
- $\Delta R_{\text{impact}}$: Revenue lift per successful feature (benchmark: 0.5%).
- $P_{\text{revenue}}$: Software portfolio annual revenue (benchmark: \$100,000,000).

#### 2.5 Downtime Stability Impact / Instability Tax ($V_{\text{stability}}$)
Increased code volume without mature guardrails increases Change Failure Rate (CFR), creating an *Instability Tax*:
$$V_{\text{stability}} = \big(D_0 \times \text{CFR}_0 \times \text{FDRT} \times C_{\text{downtime}}\big) - \big(D_1 \times \text{CFR}_1 \times \text{FDRT} \times C_{\text{downtime}}\big)$$
- $D_0, D_1$: Current vs. projected annual deployments.
- $\text{CFR}_0, \text{CFR}_1$: Current vs. projected Change Failure Rate.
- $\text{FDRT}$: Failed Deployment Recovery Time in hours.
- $C_{\text{downtime}}$: Cost of system downtime per hour.
*Note: If AI increases CFR without automated testing, $V_{\text{stability}}$ is negative and offsets capacity gains.*

---

### Ledger C: Economic Synthesis

$$\text{First-Year Net Benefit} = V_{\text{total}} - I_{\text{total}}$$

$$\text{First-Year ROI (\%)} = \left(\frac{\text{First-Year Net Benefit}}{I_{\text{total}}}\right) \times 100\%$$

$$\text{Payback Period (Years)} = \frac{I_{\text{total}}}{V_{\text{total}}} \quad (\text{for } V_{\text{total}} > 0)$$

---

## 3. Asymmetric Sensitivity Scenarios (DORA 2026)

To prevent misleading single-point precision, GAIN models risk envelopes:

| Scenario | Value Multiplier | Cost Multiplier | Rationale |
| :--- | :---: | :---: | :--- |
| **Conservative** | $0.8\times$ | $1.5\times$ | Accounts for slower adoption, high verification tax, review bottlenecks, and elevated training overhead. |
| **Expected** | $1.0\times$ | $1.0\times$ | Standard enterprise adoption trajectory with mature CI/CD. |
| **Optimistic** | $1.2\times$ | $0.8\times$ | Elite team execution, high prompt proficiency, automated testing guardrails, and low review friction. |

---

## 4. Operational Interfaces

- **Python Service**: `AIROIService.calculate_roi_scenario()` in `src/gain/services/ai_roi.py`
- **CLI Commands**:
  - `gain ai-roi --help`
  - `gain ai-roi --population enterprise-org --staff-size 500 --format summary`
  - `gain ai-impact --repo firmsoil/gain --format summary`
- **MCP Tool**: `calculate_ai_roi` in `src/gain/mcp/tools/ai.py`
