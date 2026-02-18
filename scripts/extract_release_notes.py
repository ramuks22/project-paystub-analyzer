import re
import sys
from pathlib import Path


def extract_release_notes(version: str, changelog_path: str = "CHANGELOG.md") -> str:
    """
    Extracts the release notes for a specific version from CHANGELOG.md.
    Expects "Keep a Changelog" format.
    """
    version = version.lstrip("v")
    try:
        content = Path(changelog_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Error: {changelog_path} not found.")
        sys.exit(1)

    # Regex to find the section for the version.
    # Matches: ## [version] - date ... content ... until next ## [version] or end of file
    pattern = rf"## \[{re.escape(version)}\](?: - .+)?\n(.*?)(?=\n## \[|$)"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print(f"Error: Could not find release notes for version {version} in {changelog_path}")
        # In a real pipeline, we might want to fail hard, or just print a default message.
        # Failing hard ensures we don't release without notes.
        sys.exit(1)

    return match.group(1).strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_release_notes.py <version>")
        sys.exit(1)

    version_arg = sys.argv[1]
    notes = extract_release_notes(version_arg)
    print(notes)
