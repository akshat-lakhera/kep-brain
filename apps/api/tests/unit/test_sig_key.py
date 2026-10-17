"""SIG keys in tool parameters accept the ways people write a SIG and normalise to the graph key."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.tools.base import SigKey, ToolParams, sig_key


class P(ToolParams):
    sig: SigKey | None = None


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("sig-node", "sig-node"),
        ("node", "sig-node"),
        ("Scheduling", "sig-scheduling"),
        ("SIG Apps", "sig-apps"),
        ("sig apps", "sig-apps"),
        ("sig_apps", "sig-apps"),
        ("Apps SIG", "sig-apps"),
        ("  sig-cluster-lifecycle ", "sig-cluster-lifecycle"),
        ("api machinery", "sig-api-machinery"),
    ],
)
def test_sig_key_normalises(raw: str, key: str) -> None:
    assert sig_key(raw) == key
    assert P(sig=raw).sig == key


def test_sig_key_rejects_junk() -> None:
    for bad in ("", "sig-", "sig node!", "sig-node; DROP", "a" * 70):
        with pytest.raises(ValidationError):
            P(sig=bad)
    assert P(sig=None).sig is None
