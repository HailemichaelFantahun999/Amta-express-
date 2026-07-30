import re


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("251") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+251" + digits[1:]
    if len(digits) == 9:
        return "+251" + digits
    if value and value.startswith("+") and digits:
        return "+" + digits
    return value


def phone_to_account_email(phone: str) -> str:
    normalized = normalize_phone(phone)
    digits_only = re.sub(r"\D", "", normalized)
    return f"phone+{digits_only}@local.amta.app"
