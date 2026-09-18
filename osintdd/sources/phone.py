"""Telefonszám – offline elemzés (phonenumbers). Fizetős/szürke: Truecaller, GetContact, NumLookup – nincs beépítve."""
from __future__ import annotations

from ..core import Finding, Target


def run(t: Target, http, log, case) -> list[Finding]:
    if not (case.get("person_checks") and t.phone):
        return []
    import phonenumbers
    from phonenumbers import carrier, geocoder, number_type, PhoneNumberType
    try:
        n = phonenumbers.parse(t.phone, t.country or "HU")
    except Exception as e:  # noqa: BLE001
        return [Finding("phone", "phone", "Telefonszám nem értelmezhető", str(e), severity="low")]
    types = {PhoneNumberType.MOBILE: "mobil", PhoneNumberType.FIXED_LINE: "vezetékes", PhoneNumberType.VOIP: "VoIP", PhoneNumberType.TOLL_FREE: "zöld szám"}
    valid = phonenumbers.is_valid_number(n)
    return [Finding("phone", "phone", f"Telefonszám: {phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.INTERNATIONAL)}",
                    f"érvényes: {valid} · típus: {types.get(number_type(n), 'egyéb')} · régió: {geocoder.description_for_number(n, 'hu')} · "
                    f"eredeti szolgáltató (hordozás nélkül): {carrier.name_for_number(n, 'hu') or '-'}",
                    severity="info" if valid else "low", data={"e164": phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164), "valid": valid})]
