#!/usr/bin/env python3
"""Secure CLI password manager using PBKDF2-HMAC-SHA256 and AES-256-GCM."""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VAULT_FILE = Path("vault.json")
PBKDF2_ITERATIONS = 480_000
SALT_SIZE = 16
KEY_SIZE = 32
NONCE_SIZE = 12
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
SCHEMA_VERSION = 1
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

class VaultError(Exception):
    """Base application error."""
class VaultNotFoundError(VaultError): pass
class AuthenticationError(VaultError): pass
class DecryptionError(VaultError): pass
class ValidationError(VaultError): pass


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

def b64d(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, TypeError) as exc:
        raise DecryptionError("Vault contains invalid base64 data.") from exc


def derive_key(password: str, salt: bytes) -> bytes:
    if not isinstance(password, str) or not password:
        raise ValidationError("Master password cannot be empty.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=KEY_SIZE, salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_json(key: bytes, data: dict[str, Any], aad: bytes | None = None) -> dict[str, str]:
    nonce = os.urandom(NONCE_SIZE)
    plaintext = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    combined = AESGCM(key).encrypt(nonce, plaintext, aad)
    # AESGCM returns ciphertext + 16-byte authentication tag.
    return {"nonce": b64e(nonce), "ciphertext": b64e(combined)}


def decrypt_json(key: bytes, encrypted: dict[str, str], aad: bytes | None = None) -> dict[str, Any]:
    try:
        nonce = b64d(encrypted["nonce"])
        combined = b64d(encrypted["ciphertext"])
        if len(nonce) != NONCE_SIZE or len(combined) < 16:
            raise DecryptionError("Encrypted data has invalid dimensions.")
        plaintext = AESGCM(key).decrypt(nonce, combined, aad)
        value = json.loads(plaintext.decode("utf-8"))
        if not isinstance(value, dict):
            raise DecryptionError("Decrypted data has an invalid structure.")
        return value
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, InvalidTag, ValueError) as exc:
        raise DecryptionError("Vault authentication failed or data was tampered with.") from exc


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON to a temp file and atomically replace the destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def validate_website(website: str) -> str:
    website = website.strip()
    if not website or len(website) > 2048 or not URL_RE.match(website):
        raise ValidationError("Website must be a valid http:// or https:// URL.")
    return website


def validate_nonempty(value: str, label: str, max_len: int = 512) -> str:
    value = value.strip()
    if not value or len(value) > max_len:
        raise ValidationError(f"{label} cannot be empty and must be <= {max_len} characters.")
    return value


def new_vault(master_password: str) -> tuple[dict[str, Any], bytes]:
    salt = os.urandom(SALT_SIZE)
    key = derive_key(master_password, salt)
    verifier = encrypt_json(key, {"purpose": "master-password-verifier", "value": secrets.token_hex(16)})
    vault = {
        "version": SCHEMA_VERSION,
        "kdf": {"algorithm": "PBKDF2-HMAC-SHA256", "iterations": PBKDF2_ITERATIONS, "salt": b64e(salt)},
        "cipher": {"algorithm": "AES-256-GCM", "nonce_size": NONCE_SIZE},
        "verifier": verifier,
        "entries": {},
    }
    return vault, key


