from __future__ import annotations

import pytest
from conformance import spec_conformance

from agentkit.specs import SPECS

SAMPLES = [
    {"name": "a", "instructions": "hi"},
    {"name": "t"},
    {"name": "w"},
    {"name": "e", "cases": [{"name": "c", "input": "i", "expect": "o"}]},
]
KINDS = ["agent", "team", "workflow", "eval"]


@pytest.mark.parametrize(("kind", "payload"), list(zip(KINDS, SAMPLES, strict=True)))
def test_spec_conforms(kind, payload):
    spec_conformance(SPECS.validate(kind, payload))
