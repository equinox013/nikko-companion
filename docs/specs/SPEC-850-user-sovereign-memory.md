---
id: SPEC-850
title: User Sovereign Memory (USM) Protocol
status: authoritative
supersedes: []
depends_on: [SPEC-000, SPEC-800, SPEC-600, SPEC-700]
version: 1.0.0-draft
last_reviewed: 2026-05-09
---

# SPEC-850 — User Sovereign Memory (USM) Protocol

## Status

**Authoritative.** Introduced in Phase 2 as a Director-approved extension to the zero-retention model defined in [SPEC-800](./SPEC-800-data-lifecycle-privacy.md). Permitted under the USM Exception carve-out (REQ-800-023 through REQ-800-026).

---

## ⚠️ Public Codebase Disclaimer (Read First)

> **Nikko is an open-source research project.** The encryption implementation underlying the Personal Memory File feature is publicly visible in the repository. While AES-256-GCM encryption is cryptographically robust under current standards, no security guarantee is absolute. The following practices are **strongly recommended**:
>
> - **Do not store personally identifiable information (PII)** — full name, date of birth, government IDs, contact details, or any information that would identify you if the file were obtained by a third party.
> - **Store your memory file in a secure location** — not in a shared drive, cloud folder with broad access, or an unencrypted backup.
> - **Do not use a password you use elsewhere.** The key is derived from your password; reuse increases exposure risk.
> - **If you lose your password, your memory file is unrecoverable.** There is no reset mechanism. This is by design.
>
> The memory file is yours. Nikko's infrastructure never receives or touches it.

---

## 1. Purpose

[REQ-850-001] SPEC-850 MUST define the architecture, constraints, and lifecycle of the User Sovereign Memory (USM) system — an opt-in feature that allows users to maintain a locally stored, user-encrypted personal context file that Nikko can read during a session to provide continuity of support.

[REQ-850-002] USM exists to resolve the tension between the zero-retention model (SPEC-800 §4) and the user's legitimate interest in not re-explaining their history every session. It does so without creating any server-side data obligation.

[REQ-850-003] USM MUST NOT be framed as "Nikko remembering you." It SHALL be framed as "your personal journal that Nikko reads with your permission." The intelligence is static; the relationship evolves through user-owned records.

---

## 2. Core Principle

[REQ-850-004] USM is governed by the principle of **user sovereignty**: the user creates, controls, encrypts, transports, and deletes their memory file. Nikko's infrastructure has no awareness of, access to, or dependency on the file at any time.

[REQ-850-005] USM is **assistive context only**. Memory MUST NOT be treated as authoritative. Live session signals always supersede memory content. See §10 (Safety Constraints).

---

## 3. Opt-In Model (Mandatory)

[REQ-850-010] USM MUST be strictly opt-in. Nikko MUST NOT auto-save any memory without explicit user action.

[REQ-850-011] Memory entry creation MUST require a two-step user action:
1. Nikko proposes a memory item and asks for approval (e.g., *"Would you like me to note that grounding exercises tend to help you?"*).
2. The user explicitly confirms before anything is written.

[REQ-850-012] Nikko MUST NOT silently infer, collect, or buffer memory candidates. Proposal MUST happen at the turn boundary where the candidate is identified.

[REQ-850-013] The user MUST be able to disable USM at any time. Upon disabling, no further memory proposals SHALL be made and the local file is the user's responsibility to delete.

[REQ-850-014] USM availability MUST NOT affect how Nikko behaves toward users who do not enable it. The feature is additive, not load-bearing.

---

## 4. Data Classification — Permitted Content

[REQ-850-020] The following content types are **permitted** in a USM file:

| Section | Example entries |
|---------|----------------|
| `## User Preferences` | preferred tone (e.g., direct, gentle), communication style preferences |
| `## Emotional Patterns` | recurring themes the user has self-reported (e.g., "stress spikes during exam periods") |
| `## Mood Diary` | timestamped self-reported mood entries (e.g., `2026-05-09 | mood: low | energy: 3/10`) |
| `## Helpful Interventions` | coping strategies the user has found effective |
| `## Support Notes` | user-stated preferences for how Nikko responds (e.g., "prefers validation before information") |

[REQ-850-021] All permitted content MUST be written in first-person descriptive language: what the user reports about themselves, not what Nikko concludes about them.

[REQ-850-022] Mood diary entries MUST be user-initiated or explicitly user-approved. Nikko MAY prompt the user to add an entry but MUST NOT write one without confirmation.

---

## 5. Data Classification — Prohibited Content

[REQ-850-023] The following content types are **prohibited** from USM under any circumstances:

[REQ-850-024] **Crisis state labels and risk classifications.** USM MUST NOT contain any entry that records, summarizes, or references a crisis-level signal, active risk indicator, or suicidal ideation — regardless of how it is phrased. Example of prohibited content: *"User expressed suicidal ideation on 2026-05-09."* This prohibition exists because memory content becomes self-identity reinforcement across sessions; crisis-state persistence risks anchoring the model's perception of the user to a prior event that may have resolved.

