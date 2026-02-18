from unittest.mock import patch
from paystub_analyzer.cli.annual import main


@patch("paystub_analyzer.utils.console.is_interactive", return_value=True)
@patch("paystub_analyzer.utils.console.ask_input")
@patch("paystub_analyzer.utils.console.ask_confirm")
@patch("paystub_analyzer.annual.build_household_package")
@patch("paystub_analyzer.cli.annual.write_json")
def test_interactive_mode_prompts(mock_write_json, mock_build, mock_confirm, mock_ask, mock_is_interactive):
    # Setup mocks
    mock_ask.side_effect = ["2025", "config.json"]  # Year, Config Path
    mock_confirm.return_value = True  # Yes to "Use config?"

    # Mock build return to avoid crash
    mock_build.return_value = {
        "report": {
            "household_summary": {"total_gross_pay_cents": 0, "total_fed_tax_cents": 0, "ready_to_file": True},
            "filers": [],
        },
        "filers_analysis": [],
    }

    # Mock file existence check inside read_json/path checks
    # limiting scope to just avoid FileNotFoundError on the config path "config.json"
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("paystub_analyzer.cli.annual.read_json", return_value={"version": "0.2.0", "filers": []}),
        patch("paystub_analyzer.utils.contracts.validate_output"),
    ):
        with patch("sys.argv", ["paystub-annual", "--interactive"]):
            main()

    # Verify Year was prompted
    _, kwargs = mock_build.call_args
    assert kwargs["tax_year"] == 2025

    # Verify Config was prompted
    assert mock_ask.call_count == 2
    assert mock_confirm.call_count == 1
