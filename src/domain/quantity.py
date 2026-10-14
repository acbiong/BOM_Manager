"""Quantity presentation without forced decimal rounding (SQLite REAL precision)."""
from decimal import Decimal

def format_quantity(value):
    number=Decimal(str(value or 0))
    if not number.is_finite():raise ValueError('物料数量必须为有限数字')
    text=format(number,'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text
