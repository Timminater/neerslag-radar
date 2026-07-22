"""Tests for KNMI setup metadata."""

import json
from pathlib import Path

TOKEN_URL = "https://developer.dataplatform.knmi.nl/open-data-api#token"


def test_all_knmi_key_forms_link_to_token_page() -> None:
    """Both initial setup and reconfiguration explain where keys are obtained."""
    integration = Path(__file__).parents[1] / "custom_components" / "neerslag_radar"
    for relative_path in ("strings.json", "translations/en.json", "translations/nl.json"):
        translations = json.loads(
            (integration / relative_path).read_text(encoding="utf-8")
        )
        steps = translations["config_subentries"]["provider"]["step"]
        for step_name in ("knmi", "reconfigure"):
            assert TOKEN_URL in steps[step_name]["data_description"]["api_key"]
            assert "use_anonymous_api_key" in steps[step_name]["data"]
            assert "use_anonymous_api_key" in steps[step_name]["data_description"]
