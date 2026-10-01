"""
Phase 3 — Evaluation harness, adversarial set, and ablation.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Everything here is deterministic Python. No LLM, no network. The harness scores
the deterministic engine; the ablation stands in a deliberately-naive decider
(the "model deciding alone") to quantify the safety gap the rules engine closes.
"""
