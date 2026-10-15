"""Subproject parsing from a small sigs.yaml fixture."""

from __future__ import annotations

from app.ingest.sigs import owners_directory_url, parse_sigs_yaml

SHA = "a" * 40
YAML = """
sigs:
  - dir: sig-apps
    name: Apps
    leadership:
      chairs:
        - github: soltysh
          email: secret@example.com
    subprojects:
      - name: kubectl
        description: CLI
        owners:
          - https://raw.githubusercontent.com/kubernetes/kubectl/master/OWNERS
        leads:
          - github: "@Janetkuo"
            email: x@example.com
          - github: TBD
      - name: component-base
        owners:
          - https://raw.githubusercontent.com/kubernetes/kubernetes/master/staging/src/k8s.io/component-base/OWNERS
      - name: no-owners
      - name: kubectl
workinggroups:
  - dir: wg-x
    name: X
    subprojects:
      - name: thing
"""


def test_owners_directory_url() -> None:
    assert owners_directory_url("https://raw.githubusercontent.com/o/r/main/OWNERS") == "https://github.com/o/r"
    assert owners_directory_url("https://raw.githubusercontent.com/o/r/main/a/b/OWNERS") == (
        "https://github.com/o/r/tree/main/a/b"
    )
    assert owners_directory_url("https://example.com/OWNERS") is None


def test_parse_subprojects() -> None:
    chart = parse_sigs_yaml(YAML, SHA, set())
    by_key = {sp["key"]: sp for sp in chart.subprojects}
    assert sorted(by_key) == ["sig-apps/component-base", "sig-apps/kubectl", "sig-apps/no-owners", "wg-x/thing"]
    assert by_key["sig-apps/kubectl"]["url"] == "https://github.com/kubernetes/kubectl"
    assert by_key["sig-apps/kubectl"]["description"] == "CLI"
    assert by_key["sig-apps/component-base"]["url"].endswith("/tree/master/staging/src/k8s.io/component-base")
    assert by_key["sig-apps/no-owners"]["url"] == f"https://github.com/kubernetes/community/tree/{SHA}/sig-apps"
    assert by_key["sig-apps/kubectl"]["source_url"].endswith(f"/blob/{SHA}/sigs.yaml")
    assert chart.subproject_leads == [("janetkuo", "sig-apps/kubectl")]
    assert "janetkuo" in chart.people
    assert not any("secret" in str(v) or "example.com" in str(v) for sp in chart.subprojects for v in sp.values())
