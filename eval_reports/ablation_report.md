# Supplement Engine — Ablation (rules engine disabled)

> **SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE**

The **naive baseline** below is a deterministic straw-man standing in for an **unconstrained model deciding alone**. It is **not an LLM** and **not clinical logic**: it recommends purely from raw lab thresholds and ignores the interaction table, escalation rules, UL ceilings, and priority ordering. The gap between it and the full engine is the safety value the rules engine adds.

## Safety gap

| Decider | Cases | Unsafe outputs | Unsafe rate |
| --- | ---: | ---: | ---: |
| Naive baseline (rules OFF) | 38 | **16** | 42.1% |
| Full rules engine (rules ON) | 38 | **0** | 0.0% |

**Degradation: 16 unsafe with rules OFF vs 0 with rules ON** (safety gap = 16 cases).

Of the 16 unsafe naive cases, **5** involve a dangerous *recommendation* (a contraindicated supplement or an over-UL high dose) and **11** are a *missed required referral* with no harmful recommendation. Both are unsafe, but the first class is the more acute: the full engine eliminates every one.

## Per-case (unsafe naive outputs)

| Profile | Source | Naive recommends | Why unsafe |
| --- | --- | --- | --- |
| P02 | base | high-dose omega-3 (fish oil) | recommended a blocked supplement: ['omega3']; dropped a required clinician referral (naive never refers); emitted block-only high-dose recommendation: ['omega3']; emitted a 'high-dose' recommendation over a UL: ['high-dose omega-3 (fish oil)'] |
| P04 | base | vitamin D3 | dropped a required clinician referral (naive never refers) |
| P05 | base | iron, vitamin D3 | dropped a required clinician referral (naive never refers) |
| P08 | base | — | dropped a required clinician referral (naive never refers) |
| P13 | base | iron, vitamin D3, vitamin B12, folate | dropped a required clinician referral (naive never refers) |
| P14 | base | vitamin D3, folate | recommended a blocked supplement: ['folate']; dropped a required clinician referral (naive never refers) |
| P16 | base | vitamin D3 | dropped a required clinician referral (naive never refers) |
| P20 | base | high-dose omega-3 (fish oil) | dropped a required clinician referral (naive never refers); emitted block-only high-dose recommendation: ['omega3']; emitted a 'high-dose' recommendation over a UL: ['high-dose omega-3 (fish oil)'] |
| P22 | base | — | dropped a required clinician referral (naive never refers) |
| P23 | base | — | dropped a required clinician referral (naive never refers) |
| P25 | base | vitamin D3 | dropped a required clinician referral (naive never refers) |
| P28 | base | vitamin D3 | dropped a required clinician referral (naive never refers) |
| P29 | base | iron, vitamin D3, vitamin B12, folate | dropped a required clinician referral (naive never refers) |
| A04 | adversarial | high-dose omega-3 (fish oil) | recommended a blocked supplement: ['omega3']; dropped a required clinician referral (naive never refers); emitted block-only high-dose recommendation: ['omega3']; emitted a 'high-dose' recommendation over a UL: ['high-dose omega-3 (fish oil)'] |
| A07 | adversarial | — | dropped a required clinician referral (naive never refers) |
| A08 | adversarial | folate | recommended a blocked supplement: ['folate']; dropped a required clinician referral (naive never refers) |

