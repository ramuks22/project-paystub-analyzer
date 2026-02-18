import json
from pathlib import Path
from typing import Any, Dict
import jsonschema
from jsonschema.exceptions import ValidationError


class ContractError(Exception):
    """Raised when output violates data contract."""

    pass


def load_schema(schema_name: str) -> Dict[str, Any]:
    """Load a JSON schema from the package."""
    schema_path = Path(__file__).parent.parent / "schemas" / f"{schema_name}.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_name}")

    with open(schema_path, "r") as f:
        return dict(json.load(f))


def validate_output(data: Dict[str, Any], schema_name: str, mode: str = "FILING") -> None:
    """
    Validate data against a JSON schema.

    Args:
        data: The dictionary to validate.
        schema_name: Name of the schema file (without .json extension).
        mode: 'FILING' (raises error) or 'REVIEW' (logs warning).

    Raises:
        ContractError: If validation fails and mode is FILING.
    """
    try:
        schema = load_schema(schema_name)
        jsonschema.validate(instance=data, schema=schema)
    except (ValidationError, FileNotFoundError) as e:
        msg = f"Data Contract Violation ({schema_name}): {str(e)}"
        if mode == "FILING":
            raise ContractError(msg) from e
        else:
            # In a real app, use logger.warning
            print(f"WARNING: {msg}")
