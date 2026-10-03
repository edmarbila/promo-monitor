import os
from cryptography.fernet import Fernet

_key = os.environ.get("CONFIG_ENCRYPTION_KEY", "").strip()
if not _key:
    raise RuntimeError("CONFIG_ENCRYPTION_KEY ausente.")

fernet = Fernet(_key.encode("utf-8"))

def encrypt_text(value):
    if value is None:
        return None
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")

def decrypt_text(value):
    if not value:
        return None
    return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
