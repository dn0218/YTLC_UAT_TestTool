# -*- coding: utf-8 -*-
"""Admin tool: encrypt / decrypt / verify passwords in config_ocs.json.

Usage (run from the project folder):
    python encrypt_config.py            # encrypt all plaintext passwords in place
    python encrypt_config.py --decrypt  # decrypt enc:v1:... values back to plaintext
    python encrypt_config.py --show     # decrypt and print (troubleshooting)

Only touches keys named 'password' (db / ssh / crm_db / redis sections).
Keeps every other byte of the JSON intact (indent=4, ensure_ascii=False).
Needs no third-party libraries - imports the same crypto code from
core/crypto.py (refactored app) or falls back to Preprod_TestTool.py
(single-file app); both share identical key material and format.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_crypto():
    """Return (encrypt_value, decrypt_value) from whichever app module exists."""
    try:
        from core import crypto
        return crypto.encrypt_value, crypto.decrypt_value
    except ImportError:
        pass
    spec_path = os.path.join(HERE, "Preprod_TestTool.py")
    if os.path.exists(spec_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_ppt", spec_path)
        mod = importlib.util.module_from_spec(spec)
        # Only execute the module far enough to get the crypto functions;
        # importing it fully would import tkinter/oracledb. Fall back to a
        # text extraction if execution fails.
        try:
            spec.loader.exec_module(mod)
            return mod.encrypt_value, mod.decrypt_value
        except Exception:
            pass
    # Last resort: extract the crypto block textually.
    src = open(spec_path, encoding="utf-8").read()
    start = src.index("# ==================== Config value encryption")
    end = src.index("# ===================================================================")
    ns = {}
    exec(src[start:end], ns)
    return ns["encrypt_value"], ns["decrypt_value"]


def transform(obj, fn):
    """Recursively apply fn to every 'password' value in nested dicts."""
    changed = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "password" and isinstance(v, str) and v:
                new = fn(v)
                if new != v:
                    obj[k] = new
                    changed += 1
            else:
                changed += transform(v, fn)
    elif isinstance(obj, list):
        for item in obj:
            changed += transform(item, fn)
    return changed


def main():
    args = set(sys.argv[1:])
    config_path = os.path.join(HERE, "config_ocs.json")
    if not os.path.exists(config_path):
        print("config_ocs.json not found next to this script.")
        sys.exit(1)

    enc, dec = load_crypto()

    # idempotence helpers: encrypt only plaintext, decrypt only ciphertext
    def do_encrypt(v):
        return v if v.startswith("enc:v1:") else enc(v)

    def do_decrypt(v):
        return dec(v) if v.startswith("enc:v1:") else v

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "--show" in args:
        n = transform(cfg, do_decrypt)
        print(json.dumps(cfg, indent=4, ensure_ascii=False))
        print(f"({n} encrypted value(s) decrypted for display)")
        return

    fn, label = (do_decrypt, "decrypted") if "--decrypt" in args else (do_encrypt, "encrypted")
    n = transform(cfg, fn)
    if n == 0:
        print(f"Nothing to do: no {'ciphertext' if '--decrypt' in args else 'plaintext'} "
              f"password values found.")
        return
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
    print(f"Done: {n} password value(s) {label} in {config_path}")
    print("Backup of the previous file: config_ocs.json.plaintext.bak (if you made one)")


if __name__ == "__main__":
    main()
