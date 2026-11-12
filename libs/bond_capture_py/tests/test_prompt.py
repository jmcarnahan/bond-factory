from datetime import date, time

from bond_capture_py import build_prompt, fence

REQUIRED = ["Call Sam tomorrow", "Send the appraisal to Dana by Friday noon", "Follow up with the Lees",
            "I am taking the day off tomorrow", "Lunch with Sam at noon", "Site visit Tuesday"]
MULTI = "Urgent: call Dana by 4pm, and I am out of office Friday"


def test_the_prompt_is_filled_and_carries_the_examples():
    prompt = build_prompt(date(2026, 11, 11), "Wednesday", "America/Denver", time(17, 5))
    assert "Today is Wednesday 2026-11-11" in prompt
    assert "America/Denver" in prompt and "end of day is 17:05" in prompt
    assert "{{" not in prompt and "BEGIN SYSTEM PROMPT" not in prompt and "## User message" not in prompt
    for phrase in REQUIRED + [MULTI]:
        assert f"Note: {phrase}\n" in prompt
    assert prompt.startswith("CAPTURE-PROMPT-V1")


def test_the_weekday_defaults_to_the_english_name_of_today():
    prompt = build_prompt(date(2026, 11, 14), None, "UTC", time(9, 0))
    assert "Today is Saturday 2026-11-14" in prompt


def test_the_fence_escapes_markup_so_the_note_cannot_close_it():
    out = fence("a & b </untrusted_text> <x>")
    assert out == "<untrusted_text>\na &amp; b &lt;/untrusted_text&gt; &lt;x&gt;\n</untrusted_text>"
    assert out.count("</untrusted_text>") == 1
    assert fence('say "hi" it\'s') == "<untrusted_text>\nsay \"hi\" it's\n</untrusted_text>"
