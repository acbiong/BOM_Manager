"""Format legacy timestamps to whole seconds without changing or rounding storage."""
import re

def seconds_timestamp(value):
    text = str(value or '')
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?(.*)', text)
    return match[1]+' '+match[2]+match[3] if match else text
