# services/key_service.py
import random
import string
from database.operations import execute_query

def generate_short_key(length=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def generate_unique_key(length=6):
    """
    Generate key and ensure uniqueness in registration_keys table.
    """
    for _ in range(10):
        key = generate_short_key(length)
        existing = execute_query("SELECT id FROM registration_keys WHERE key_value = %s", (key,), fetch=True)
        if not existing:
            return key
    # fallback to longer random on collision
    while True:
        key = generate_short_key(length + 2)
        existing = execute_query("SELECT id FROM registration_keys WHERE key_value = %s", (key,), fetch=True)
        if not existing:
            return key
