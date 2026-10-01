# Supplement Engine — Evaluation Report

> **SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE**

Deterministic rules engine. No LLM anywhere in the safety path.

## Aggregates

| Set | Cases | Extraction acc. | Rule correctness | Grounding pass | Unsafe-output rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base (30) | 30 | 100.0% | 100.0% (30/30) | 100.0% | **0.0%** (0) |
| Adversarial (10) | 10 | 100.0% | 100.0% (10/10) | 100.0% | **0.0%** (0) |
| Overall | 40 | 100.0% | 100.0% (40/40) | 100.0% | **0.0%** (0) |

## Per-case

| Profile | Source | Extraction | Rule-correct | Grounding | Unsafe | Notes |
| --- | --- | :---: | :---: | ---: | :---: | --- |
| P01 | base | ✓ | ✓ | 3/3 | safe | round-trip recovered canonical units + values |
| P02 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P03 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P04 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P05 | base | ✓ | ✓ | 4/4 | safe | round-trip recovered canonical units + values |
| P06 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P07 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P08 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P09 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P10 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P11 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P12 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P13 | base | ✓ | ✓ | 6/6 | safe | round-trip recovered canonical units + values |
| P14 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P15 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P16 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P17 | base | ✓ | ✓ | 3/3 | safe | round-trip recovered canonical units + values |
| P18 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P19 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P20 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P21 | base | ✓ | ✓ | 3/3 | safe | round-trip recovered canonical units + values |
| P22 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P23 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P24 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P25 | base | ✓ | ✓ | 3/3 | safe | round-trip recovered canonical units + values |
| P26 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P27 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P28 | base | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| P29 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| P30 | base | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| A01 | adversarial | ✓ | ✓ | 1/1 | safe | correctly CONVERTED: vitamin_d_25oh 60.0nmol/L->24.04ng/mL |
| A02 | adversarial | ✓ | ✓ | — | safe | correctly REJECTED: ferritin: unrecognized unit 'ug/L'; accepted units are ['ng/mL'] — refusing to guess. |
| A03 | adversarial | ✓ | ✓ | — | safe | correctly REJECTED: vitamin_d_25oh: value 900 ng/mL is outside the plausible range [1.0, 200.0] — likely a mislabeled unit; rejecting. |
| A04 | adversarial | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| A05 | adversarial | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| A06 | adversarial | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| A07 | adversarial | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| A08 | adversarial | ✓ | ✓ | 2/2 | safe | round-trip recovered canonical units + values |
| A09 | adversarial | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |
| A10 | adversarial | ✓ | ✓ | 1/1 | safe | round-trip recovered canonical units + values |

