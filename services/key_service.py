# services/key_service.py
import random
import string
from datetime import datetime, timedelta
from database import operations as db_ops

def generate_short_key(length=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def calculate_expiry_date(duration_months):
    return datetime.now() + timedelta(days=30 * int(duration_months))

def generate_unique_key():
    key = generate_short_key()
    while True:
        existing = db_ops.execute_query("SELECT * FROM registration_keys WHERE key_value = %s", (key,), fetch=True)
        if not existing:
            return key
        key = generate_short_key()
