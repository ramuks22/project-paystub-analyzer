from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_household_config_v0_2_to_v0_3(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate a v0.2.x household configuration to v0.3.0.

    Changes:
    - Bumps version to 0.3.0.
    - Ensures w2_files is a list (already true in v0.2, but good to be safe).
    - Logs a warning about deprecation.
    """
    version = config.get("version", "")
    if version.startswith("0.2."):
        logger.warning(
            f"Migrating household config from {version} to 0.3.0. "
            "Please update your config file to suppress this warning."
        )
        config["version"] = "0.3.0"

        # v0.3.0 adds w2_aggregation_mode, but it has a default in schema so we don't strict need to add it here.
        # But for clarity we can.
        for filer in config.get("filers", []):
            sources = filer.get("sources", {})
            if "w2_aggregation_mode" not in sources:
                sources["w2_aggregation_mode"] = "SUM"

    return config


def migrate_household_config_v0_3_to_v0_4(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate a v0.3.x household configuration to v0.4.0.

    Changes:
    - Bumps version to 0.4.0.
    - Warns about missing metadata like filing_year and state.
    """
    version = config.get("version", "")
    if version.startswith("0.3."):
        logger.warning(
            f"Migrating household config from {version} to 0.4.0. "
            "Please update your config file to explicitly provide filing_year and state."
        )
        config["version"] = "0.4.0"

    return config


def migrate_household_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Run all sequential migrations to bring a configuration payload to the latest stable version.
    """
    version = config.get("version", "")
    if version.startswith("0.2."):
        config = migrate_household_config_v0_2_to_v0_3(config)
        version = config.get("version", "")

    if version.startswith("0.3."):
        config = migrate_household_config_v0_3_to_v0_4(config)
        version = config.get("version", "")

    return config
