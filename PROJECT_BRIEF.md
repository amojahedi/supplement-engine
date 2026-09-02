# Supplement Reasoning Engine — Project Brief

> **⚠️ SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE**
> This project operates exclusively over synthetic patient profiles and is never for clinical use. This constraint is **structural** — enforced in code and visible in the UI — not a disclaimer bolted on.

A research prototype: a supplement reasoning engine over synthetic patient profiles.

## The One Architectural Rule

**Safety logic lives in deterministic Python code, never in a prompt.**

- The LLM may **explain, prioritize, and phrase**.
- The LLM may **never** decide whether something is safe, and may **never** produce a dose.
- Any statement not backed by a rule hit or a cited passage **does not ship**.

---

## Phase 1 — Synthetic Data

30 patient profiles. Each profile includes:

- **Lab panel:** ferritin, 25-OH vitamin D, B12, folate, TSH, HbA1c, lipids
- **Current medications:** with real, documented interactions
- **Intake answers:** diet, sun exposure, pregnancy status, GI conditions, age, sex

Hand-write the **expected output for each profile as ground truth**.

The set must cover:
- Conflicting deficiencies where **priority matters**
- A **contraindication** blocking an otherwise obvious recommendation
- Values **just inside range** that should **not** trigger
- At least one profile where the right answer is **"refer to a clinician, recommend nothing"**
- One **pregnancy** case

Format: **JSON**, with **reproducible generation logic**.

---

## Phase 2 — Backend

**Stack:** Python, FastAPI, Pydantic, SQLite, pytest. **No agent frameworks** — build orchestration yourself.

Five stages:

1. **Extraction** — Parse lab text and questionnaire into a typed Pydantic profile. **Reject rather than guess** on ambiguous units — mg/dL vs nmol/L is a **2.5x silent error**.
2. **Rules engine** — Pure, tested Python with **zero LLM involvement**:
   - Age- and sex-aware reference ranges
   - Tolerable Upper Intake Levels (ULs) as **hard ceilings**
   - An interaction table covering **supplement–medication**, **supplement–supplement**, and **supplement–condition**
   - Escalation rules that **force a clinician referral and suppress all other output**
3. **Retrieval** — Over **NIH Office of Dietary Supplements** fact sheets, chunked small enough to verify a claim against.
4. **Generation** — From rule hits plus retrieved passages. **Structured output only.**
5. **Grounding guard** — Verifies every claim and number traces to a rule hit or cited passage, **drops what doesn't**, and **logs each drop with its reason**.

---

## Phase 3 — Evaluation

Score all **30 profiles** on:
- Extraction accuracy
- Rule correctness
- Grounding pass rate
- **Unsafe-output rate — must be zero**

Add **10 adversarial profiles** designed to induce bad recommendations via:
- Misleading units
- An easily-overlooked medication
- A plausible but wrong deficiency pattern
- An alarming-looking but age-appropriate value

Add an **ablation run** with the rules engine disabled and the LLM deciding alone; report the degradation.

Log **every LLM call, tool result, rule hit, and dropped claim** to SQLite, with a **CLI to replay any case offline**.

---

## Phase 4 — Frontend

**Stack:** Next.js, TypeScript, Tailwind. **Designed, not templated.**

**Design thesis:** Most AI demos hide the pipeline and show a chat bubble. This one makes the machinery **legible** so the user can **doubt the system**.

**Three panes:**
- **Left** — Profile selector with **badges for hard and adversarial cases**.
- **Center** — The reasoning trace as an **expandable vertical pipeline** (extraction → rule hits → retrieval → generation → guard), showing each step's input, output, and timing, with **dropped claims struck through and their reason shown**.
- **Right** — The final output, where **every claim links to its source**, and **hovering highlights the backing rule hit or passage**.

**Plus:**
- An **eval view** with the results table, ablation chart, and adversarial pass/fail
- A **persistent, non-dismissible banner**: *synthetic data, research prototype, not medical advice*
- Keyboard navigation
- Dark mode
- Real **empty, error, and loading** states

---

## Build Order

1. Synthetic profiles and ground truth
2. Rules engine and tests
3. Extraction
4. Retrieval and grounding guard
5. Eval harness, adversarial set, and ablation
6. **Frontend last**

**Do not start the frontend before the eval harness runs.**

---

## README Requirements

The README must include:
- The problem, in two sentences
- The **synthetic-data / research-only statement at the very top**
- Why **safety-in-code** rather than safety-in-prompt
- An architecture diagram
- The eval table
- The ablation result
- What broke during development
- Honest limitations
