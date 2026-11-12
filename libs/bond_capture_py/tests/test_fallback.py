"""The rule fallback, table-driven. Today is Wednesday 2026-11-11."""

import json
from datetime import date

import pytest
from conftest import FIXTURES, TODAY

from bond_capture_py import degraded_draft

N = None
CASES = [
    # English dates
    ("Call Sam tomorrow", "2026-11-12", N, N),
    ("Do it today", "2026-11-11", N, N),
    ("Pay the bill tonight", "2026-11-11", "19:00", N),
    ("Call Sam day after tomorrow", "2026-11-13", N, N),
    ("Call Sam Thursday", "2026-11-12", N, N),
    ("Call Sam Wednesday", "2026-11-18", N, N),  # a bare weekday is never today
    ("Call Sam on Monday", "2026-11-16", N, N),
    ("Call Sam next Monday", "2026-11-16", N, N),
    ("Call Sam next Friday", "2026-11-20", N, N),
    ("Call Sam next Wednesday", "2026-11-18", N, N),
    ("Call Sam in 3 days", "2026-11-14", N, N),
    ("Call Sam in 2 weeks", "2026-11-25", N, N),
    ("Finish by end of week", "2026-11-13", N, N),
    ("Tidy up by the end of the month", "2026-11-30", N, N),
    ("Plan it next week", "2026-11-16", N, N),
    ("Send it by 11/20", "2026-11-20", N, N),
    ("Send it on 3/5", "2027-03-05", N, N),
    ("Room 11/20 needs a key", "2026-11-11", N, N),  # M/D counts only after by, on, before or due
    ("Pay the invoice Nov 25", "2026-11-25", N, N),
    ("Renew on Nov 5", "2027-11-05", N, N),
    ("File by 5 December", "2026-12-05", N, N),
    ("Deadline Dec 3rd", "2026-12-03", N, N),
    ("Renew my license on the 15th", "2026-11-15", N, N),
    ("Renew my license on the 5th", "2026-12-05", N, N),
    ("Book flights for the March conference", "2026-11-11", N, N),
    # English times
    ("Call Sam at 3pm", "2026-11-11", "15:00", N),
    ("Call Sam 3:30 pm", "2026-11-11", "15:30", N),
    ("Call Sam at 10:30", "2026-11-11", "10:30", N),
    ("Call Sam at noon", "2026-11-11", "12:00", N),
    ("Call Sam at 3", "2026-11-11", "15:00", N),  # a bare "at 3" is the afternoon
    ("Call Sam at 9am", "2026-11-11", "09:00", N),
    ("Call Sam at 12am", "2026-11-11", "00:00", N),
    ("Call Sam by 4pm Friday", "2026-11-13", "16:00", N),
    ("Call Sam tomorrow morning", "2026-11-12", "09:00", N),
    ("Call Sam this afternoon", "2026-11-11", "14:00", N),
    ("Call Sam tomorrow evening", "2026-11-12", "17:00", N),
    ("Call Sam tonight at 8pm", "2026-11-11", "20:00", N),  # a stated time beats a daypart
    # priority words
    ("Urgent: call Sam", "2026-11-11", N, 3),
    ("Send it ASAP", "2026-11-11", N, 3),
    ("This is important", "2026-11-11", N, 3),
    ("High priority: sign it", "2026-11-11", N, 3),
    ("Low priority: tidy the drive", "2026-11-11", N, 1),
    ("Tidy the drive whenever", "2026-11-11", N, 1),
    ("Learn Spanish someday", "2026-11-11", N, 1),
    ("Important but whenever", "2026-11-11", N, 3),  # high wins
    # Spanish
    ("Llamar a Sam hoy", "2026-11-11", N, N),
    ("Llamar a Sam mañana", "2026-11-12", N, N),
    ("Llamar a Sam manana", "2026-11-12", N, N),
    ("Llamar a Sam pasado mañana", "2026-11-13", N, N),
    ("Llamar a Sam el viernes", "2026-11-13", N, N),
    ("Llamar a Sam el miércoles", "2026-11-18", N, N),
    ("Llamar a Sam el próximo lunes", "2026-11-16", N, N),
    ("Llamar a Sam en 3 días", "2026-11-14", N, N),
    ("Llamar a Sam en 2 semanas", "2026-11-25", N, N),
    ("Llamar a Sam a las 9", "2026-11-11", "09:00", N),
    ("Enviar el informe el viernes a las 12", "2026-11-13", "12:00", N),
    ("Almuerzo al mediodía", "2026-11-11", "12:00", N),
    ("Llamar al banco el jueves a las 3 de la tarde", "2026-11-12", "15:00", N),
    ("Cena a las 9 de la noche", "2026-11-11", "21:00", N),
    ("Llamar a Sam mañana por la mañana", "2026-11-12", "09:00", N),
    ("Viernes a las 9 de la mañana", "2026-11-13", "09:00", N),
    ("Llamar a Sam esta noche", "2026-11-11", "19:00", N),
    ("Urgente: llamar a Sam", "2026-11-11", N, 3),
    ("Es importante", "2026-11-11", N, 3),
    ("Ordenar el archivo cuando pueda", "2026-11-11", N, 1),
    # month names, English and Spanish
    ("Send it December 15", "2026-12-15", N, N),
    ("Send it 15 December", "2026-12-15", N, N),
    ("Send it Dec 15th", "2026-12-15", N, N),
    ("Send it on the 15th of December", "2026-12-15", N, N),
    ("Enviar el 15 de diciembre", "2026-12-15", N, N),
    ("Enviar el 3 de marzo", "2027-03-03", N, N),
    ("Enviar el 20 de noviembre a las 3 de la tarde", "2026-11-20", "15:00", N),
    ("Enviar el 1 de enero", "2027-01-01", N, N),
    ("Enviar 3 de mayo", "2027-05-03", N, N),
    ("Meeting Dec 15 at 3pm", "2026-12-15", "15:00", N),
    # ISO dates anywhere
    ("Send it 2026-11-20", "2026-11-20", N, N),
    ("2026-12-01 file the return", "2026-12-01", N, N),
    ("File by 2027-01-15 at noon", "2027-01-15", "12:00", N),
    ("Odd 2026-02-30 date", "2026-11-11", N, N),
    # numeric dates: US order unless it cannot be one
    ("Pay by 3/5", "2027-03-05", N, N),
    ("Pay by 12/31", "2026-12-31", N, N),
    ("Pay by 31/12", "2026-12-31", N, N),
    ("Abonar el 31/12", "2026-12-31", N, N),
    ("Abonar para el 15/12", "2026-12-15", N, N),
    ("Pay on 12/3", "2026-12-03", N, N),
    ("Pay on 3/5/2028", "2028-03-05", N, N),
    ("Pay due 1/2/27", "2027-01-02", N, N),
    ("Pay by 13/13", "2026-11-11", N, N),
    # a bare hour 1 to 6 is pm unless a morning word keeps it
    ("Call at 6:30", "2026-11-11", "18:30", N),
    ("Call at 6", "2026-11-11", "18:00", N),
    ("Call tomorrow morning at 6:30", "2026-11-12", "06:30", N),
    ("Call tomorrow morning at 6", "2026-11-12", "06:00", N),
    ("Call at 6:30am", "2026-11-11", "06:30", N),
    ("Call at 7", "2026-11-11", "07:00", N),
    ("Call at 7:30", "2026-11-11", "07:30", N),
    ("Llamar mañana a las 6:30 de la mañana", "2026-11-12", "06:30", N),
    ("Llamar a las 6:30", "2026-11-11", "18:30", N),
    # "next friday" is the friday of next week; a bare "friday" is the coming one
    ("Call Friday", "2026-11-13", N, N),
    ("Call next friday", "2026-11-20", N, N),
]


