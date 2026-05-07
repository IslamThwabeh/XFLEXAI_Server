SAFE_KEY_CHARACTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_registration_key(key_value):
    if key_value is None:
        return ""

    normalized = []
    for character in str(key_value).strip().upper():
        if character.isalnum():
            normalized.append(character)

    return "".join(normalized)