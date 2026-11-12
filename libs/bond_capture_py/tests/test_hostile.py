"""Hostile or sloppy model answers: patterns, control characters, partial answers, event ends."""

import pytest
from conftest import TODAY, FakeLlm, event_item, model_item, run

from bond_capture_py import MAX_ITEMS, CaptureError, CaptureResult, degraded_draft


def ok(*items):
    result = run({"items": list(items)})
    assert not result.degraded, result.reason
    return result


RLO, PDF = chr(0x202E), chr(0x202C)  # right-to-left override and its terminator


@pytest.mark.parametrize("value", ["09:00\n", "09:00 ", "\n09:00", "０９:００", "9:00"])
def test_time_is_matched_in_full(value):
    assert run({"items": [model_item(time=value)]}).reason == "invalid_output"
    assert run({"items": [model_item(end_time=value)]}).reason == "invalid_output"


@pytest.mark.parametrize("value", ["2026-11-12\n", " 2026-11-12", "２０２６-１１-１２", "2026-11-12T00:00"])
def test_date_is_matched_in_full(value):
    assert run({"items": [model_item(date=value)]}).reason == "invalid_output"
    assert run({"items": [model_item(end_date=value)]}).reason == "invalid_output"


@pytest.mark.parametrize("raw, clean", [
    ("Call\x00Sam", "CallSam"),
    ("Call\nSam\r\nnow", "Call Sam now"),
    ("Call\tSam", "Call Sam"),
    ("Call\x7fSam\x1b[0m", "CallSam[0m"),
    (RLO + "Call Sam" + PDF, "Call Sam"),
    ("A" + "".join(map(chr, [0x202A, 0x202B, 0x202D, 0x2066, 0x2067, 0x2068, 0x2069])) + "B", "AB"),
    ("Call\x85Sam", "CallSam"),
    ("Café ñ é", "Café ñ é"),  # ordinary text is untouched
])
def test_titles_lose_control_characters_and_bidi_overrides(raw, clean):
    (item,) = ok(model_item(title=raw)).items
    assert item.title == clean


def test_a_title_that_is_empty_after_cleaning_drops_the_item_and_link_names_are_cleaned_too():
    link = {"text": RLO + "Sam\x00", "kind": "contact"}
    result = ok(model_item(title="\x00" + RLO + "\n"), model_item(title="kept", links=[link]))
    assert [i.title for i in result.items] == ["kept"] and result.items[0].links[0].text == "Sam"
    assert result.dropped == 1


def test_the_cap_applies_after_cleaning():
    (item,) = ok(model_item(title="\x00" * 300 + "y" * 300)).items
    assert item.title == "y" * 255


def test_one_bad_item_costs_only_itself_and_the_result_says_so():
    result = ok(model_item(title="a"), model_item(title="bad date", date="2026-13-45"),
                model_item(title="bad kind", kind="reminder"), "junk", model_item(title="b"))
    assert [i.title for i in result.items] == ["a", "b"] and result.dropped == 3
    assert result.to_dict()["dropped"] == 3 and not result.degraded and result.reason is None


def test_items_past_the_limit_count_as_dropped():
    result = ok(*[model_item(title=f"t{i}") for i in range(MAX_ITEMS + 2)])
    assert len(result.items) == MAX_ITEMS and result.dropped == 2


def test_a_clean_answer_has_no_dropped_key_and_a_degraded_one_neither():
    assert "dropped" not in ok(model_item()).to_dict()
    assert "dropped" not in run(None, llm=None).to_dict()
    assert "dropped" not in CaptureResult().to_dict()


def test_the_answer_is_invalid_only_for_a_wrong_top_level_or_when_no_item_survives():
    assert run({"items": [model_item(date="bad"), "junk"]}).reason == "invalid_output"
    assert run({"items": [model_item(title="  ")]}).reason == "invalid_output"
    assert run({"items": "x"}).reason == "invalid_output"
    assert run({"items": []}).degraded is False


@pytest.mark.parametrize("field, value", [
    ("confidence", 10**400), ("confidence", -(10**400)), ("confidence", float("inf")),
    ("confidence", float("-inf")), ("priority", 10**400), ("priority", float("inf")),
    ("priority", float("nan")),
])
def test_a_huge_or_infinite_number_costs_only_its_item(field, value):
    result = ok(model_item(title="bad", **{field: value}), model_item(title="kept"))
    assert [i.title for i in result.items] == ["kept"] and result.dropped == 1
    assert run({"items": [model_item(**{field: value})]}).reason == "invalid_output"  # none left


def test_a_task_due_today_with_a_time_is_not_treated_as_past():
    (item,) = ok(model_item(date="2026-11-11", time="09:00")).items
    assert (item.due_date, item.due_time, item.due_defaulted) == ("2026-11-11", "09:00", False)


def test_a_past_task_that_had_no_time_still_defaults_to_today():
    (item,) = ok(model_item(date="2026-01-01")).items
    assert (item.due_date, item.due_time, item.due_defaulted) == ("2026-11-11", None, True)


def test_event_end_rules():
    same_day, no_end_date, backwards, fine = ok(
        event_item(time="15:00", end_time="14:00"),                   # ends before it starts, same day
        event_item(time="15:00", end_time="16:30"),                   # an end time alone ends on the start day
        event_item(time="15:00", end_date="2026-11-11", end_time="16:00"),  # end date before the start date
        event_item(time="15:00", end_date="2026-11-13", end_time="09:00"),  # a later day: the time is fine
    ).items
    assert (same_day.end_date, same_day.end_time) == (None, None)
    assert (no_end_date.end_date, no_end_date.end_time) == ("2026-11-12", "16:30")
    assert (backwards.end_date, backwards.end_time) == (None, None)
    assert (fine.end_date, fine.end_time) == ("2026-11-13", "09:00")


def test_the_fallback_title_is_cleaned_and_a_note_of_only_controls_is_no_text():
    assert degraded_draft("Call\x00 Sam" + RLO + "\ntomorrow", TODAY)["title"] == "Call Sam tomorrow"
    with pytest.raises(CaptureError) as err:
        run(None, text=RLO + "\x00 \n", llm=FakeLlm({"items": []}))
    assert err.value.code == "text_required"
