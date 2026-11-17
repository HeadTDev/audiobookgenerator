"""Notes-to-script tests with a fake Gemini client: no network, no quota."""
from types import SimpleNamespace

import pytest
from google.genai import errors

from audiobook_generator.core import script_writer
from audiobook_generator.core.script_writer import (
    ScriptWriterError,
    ScriptWriterThread,
    build_system_prompt,
    build_user_prompt,
    describe_error,
    notes_to_script,
    script_path_for,
)

CLEAN = "# T1: Teszt - SCRIPT\n\n[serious] Ez egy tiszta szöveg.\n"
BAD = "# T1: Teszt - SCRIPT\nAz I/O busz.\n"


def reply(text, finish="STOP", block=None):
    feedback = SimpleNamespace(block_reason=block) if block else None
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish)], prompt_feedback=feedback)


class FakeGemini:
    """Stands in for genai.Client; records every generate_content call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def turn_texts(call):
    return [turn.parts[0].text for turn in call["contents"]]


def test_prompts_carry_rules_and_notes():
    system = build_system_prompt()
    assert "[serious]" in system and "vagy" in system and "same language" in system
    user = build_user_prompt("# Busz\nszöveg", "busz.md")
    assert "busz.md" in user and "# Busz\nszöveg" in user and "Suggested title: Busz" in user
    assert "Suggested title: jegyzet" in build_user_prompt("szöveg", "jegyzet.txt")


def test_clean_reply_is_one_call():
    fake = FakeGemini(reply(CLEAN))
    result = notes_to_script(fake, "jegyzet", "j.md")
    assert len(fake.calls) == 1
    assert result.text.strip() == CLEAN.strip() and result.issues == [] and not result.repaired


def test_repair_round_fixes_issues():
    fake = FakeGemini(reply(BAD), reply(CLEAN))
    logs = []
    result = notes_to_script(fake, "jegyzet", "j.md", logs.append)
    assert len(fake.calls) == 2 and result.repaired and result.text == CLEAN.strip()
    texts = turn_texts(fake.calls[1])
    assert len(texts) == 3 and "Line 2" in texts[2] and "I/O" in texts[2]
    assert logs and "1 issue" in logs[0]


def test_worse_repair_keeps_first():
    worse = BAD + "Az A/B és C/D.\n"
    fake = FakeGemini(reply(BAD), reply(worse))
    result = notes_to_script(fake, "jegyzet", "j.md")
    assert len(fake.calls) == 2 and result.text == BAD.strip() and not result.repaired and result.issues


def test_truncated_repair_keeps_first():
    fake = FakeGemini(reply(BAD + "Hosszú sor. " * 20), reply("# T1: Teszt - SCRIPT\nRövid."))
    result = notes_to_script(fake, "jegyzet", "j.md")
    assert not result.repaired and "Hosszú" in result.text


def test_code_fence_is_stripped():
    fake = FakeGemini(reply("```markdown\n" + CLEAN + "```"))
    assert notes_to_script(fake, "jegyzet", "j.md").text == CLEAN.strip()


def test_script_path_naming(tmp_path):
    assert script_path_for("C:/x/Mesterséges Intelligencia: 1?.txt", str(tmp_path)) == str(
        tmp_path / "Mesterséges_Intelligencia_1_SCRIPT.md"
    )
    assert script_path_for("MI12_Teszt_script.md", str(tmp_path)) == str(tmp_path / "MI12_Teszt_SCRIPT.md")
    (tmp_path / "jegyzet_SCRIPT.md").write_text("x")
    assert script_path_for("jegyzet.txt", str(tmp_path)) == str(tmp_path / "jegyzet_2_SCRIPT.md")
    (tmp_path / "jegyzet_2_SCRIPT.md").write_text("x")
    assert script_path_for("jegyzet.txt", str(tmp_path)) == str(tmp_path / "jegyzet_3_SCRIPT.md")


@pytest.mark.parametrize(
    "response, message",
    [
        (reply("x", block="PROHIBITED_CONTENT"), r"refused the notes \(PROHIBITED_CONTENT\)"),
        (reply("x", finish="SAFETY"), r"refused the notes \(SAFETY\)"),
        (reply("x", finish="MAX_TOKENS"), "cut off"),
        (reply(None), "empty response"),
        (reply("```\n```"), "empty response"),
    ],
)
def test_bad_replies_raise(response, message):
    with pytest.raises(ScriptWriterError, match=message):
        notes_to_script(FakeGemini(response), "jegyzet", "j.md")


class FakeTransportError(Exception):
    __module__ = "httpx2._exceptions"


@pytest.mark.parametrize(
    "error, expected",
    [
        (errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}), "limit reached"),
        (errors.ClientError(401, {"error": {"message": "nope", "status": "UNAUTHENTICATED"}}), "rejected the API key"),
        (errors.ClientError(400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}}), "rejected the API key"),
        (errors.ClientError(404, {"error": {"message": "gone", "status": "NOT_FOUND"}}), "GEMINI_MODEL"),
        (errors.ClientError(400, {"error": {"message": "bad", "status": "INVALID_ARGUMENT"}}), "HTTP 400 INVALID_ARGUMENT"),
        (errors.ServerError(503, {"error": {"message": "busy", "status": "UNAVAILABLE"}}), "overloaded"),
        (FakeTransportError("boom"), "Network error"),
        (PermissionError("denied"), "File error"),
        (ValueError("x"), "Unexpected error"),
    ],
)
def test_describe_error(error, expected):
    assert expected in describe_error(error)


def run_thread(monkeypatch, fake, api_key, notes, folder):
    monkeypatch.setattr(
        script_writer, "genai", SimpleNamespace(Client=lambda **kw: fake)
    )
    thread = ScriptWriterThread(api_key, str(notes), str(folder))
    logs, done = [], []
    thread.log_msg.connect(logs.append)
    thread.done.connect(lambda *args: done.append(args))
    thread.run()
    return logs, done


def test_thread_saves_script(qapp, monkeypatch, tmp_path):
    notes = tmp_path / "jegyzet.txt"
    notes.write_text("Az I/O busz.", encoding="utf-8")
    folder = tmp_path / "scripts"
    folder.mkdir()
    logs, done = run_thread(monkeypatch, FakeGemini(reply(CLEAN)), "key", notes, folder)
    path = folder / "jegyzet_SCRIPT.md"
    assert path.read_text(encoding="utf-8") == CLEAN
    assert done == [(True, "✅ Script saved: jegyzet_SCRIPT.md · pre-flight clean", str(path))]
    assert logs[0].startswith("✍️")


def test_thread_without_key_fails(qapp, monkeypatch, tmp_path):
    notes = tmp_path / "jegyzet.txt"
    notes.write_text("szöveg", encoding="utf-8")
    logs, done = run_thread(monkeypatch, FakeGemini(), "", notes, tmp_path)
    assert done[0][0] is False and "GEMINI_API_KEY" in done[0][1] and done[0][2] == ""
    assert logs[-1].startswith("❌")
