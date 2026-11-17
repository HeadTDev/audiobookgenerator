"""Notes-to-script tests with a fake Gemini client: no network, no quota."""
from types import SimpleNamespace

import pytest
from google.genai import errors

from audiobook_generator.core import script_writer
from audiobook_generator.core.config import GEMINI_MODELS
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

    def generate_content(self, model, **kwargs):
        self.calls.append({"model": model, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def turn_texts(call):
    return [turn.parts[0].text for turn in call["contents"]]


def test_prompts_carry_rules_and_notes():
    system = build_system_prompt()
    assert "[serious]" in system and "vagy" in system and "same language" in system
    assert "`I-O`" in system
    user = build_user_prompt("# Busz\nszöveg", "busz.md")
    assert "busz.md" in user and "# Busz\nszöveg" in user and "Suggested title: Busz" in user
    assert "Suggested title: jegyzet" in build_user_prompt("szöveg", "jegyzet.txt")


def test_clean_reply_is_one_call():
    fake = FakeGemini(reply(CLEAN))
    result = notes_to_script(fake, "jegyzet", "j.md")
    assert len(fake.calls) == 1
    assert result.text.strip() == CLEAN.strip() and result.issues == [] and not result.repaired
    assert result.model == GEMINI_MODELS[0] and fake.calls[0]["model"] == GEMINI_MODELS[0]


def test_repair_round_fixes_issues():
    fake = FakeGemini(reply(BAD), reply(CLEAN))
    logs = []
    result = notes_to_script(fake, "jegyzet", "j.md", log=logs.append)
    assert len(fake.calls) == 2 and result.repaired and result.text == CLEAN.strip()
    texts = turn_texts(fake.calls[1])
    assert len(texts) == 3 and "Line 2" in texts[2] and "I/O" in texts[2]
    assert any("1 issue" in m for m in logs)


def test_worse_repair_keeps_first():
    worse = BAD + "Az A/B és C/D.\n"
    fake = FakeGemini(reply(BAD), reply(worse))
    result = notes_to_script(fake, "jegyzet", "j.md")
    assert len(fake.calls) == 2 and result.text == BAD.strip() and not result.repaired and result.issues


def test_truncated_repair_keeps_first():
    fake = FakeGemini(reply(BAD + "Hosszú sor. " * 20), reply("# T1: Teszt - SCRIPT\nRövid."))
    result = notes_to_script(fake, "jegyzet", "j.md")
    assert not result.repaired and "Hosszú" in result.text


def test_failed_repair_keeps_first_draft():
    busy = errors.ServerError(503, {"error": {"message": "busy", "status": "UNAVAILABLE"}})
    fake = FakeGemini(reply(BAD), busy)
    result = notes_to_script(fake, "jegyzet", "j.md")
    assert result.text == BAD.strip() and not result.repaired and result.issues


QUOTA = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
BUSY = errors.ServerError(503, {"error": {"message": "busy", "status": "UNAVAILABLE"}})
GONE = errors.ClientError(404, {"error": {"message": "gone", "status": "NOT_FOUND"}})


def httpx2_error(name):
    """An exception class that looks like it comes from the SDK's httpx2 transport."""
    return type(name, (Exception,), {"__module__": "httpx2._exceptions"})("boom")


@pytest.mark.parametrize("error", [QUOTA, BUSY, GONE, httpx2_error("ReadTimeout")])
def test_model_specific_error_falls_back_to_next_model(error):
    fake = FakeGemini(error, reply(BAD), reply(CLEAN))
    logs = []
    result = notes_to_script(fake, "jegyzet", "j.md", log=logs.append)
    assert [c["model"] for c in fake.calls] == [GEMINI_MODELS[0], GEMINI_MODELS[1], GEMINI_MODELS[1]]
    assert result.model == GEMINI_MODELS[1] and result.repaired  # repair stays on the model that answered
    assert any("trying next model" in m for m in logs)


@pytest.mark.parametrize(
    "error",
    [
        errors.ClientError(401, {"error": {"message": "nope", "status": "UNAUTHENTICATED"}}),
        httpx2_error("ConnectError"),
        httpx2_error("ConnectTimeout"),
        ScriptWriterError("Gemini refused the notes (SAFETY)."),
    ],
)
def test_key_network_and_refusal_errors_do_not_fall_back(error):
    fake = FakeGemini(error, reply(CLEAN))
    with pytest.raises(type(error)):
        notes_to_script(fake, "jegyzet", "j.md")
    assert len(fake.calls) == 1


def test_all_models_failing_raises_last_error():
    fake = FakeGemini(*([BUSY] * (len(GEMINI_MODELS) - 1)), QUOTA)
    with pytest.raises(ScriptWriterError, match="All Gemini models failed.*limit reached"):
        notes_to_script(fake, "jegyzet", "j.md")
    assert [c["model"] for c in fake.calls] == list(GEMINI_MODELS)


def test_stop_request_ends_the_chain():
    fake = FakeGemini(QUOTA, reply(CLEAN))
    with pytest.raises(ScriptWriterError, match="Stopped"):
        notes_to_script(fake, "jegyzet", "j.md", should_stop=lambda: bool(fake.calls))
    assert len(fake.calls) == 1


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
        (errors.ClientError(404, {"error": {"message": "gone", "status": "NOT_FOUND"}}), "GEMINI_MODELS"),
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
    assert done == [(True, f"✅ Script saved: jegyzet_SCRIPT.md ({GEMINI_MODELS[0]}) · pre-flight clean", str(path))]
    assert logs[0].startswith("✍️")


def test_thread_without_key_fails(qapp, monkeypatch, tmp_path):
    notes = tmp_path / "jegyzet.txt"
    notes.write_text("szöveg", encoding="utf-8")
    logs, done = run_thread(monkeypatch, FakeGemini(), "", notes, tmp_path)
    assert done[0][0] is False and "GEMINI_API_KEY" in done[0][1] and done[0][2] == ""
    assert logs[-1].startswith("❌")
