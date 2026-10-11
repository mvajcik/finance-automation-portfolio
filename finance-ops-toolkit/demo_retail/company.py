"""Master data of the fictional company used across the toolkit.

Demo Retail s.r.o. does not exist. Supplier and employee names are invented
and deliberately read as fake ("Demo…", "Sample…", "Testová"). IBANs are
SWIFT IBAN Registry examples (see iban.py).
"""

COMPANY = {
    "name": "Demo Retail s.r.o.",
    "iban": "SK3112000000198742637541",
    "bic": "DEMOSKBXXXX",
}

SUPPLIERS = [
    {"category": "Goods", "name": "Demo Paper Supply s.r.o.", "iban": "CZ6508000000192000145399"},
    {"category": "Logistics", "name": "Sample Logistics GmbH", "iban": "AT611904300234573201"},
    {"category": "Energy", "name": "Example Energy AG", "iban": "DE89370400440532013000"},
    {"category": "Other", "name": "Fictional Office Furniture BV", "iban": "NL91ABNA0417164300"},
    {"category": "Goods", "name": "Mock Packaging Sp. z o.o.", "iban": "PL61109010140000071219812874"},
    {"category": "Services", "name": "Placeholder Cleaning Kft.", "iban": "HU42117730161111101800000000"},
    {"category": "Rent", "name": "Test Rent d.o.o.", "iban": "SI56263300012039086"},
    {"category": "Services", "name": "Dummy Telecom SA", "iban": "BE68539007547034"},
]

EMPLOYEES = [
    {"id": "E01", "name": "Jana Testová", "store": "Store North", "hourly_rate": "8.40"},
    {"id": "E02", "name": "Ondrej Ukážka", "store": "Store North", "hourly_rate": "8.10"},
    {"id": "E03", "name": "Eva Vzorová", "store": "Store Centre", "hourly_rate": "9.20"},
    {"id": "E04", "name": "Matej Fiktívny", "store": "Store Centre", "hourly_rate": "8.10"},
    {"id": "E05", "name": "Lucia Príkladová", "store": "Store South", "hourly_rate": "8.75"},
    {"id": "E06", "name": "Tomáš Demo", "store": "Store East", "hourly_rate": "8.40"},
]

STORES = ["Store North", "Store Centre", "Store South", "Store East"]
