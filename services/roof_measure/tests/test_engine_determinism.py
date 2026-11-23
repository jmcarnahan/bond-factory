"""Determinism across processes: the same input gives byte-identical output whatever PYTHONHASHSEED is (set / dict order
must never reach the result). Plan gate 2 needs identical digests."""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES = ["gable_d8_trees", "l_shape_p25_d8", "complex_hip_d8", "flat_equipment_d8", "two_level_flat_d8_rot17"]
CODE = """
import sys, json, hashlib
sys.path.insert(0, 'tests')
from engine_improve_cases import run
res = run(sys.argv[1])
print(hashlib.sha256(json.dumps(res.to_result_json('x'), sort_keys=True).encode()).hexdigest())
"""


def _digest(name: str, seed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    out = subprocess.run([sys.executable, "-c", CODE, name], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.mark.parametrize("name", CASES)
def test_output_does_not_depend_on_the_hash_seed(name):
    digests = {_digest(name, s) for s in ("0", "1", "424242")}
    assert len(digests) == 1 and len(next(iter(digests))) == hashlib.sha256().digest_size * 2
