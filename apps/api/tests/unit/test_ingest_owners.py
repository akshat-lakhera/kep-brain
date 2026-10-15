from app.ingest.owners import parse_aliases, parse_owners, select_owners

OWNERS = """
approvers:
  - sig-node-approvers # alias
  - SomeOne
emeritus_approvers:
  - dashpole
reviewers:
  - sig-node-reviewers
labels:
  - area/kubelet
  - sig/node
options:
  no_parent_owners: true
filters:
  ".*":
    approvers:
      - extra
  "^foo":
    approvers:
      - other
"""


def test_parse_owners_lists_filters_and_options() -> None:
    f = parse_owners("pkg/kubelet/OWNERS", "abc", OWNERS)
    assert f.directory == "pkg/kubelet"
    assert f.approvers == ["sig-node-approvers", "someone", "extra"]
    assert f.reviewers == ["sig-node-reviewers"]
    assert f.emeritus == ["dashpole"]
    assert f.labels == ["area/kubelet", "sig/node"]
    assert f.no_parent_owners is True
    assert f.filters_raw is not None and "other" in f.filters_raw


def test_parse_aliases_lowercases_members() -> None:
    assert parse_aliases("aliases:\n  sig-node-approvers:\n    - Dims\n    - mrunalp\n") == {
        "sig-node-approvers": ["dims", "mrunalp"]
    }


SIGS_YAML = """
sigs:
- dir: sig-node
  name: Node
  subprojects:
  - name: kubelet
    owners:
    - https://raw.githubusercontent.com/kubernetes/kubernetes/master/pkg/kubelet/OWNERS
    - https://raw.githubusercontent.com/kubernetes/kubernetes/master/staging/src/k8s.io/kubelet/pkg/apis/dra/OWNERS
    - https://raw.githubusercontent.com/kubernetes-sigs/other/main/OWNERS
- dir: sig-other
  name: Other
  subprojects:
  - name: proxy
    owners:
    - https://raw.githubusercontent.com/kubernetes/kubernetes/master/pkg/proxy/OWNERS
"""
PLAIN = "approvers: [a]"
FILES = {
    "pkg/kubelet/cm/OWNERS": PLAIN,
    "pkg/kubelet/OWNERS": PLAIN,
    "pkg/OWNERS": PLAIN,
    "staging/src/k8s.io/kubelet/OWNERS": "labels: [sig/node]",
    "staging/src/k8s.io/kubelet/pkg/OWNERS": "labels: [sig/other, sig/node]",
    "staging/src/k8s.io/kubelet/x/OWNERS": "labels: [sig/network]",
    "pkg/proxy/OWNERS": PLAIN,
    "OWNERS": PLAIN,
}


def test_select_owners_derives_from_sigs_yaml_and_labels() -> None:
    from app.ingest.sigs import parse_sigs_yaml

    chart = parse_sigs_yaml(SIGS_YAML, "abc", {"sig-node"})
    tree = [{"path": p, "type": "blob", "sha": "s"} for p in (*FILES, "README.md")]
    reads: list[str] = []

    def read(path: str) -> str:
        reads.append(path)
        return FILES[path]

    sel = select_owners(tree, chart, {"sig-node"}, read, lambda _p: False)
    assert list(sel.paths) == ["OWNERS", "pkg/OWNERS", "pkg/kubelet/OWNERS", "pkg/kubelet/cm/OWNERS",
                               "staging/src/k8s.io/kubelet/OWNERS",
                               "staging/src/k8s.io/kubelet/pkg/OWNERS"]  # fmt: skip
    assert sel.origins["pkg/kubelet/cm/OWNERS"] == [("Subproject", "sig-node/kubelet")]
    assert sel.origins["staging/src/k8s.io/kubelet/OWNERS"] == [("SIG", "sig-node")]
    assert "pkg/OWNERS" not in sel.origins
    assert sel.seed_dirs == {"sig-node": 2} and sel.labelled_dirs == {"sig-node": 2}
    assert "pkg/proxy/OWNERS" not in sel.paths and "staging/src/k8s.io/kubelet/x/OWNERS" not in sel.paths
    assert sel.fetches == len(reads) == 3  # the three OWNERS files in the staging region outside the seeds
