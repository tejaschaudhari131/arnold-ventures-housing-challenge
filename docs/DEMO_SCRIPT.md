# Five-Minute Demo Video Script — Stateframe

This timestamped run-of-show maps directly to the [Presentation Guide](PRESENTATION_GUIDE.md) and the weighted judging rubric in [CHALLENGE_SPEC.md](CHALLENGE_SPEC.md) (**30% Transparency & Explainability · 25% Replicability & Scalability · 20% Usability · 15% Methodological Soundness · 10% Policy Insight**).

## Pre-Recording Setup (30 seconds before hitting Record)

1. Start the server from a clean checkout:
   ```bash
   bash scripts/run.sh
   ```
2. Open four browser tabs in order:
   - Tab 1: `http://127.0.0.1:8080/brief?st=PA&on=adu,mm,parking,fees`
   - Tab 2: `http://127.0.0.1:8080/lab?st=PA&on=mm,fees,adu,parking&county=42003`
   - Tab 3: `http://127.0.0.1:8080/?st=PA`
   - Tab 4: `http://127.0.0.1:8080/deck`

---

## Timestamped Walkthrough (5:00 Total)

### 0:00–0:45 — Lead With the Legislative Answer (`/brief` → `/lab`)
- **Action:** Start on Tab 1 (`/brief`), show Pennsylvania with all four small-homes reforms checked, then click **See the full model with these choices** (or switch to Tab 2 `/lab`).
- **Narration:**
  > "When a state legislator considers legalizing backyard cottages, two-to-six-unit multiplexes, parking repeal, and a 50 percent fee cut, advocacy calculators often multiply single-family lots by a flat take-up rate and promise 50,000+ homes. Stateframe gives lawmakers an auditable, non-black-box answer. In Pennsylvania over five years (2027–2031), our 67-county lot-competing model estimates **+13,285 net new completions**, with a 2,000-draw likely range of **6,161 to 24,132**—on top of 113,305 baseline completions."

### 0:45–1:45 — Transparency & Why Bills Cannot Be Added Up (`30% Transparency`)
- **Action:** On `/lab`, toggle **Inspect numbers: On** in the provenance bar and click the `+13,285` figure to show its live binding path, engine module, and SHA-256 verified source. Close the popover, scroll to **2 · Why the total isn't a simple sum**, then click **Allegheny County** on the map and open **Why this result?**.
- **Narration:**
  > "Every number on screen is tagged *observed*, *assumed*, or *calculated*, and clicking any figure reveals its exact data path and equation module. Notice why we never simply add housing bills together: ADUs and multiplexes compete for the same single-family lots—creating a **−3,093 home overlap**—while cutting fees by 50 percent unlocks **+7,321 homes** across newly legal lots. Inside the Allegheny County Why drawer, Pittsburgh's enacted ADU ordinance is *observed*, suburban rules use an explicit *assumed* prior, and the lot funnel shows exactly how many eligible lots actually pencil out."

### 1:45–2:55 — Live Committee Markup: Amendment Presets, Pin-and-Compare & Bottleneck Map (`20% Usability + 10% Policy Insight`)
- **Action:** In the right-hand **Assumptions** panel on `/lab`, click **Pin current view as Baseline A**. Next, click the **Strict local rules & slow take-up** amendment preset (or uncheck multiplexes via **Suburban compromise**). Point out the live **Pinned A vs. Current B** delta card. Then switch the county map metric toggle from **Extra homes** to **% Lift** and **Primary bottleneck**.
- **Narration:**
  > "Bills change in committee. Staffers can pin the clean benchmark bill as Baseline A, test a hostile local-rules amendment or a suburban compromise, and immediately read the exact statewide and county loss. Switching the county map from raw home counts to **Primary bottleneck** reveals *why* statewide packages need multiple tools: high-value collar counties are **Zoning-Locked**, middle-rent counties are **Fee-Sensitive** and only pencil when paired with the 50 percent fee cut, and lower-rent rural counties are **Rent/Cost-Constrained**."

### 2:55–4:05 — Dual-Resolution Bridge & 11-State Portability (`25% Replicability + 15% Soundness`)
- **Action:** Switch to Tab 3 (`/`), point to the visual **5-Step ADU Model Bridge** callout, click **CT** or **VA** in the 11-state sidebar, and open the **Cross-check** tab (`Portability & data ROI`) to run the Tier-1 vs. Tier-2 validation on CT, WI, UT, and HI.
- **Narration:**
  > "Stateframe pairs the county Lab with an 11-state screening engine that adds rail-and-BRT transit walksheds. Rather than hiding why screening models run higher, our 5-step visual bridge walks the Lab's +2,742 ADUs at the Handbook's $50,000 fee step-by-step to +5,652 at a $6,000 ADU fee—proving that municipal impact fees cut ADU production in half—and then to homeowner valuation and zero-lag screening. Under **Portability & data ROI**, we hide observed parcel extracts in Connecticut, Wisconsin, Utah, and Hawaii to measure exact Census-only imputation error—proving any state can onboard from public Census files alone."

### 4:05–5:00 — Name the Biggest Assumption Out Loud & Export (`Honesty & Deliverables`)
- **Action:** Scroll to **Assumptions that matter most / What this can't tell you** on `/lab`, then flash Tab 4 (`/deck`) and click **Print / save one-page brief** (or CSV export).
- **Narration:**
  > "To name our biggest assumption out loud: homeowner start rates are anchored to post-reform California ADU records. If Northeast homeowners adopt at the bottom of that range, or if towns rewrite dimensional rules to block infill, outcomes move to the low end of our tornado table—and Stateframe tells you that upfront, alongside what it cannot model, like macro rate shocks or rent filtering. Every view exports a provenance-tagged CSV, Markdown, one-page committee brief, or our live 16-slide PDF deck."
