# ADR 0019 · Data scope: three SIGs, P0 tickets

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12; adopts `01-recon-kubernetes-data.md` §7). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Yes (SIG swap; P1 on) |
| Related | `02-architecture.md` §1.4, §9; ADR 0007 |

## Context

The prep context recommends 2–3 SIGs. KEPs per `owning-sig` (`01` §3.6, n = 684): sig-node 139, sig-api-machinery 86, sig-storage 69, sig-network 62, sig-scheduling 58, sig-auth 36, sig-cli 35, sig-apps 35. Organiser advice: one narrow job finished end to end beats a broad platform. `01` §7.1 compares the candidates on status spread, participating-SIG edges, tracking issues, PRR files, commit depth, OWNERS files and KEP-linked items.

## Decision

`sig-node`, `sig-scheduling`, `sig-apps` (232 KEPs) plus about 5 stub KEPs they reference, configured by `SIGS`. Tickets: **P0 only by default** (`TICKETS_SCOPE=p0`): ≈ 575 tracking issues and ≈ 1,600 enhancements PRs with threads, reviews and label/milestone history. P1 (≈ 2,600 `kubernetes/kubernetes` items that reference a tracking issue) is a switch; when on, it is a load-time snapshot (ADR 0007). P2 (all 8,510 SIG-labelled k/k items) is out of scope.

- `sig-node` has the deepest decision history (2,291 commits under `keps/sig-node`; in-place pod resize with 28 metadata commits; withdrawn classic DRA) and 129 PRR files.
- `sig-scheduling` shares the 21-KEP DRA family with `sig-node`, and Gang Scheduling (4671) replaces a still-"provisional" KEP whose tracking issue was closed in 2019, and its stage label once moved backwards: the audit's best material.
- `sig-apps` is small and user-visible (Job failure policy with cross-SIG approvals).

## Alternatives considered

- `sig-auth` instead of `sig-apps`: cleanest replaced/replaces pairs; scale changes by under 10%.
- `sig-api-machinery`: high ticket volume, abstract subject matter, cross-SIG edges to SIGs we would not load.
- `sig-storage`: good replacement history, but participating lists point mostly at sig-node.
- P1 on by default (v1's plan): ≈ 2,600 more items whose threads would never refresh incrementally; adds implementation edges, not decisions.

## Consequences

- The audit's findings and the eval's ground truth come from these SIGs.
- `IMPLEMENTS` edges to k/k PRs are absent unless P1 is switched on; the README says so.

## Revision 2026-10-12

P1 off by default and defined as a snapshot; scope rationale tied to the audit job (design review R6, R12).
