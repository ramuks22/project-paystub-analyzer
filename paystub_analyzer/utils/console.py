import sys
from typing import List, Optional

# Try importing rich, else set flag
try:
    from rich.console import Console
    from rich.table import Table
    from rich.prompt import Prompt, Confirm

    RICH_AVAILABLE = True
    _console: Optional[Console] = Console()
except ImportError:
    RICH_AVAILABLE = False
    _console = None


def is_interactive() -> bool:
    """Check if we are in an interactive TTY session."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def print_step(title: str) -> None:
    """Print a step header."""
    if RICH_AVAILABLE and _console:
        _console.rule(f"[bold blue]{title}[/]")
    else:
        print(f"\n--- {title} ---")


def print_success(message: str) -> None:
    """Print a success message."""
    if RICH_AVAILABLE and _console:
        _console.print(f"[bold green]SUCCESS:[/] {message}")
    else:
        print(f"SUCCESS: {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    if RICH_AVAILABLE and _console:
        _console.print(f"[bold yellow]WARNING:[/] {message}")
    else:
        print(f"WARNING: {message}")


def print_error(message: str, exit_code: Optional[int] = None) -> None:
    """Print an error message and optionally exit."""
    if RICH_AVAILABLE and _console:
        _console.print(f"[bold red]ERROR:[/] {message}")
    else:
        print(f"ERROR: {message}")

    if exit_code is not None:
        sys.exit(exit_code)


def print_table(title: str, columns: List[str], rows: List[List[str]]) -> None:
    """Print a table with optional title."""
    if RICH_AVAILABLE and _console:
        table = Table(title=title)
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        _console.print(table)
    else:
        print(f"\n{title}")
        # Simple ASCII fallback
        # Calc widths
        if not rows:
            print("(No data)")
            return

        widths = [len(c) for c in columns]
        for row in rows:
            for i, val in enumerate(row):
                widths[i] = max(widths[i], len(str(val)))

        # Header
        header = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
        print(header)
        print("-" * len(header))

        # Rows
        for row in rows:
            print(" | ".join(str(v).ljust(w) for v, w in zip(row, widths)))
        print("")


def ask_input(prompt_text: str, default: Optional[str] = None, required: bool = True) -> str:
    """
    Prompt for user input (interactive only).
    If not interactive, returns default if present, else raises generic error.
    """
    if not is_interactive():
        if default is not None:
            return default
        raise RuntimeError("Interactive input required but not in TTY mode.")

    if RICH_AVAILABLE:
        if default is not None:
            return str(Prompt.ask(prompt_text, default=default))
        return str(Prompt.ask(prompt_text))
    else:
        p = f"{prompt_text} [{default}]: " if default else f"{prompt_text}: "
        val = input(p).strip()
        if not val and default:
            return default
        return val


def ask_confirm(prompt_text: str, default: bool = False) -> bool:
    """Ask for yes/no confirmation."""
    if not is_interactive():
        return default

    if RICH_AVAILABLE:
        return bool(Confirm.ask(prompt_text, default=default))
    else:
        d_str = "Y/n" if default else "y/N"
        val = input(f"{prompt_text} ({d_str}): ").strip().lower()
        if not val:
            return default
        return val in ("y", "yes")
