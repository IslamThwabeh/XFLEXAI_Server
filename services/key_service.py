# services/key_service.py
import random
from database.operations import execute_query
from utils.key_helpers import SAFE_KEY_CHARACTERS

def generate_short_key(length=6):
    return ''.join(random.choice(SAFE_KEY_CHARACTERS) for _ in range(length))

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
