# ruff: noqa: E501
"""A small graph in the `kep` contract shape, for tool tests on a throwaway graph.

Values mirror public records cited in the eval set (KEP-583, 4671, 5832, 1287);
they are test fixtures only and never reach the product graph.
"""

from __future__ import annotations

OPEN = 4102444800
GH = "https://github.com/kubernetes/enhancements"

STATEMENTS = [
    f"""
CREATE (sn:SIG {{key: 'sig-node', display_name: 'Node', url: 'https://github.com/kubernetes/community/tree/master/sig-node'}}),
 (ss:SIG {{key: 'sig-scheduling', display_name: 'Scheduling', url: 'https://github.com/kubernetes/community/tree/master/sig-scheduling'}}),
 (sa:SIG {{key: 'sig-apps', display_name: 'Apps', url: 'https://github.com/kubernetes/community/tree/master/sig-apps'}}),
 (k583:KEP {{key: 'keps/sig-scheduling/583-coscheduling', number: 583, title: 'Coscheduling', owning_sig: 'sig-scheduling',
   status: 'provisional', url: '{GH}/tree/master/keps/sig-scheduling/583-coscheduling'}}),
 (k4671:KEP {{key: 'keps/sig-scheduling/4671-gang-scheduling', number: 4671, title: 'Gang Scheduling using Workload Object',
   owning_sig: 'sig-scheduling', status: 'implementable', stage: 'stable', latest_milestone: 'v1.38',
   url: '{GH}/tree/master/keps/sig-scheduling/4671-gang-scheduling'}}),
 (k5832:KEP {{key: 'keps/sig-scheduling/5832-decouple-podgroup-api', number: 5832, title: 'Decouple PodGroup API',
   owning_sig: 'sig-scheduling', status: 'implementable', stage: 'alpha', latest_milestone: 'v1.36',
   url: '{GH}/tree/master/keps/sig-scheduling/5832-decouple-podgroup-api'}}),
 (k1287:KEP {{key: 'keps/sig-node/1287-in-place-update-pod-resources', number: 1287,
   title: 'In-place Update of Pod Resources', owning_sig: 'sig-node', status: 'implemented', stage: 'stable',
   url: '{GH}/tree/master/keps/sig-node/1287-in-place-update-pod-resources'}}),
 (a2133:KEP {{key: 'keps/sig-node/2133-a', number: 2133, title: 'Duplicate A', owning_sig: 'sig-node', status: 'implemented', url: '{GH}/a'}}),
 (b2133:KEP {{key: 'keps/sig-apps/2133-b', number: 2133, title: 'Duplicate B', owning_sig: 'sig-apps', status: 'implemented', url: '{GH}/b'}}),
 (g:FeatureGate {{key: 'GenericWorkload', name: 'GenericWorkload', url: '{GH}/blob/master/keps/sig-scheduling/4671-gang-scheduling/kep.yaml'}}),
 (sol:Person {{key: 'soltysh', login: 'soltysh', url: 'https://github.com/soltysh', is_bot: false}}),
 (nat:Person {{key: 'natasha41575', login: 'natasha41575', url: 'https://github.com/natasha41575', is_bot: false}}),
 (bot:Person {{key: 'k8s-ci-robot', login: 'k8s-ci-robot', url: 'https://github.com/k8s-ci-robot', is_bot: true}}),
 (i583:Issue:Ticket {{key: 'kubernetes/enhancements#583', number: 583, title: 'Coscheduling', state: 'closed',
   closed_at_iso: '2019-09-09T21:03:18Z', labels_current: ['lifecycle/rotten', 'stage/alpha'], url: '{GH}/issues/583'}}),
 (i5832:Issue:Ticket {{key: 'kubernetes/enhancements#5832', number: 5832, title: 'Decouple PodGroup API', state: 'closed',
   closed_at_iso: '2026-05-18T23:01:00Z', url: '{GH}/issues/5832'}}),
 (pr:PullRequest:Ticket {{key: 'kubernetes/enhancements#5761', number: 5761,
   title: 'KEP-1287: Mark in-place pod resize as implemented', state: 'merged', url: '{GH}/pull/5761'}}),
 (cm:Commit {{key: 'kubernetes/enhancements@d47a8df46c0000000000000000000000000000', sha: 'd47a8df46c0000000000000000000000000000',
   authored_at_iso: '2025-12-29T00:00:00Z', subject: 'mark implemented', url: '{GH}/commit/d47a8df46c'}}),
 (sc:StatusChange {{key: 'sc:keps/sig-node/1287-in-place-update-pod-resources:status:d47a8df46c', kind: 'metadata',
   kep_path: 'keps/sig-node/1287-in-place-update-pod-resources', field: 'status', op: 'set', from_value: 'implementable',
   to_value: 'implemented', at: 1766966400, at_iso: '2025-12-29T00:00:00Z', seq: 1, valid_from: 1766966400, valid_to: {OPEN},
   is_reversal: false, actor_login: 'natasha41575', source_url: '{GH}/commit/d47a8df46c'}}),
 (d:Decision {{key: 'dec:status_transition:keps/sig-node/1287-in-place-update-pod-resources:d47a8df46c', kind: 'status_transition',
   kep_path: 'keps/sig-node/1287-in-place-update-pod-resources', summary: 'status implementable -> implemented',
   decided_at: 1768531528, decided_at_iso: '2026-01-16T02:45:28Z', derived: true, human_decider: 'natasha41575',
   url: '{GH}/pull/5761'}}),
 (f1:Finding {{key: 'fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling', kind: 'active_status_closed_issue',
   kep_path: 'keps/sig-scheduling/583-coscheduling', state: 'open', rule_version: 1, a_label: 'kep.yaml status',
   a_value: 'provisional', a_url: '{GH}/blob/master/keps/sig-scheduling/583-coscheduling/kep.yaml', b_label: 'tracking issue',
   b_value: 'closed 2019-09-09', b_url: '{GH}/issues/583', suggested_fix: 'set_status_withdrawn_or_deferred',
   detected_at: 1760000000, detected_at_iso: '2025-10-09T00:00:00Z', source_url: '{GH}/issues/583'}}),
 (k583)-[:OWNED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(ss),
 (k4671)-[:OWNED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(ss),
 (k5832)-[:OWNED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(ss),
 (k1287)-[:OWNED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(sn),
 (sa)-[:PARTICIPATES {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k4671),
 (k4671)-[:REPLACES {{declared_by: 'successor', valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k583),
 (k4671)-[:REPLACES {{declared_by: 'successor', valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k5832),
 (k5832)-[:REPLACES {{declared_by: 'successor', valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k583),
 (k583)-[:SUPERSEDED_BY {{derived: true, valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k4671),
 (k5832)-[:SEE_ALSO {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k4671),
 (k4671)-[:GATED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(g),
 (sol)-[:PRR_APPROVED {{stage: 'alpha', valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k4671),
 (bot)-[:APPROVES {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(k4671),
 (k583)-[:TRACKED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(i583),
 (k5832)-[:TRACKED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(i5832),
 (k1287)-[:CHANGED]->(sc), (sc)-[:IN_COMMIT]->(cm), (cm)-[:IN_PR]->(pr), (nat)-[:ACTED {{at: 1766966400}}]->(sc),
 (d)-[:ABOUT]->(k1287), (d)-[:FROM_CHANGE]->(sc), (d)-[:DECIDED_BY {{role: 'author'}}]->(nat),
 (d)-[:EVIDENCED_BY {{evidence_kind: 'pull_request', source_url: '{GH}/pull/5761'}}]->(pr),
 (f1)-[:ABOUT]->(k583), (f1)-[:EVIDENCED_BY {{evidence_kind: 'issue', source_url: '{GH}/issues/583'}}]->(i583)
""",
    "CREATE FULLTEXT INDEX FOR (n:KEP) ON (n.title, n.summary)",
    "CREATE FULLTEXT INDEX FOR (n:FeatureGate) ON (n.name)",
    "CREATE FULLTEXT INDEX FOR (n:Person) ON (n.login)",
    "CREATE INDEX FOR (n:KEP) ON (n.key)",
    "CREATE INDEX FOR (n:KEP) ON (n.number)",
]
