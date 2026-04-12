"""PII and semantic heuristic detector."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ProfileSuggestion:
    profile: str
    confidence: float
    reason: str


# Rule set: (compiled_pattern, profile_name, confidence, reason)
_NAME_RULES: list[tuple[re.Pattern[str], str, float, str]] = [
    # ── Healthcare ────────────────────────────────────────────────────
    (
        re.compile(r"\bnhs[_\s]?(no|num|number|id)?\b", re.I),
        "nhs_number",
        0.95,
        "column name matches NHS number pattern",
    ),
    (
        re.compile(r"\bssn\b|social[_\s]security", re.I),
        "ssn_us",
        0.95,
        "column name matches SSN pattern",
    ),
    (
        re.compile(r"\bmrn\b|medical[_\s]record", re.I),
        "mrn",
        0.90,
        "column name matches MRN pattern",
    ),
    (re.compile(r"\bsnomed\b", re.I), "snomed_code", 0.90, "column name matches SNOMED code"),
    (
        re.compile(r"\bicd[_\s]?10\b|\bdiagnosis[_\s]code\b", re.I),
        "icd10_code",
        0.88,
        "column name matches ICD-10 code",
    ),
    (
        re.compile(r"\bdate[_\s]of[_\s]birth\b|\bdob\b|\bbirthdate\b", re.I),
        "date_of_birth",
        0.92,
        "column name matches date of birth",
    ),
    # ── Finance / Banking ─────────────────────────────────────────────
    (re.compile(r"\biban\b", re.I), "iban", 0.98, "column name is IBAN"),
    (
        re.compile(r"\bbic\b|\bswift[_\s]?code\b", re.I),
        "bic_swift",
        0.95,
        "column name matches BIC/SWIFT",
    ),
    (
        re.compile(r"\bsort[_\s]?code\b", re.I),
        "sort_code_uk",
        0.95,
        "column name matches UK sort code",
    ),
    (re.compile(r"cusip", re.I), "cusip", 0.98, "column name matches CUSIP"),
    (re.compile(r"\bisin\b", re.I), "isin", 0.98, "column name is ISIN"),
    (re.compile(r"\blei\b", re.I), "lei", 0.95, "column name is LEI"),
    (
        re.compile(r"\bticker[_\s]?(symbol)?\b|\bsymbol\b", re.I),
        "ticker",
        0.88,
        "column name matches ticker symbol",
    ),
    (
        re.compile(r"\bcard[_\s]?(number|no|num)\b|credit[_\s]card", re.I),
        "card_number",
        0.92,
        "column name matches card number",
    ),
    (
        re.compile(r"\bcurrenc(y|ies)[_\s]?(code)?\b", re.I),
        "currency_code",
        0.90,
        "column name matches currency code",
    ),
    (
        re.compile(r"\b(unit[_\s]?)?price\b|\bamount\b|\bcost\b|\bfee\b", re.I),
        "price",
        0.75,
        "column name suggests monetary amount",
    ),
    # ── Personal contact ──────────────────────────────────────────────
    (
        re.compile(r"\bemail[_\s]?(address)?\b", re.I),
        "email",
        0.97,
        "column name matches email address",
    ),
    (
        re.compile(r"\b(mobile|cell)[_\s]?(phone|no|number)?\b|\bphone[_\s]?uk\b", re.I),
        "phone_uk",
        0.85,
        "column name suggests UK phone",
    ),
    (
        re.compile(r"\bphone[_\s]?(number|no|num)?\b|\bmobile\b", re.I),
        "phone_us",
        0.80,
        "column name suggests phone number",
    ),
    (
        re.compile(r"\bfirst[_\s]?name\b|\bgiven[_\s]?name\b", re.I),
        "first_name",
        0.92,
        "column name matches first name",
    ),
    (
        re.compile(r"\blast[_\s]?name\b|\bsurname\b|\bfamily[_\s]?name\b", re.I),
        "last_name",
        0.92,
        "column name matches last name",
    ),
    (
        re.compile(r"\bfull[_\s]?name\b|\bname\b", re.I),
        "full_name",
        0.78,
        "column name matches full name",
    ),
    (
        re.compile(r"\busername\b|\buser[_\s]?handle\b|\blogin\b", re.I),
        "username",
        0.88,
        "column name matches username",
    ),
    # ── Address / Location ────────────────────────────────────────────
    (
        re.compile(r"\bpost[_\s]?code\b|\bzip[_\s]?(code)?\b", re.I),
        "postcode_uk",
        0.88,
        "column name matches postcode",
    ),
    (re.compile(r"\bcity\b|\btown\b|\blocality\b", re.I), "city", 0.85, "column name matches city"),
    (
        re.compile(r"\bcountry[_\s]?(code)?\b", re.I),
        "country_code",
        0.85,
        "column name matches country",
    ),
    (
        re.compile(r"\b(street|address)[_\s]?(line)?\b", re.I),
        "address_line",
        0.85,
        "column name matches street address",
    ),
    (re.compile(r"\blatitude\b|\blat\b", re.I), "latitude", 0.92, "column name matches latitude"),
    (
        re.compile(r"\blongitude\b|\blon(g)?\b", re.I),
        "longitude",
        0.92,
        "column name matches longitude",
    ),
    # ── Internet / Tech ───────────────────────────────────────────────
    (re.compile(r"url|website|homepage|link", re.I), "url", 0.88, "column name matches URL"),
    (
        re.compile(r"\bip[_\s]?(address|addr)?\b", re.I),
        "ipv4",
        0.85,
        "column name matches IP address",
    ),
    (re.compile(r"\buuid\b|\bguid\b", re.I), "uuid", 0.95, "column name matches UUID/GUID"),
    (
        re.compile(r"\bpassword[_\s]?(hash|digest)?\b", re.I),
        "password_hash",
        0.85,
        "column name matches password/hash",
    ),
    # ── Organisation ──────────────────────────────────────────────────
    (
        re.compile(r"\bcompan(y|ies)[_\s]?(name)?\b|\bfirm\b", re.I),
        "company_name",
        0.85,
        "column name matches company name",
    ),
    (
        re.compile(r"\bjob[_\s]?title\b|\brole\b|\bposition\b", re.I),
        "job_title",
        0.82,
        "column name matches job title",
    ),
    (
        re.compile(r"\bdepartment\b|\bdept\b", re.I),
        "department",
        0.82,
        "column name matches department",
    ),
]

_VALUE_RULES: list[tuple[re.Pattern[str], str, float, str]] = [
    (
        re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"),
        "email",
        0.95,
        "sampled values match email format",
    ),
    (
        re.compile(r"^\d{3}\s\d{3}\s\d{4}$"),
        "nhs_number",
        0.90,
        "sampled values match NHS number format",
    ),
    (re.compile(r"^\d{9}$"), "ssn_us", 0.75, "sampled values match SSN format (9 digits)"),
    (
        re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}$"),
        "iban",
        0.92,
        "sampled values match IBAN format",
    ),
    (
        re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$"),
        "bic_swift",
        0.88,
        "sampled values match BIC/SWIFT format",
    ),
    (
        re.compile(r"^\d{2}-\d{2}-\d{2}$"),
        "sort_code_uk",
        0.88,
        "sampled values match UK sort code format",
    ),
    (re.compile(r"^[A-Z]{2}\d{10}$"), "isin", 0.90, "sampled values match ISIN format"),
    (re.compile(r"^https?://"), "url", 0.88, "sampled values match URL format"),
    (
        re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),
        "ipv4",
        0.92,
        "sampled values match IPv4 format",
    ),
    (
        re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
        "uuid",
        0.95,
        "sampled values match UUID format",
    ),
]


class PIIDetector:
    def suggest(
        self,
        column_name: str,
        sampled_values: Optional[list[Any]] = None,
        min_confidence: float = 0.75,
    ) -> Optional[ProfileSuggestion]:
        best: Optional[ProfileSuggestion] = None
        for pattern, profile, confidence, reason in _NAME_RULES:
            if pattern.search(column_name):
                if best is None or confidence > best.confidence:
                    best = ProfileSuggestion(profile=profile, confidence=confidence, reason=reason)
        if sampled_values:
            value_suggestion = self._analyse_values(sampled_values)
            if value_suggestion:
                if best is None or value_suggestion.confidence > best.confidence:
                    best = value_suggestion
        if best and best.confidence >= min_confidence:
            return best
        return None

    def suggest_all(
        self, column_name: str, sampled_values: Optional[list[Any]] = None
    ) -> list[ProfileSuggestion]:
        results: list[ProfileSuggestion] = []
        for pattern, profile, confidence, reason in _NAME_RULES:
            if pattern.search(column_name):
                results.append(
                    ProfileSuggestion(profile=profile, confidence=confidence, reason=reason)
                )
        if sampled_values:
            vs = self._analyse_values(sampled_values)
            if vs:
                results.append(vs)
        return sorted(results, key=lambda s: s.confidence, reverse=True)

    def _analyse_values(self, values: list[Any]) -> Optional[ProfileSuggestion]:
        str_values = [str(v) for v in values if v is not None]
        if not str_values:
            return None
        for pattern, profile, confidence, reason in _VALUE_RULES:
            matches = sum(1 for v in str_values if pattern.match(v))
            match_rate = matches / len(str_values)
            if match_rate >= 0.7:
                return ProfileSuggestion(
                    profile=profile,
                    confidence=round(confidence * match_rate, 3),
                    reason=f"{reason} ({match_rate:.0%} match)",
                )
        return None
