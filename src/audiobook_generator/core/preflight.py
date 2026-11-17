"""Pre-flight check: find notation the voice would misread, before paying for it.

Two severities, kept honest:
- MISREAD: confirmed with Eleven v4 (a slash is read as "per"; "[MAR]" is swallowed as an
  audio tag).
- CHECK: likely to read oddly but not verified; listen to it or write it out in words.
"""
import re
from dataclasses import dataclass

from .text import clean_line

MISREAD = "misread"
CHECK = "check"

# Standalone lowercase words in brackets are v4 audio tags ("[serious]") and are fine.
AUDIO_TAG = re.compile(r"(?<!\S)\[[a-z][a-z ]*\](?!\S)")

# (severity, pattern, message). Order matters: each match is blanked out before the
# next rule runs, so "<-" counts as an arrow only, not also as "<", and URL slashes
# are not reported again as slashes.
RULES = [
    (CHECK, re.compile(r"https?://\S+|www\.\S+"), "URL: would be spelled out character by character."),
    (MISREAD, re.compile(r"\[[^\]\n]*\]"), "Bracketed text is treated as an audio tag and skipped silently. Remove the brackets."),
    # The token around the slash, without surrounding punctuation: "(zoom/crop)," -> "zoom/crop".
    (MISREAD, re.compile(r"[^\s.,;:!?()\"']*/[^\s.,;:!?()\"']*"),
     'Slash is read as "per". Write "or", "and" or "per" in words.'),
    (CHECK, re.compile(r"<=>|<-+|-+>|=>|[←→⇒⇔]"), "Arrow: may be skipped or misread. Describe it in words."),
    (CHECK, re.compile(r"\S*\^\S*"), 'Power "^": write it out, e.g. "to the power of".'),
    (CHECK, re.compile(r"\w+_\w+"), 'Subscript "_": may be read literally. Write e.g. "x sub i".'),
    (CHECK, re.compile(r"[=<>≤≥≠±×÷√∑∫∞]"), "Math symbol: may be misread. Write the formula in words."),
    (CHECK, re.compile(r"`[^`]*`?"), "Code formatting: backticks may be read aloud. Use plain text."),
    (CHECK, re.compile(r"(?<!\*)\*(?!\*)"), 'Single "*": markdown emphasis or multiplication; may be read aloud.'),
    (CHECK, re.compile(r"\|"), 'Table "|": tables are not read well. Rewrite as sentences.'),
]


@dataclass
class Issue:
    line: int  # 1-based line number in the .md file
    severity: str
    message: str
    text: str  # the spoken form of the line
    start: int
    end: int


def check_script(text):
    """All issues in a script, in line order. Lines the cleaner drops are not checked."""
    issues = []
    any_spoken = False
    for number, raw in enumerate(text.split("\n"), start=1):
        spoken = clean_line(raw)
        if not spoken:
            continue
        any_spoken = True
        scan = AUDIO_TAG.sub(lambda m: " " * len(m.group()), spoken)
        for severity, pattern, message in RULES:
            for match in pattern.finditer(scan):
                if not match.group().strip():
                    continue
                issues.append(Issue(number, severity, message, spoken, match.start(), match.end()))
            scan = pattern.sub(lambda m: " " * len(m.group()), scan)
    if not any_spoken:
        issues.append(Issue(1, MISREAD, "No readable text: nothing would be generated.", "", 0, 0))
    return sorted(issues, key=lambda issue: (issue.line, issue.start))


def count_by_severity(issues):
    misread = sum(issue.severity == MISREAD for issue in issues)
    return misread, len(issues) - misread
