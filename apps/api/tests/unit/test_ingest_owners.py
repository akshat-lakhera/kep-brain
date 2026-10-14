from app.ingest.owners import parse_aliases, parse_owners, select_owner_paths

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


def test_select_owner_paths_keeps_wanted_dirs_and_ancestors() -> None:
    tree = [{"path": p, "type": "blob", "sha": "s"} for p in (
        "OWNERS", "pkg/OWNERS", "pkg/kubelet/OWNERS", "pkg/kubelet/cm/OWNERS", "pkg/proxy/OWNERS",
        "cmd/OWNERS", "README.md",
    )]  # fmt: skip
    assert list(select_owner_paths(tree)) == [
        "OWNERS",
        "cmd/OWNERS",
        "pkg/OWNERS",
        "pkg/kubelet/OWNERS",
        "pkg/kubelet/cm/OWNERS",
    ]
