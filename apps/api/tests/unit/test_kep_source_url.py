"""The kep.yaml link of a KEP detail names the file, also for graphs synced while it held the folder URL."""

from __future__ import annotations

from app.api.keps import kep_yaml_url

SHA = "8659e382efab7340d70de52432ee8f3d9979b797"
DIR = "keps/sig-node/1287-in-place-update-pod-resources"
TREE = f"https://github.com/kubernetes/enhancements/tree/{SHA}/{DIR}"
BLOB = f"https://github.com/kubernetes/enhancements/blob/{SHA}/{DIR}/kep.yaml"


def test_a_folder_url_becomes_the_kep_yaml_file_url() -> None:
    assert kep_yaml_url(TREE, f"{DIR}/kep.yaml") == BLOB
    assert kep_yaml_url(TREE + "/", f"{DIR}/kep.yaml") == BLOB


def test_a_file_url_or_missing_path_is_left_alone() -> None:
    assert kep_yaml_url(BLOB, f"{DIR}/kep.yaml") == BLOB
    assert kep_yaml_url(TREE, None) == TREE
    assert kep_yaml_url(None, f"{DIR}/kep.yaml") is None
