"""Credential encryption using AES-256-GCM with an instance-derived key."""

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12  # 96 bits, recommended for AES-GCM


def get_or_create_master_key(data_dir: Path) -> bytes:
    """Load master key from .secret file, or generate and save one.

    The master key is 32 random bytes (256 bits) for AES-256-GCM.
    If the .secret file is lost, all encrypted credentials become unrecoverable.
    """
    secret_path = data_dir / ".secret"
    if secret_path.exists():
        return secret_path.read_bytes()
    key = os.urandom(32)
    secret_path.write_bytes(key)
    secret_path.chmod(0o600)
    return key


def encrypt_value(plaintext: str, master_key: bytes) -> bytes:
    """Encrypt a credential value. Returns nonce + ciphertext + tag as a single blob."""
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_value(encrypted: bytes, master_key: bytes) -> str:
    """Decrypt a credential value blob back to plaintext string.

    Raises cryptography.exceptions.InvalidTag on tampered or invalid data.
    """
    nonce = encrypted[:_NONCE_SIZE]
    ciphertext = encrypted[_NONCE_SIZE:]
    aesgcm = AESGCM(master_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
