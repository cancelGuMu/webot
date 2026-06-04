"""Extract WCDB decrypt key from WeFlow config using Windows DPAPI.

Prints the hex key to stdout. Used by the bridge startup flow.

Usage:
    python src/wechat/extract_key.py
"""
import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def extract_aes_key() -> str | None:
    """Extract the AES storage key from WeFlow's Local State via DPAPI."""
    local_state = Path(os.environ["APPDATA"]) / "WeFlow" / "Local State"
    if not local_state.exists():
        return None

    with open(local_state, "r", encoding="utf-8") as f:
        state = json.load(f)

    encrypted_key_b64 = state.get("os_crypt", {}).get("encrypted_key", "")
    if not encrypted_key_b64:
        return None

    key_data = base64.b64decode(encrypted_key_b64)
    if key_data[:5] != b"DPAPI":
        return None

    dpapi_blob = key_data[5:]

    blob_in = DATA_BLOB(
        len(dpapi_blob),
        ctypes.cast(
            ctypes.create_string_buffer(dpapi_blob),
            ctypes.POINTER(ctypes.c_byte),
        ),
    )
    blob_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None, None, None, None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(blob_out),
    ):
        return None

    aes_key = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return aes_key.hex()


def decrypt_wcdb_key(aes_key_hex: str) -> str | None:
    """Use the AES key to decrypt the WCDB key from WeFlow config."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    config_path = Path(os.environ["APPDATA"]) / "WeFlow" / "WeFlow-config.json"
    if not config_path.exists():
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    encrypted = config.get("decryptKey", "")
    if not encrypted.startswith("safe:"):
        return encrypted  # Maybe already plaintext

    # Outer base64 decode
    outer_data = base64.b64decode(encrypted[5:])
    if outer_data[:3] != b"v10":
        return None

    # Inner is: nonce(12) || ciphertext || tag(16)
    inner = outer_data[3:]
    nonce = inner[:12]
    tag = inner[-16:]
    ciphertext = inner[12:-16]

    aes_key = bytes.fromhex(aes_key_hex)
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, ciphertext + tag, None).decode("utf-8")


if __name__ == "__main__":
    aes_key = extract_aes_key()
    if not aes_key:
        sys.exit(1)

    wcdb_key = decrypt_wcdb_key(aes_key)
    if not wcdb_key:
        sys.exit(1)

    print(wcdb_key)
