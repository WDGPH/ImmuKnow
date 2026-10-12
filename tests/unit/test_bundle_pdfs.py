"""Override validation uses documented warning codes and unambiguous public IDs."""

import pytest

from immuknow.bundle_pdfs import validate_overrides


def test_overrides_accept_known_absent_and_recorded_custom_warnings() -> None:
    record = {
        "entries": [
            {
                "client_id": "0000000001",
                "checks": [{"code": "authored.follow_up", "status": "warn"}],
            }
        ]
    }
    overrides = {
        "allow_delivery_warnings": ["data.school_unmatched", "authored.follow_up"],
        "clients": {"0000000001": "review"},
    }
    result = validate_overrides(overrides, record)
    assert result["allow_delivery_warnings"] == [
        "authored.follow_up",
        "data.school_unmatched",
    ]
    assert result["clients"] == {"0000000001": "review"}
    with pytest.raises(ValueError, match="Unknown warning code"):
        validate_overrides(
            {"allow_delivery_warnings": ["data.school_unmatced"]}, record
        )
    with pytest.raises(ValueError, match="unique ten-digit"):
        validate_overrides({"clients": {"0000000002": "delivery"}}, record)
    with pytest.raises(ValueError, match="delivery or review"):
        validate_overrides({"clients": {"0000000001": "both"}}, record)
    repeated = {"entries": record["entries"] * 2}
    with pytest.raises(ValueError, match="unique ten-digit"):
        validate_overrides({"clients": {"0000000001": "delivery"}}, repeated)
