# ADR 0026 · Human ownership of core artefacts; AI lane cap; explain-back at every major checkpoint

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d, where the roles below are mapped to names |
| Date | 2026-10-12 |
| Veto-able | Which artefacts are hand-written and the lane cap: yes. A named human owner per core artefact: no |
| Related | `02-architecture.md` §2.4; `06-build-plan.md` §3, §5.8, §7; ADR 0001, ADR 0004, ADR 0008, ADR 0009 |

## Context

Rule 13: "Projects that are entirely generated using AI without meaningful participant contribution, verification, or technical understanding may be rejected." Rule 12 requires the team to explain the graph model, the queries, the architecture and the decisions. The v1.1 build plan used up to six parallel AI build agents, about 30 human hours for 40 task cards, an explain-back session only on D4 after everything was built, AI-drafted ADRs marked "Accepted", and pre-event `docs/AI_USAGE.md` rows that say "No human decision yet". The team roster is not yet known. The model the team must explain is large (`03`: 39 labels, 84 relationship types).

## Decision

- **Named human owners** (roles mapped to names at HUM-00d, written into `docs/team/team-charter-and-raci.md` and the README):

| Artefact | Owner role | What the human does |
|---|---|---|
| Graph schema module (labels, edge types, key builders, property allow-list) | H-Lead | writes it by hand; an agent may add tests in a separate commit |
| Normalisation map (`01` Q4 status/stage map; Q8 reference resolution order) | H-Data/Eval | writes the table and its unit cases |
| Cypher templates of `find_contradictions`, `trace_decision`, `kep_relations`, `path_between` and the `find_entities` nearest match | one member per template | writes the template; agents write models, mappers, tests |
| ACL role table and the `acl-init` contract | H-Lead | decides, reviews, records the ACL test results |
| Claim validator rules | H-Review | writes the rules and the abstention cases |
| Ground truth re-verification, findings precision labels, judge calibration | H-Data/Eval | labels and signs the frozen run |
| README "Why a graph" and the substitution table | H-Demo | writes the prose from `02` §14 |

- **At most three agent lanes** at any time (infra/CI; ingestion; web or agent), down from six.
- **Explain-back at every checkpoint from CP1**: full sessions at CP1 (D1) and CP4 (D2); a long session at CP7 (D4). Each member explains their own area without notes (graph model and keys; the hand-written templates; the architecture and identities; the eval and its losses); gaps are fixed the same day; each session is a row in `docs/AI_USAGE.md` naming who explained what and what was corrected.
- **`docs/AI_USAGE.md` rows** must name a concrete human edit or check (a file and what changed, or a test run and its result); a row that only says "reviewed" is sent back. Before the repository goes public at CP4, H-Lead rewrites the pre-event rows so each states what humans decided (concept and master track, SIG scope, which ADRs were ratified, changed or vetoed) and that the design notes were AI-drafted.
- **ADR status**: every AI-drafted ADR stays Proposed until a named human ratifies it (ADR 0001).
- **Human hours** (INFERENCE): v1.1's ≈ 30 hours plus ≈ 3 for the schema module, ≈ 5 for the five templates, ≈ 1.5 for the normalisation map, ≈ 1 for findings labels and ≈ 2.25 per member for three explain-backs: ≈ 43 hours for a one-person team; ≈ 50 hours in total for four people (≈ 12.5 each).

## Alternatives considered

- Six agent lanes with human review only (v1.1): fastest, but the human contribution on record is review rows, which Rule 13 does not obviously count as "meaningful participant contribution".
- Humans write everything: not feasible in four days for a team of unknown size.
- One explain-back on D4: finds gaps after the video script is fixed.

## Consequences

- The five judge-path queries, the schema and the normalisation map are human commits that the authors can explain line by line, which is what judges ask about.
- The schedule loses some parallelism; `06` re-plans GR-01 and the five templates as human cards.

## Revision 2026-10-12

New (design review R2).
