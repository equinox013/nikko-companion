---
id: SPEC-810
title: Release Governance
status: authoritative
supersedes: []
depends_on: [SPEC-000, SPEC-400, SPEC-500, SPEC-600]
version: 1.0.0-draft
last_reviewed: 2026-05-09
---

# SPEC-810 — Release Governance

## Status

**Authoritative.** Ratified 2026-05-09 as part of Director gaps deliberation (G-RELEASE-01). Required deliverable before Phase 7 (deployment).

---

## 1. Purpose

[REQ-810-001] This specification defines the governance process for promoting new adapter versions, base model updates, and configuration changes to production. For a safety-critical mental-health system, an unsupervised model update is equivalent to deploying untested code into the Crisis response path.

---

## 2. Core Governance Principle

[REQ-810-002] No change that affects model inference output — including adapter weight updates, base model changes, prompt template changes, and routing configuration changes — MAY be deployed to production without completing the release gate defined in this spec.

---

## 3. Release Gate Requirements

[REQ-810-003] Before any release is promoted to production, ALL of the following conditions MUST be met:

1. **Full regression suite:** The complete SPEC-500 evaluation suite MUST pass with a composite score ≥ 0.85 and no hard-fail conditions triggered (see [SPEC-500 §7](./SPEC-500-evaluation-benchmarking.md#7-hard-failure-conditions)).

2. **Canary deployment:** The candidate release MUST be deployed to the staging environment and tested against synthetic crisis traffic (representative adversarial and genuine crisis scenarios) for a minimum of one evaluation cycle before production promotion.

3. **Director sign-off:** The Director MUST explicitly approve the release after reviewing the regression results and canary outcomes. Sign-off MUST be recorded with a timestamp and the regression suite version used.

4. **Safety adapter gate:** Any release that modifies the Safety adapter — including weight changes, fine-tuning, prompt changes, or combination rules — requires a SEPARATE Director sign-off for the Safety adapter change specifically, in addition to the general release sign-off (Condition 3 above).

---

## 4. Auto-Rollback Policy

[REQ-810-004] Automatic rollback is triggered when any of the following drift-detection conditions are met post-deployment (see [SPEC-600 §16](./SPEC-600-deployment-architecture.md#16-monitoring--drift-detection)):
- Composite evaluation score drops below 0.85 on the live monitoring suite
- Crisis handling score drops below its Phase 6 baseline by more than 0.05
- Any hard-fail condition in SPEC-500 §7 is triggered on live traffic
- Missed-crisis signal rate exceeds 0.5% on monitored live sessions

[REQ-810-005] Rollback MUST restore the previous production release within the latency window defined in [SPEC-600 §12](./SPEC-600-deployment-architecture.md#12-latency-constraints). Manual rollback can also be initiated by the Director at any time via the override mechanism ([SPEC-600 §17](./SPEC-600-deployment-architecture.md#17-human-override-mechanism)).

---

## 5. Model Card Requirement

[REQ-810-006] Every production release MUST be accompanied by a model card documenting:
- Base model identity and version
- Adapter versions and training dataset references
- Evaluation results (full SPEC-500 suite) from the release gate run
- Known limitations and failure modes observed during canary testing
- Director sign-off timestamp and release version

[REQ-810-007] Model cards MUST be stored in `docs/releases/` in the repository and committed before the production deployment is made.

---

## 6. Versioning

[REQ-810-008] Production releases follow semantic versioning: `MAJOR.MINOR.PATCH`. A change to the Safety adapter constitutes at minimum a MINOR version bump. A change to the base model constitutes a MAJOR version bump.

[REQ-810-009] The version identifier of the currently deployed model MUST be visible in the UI (e.g., in a footer or info panel) for transparency.

---

## 7. Scope Boundaries

[REQ-810-010] This spec applies to all production deployments. It does not govern staging or local development environments, which may be updated freely. However, canary testing on staging (REQ-810-003 Condition 2) is a required step of the release gate.

---

## 8. Success Criteria

[REQ-810-011] This spec is satisfied when:
- No production release occurs without passing the full release gate (REQ-810-003)
- Auto-rollback is tested and verified before the first production deployment
- Model cards exist for all production releases
- Director sign-off records are auditable
