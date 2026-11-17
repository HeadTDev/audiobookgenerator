"""Offscreen UI tests with temporary settings; the real .env and saved settings are untouched."""
import pytest
from PySide6.QtCore import QSettings

from audiobook_generator.ui import main_window, player
from conftest import write_script


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(main_window, "load_api_key", lambda: "sk_test")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    win = main_window.MainWindow(settings=settings)
    yield win
    win.close()


def load_folder(win, folder):
    win.input_edit.setText(str(folder))
    win.output_edit.setText(str(folder))
    win.refresh_file_list()


def test_file_table_sorting_check_column_and_summary(window, tmp_path):
    for number in (2, 10, 1):
        write_script(tmp_path, number, lines=1)
    (tmp_path / "T2_Teszt_SCRIPT.md").write_text("# T2: Cím\nAz I/O busz.\n", encoding="utf-8")
    load_folder(window, tmp_path)

    numbers = [window.table.item(r, main_window.COL_NUM).text() for r in range(3)]
    assert numbers == ["1", "2", "10"]  # numeric, not text order
    checks = {i["file_name"]: i["items"]["issues"].text() for i in window.rows.values()}
    assert checks["T2_Teszt_SCRIPT.md"] == "⚠ 1" and checks["T1_Teszt_SCRIPT.md"] == "✓"
    assert window.generate_btn.text() == "Generate 3 files"

    window._on_header_clicked(main_window.COL_CHECK)  # all checked -> none
    assert not window.generate_btn.isEnabled()


def test_clicking_check_cell_opens_details_without_toggling(window, tmp_path, monkeypatch):
    (tmp_path / "T1_Teszt_SCRIPT.md").write_text("# T1: Cím\nAz I/O busz.\n", encoding="utf-8")
    load_folder(window, tmp_path)
    info = next(iter(window.rows.values()))
    opened = []
    monkeypatch.setattr(window, "show_issues", opened.append)
    before = info["items"]["check"].checkState()
    window._on_cell_clicked(info["items"]["check"].row(), main_window.COL_ISSUES)
    assert opened == [info] and info["items"]["check"].checkState() == before


def test_format_time():
    assert player.format_time(700_000) == "11:40"
    assert player.format_time(3_725_000) == "1:02:05"


def test_waveform_peaks(tmp_path, tone_mp3):
    path = tmp_path / "tone.mp3"
    path.write_bytes(tone_mp3)
    peaks = player.compute_peaks(str(path))
    assert peaks and max(peaks) == 1.0 and min(peaks) >= 0.12
