from audiobook_generator.core.text import (
    audio_metadata_for,
    clean_line,
    clean_markdown_text,
    create_chunks,
    heading_title,
    output_name_for,
)


def test_heading_title_drops_marker_and_script_suffix():
    assert heading_title("# SzA13: A futószalag - SCRIPT") == "SzA13: A futószalag"
    assert heading_title("## Cím – script") == "Cím"


def test_clean_line_keeps_audio_tags_and_drops_markup_only_lines():
    assert clean_line("  [serious] A **fontos** rész.  ") == "[serious] A fontos rész."
    assert clean_line("---") == ""
    assert clean_line("**") == ""


def test_clean_markdown_text_joins_spoken_lines_only():
    text = "# T1: Cím - SCRIPT\n\n---\nElső sor.\n\n**Második** sor."
    assert clean_markdown_text(text) == "T1: Cím\nElső sor.\nMásodik sor."


def test_short_text_is_one_chunk():
    assert create_chunks("Egy rövid mondat.") == ["Egy rövid mondat."]


def test_chunks_respect_limit_and_lose_no_text():
    lines = [f"Sor {i}. " + "y" * 900 for i in range(20)]
    text = "\n".join(lines)
    chunks = create_chunks(text, limit=2500)
    assert len(chunks) > 1
    assert all(len(chunk) <= 2500 for chunk in chunks)
    assert "\n".join(chunks) == clean_markdown_text(text)


def test_overlong_line_is_split_at_sentence_ends():
    line = " ".join(f"Ez a(z) {i}. mondat, ami elég hosszú." for i in range(200))
    chunks = create_chunks(line, limit=1000)
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert " ".join(chunks) == line
    assert all(chunk.endswith(".") for chunk in chunks)


def test_output_name_for():
    assert output_name_for("MI1_Gepi_Tanulas_SCRIPT.md") == "MI1_Gepi_Tanulas.mp3"
    assert output_name_for("notes.md") == "notes.mp3"


def test_audio_metadata_from_heading_and_folders(tmp_path):
    script = tmp_path / "MI_Audiobook" / "Scripts" / "MI12_Nyelvi_Modellek_SCRIPT.md"
    script.parent.mkdir(parents=True)
    text = "# MI12: Nagy nyelvi modellek - SCRIPT\nSzöveg."
    assert audio_metadata_for(str(script), text) == {
        "title": "MI12: Nagy nyelvi modellek",
        "album": "MI",
        "track": "12",
    }
