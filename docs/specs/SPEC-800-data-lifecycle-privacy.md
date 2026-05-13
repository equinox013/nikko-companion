---
id: SPEC-800
title: Data Lifecycle & Privacy
status: authoritative
supersedes: []
depends_on: [SPEC-000, SPEC-600, SPEC-700]
version: 1.0.0-draft
last_reviewed: 2026-05-09
---

# SPEC-800 — Data Lifecycle & Privacy

## Status

**Authoritative.** Ratified 2026-05-09 as part of Director gaps deliberation (G-DATA-01, G-PRIVACY-01, G-AGE-01). Required deliverable before Phase 7 (deployment).

---

## 1. Purpose

[REQ-800-001] This specification defines the complete data lifecycle policy for Nikko, including what data is and is not collected, how session data is handled, and the privacy disclosures required in the user interface. It is binding across all system components.

---

## 2. Core Privacy Principle

[REQ-800-002] Nikko is a research-preview mental-health support system. The protection of user privacy is a first-order constraint, not a feature. This spec takes precedence over any operational convenience in matters of data handling.

[REQ-800-003] Nikko operates on a **zero-retention model**: no user conversation data is written to persistent storage under any circumstances.

---

## 3. Training Data Prohibition (Absolute Constraint)

[REQ-800-004] The system MUST NOT ingest, store, export, or use real user conversation data for model training. This constraint is permanent and irrevocable. It is not overridable by any phase gate, Director instruction, or engineering decision.

[REQ-800-005] Model training uses only pre-approved open-license corpora (see [SPEC-400 §4](./SPEC-400-model-training.md#4-dataset-stratification)). No pathway exists from production user sessions to the training pipeline.

---

## 4. Session Data Policy

[REQ-800-006] Conversation state (message history, signal classifications, routing decisions, adapter outputs) exists only in-memory within the active LLM context window for the duration of the session.

[REQ-800-007] All session data MUST be automatically purged when the user terminates the session (closes the chat window, navigates away, or explicitly ends the session). No session data persists beyond the active session boundary.

[REQ-800-008] No server-side database, cache (Redis or otherwise), file system, or logging service MAY receive conversation content, signal classifications, or routing decisions.

[REQ-800-009] Session continuity across browser refreshes is not supported in v0. If the user refreshes the page, the session resets. The UI MUST communicate this limitation (see REQ-800-015).

---

## 5. Operational Logs

[REQ-800-010] The system MAY maintain transient operational logs during an active session for debugging and observability (e.g., latency metrics, error codes, agent routing decisions without conversation content).

[REQ-800-011] Operational logs MUST NOT contain raw conversation text, user-identifiable information, signal classifications linked to conversation content, or any data that could reconstruct a user's session.

[REQ-800-012] All operational logs MUST be purged at session end, consistent with the session data policy (REQ-800-007).

---

## 6. Mandatory UI Disclosures

[REQ-800-013] The following disclosures MUST be displayed to the user before the chat interface is accessible. Presentation order is not mandated but all four MUST appear:

**Disclosure A — Geographic scope:**
> "Nikko is currently available in Australia only. Crisis resources shown are Australian services."

**Disclosure B — Research preview:**
> "Nikko is a research preview. It is not a substitute for professional mental health support."

**Disclosure C — Privacy statement:**
> "Your conversation is private. Nikko does not collect, store, or use your messages. No data leaves this session."

**Disclosure D — Session scope:**
> "Your conversation will be cleared if you close or refresh this page."

[REQ-800-014] Disclosures A, B, and C MUST appear as a mandatory acknowledgement step before the user can access the chat. The user MUST actively confirm (checkbox or button) before proceeding.

[REQ-800-015] Disclosure D MUST be persistently visible in the chat UI (e.g., footer or info banner) throughout the session.

---

## 7. Age Gate

[REQ-800-016] The user MUST confirm they are 18 years of age or older before accessing the chat interface. This self-attestation gate is a mandatory UI step that cannot be bypassed.

[REQ-800-017] Users who do not attest to being 18+ MUST NOT be granted access to the chat interface in v0.

[REQ-800-018] Age gate upgrade path (GA): Option 3 (minor-adapted mode with Kids Helpline foregrounded and parental-notice copy) is reserved for a future GA release. This requires separate Director approval and spec revision.

---

## 8. Australian Privacy Act Alignment

[REQ-800-019] Given the zero-retention model (REQ-800-003 to REQ-800-008), Nikko does not collect personal information as defined under the Australian Privacy Act 1988 (APP-1 to APP-13). The privacy disclosures in §6 satisfy APP-1 (open and transparent management of personal information) as a precautionary measure.

[REQ-800-020] If a future version accepts non-Australian users or introduces any form of data persistence, a full Australian Privacy Act compliance review and GDPR assessment MUST be completed before deployment. This spec must be revised accordingly.

---

## 9. Applicability to Future Phases

[REQ-800-021] This spec is binding from Phase 7 (deployment) forward. Any architectural component introduced in Phases 2–6 that would conflict with the zero-retention model MUST NOT be promoted to production without Director approval and a revision to this spec.

---

## 10. Success Criteria

[REQ-800-022] This spec is satisfied when:
- The chat interface is inaccessible without completing the disclosure acknowledgement and age gate
- No conversation data is written to any persistent store under any conditions
- Operational logs contain no conversation content
- All session data is purged on session termination

---

## 11. User Sovereign Memory Exception

[REQ-800-023] The zero-retention model (REQ-800-003 through REQ-800-008) governs **Nikko's server-side infrastructure and system components**. It does not prohibit user-initiated, user-controlled, client-side local file storage conducted entirely outside the server perimeter.

[REQ-800-024] The **User Sovereign Memory (USM)** feature, specified in [SPEC-850](./SPEC-850-user-sovereign-memory.md), is a permitted exception to the zero-retention model under the following conditions, all of which are binding:

- The feature MUST be strictly opt-in; no memory is created without explicit user action.
- All encryption and decryption MUST occur in the user's browser (client-side only). The server MUST NOT receive plaintext or ciphertext USM content at any point.
- USM files are stored on the user's local device. Nikko's infrastructure has no awareness of, access to, or dependency on these files.
- USM content MUST NEVER enter the model training pipeline. The training prohibition (REQ-800-004) remains absolute and is not affected by this exception.

[REQ-800-025] The phrase "under any circumstances" in REQ-800-003 and the phrase "no file-based persistence" in the G-MEMORY-01 ratification ([GAPS.md](../GAPS.md#g-memory-01--conversation-state-store)) are scoped to Nikko's server-side infrastructure. Client-side user-controlled files created under the conditions of SPEC-850 are outside that scope.

[REQ-800-026] If a future architectural change would require any USM ciphertext or plaintext to transit or be processed by the server, USM MUST be disabled until a fully client-side pathway is restored. This requirement supersedes any operational convenience argument.

---

## 12. USM UI Disclosure

[REQ-800-027] When USM is available in the product, the mandatory disclosures in §6 MUST be supplemented with **Disclosure E**:

**Disclosure E — Personal Memory File (displayed only if USM is implemented):**
> "Nikko offers an optional Personal Memory File. If you enable it, your notes are encrypted on your device and never sent to Nikko's servers. Your password cannot be recovered if lost. Do not store personally identifying information in this file."

[REQ-800-028] Disclosure E MUST appear in the pre-chat acknowledgement screen alongside Disclosures A through C. It is informational only and does not require a separate acknowledgement step beyond the one in REQ-800-014 — unless the user is actively enabling USM for the first time, in which case the dedicated USM disclosure (REQ-850-090) applies.
