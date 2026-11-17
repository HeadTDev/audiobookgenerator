from audiobook_generator.core.preflight import (
    CHECK,
    MISREAD,
    check_script,
    count_by_severity,
)


def found(text):
    return [(issue.severity, issue.text[issue.start:issue.end]) for issue in check_script(text)]


def test_clean_script_has_no_issues():
    text = (
        "# T1: Cím - SCRIPT\n"
        "[serious] A **Byte-Pair Encoding** – pl. 98%-os pontosság, 2014-ben.\n"
        "A Levenberg–Marquardt módszer. [slowly] Szöveg [emphasizes] itt."
    )
    assert found(text) == []


def test_slash_and_brackets_are_confirmed_misreads():
    assert found("Az I/O busz.") == [(MISREAD, "I/O")]
    assert found("MDR értéke [MAR] lesz.") == [(MISREAD, "[MAR]")]
    assert found("Az a[i] elem.") == [(MISREAD, "[i]")]


def test_arrow_is_reported_once_not_also_as_less_than():
    assert found("MAR <- PC") == [(CHECK, "<-")]


def test_url_is_not_reported_again_as_slash():
    assert found("Lásd: https://example.com/a/b") == [(CHECK, "https://example.com/a/b")]


def test_unverified_notation_is_check_level():
    kinds = {severity for severity, _ in found("x_i^2 = 3, `kód` és | tábla")}
    assert kinds == {CHECK}


def test_script_without_readable_text_is_flagged():
    assert found("---\n\n**\n")[0][0] == MISREAD


def test_issues_are_in_line_and_column_order_with_line_numbers():
    issues = check_script("# Cím\nElső I/O.\nMAR <- [MAR]\n")
    assert [(i.line, i.text[i.start:i.end]) for i in issues] == [
        (2, "I/O"), (3, "<-"), (3, "[MAR]"),
    ]
    assert count_by_severity(issues) == (2, 1)
