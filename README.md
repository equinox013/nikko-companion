# Nikko — Evidence-Grounded Wellbeing Assistant

A safety-aligned, evidence-grounded LLM ecosystem designed to function as a compassionate digital confidant — never therapy, never diagnosis, never treatment.

> *Nikko is sunlight at the end of the tunnel: it illuminates possible paths, but the user must always walk toward human support themselves.*

## Status

**Phase 1 — Specification Initialization.** All implementation is gated behind formal Markdown specifications in [`docs/specs/`](docs/specs/). No code yet.

## Where to start

| If you are… | Read |
|------|------|
| A new contributor | [`CLAUDE.md`](CLAUDE.md) — project operating manual |
| Architecting a feature | [`docs/INDEX.md`](docs/INDEX.md) — full spec map |
| Reviewing safety boundaries | [`docs/specs/SPEC-000-charter.md`](docs/specs/SPEC-000-charter.md) — the System Charter |
| Implementing the runtime | [`docs/specs/SPEC-700-execution-pipeline.md`](docs/specs/SPEC-700-execution-pipeline.md) — end-to-end execution trace |
| Reviewing open questions | [`docs/GAPS.md`](docs/GAPS.md) — unresolved Director questions |

## Core constraints (read once, then internalize)

- **Non-clinical:** Nikko never diagnoses, treats, or prescribes.
- **Spec-driven:** if it is not in a spec, it does not exist.
- **Crisis-first:** any crisis signal preempts every other workflow.
- **Evidence-bound:** medical knowledge is retrieved, never embedded in model weights.
- **Australian crisis resources** are baseline. See `G-CRISIS-01` in `GAPS.md` for the international fallback question.

## License

Proprietary / unreleased. Do not redistribute the spec set without Director approval.