[REQ-850-025] **Clinical diagnoses or diagnostic language.** USM MUST NOT contain entries that name, imply, or suggest a mental health diagnosis. Permitted: *"User reports anxiety during social situations."* Prohibited: *"User has social anxiety disorder."*

[REQ-850-026] **Predictive risk labels.** Entries that characterize the user as belonging to a risk category (e.g., "high-risk user," "self-harm history") are prohibited.

[REQ-850-027] **Raw conversation excerpts.** USM MUST NOT contain verbatim copies of conversation turns. Only distilled, user-approved summaries are permitted.

[REQ-850-028] **PII.** The system SHOULD NOT prompt users to include personally identifiable information. Nikko MUST warn users (per §12 and the disclaimer above) that PII in the file is their responsibility to protect.

---

## 6. Encryption Standard

[REQ-850-030] All USM file content MUST be encrypted before writing to disk. Plaintext USM files are not a supported format.

[REQ-850-031] The required encryption scheme is:
- **Algorithm:** AES-256-GCM (authenticated encryption — provides both confidentiality and integrity)
- **Key derivation:** PBKDF2-SHA-256 with a minimum of 310,000 iterations (NIST 2023 recommended minimum), or Argon2id with memory ≥ 64 MiB and time ≥ 3 iterations
- **Salt:** 16-byte cryptographically random salt, generated at file creation, stored in the file header (plaintext)
- **IV/Nonce:** 12-byte cryptographically random nonce per encryption operation, stored in the file header

[REQ-850-032] The encryption implementation MUST use the browser's native Web Crypto API (`window.crypto.subtle`). No third-party cryptographic libraries are permitted for the core encrypt/decrypt path. This ensures auditability against a known, browser-vendor-maintained implementation.

[REQ-850-033] The derived key MUST NOT be stored in memory beyond the duration of the active session. On session end, the key reference MUST be explicitly dereferenced.

[REQ-850-034] The file extension for an encrypted USM file MUST be `.nikko-mem.enc` to make its purpose and encrypted status unambiguous to the user.

---

## 7. Client-Side Processing Constraint (Absolute)

[REQ-850-040] All encryption and decryption operations MUST occur exclusively in the user's browser. No plaintext memory content MAY leave the client environment under any circumstances.

[REQ-850-041] The backend (Hugging Face Spaces inference endpoint or any successor) MUST NOT receive, process, log, or cache plaintext or ciphertext USM content. The file upload workflow (when the user loads their memory file) MUST be handled entirely in client-side JavaScript before any prompt construction occurs.

[REQ-850-042] If the architecture ever shifts to a model requiring server-side prompt assembly, USM MUST be disabled until a fully client-side injection pathway is re-established. This is not negotiable.

---

## 8. Memory File Format

[REQ-850-050] The decrypted content of a USM file MUST be valid Markdown conforming to the following section schema:

```markdown
# Nikko Personal Memory File
> Generated: YYYY-MM-DD | Version: 1.0

## User Preferences
<!-- Tone, communication style, what user wants Nikko to know about how they prefer to interact -->

## Emotional Patterns
<!-- Recurring themes, known triggers, self-reported patterns -->

## Mood Diary
<!-- Timestamped entries: YYYY-MM-DD | mood: <descriptor> | energy: <optional> -->
<!-- note: <optional free-text approved by user> -->

## Helpful Interventions
<!-- Coping strategies and responses the user has found effective -->

## Support Notes
<!-- Specific guidance for Nikko's response style based on user experience -->
```

[REQ-850-051] Each section is optional. An empty section MUST contain only its header and MAY contain the comment placeholder. Empty sections MUST NOT be removed (preserves structure for future entries).

[REQ-850-052] The file MUST include a generated date and schema version in the header comment. Schema versioning allows future Nikko versions to detect and migrate outdated file formats rather than silently misreading them.

[REQ-850-053] Entries within a section MUST be separated by a blank line. No entry may span more than 200 characters (this is a context injection size control, not a display constraint).

---

## 9. Memory Lifecycle

[REQ-850-060] The complete USM lifecycle is:

```
1. CREATION   — User clicks "Create Personal Memory File"
                → Password entry + confirmation
                → Empty encrypted file generated and downloaded

2. PROPOSAL   — During session, Nikko identifies a memory candidate
                → Nikko proposes the entry in natural language
                → User approves or declines

3. WRITE      — User approves
                → Entry appended to in-memory plaintext buffer
                → User prompted to save (re-encrypt + download) at session end

4. LOAD       — Next session, user uploads file
                → Password entry → local decryption → plaintext loaded to browser memory only

5. INJECT     — Compressed summary of memory content injected into system prompt
                → Size-limited per REQ-850-080 through REQ-850-084

6. RE-ENCRYPT — Session end or explicit user save
                → Buffer re-encrypted with same password + new random nonce
                → New ciphertext downloaded, replacing old file
```

[REQ-850-061] At no point in this lifecycle does the server receive plaintext content. Steps 1, 3, 4, 5, and 6 are browser-local operations.

[REQ-850-062] If the user declines to save at session end, any approved-but-unsaved entries are lost. Nikko MUST warn the user before the session ends if there are unsaved entries.

