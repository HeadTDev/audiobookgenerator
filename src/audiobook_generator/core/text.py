"""Script text cleaning, chunking and naming helpers."""
import os
import re
import textwrap

from .config import MAX_CHUNK_CHARS

HEADING_MARKER_REGEX = re.compile(r"^#+\s*")
# Every script title ends in " - SCRIPT", which should not be read aloud.
HEADING_SCRIPT_SUFFIX_REGEX = re.compile(r"\s*[-–]\s*SCRIPT\s*$", re.IGNORECASE)
SENTENCE_END_REGEX = re.compile(r"(?<=[.!?…])\s+")


def heading_title(line):
    """'# SzA13: Title - SCRIPT' -> 'SzA13: Title'."""
    return HEADING_SCRIPT_SUFFIX_REGEX.sub("", HEADING_MARKER_REGEX.sub("", line.strip()))


def clean_markdown_text(text):
    # Square brackets are kept on purpose: "[serious]"-style audio tags are
    # interpreted (not spoken) by Eleven v4. Scripts must spell notation out in words
    # (v4 reads "/" as "per", for example); nothing is rewritten here.
    return "\n".join(spoken for spoken in map(clean_line, text.split("\n")) if spoken)


def clean_line(line):
    """Spoken form of one script line; '' when nothing in it would be read aloud.

    Shared by the cleaner and the pre-flight check, so reported line numbers match
    exactly what is sent to the API.
    """
    line = line.replace("**", "").strip()
    if line.startswith("#"):
        line = heading_title(line)
    return line if any(c.isalnum() for c in line) else ""


def create_chunks(text, limit=MAX_CHUNK_CHARS):
    """Pack cleaned lines into chunks of at most `limit` characters.

    Lines longer than the limit are split at sentence ends, or at spaces as a last resort.
    """
    units = []  # (separator before the unit, unit text)
    for line in clean_markdown_text(text).split("\n"):
        if len(line) <= limit:
            units.append(("\n", line))
            continue
        pieces = [
            piece
            for sentence in SENTENCE_END_REGEX.split(line)
            for piece in textwrap.wrap(sentence, limit)
        ]
        units.extend((" " if i else "\n", piece) for i, piece in enumerate(pieces))

    chunks = []
    current = ""
    for separator, unit in units:
        if not current:
            current = unit
        elif len(current) + len(separator) + len(unit) <= limit:
            current += separator + unit
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    return chunks


def output_name_for(md_name):
    stem = os.path.splitext(md_name)[0]
    if stem.endswith("_SCRIPT"):
        stem = stem[: -len("_SCRIPT")]
    return stem + ".mp3"


def audio_metadata_for(script_file, text):
    """ID3 tags: title from the script heading, album from the subject folder, track number."""
    base_name = os.path.basename(script_file)
    title = next(
        (heading_title(line) for line in text.split("\n") if line.strip().startswith("#")),
        os.path.splitext(output_name_for(base_name))[0],
    )
    folder = os.path.dirname(os.path.abspath(script_file))
    if os.path.basename(folder).lower() == "scripts":
        folder = os.path.dirname(folder)  # e.g. MI_Audiobook/Scripts -> MI_Audiobook
    album = re.sub(r"_?Audiobook$", "", os.path.basename(folder)).replace("_", " ").strip()
    metadata = {"title": title, "album": album or "Audiobook"}
    track = re.search(r"\d+", base_name)
    if track:
        metadata["track"] = str(int(track.group()))
    return metadata
