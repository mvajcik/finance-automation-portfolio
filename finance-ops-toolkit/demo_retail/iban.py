"""IBAN validation (ISO 13616, mod-97).

Every IBAN in this repository is an official *example* IBAN published in the
SWIFT IBAN Registry — none of them belongs to a real account holder.
"""
import re

LENGTHS = {"AT": 20, "BE": 16, "CZ": 24, "DE": 22, "ES": 24, "FR": 27, "HU": 28,
           "IT": 27, "NL": 18, "PL": 28, "SI": 19, "SK": 24}


def normalize(iban: str) -> str:
    return re.sub(r"\s+", "", iban or "").upper()


def is_valid(iban: str) -> bool:
    iban = normalize(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", iban):
        return False
    if LENGTHS.get(iban[:2]) != len(iban):
        return False
    digits = "".join(str(int(c, 36)) for c in iban[4:] + iban[:4])
    return int(digits) % 97 == 1
