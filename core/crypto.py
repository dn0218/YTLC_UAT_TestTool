"""Obfuscation-grade encryption for sensitive config values.

Format: enc:v1:<base64(payload)> where payload = ciphertext + 8-byte HMAC tag.
Algorithm: HMAC-SHA256(key, nonce)-derived keystream XOR (standard library
only - no third-party deps). This is NOT secure against a determined reverse
engineer (the key ships with the program); it prevents casual reading of
plaintext passwords in config files / screenshots / forwarded files.
"""
import base64
import hashlib
import hmac

_PREFIX = "enc:v1:"

# Build key material. Split so that a plain "strings" scan of the binary
# does not reveal a single contiguous key blob.
_K1 = bytes.fromhex("5f2a7c91e4b08d36a1f4c5e29b7d3a88")
_K2 = bytes.fromhex("6d1e9f4a2c8b7e5d0a3f6c9b1e8d4a72")
_SECRET = _K1 + bytes([0x50]) + _K2
_KEY = hashlib.sha256(_SECRET).digest()


def _keystream(nonce: bytes, length: int) -> bytes:
    """Deterministic keystream from (key, nonce) via HMAC-SHA256 counter mode."""
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(_KEY, nonce + counter.to_bytes(4, "big"),
                        hashlib.sha256).digest()
        counter += 1
    return out[:length]


def _xor(data: bytes, ks: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, ks))


def encrypt_value(plaintext: str, nonce: bytes = None) -> str:
    """Encrypt a string into 'enc:v1:<base64>' form."""
    if nonce is None:
        nonce = hashlib.sha256(plaintext.encode("utf-8")).digest()[:8]
    data = plaintext.encode("utf-8")
    ct = _xor(data, _keystream(nonce, len(data)))
    tag = hmac.new(_KEY, nonce + ct, hashlib.sha256).digest()[:8]
    return _PREFIX + base64.b64encode(nonce + ct + tag).decode("ascii")


def decrypt_value(value: str) -> str:
    """Decrypt an 'enc:v1:...' string back to plaintext.

    Raises ValueError on malformed input / tamper detection.
    A value without the prefix is returned unchanged (backward compatible).
    """
    if not isinstance(value, str) or not value.startswith(_PREFIX):
        return value
    try:
        raw = base64.b64decode(value[len(_PREFIX):])
        nonce, ct, tag = raw[:8], raw[8:-8], raw[-8:]
        expected = hmac.new(_KEY, nonce + ct, hashlib.sha256).digest()[:8]
        if not hmac.compare_digest(tag, expected):
            raise ValueError("integrity check failed (wrong key or tampered)")
        pt = _xor(ct, _keystream(nonce, len(ct)))
        return pt.decode("utf-8")
    except Exception as e:
        raise ValueError(f"cannot decrypt config value: {e}") from e


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)
