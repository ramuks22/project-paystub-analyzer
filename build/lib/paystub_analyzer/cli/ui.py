"""
CLI Entry Point: paystub-ui

Launches the Streamlit UI.
"""

import sys
from pathlib import Path
from streamlit.web import cli as stcli


def main() -> None:
    # Resolve the absolute path to `ui/app.py` in the package source
    # Assumes structure:
    # pyproject.toml
    # ui/app.py
    # paystub_analyzer/cli/ui.py

    # Locate app.py relative to this file:
    # paystub_analyzer/cli/ui.py -> paystub_analyzer/ui/app.py
    package_root = Path(__file__).resolve().parent.parent
    app_path = package_root / "ui" / "app.py"

    if not app_path.exists():
        # Fallback: try to find it as a resource if installed as a zip (unlikely for streamlit)
        # or error out clearly
        print(f"Error: Could not find UI entry point at {app_path}", file=sys.stderr)
        sys.exit(1)

    # Allow passing arguments to streamlit
    # By default, run the app. If user passes args, they might be for streamlit.
    sys.argv = ["streamlit", "run", str(app_path)] + sys.argv[1:]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
