import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def get_vault_key() -> bytes:
    val = os.getenv('SM_VAULT_KEY', '')
    if not val or len(val) != 64:
        # Fallback to sha256 of JWT_SECRET if SM_VAULT_KEY is not set
        import hashlib
        return hashlib.sha256(settings.JWT_SECRET.encode()).digest()
    return bytes.fromhex(val)


def seal(plain: str) -> dict:
    key = get_vault_key()
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    # cryptography AESGCM appends 16-byte tag to the ciphertext
    ct_with_tag = aesgcm.encrypt(iv, plain.encode('utf-8'), None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    return {
        'encrypted_value': base64.b64encode(ciphertext).decode('utf-8'),
        'iv': base64.b64encode(iv).decode('utf-8'),
        'tag': base64.b64encode(tag).decode('utf-8'),
    }


def unseal(row) -> str:
    key = get_vault_key()
    iv = base64.b64decode(row.iv)
    ciphertext = base64.b64decode(row.encrypted_value)
    tag = base64.b64decode(row.tag)
    ct_with_tag = ciphertext + tag

    aesgcm = AESGCM(key)
    decrypted = aesgcm.decrypt(iv, ct_with_tag, None)
    return decrypted.decode('utf-8')
