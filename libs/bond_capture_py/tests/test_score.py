"""tools/score.py is the prompt's regression; its matching must pair a label with the item of the right kind."""

import importlib.util
import json
from pathlib import Path

from conftest import FIXTURES

_spec = importlib.util.spec_from_file_location("score", Path(__file__).resolve().parents[1] / "tools" / "score.py")
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)


def test_a_keyword_shared_by_two_items_pairs_with_the_item_of_the_labelled_kind():
    pred = [{"kind": "task", "title": "Tell Marcus I am out"}, {"kind": "event", "title": "Out of office"}]
    label = [{"kw": "out", "kind": ["event", "task"], "date": "x"}]
    assert score.match([{"kw": "out", "kind": "event"}], pred) == [pred[1]]
    assert score.match([{"kw": "out", "kind": "task"}], pred) == [pred[0]]
    assert score.match(label, pred) == [pred[0]]  # either kind fits: the first hit


def test_with_no_item_of_the_kind_the_first_keyword_hit_is_used_and_each_item_pairs_once():
    pred = [{"kind": "task", "title": "Call out"}]
    assert score.match([{"kw": "out", "kind": "event"}], pred) == [pred[0]]
    two = [{"kw": "out", "kind": "task"}, {"kw": "out", "kind": "task"}]
    assert score.match(two, pred) == [pred[0], None]


def test_phrase_52_accepts_three_or_four_items():
    rows = {r["id"]: r for r in map(json.loads, (FIXTURES / "phrases.jsonl").read_text().splitlines())}
    assert rows[52]["expect"]["count"] == [3, 4]