[REQ-850-063] File versioning is the user's responsibility. Nikko SHOULD warn on overwrite that the previous file will be replaced, and SHOULD recommend the user keep a backup copy.

---

## 10. Context Injection Protocol

[REQ-850-070] When a USM file is loaded, its content MUST be injected into the system prompt as a clearly delimited block, positioned after system instructions and before the conversation history.

[REQ-850-071] The injection block MUST carry an explicit header identifying it as user-provided personal context, not system-generated information:

```
<user_memory>
[User's personal memory file — user-authored context only]
...
</user_memory>
```

[REQ-850-072] Maximum injection size: 1,500 tokens. If the decrypted file exceeds this limit, the most-recent entries in each section MUST be prioritized. Older entries MUST be truncated, not silently dropped — Nikko MUST notify the user that their file has grown beyond the injection limit.

[REQ-850-073] Memory content MUST be treated as self-reported user context, not verified fact. The prompt injection MUST include an explicit instruction to the Interaction Model that memory content is user-authored and may be outdated, incomplete, or inaccurate.

[REQ-850-074] Memory content MUST NOT be referenced in Nikko's responses in a way that suggests Nikko independently recalled or discovered it (e.g., *"I remember you mentioned..."* is acceptable; *"I know you struggle with..."* is not).

---

## 11. Safety Constraints (Non-Negotiable)

[REQ-850-080] **Live signals always supersede memory.** The Signal Agent's real-time distress classification MUST NOT be influenced or suppressed by USM content. If a user's memory file indicates a history of low distress but the current turn produces crisis-level signals, Crisis Mode MUST activate normally.

[REQ-850-081] **Memory MUST NOT be used to downgrade crisis assessment.** A prior history of stability in the memory file is not a mitigating factor in crisis detection.

[REQ-850-082] **Memory MUST NOT be used to upgrade crisis assessment.** Conversely, a prior history of distress in the memory file MUST NOT cause the Signal Agent to classify a genuinely low-distress turn as higher risk. The Signal Agent operates on current-turn signals only.

[REQ-850-083] **The Evaluator MUST audit memory injection.** For every response where USM content was injected, the Evaluator (SPEC-200 §5.7) MUST verify that the response does not: (a) reference crisis-state history from memory, (b) use memory content to make clinical inferences, or (c) position Nikko as a continuous care provider based on memory continuity.

[REQ-850-084] **USM MUST be suspended during Crisis Mode.** When the system enters Crisis Mode (Level 3), memory injection MUST be halted for the duration of the crisis episode. Context window space must be reserved for crisis resources and stabilization content. USM resumes only after de-escalation (per SPEC-300 §9).

[REQ-850-085] **No memory of prior crisis events.** Even if a prior session resulted in a crisis episode and the user saved a mood diary entry from that session, the Evaluator MUST filter any such entry from the injection block before it reaches the Interaction Model. Crisis-adjacent content in USM is treated as prohibited per REQ-850-024.

---

## 12. Mandatory UI Disclosures

[REQ-850-090] Before the user creates their first USM file, the following disclosure MUST be acknowledged (checkbox or button):

> **Personal Memory File — What you're agreeing to:**
> - Your memory file is encrypted and stored only on your device. Nikko's servers never receive it.
> - Your password cannot be recovered. If lost, the file cannot be opened.
> - The encryption code is open-source and publicly visible. Do not include personally identifying information.
> - You control what goes in the file. Nikko will always ask before adding anything.
> - This feature is experimental and part of a research preview.

[REQ-850-091] The session UI MUST display a persistent indicator when a USM file is loaded (e.g., *"Personal memory active"*). Users MUST be able to see at a glance whether their memory is loaded into the current session.

[REQ-850-092] When Nikko proposes a memory entry, the proposal text MUST be clearly distinguished from Nikko's support response. It MUST be visually separate (e.g., a callout box) and include a clear Accept / Decline affordance. No memory action MUST ever be the default.

[REQ-850-093] At session end when unsaved entries exist, the UI MUST present a modal or equivalent blocking prompt: *"You have [N] unsaved memory entries. Save your updated memory file now, or these entries will be lost."*

---

## 13. SPEC-800 Relationship

[REQ-850-094] USM operates under the explicit exception granted by [REQ-800-023 through REQ-800-026](./SPEC-800-data-lifecycle-privacy.md#11-user-sovereign-memory-exception). The zero-retention model in SPEC-800 governs Nikko's server-side infrastructure. USM is user-controlled, client-side, and outside that perimeter.

[REQ-850-095] Any future change to SPEC-800's zero-retention model that would restrict client-side user file operations MUST be reviewed against this spec before ratification.

---

## 14. Success Criteria

[REQ-850-096] USM is correctly implemented when:
- A user can create, encrypt, download, re-upload, and decrypt a memory file without the Nikko backend ever touching the plaintext content
- All memory proposals require explicit user confirmation before writing
- Crisis Mode correctly suspends memory injection for its full duration
- The Evaluator correctly filters crisis-adjacent content from injection
- The public codebase disclaimer is visible and acknowledged before first use
- Memory injection respects the 1,500-token limit
- Session-end save prompt fires when unsaved entries exist
