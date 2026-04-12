"""Semantic column profiles — named generators that map to Faker providers.

Users reference these by name in forge.yaml instead of raw Faker internals:

    columns:
      patient_email:   { profile: email }
      mobile:          { profile: phone_uk }
      sort_code:       { profile: sort_code_uk }

Each entry is a factory: (Faker, locale) -> zero-arg callable -> Any.
"""

from __future__ import annotations

from typing import Any, Callable

from faker import Faker

ProfileFactory = Callable[[Faker], Callable[[], Any]]

# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------

PROFILES: dict[str, ProfileFactory] = {
    # ── Personal identity ──────────────────────────────────────────────
    "first_name": lambda f: f.first_name,
    "last_name": lambda f: f.last_name,
    "full_name": lambda f: f.name,
    "username": lambda f: f.user_name,
    "password_hash": lambda f: lambda: f.sha256(),
    "gender": lambda f: lambda: f.random_element(["M", "F", "NB", "U"]),
    "date_of_birth": lambda f: lambda: str(f.date_of_birth(minimum_age=18, maximum_age=90)),
    # ── Contact ───────────────────────────────────────────────────────
    "email": lambda f: f.email,
    "email_work": lambda f: lambda: f.company_email(),
    "phone_us": lambda f: lambda: f.numerify("(###) ###-####"),
    "phone_uk": lambda f: lambda: f.numerify("07### ######"),
    "phone_international": lambda f: f.phone_number,
    # ── Address ───────────────────────────────────────────────────────
    "address_line": lambda f: f.street_address,
    "city": lambda f: f.city,
    "country": lambda f: f.country,
    "country_code": lambda f: f.country_code,
    "postcode_uk": lambda f: lambda: f.bothify("??# #??").upper(),
    "postcode_us": lambda f: lambda: f.numerify("#####"),
    "us_state": lambda f: f.state,
    "us_state_abbr": lambda f: f.state_abbr,
    "latitude": lambda f: lambda: round(float(f.latitude()), 6),
    "longitude": lambda f: lambda: round(float(f.longitude()), 6),
    # ── Finance ───────────────────────────────────────────────────────
    "iban": lambda f: f.iban,
    "bic_swift": lambda f: lambda: f.swift(),
    "sort_code_uk": lambda f: lambda: f.numerify("##-##-##"),
    "card_number": lambda f: lambda: f.credit_card_number(),
    "card_expiry": lambda f: lambda: f.credit_card_expire(),
    "currency_code": lambda f: f.currency_code,
    "currency_name": lambda f: f.currency_name,
    "price": lambda f: lambda: round(abs(f.pyfloat(min_value=0.01, max_value=9999)), 2),
    # ── Healthcare identifiers ─────────────────────────────────────────
    "nhs_number": lambda f: lambda: f.numerify("### ### ####"),
    "ssn_us": lambda f: lambda: f.ssn(),
    "mrn": lambda f: lambda: f.bothify("MRN-#######"),
    "snomed_code": lambda f: lambda: str(f.random_int(min=100000000, max=999999999)),
    "icd10_code": lambda f: lambda: f.bothify("?##.#").upper(),
    # ── Securities / Finance codes ─────────────────────────────────────
    "cusip": lambda f: lambda: f.bothify("?######?#").upper(),
    "isin": lambda f: lambda: f.bothify("??##########").upper(),
    "ticker": lambda f: lambda: f.lexify("????", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "lei": lambda f: lambda: f.bothify("####00####0000??????00").upper(),
    # ── Internet / Tech ───────────────────────────────────────────────
    "url": lambda f: f.url,
    "domain": lambda f: f.domain_name,
    "ipv4": lambda f: f.ipv4,
    "ipv6": lambda f: f.ipv6,
    "mac_address": lambda f: f.mac_address,
    "user_agent": lambda f: f.user_agent,
    "hex_colour": lambda f: f.hex_color,
    "mime_type": lambda f: f.mime_type,
    "file_path": lambda f: f.file_path,
    "slug": lambda f: f.slug,
    "uuid": lambda f: lambda: str(f.uuid4()),
    # ── Organisation ──────────────────────────────────────────────────
    "company_name": lambda f: f.company,
    "company_suffix": lambda f: f.company_suffix,
    "job_title": lambda f: f.job,
    "department": lambda f: (
        lambda: f.random_element(
            [
                "Engineering",
                "Sales",
                "Marketing",
                "Finance",
                "HR",
                "Legal",
                "Product",
                "Operations",
                "Customer Success",
            ]
        )
    ),
    # ── Content ───────────────────────────────────────────────────────
    "sentence": lambda f: f.sentence,
    "paragraph": lambda f: f.paragraph,
    "word": lambda f: f.word,
    "catch_phrase": lambda f: f.catch_phrase,
}


def apply_profile(profile_name: str, faker: Faker) -> Any:
    """Generate one value using the named profile.

    Raises ValueError for unknown profile names.
    """
    factory = PROFILES.get(profile_name)
    if factory is None:
        available = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles:\n  {available}")
    return factory(faker)()


def list_profiles() -> list[str]:
    """Return sorted list of all profile names."""
    return sorted(PROFILES)