@pytest.mark.parametrize("text, due_date, due_time, priority", CASES)
def test_rules(text, due_date, due_time, priority):
    draft = degraded_draft(text, TODAY)
    assert (draft["due_date"], draft["due_time"], draft["priority"]) == (due_date, due_time, priority)


@pytest.mark.parametrize("text", ["2020-01-01 call Sam", "Pay on 3/5/2020", "Call Sam 2026-11-10",
                                  "Call Sam 2026-11-10 at 9am", "Pay due 1/2/19"])
def test_a_date_in_the_past_becomes_today_defaulted_with_no_time_like_the_model_path(text):
    draft = degraded_draft(text, TODAY)
    assert (draft["due_date"], draft["due_defaulted"], draft["due_time"]) == ("2026-11-11", True, None)


@pytest.mark.parametrize("text", ["Call Sam 2031-11-12", "Pay on 3/5/2040", "Call Sam 2099-01-01 at 3pm"])
def test_a_date_beyond_five_years_is_ignored(text):
    draft = degraded_draft(text, TODAY)
    assert (draft["due_date"], draft["due_defaulted"]) == ("2026-11-11", True)


def test_the_edges_of_the_window_are_kept():
    assert degraded_draft("Call 2026-11-11 at 9am", TODAY)["due_time"] == "09:00"  # today is not past
    edge = degraded_draft("Call 2031-11-11", TODAY)
    assert (edge["due_date"], edge["due_defaulted"]) == ("2031-11-11", False)