def load_vault(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            vault = json.load(handle)
    except FileNotFoundError as exc:
        raise VaultNotFoundError(f"Vault not found: {path}. Use 'init' first.") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise VaultError(f"Cannot read vault: {exc}") from exc
    if not isinstance(vault, dict) or vault.get("version") != SCHEMA_VERSION:
        raise VaultError("Unsupported or corrupted vault format.")
    if not isinstance(vault.get("entries"), dict):
        raise VaultError("Vault entries are corrupted.")
    return vault


def authenticate(vault: dict[str, Any], password: str) -> bytes:
    try:
        salt = b64d(vault["kdf"]["salt"])
        key = derive_key(password, salt)
        verifier = decrypt_json(key, vault["verifier"])
        if verifier.get("purpose") != "master-password-verifier":
            raise DecryptionError("Invalid verifier.")
        return key
    except (KeyError, TypeError, DecryptionError, ValidationError) as exc:
        raise AuthenticationError("Incorrect master password or corrupted vault.") from exc


def prompt_master(confirm: bool = False) -> str:
    password = getpass.getpass("Master Password: ")
    if not password:
        raise ValidationError("Master password cannot be empty.")
    if len(password) < 8:
        raise ValidationError("Master password must contain at least 8 characters.")
    if confirm:
        confirmation = getpass.getpass("Confirm Master Password: ")
        if not secrets.compare_digest(password, confirmation):
            raise ValidationError("Master passwords do not match.")
    return password


def unlock(vault: dict[str, Any], path: Path) -> bytes:
    """Authenticate with a short-lived failed-attempt lockout."""
    attempts = 0
    while attempts < MAX_FAILED_ATTEMPTS:
        password = getpass.getpass("Master Password: ")
        try:
            return authenticate(vault, password)
        except AuthenticationError:
            attempts += 1
            remaining = MAX_FAILED_ATTEMPTS - attempts
            print(f"Authentication failed. Attempts remaining: {remaining}", file=sys.stderr)
            if attempts >= MAX_FAILED_ATTEMPTS:
                print(f"Vault locked for {LOCKOUT_SECONDS} seconds.", file=sys.stderr)
                time.sleep(LOCKOUT_SECONDS)
                raise AuthenticationError("Too many failed attempts.")
    raise AuthenticationError("Unable to unlock vault.")


def save_entry(vault: dict[str, Any], key: bytes, website: str, username: str, password: str) -> None:
    website = validate_website(website)
    username = validate_nonempty(username, "Username")
    if not password:
        raise ValidationError("Password cannot be empty.")
    aad = website.encode("utf-8")
    vault["entries"][website] = encrypt_json(key, {"username": username, "password": password}, aad)


def get_entry(vault: dict[str, Any], key: bytes, website: str) -> dict[str, Any]:
    website = validate_website(website)
    try:
        encrypted = vault["entries"][website]
    except KeyError as exc:
        raise VaultError(f"No credentials stored for {website}") from exc
    return decrypt_json(key, encrypted, website.encode("utf-8"))


def cmd_init(args: argparse.Namespace) -> None:
    if args.vault.exists() and not args.force:
        raise VaultError(f"Vault already exists: {args.vault}. Use --force only to replace it.")
    password = prompt_master(confirm=True)
    vault, _ = new_vault(password)
    atomic_write_json(args.vault, vault)
    print(f"Created encrypted vault: {args.vault}")


def cmd_add(args: argparse.Namespace) -> None:
    vault = load_vault(args.vault)
    key = unlock(vault, args.vault)
    website = args.website or input("Website: ")
    username = args.username or input("Username: ")
    password = args.password if args.password is not None else getpass.getpass("Password: ")
    save_entry(vault, key, website, username, password)
    atomic_write_json(args.vault, vault)
    print(f"Saved credentials for {website}")


def cmd_get(args: argparse.Namespace) -> None:
    vault = load_vault(args.vault)
    key = unlock(vault, args.vault)
    entry = get_entry(vault, key, args.website)
    print(f"Website: {args.website}")
    print(f"Username: {entry['username']}")
    print(f"Password: {entry['password']}")


def cmd_list(args: argparse.Namespace) -> None:
    vault = load_vault(args.vault)
    unlock(vault, args.vault)
    sites = sorted(vault["entries"])
    if not sites:
        print("Vault is empty.")
        return
    print("Stored sites:")
    for site in sites:
        print(f"- {site}")


def cmd_delete(args: argparse.Namespace) -> None:
    vault = load_vault(args.vault)
    unlock(vault, args.vault)
    website = validate_website(args.website)
    if website not in vault["entries"]:
        raise VaultError(f"No credentials stored for {website}")
    del vault["entries"][website]
    atomic_write_json(args.vault, vault)
    print(f"Deleted credentials for {website}")


def cmd_change_master(args: argparse.Namespace) -> None:
    vault = load_vault(args.vault)
    old_key = unlock(vault, args.vault)
    new_password = prompt_master(confirm=True)
    new_vault_data, new_key = new_vault(new_password)

    # Decrypt all existing entries with the old key and immediately encrypt
    # them with fresh nonces under the new key.
    for website, encrypted in vault["entries"].items():
        entry = decrypt_json(old_key, encrypted, website.encode("utf-8"))
        new_vault_data["entries"][website] = encrypt_json(
            new_key, entry, website.encode("utf-8")
        )
    atomic_write_json(args.vault, new_vault_data)
    print("Master password changed and all credentials re-encrypted.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Secure AES-256-GCM CLI password manager")
    parser.add_argument("--vault", type=Path, default=VAULT_FILE, help="Vault JSON path (default: vault.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create a new encrypted vault")
    p.add_argument("--force", action="store_true", help="Replace an existing vault")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add", help="Add or replace credentials")
    p.add_argument("website", nargs="?", help="Website URL")
    p.add_argument("--username", help="Username; omit for interactive input")
    p.add_argument("--password", help="Password; omit for hidden interactive input (less safe on shell history if used)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("get", help="Retrieve credentials")
    p.add_argument("website", help="Website URL")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("list", help="List stored website URLs")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("delete", help="Delete credentials")
    p.add_argument("website", help="Website URL")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("change-master", help="Change master password and re-encrypt the vault")
    p.set_defaults(func=cmd_change_master)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except VaultError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
