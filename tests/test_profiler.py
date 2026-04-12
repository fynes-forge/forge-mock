"""Tests for the profiler module — PII detection, profiles, and forge.yaml writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_mock.profiler.pii_detector import PIIDetector, ProfileSuggestion
from forge_mock.generators.profiles import apply_profile, list_profiles


# ---------------------------------------------------------------------------
# PIIDetector — name-based detection
# ---------------------------------------------------------------------------


class TestPIIDetectorNameRules:
    def setup_method(self) -> None:
        self.detector = PIIDetector()

    def test_email_detected(self) -> None:
        s = self.detector.suggest("email_address")
        assert s is not None
        assert s.profile == "email"
        assert s.confidence >= 0.90

    def test_nhs_number_detected(self) -> None:
        s = self.detector.suggest("nhs_no")
        assert s is not None
        assert s.profile == "nhs_number"

    def test_iban_detected(self) -> None:
        s = self.detector.suggest("iban")
        assert s is not None
        assert s.profile == "iban"
        assert s.confidence >= 0.95

    def test_ssn_detected(self) -> None:
        s = self.detector.suggest("ssn")
        assert s is not None
        assert s.profile == "ssn_us"

    def test_cusip_detected(self) -> None:
        s = self.detector.suggest("cusip_code")
        assert s is not None
        assert s.profile == "cusip"

    def test_postcode_detected(self) -> None:
        s = self.detector.suggest("postcode")
        assert s is not None
        assert "postcode" in s.profile

    def test_phone_uk_detected(self) -> None:
        s = self.detector.suggest("mobile_phone")
        assert s is not None

    def test_first_name_detected(self) -> None:
        s = self.detector.suggest("first_name")
        assert s is not None
        assert s.profile == "first_name"

    def test_uuid_detected(self) -> None:
        s = self.detector.suggest("guid")
        assert s is not None
        assert s.profile == "uuid"

    def test_url_detected(self) -> None:
        s = self.detector.suggest("website_url")
        assert s is not None
        assert s.profile == "url"

    def test_latitude_detected(self) -> None:
        s = self.detector.suggest("lat")
        assert s is not None
        assert s.profile == "latitude"

    def test_unrecognised_column_returns_none(self) -> None:
        s = self.detector.suggest("xyzzy_column_99")
        assert s is None

    def test_min_confidence_filter(self) -> None:
        # "price" matches with ~0.75 confidence
        s = self.detector.suggest("price", min_confidence=0.99)
        assert s is None

    def test_suggestion_is_dataclass(self) -> None:
        s = self.detector.suggest("email")
        assert isinstance(s, ProfileSuggestion)

    def test_suggest_all_returns_list(self) -> None:
        results = self.detector.suggest_all("email_address")
        assert isinstance(results, list)
        assert len(results) >= 1


class TestPIIDetectorValueRules:
    def setup_method(self) -> None:
        self.detector = PIIDetector()

    def test_email_values_detected(self) -> None:
        values = ["alice@example.com", "bob@test.org", "carol@domain.net"]
        s = self.detector.suggest("contact_field", sampled_values=values)
        assert s is not None
        assert s.profile == "email"

    def test_uuid_values_detected(self) -> None:
        values = [
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        ]
        s = self.detector.suggest("ref_id", sampled_values=values)
        assert s is not None
        assert s.profile == "uuid"

    def test_ipv4_values_detected(self) -> None:
        values = ["192.168.1.1", "10.0.0.255", "172.16.0.1"]
        s = self.detector.suggest("source_ip", sampled_values=values)
        assert s is not None
        assert s.profile == "ipv4"

    def test_url_values_detected(self) -> None:
        values = ["https://example.com", "http://test.org/path"]
        s = self.detector.suggest("link_field", sampled_values=values)
        assert s is not None
        assert s.profile == "url"

    def test_empty_values_still_uses_name(self) -> None:
        s = self.detector.suggest("email", sampled_values=[])
        assert s is not None
        assert s.profile == "email"


# ---------------------------------------------------------------------------
# Profiles library
# ---------------------------------------------------------------------------


class TestProfiles:
    def setup_method(self) -> None:
        from faker import Faker

        Faker.seed(42)
        self._faker = Faker()

    def test_list_profiles_returns_sorted_list(self) -> None:
        profiles = list_profiles()
        assert isinstance(profiles, list)
        assert len(profiles) >= 30
        assert profiles == sorted(profiles)

    def test_email_profile_generates_string(self) -> None:
        val = apply_profile("email", self._faker)
        assert isinstance(val, str)
        assert "@" in val

    def test_nhs_number_format(self) -> None:
        val = apply_profile("nhs_number", self._faker)
        assert isinstance(val, str)
        # Should be numeric with spaces, e.g. "123 456 7890"
        digits = val.replace(" ", "")
        assert digits.isdigit()

    def test_iban_returns_string(self) -> None:
        val = apply_profile("iban", self._faker)
        assert isinstance(val, str)
        assert len(val) >= 15

    def test_uuid_format(self) -> None:
        import re

        val = apply_profile("uuid", self._faker)
        assert re.match(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", val, re.I)

    def test_latitude_in_range(self) -> None:
        for _ in range(20):
            val = apply_profile("latitude", self._faker)
            assert -90.0 <= val <= 90.0

    def test_longitude_in_range(self) -> None:
        for _ in range(20):
            val = apply_profile("longitude", self._faker)
            assert -180.0 <= val <= 180.0

    def test_price_positive(self) -> None:
        for _ in range(20):
            val = apply_profile("price", self._faker)
            assert val >= 0.0

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown profile"):
            apply_profile("nonexistent_profile_xyz", self._faker)

    def test_all_profiles_generate_without_error(self) -> None:
        """Smoke-test every profile generates a value without raising."""
        errors = []
        for name in list_profiles():
            try:
                apply_profile(name, self._faker)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        assert not errors, f"Profiles failed: {errors}"


# ---------------------------------------------------------------------------
# forge.yaml writer/reader
# ---------------------------------------------------------------------------


class TestForgeYamlWriter:
    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        from forge_mock.profiler.forge_yaml_writer import write_forge_yaml, load_forge_yaml

        plan = {
            "tables": {
                "customers": {
                    "rows": 500,
                    "columns": {
                        "email": {"profile": "email"},
                        "amount": {"distribution": "normal", "mean": 50.0, "std": 5.0},
                    },
                }
            }
        }
        output_path = str(tmp_path / "forge.yaml")
        write_forge_yaml(plan, output_path)

        loaded = load_forge_yaml(output_path)
        assert "tables" in loaded
        assert "customers" in loaded["tables"]
        assert loaded["tables"]["customers"]["rows"] == 500
        assert loaded["tables"]["customers"]["columns"]["email"]["profile"] == "email"

    def test_write_strips_metadata_on_read(self, tmp_path: Path) -> None:
        from forge_mock.profiler.forge_yaml_writer import write_forge_yaml, load_forge_yaml

        plan = {"tables": {"orders": {"rows": 100}}}
        path = str(tmp_path / "forge.yaml")
        write_forge_yaml(plan, path)
        loaded = load_forge_yaml(path)
        assert "_forge_mock" not in loaded

    def test_load_missing_file_returns_empty(self) -> None:
        from forge_mock.profiler.forge_yaml_writer import load_forge_yaml

        result = load_forge_yaml("/nonexistent/path/forge.yaml")
        assert result == {}