def test_the_table_is_wide_enough():
    assert len(CASES) >= 40


def test_the_draft_is_one_degraded_low_confidence_task_with_the_text_as_title():
    draft = degraded_draft("  Call Sam tomorrow  ", TODAY)
    assert draft["kind"] == "task" and draft["title"] == "Call Sam tomorrow"
    assert draft["degraded"] is True and draft["confidence"] == 0.2 and draft["flags"] == ["low_confidence"]
    assert draft["links"] == [] and draft["due_defaulted"] is False
    assert degraded_draft("x" * 400, TODAY)["title"] == "x" * 200


def test_no_date_found_means_today_defaulted():
    draft = degraded_draft("Follow up with the Lees", TODAY)
    assert (draft["due_date"], draft["due_defaulted"]) == ("2026-11-11", True)
    assert degraded_draft("Call at 3pm", TODAY)["due_defaulted"] is True


def test_month_ends_and_weekends():
    assert degraded_draft("by end of month", date(2026, 12, 5))["due_date"] == "2026-12-31"
    assert degraded_draft("by end of month", date(2028, 2, 3))["due_date"] == "2028-02-29"
    assert degraded_draft("end of week", date(2026, 11, 14))["due_date"] == "2026-11-20"  # a Saturday
    assert degraded_draft("end of week", date(2026, 11, 13))["due_date"] == "2026-11-13"  # a Friday
    assert degraded_draft("next Tuesday", date(2026, 11, 16))["due_date"] == "2026-11-24"  # a Monday
    assert degraded_draft("on the 31st", date(2026, 11, 11))["due_date"] == "2026-12-31"
    assert degraded_draft("on Feb 30", TODAY)["due_defaulted"] is True  # not a date


def test_an_impossible_time_is_ignored():
    assert degraded_draft("at 27", TODAY)["due_time"] is None
    assert degraded_draft("Pay 12/45 by 3", TODAY)["due_time"] == "15:00"


def test_the_fallback_scores_on_the_single_task_phrases():
    """The same numbers ``tools/score.py --run-fallback`` prints: every single-task phrase."""
    rows = [json.loads(line) for line in (FIXTURES / "phrases.jsonl").read_text().splitlines()]
    scored = 0
    for row in rows:
        items = row["expect"].get("items") or []
        if row["cat"] != "task" or len(items) != 1 or items[0]["kind"] != "task":
            continue
        draft = degraded_draft(row["text"], TODAY)
        assert draft["kind"] == "task"
        assert draft["due_date"] == items[0]["date"], row["text"]
        if "time" in items[0]:
            assert draft["due_time"] == items[0]["time"], row["text"]
        scored += 1
    assert scored >= 20
