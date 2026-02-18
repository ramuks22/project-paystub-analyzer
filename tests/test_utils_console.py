import pytest
from unittest.mock import patch
from paystub_analyzer.utils import console


def test_is_interactive_false():
    with patch("sys.stdin.isatty", return_value=False):
        assert console.is_interactive() is False


def test_is_interactive_true():
    with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
        assert console.is_interactive() is True


def test_ask_input_non_interactive_default():
    with patch("paystub_analyzer.utils.console.is_interactive", return_value=False):
        assert console.ask_input("Prompt", default="Default") == "Default"


def test_ask_input_non_interactive_no_default_raises():
    with patch("paystub_analyzer.utils.console.is_interactive", return_value=False):
        with pytest.raises(RuntimeError):
            console.ask_input("Prompt")


def test_ask_input_interactive_mock_tty():
    with (
        patch("paystub_analyzer.utils.console.is_interactive", return_value=True),
        patch("builtins.input", return_value="UserValue"),
        patch("paystub_analyzer.utils.console.RICH_AVAILABLE", False),
    ):
        assert console.ask_input("Prompt") == "UserValue"


def test_print_table_ascii_fallback(capsys):
    with patch("paystub_analyzer.utils.console.RICH_AVAILABLE", False):
        console.print_table("Test Table", ["Col1", "Col2"], [["A", "B"], ["CCCC", "D"]])

    captured = capsys.readouterr()
    assert "Test Table" in captured.out
    assert "Col1 | Col2" in captured.out
    assert "CCCC | D   " in captured.out
