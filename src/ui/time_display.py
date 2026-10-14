"""Stable local timestamp display without changing stored historical values."""
import re

def sku_timestamp(value):
    text=str(value or '')
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:\.(\d+))?',text)
    if not match:return text
    return match[1].replace('T',' ')+'.'+((match[2] or '')+'00')[:2]
