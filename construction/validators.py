"""Власні валідатори (повідомлення українською)."""
import re
from decimal import Decimal

from django.core.exceptions import ValidationError

PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,20}$")


def validate_phone(value):
    """Телефон: необов'язковий «+», цифри, пробіли, дефіси та дужки; не менше 7 цифр."""
    if not PHONE_RE.match(value) or sum(ch.isdigit() for ch in value) < 7:
        raise ValidationError("Введіть коректний номер телефону, наприклад +380671234567.", code="invalid_phone")


def validate_quarter_hour(value):
    """Години вносяться з кроком 0,25 (чверть години)."""
    if (Decimal(value) * 4) % 1 != 0:
        raise ValidationError("Години вносяться з кроком 0,25 (наприклад, 7,5 або 8,25).", code="invalid_step")
