# Project 2: CLI Password Manager

A security-focused command-line password manager built with Python. It stores credentials in an encrypted JSON vault using **PBKDF2-HMAC-SHA256** for key derivation and **AES-256-GCM** for authenticated encryption.

## Features

- CLI built with `argparse` and subcommands
- `init` — create an encrypted vault
- `add` — store website, username and password
- `get` — retrieve credentials after authentication
- `list` — list stored websites without exposing passwords
- `delete` — remove credentials
- `change-master` — change the master password and re-encrypt every entry
- Hidden password input using `getpass`
- PBKDF2-HMAC-SHA256 with 480,000 iterations and a random 16-byte salt
- AES-256-GCM with a fresh 12-byte nonce for every encryption
- Authentication tags provided by AES-GCM detect tampering/wrong keys
- Encrypted master-password verifier
- Atomic JSON writes using temporary files + `os.replace()`
- Duplicate website entries are replaced deliberately rather than duplicated
- URL and input validation
- Missing/corrupt vault and decryption errors are handled gracefully
- Five failed authentication attempts trigger a 30-second lockout
- Vault file permissions are restricted to owner-only where supported

## Installation

Python 3.10+ is recommended.

```bash
python -m pip install -r requirements.txt
```

## Usage

### Create a vault

```bash
python password_manager.py init
```

You will be asked for the master password twice. The vault is created as `vault.json`.

### Add credentials

```bash
python password_manager.py add https://example.com
```

The username and password are requested interactively. Password input is hidden.

### List websites

```bash
python password_manager.py list
```

### Retrieve credentials

```bash
python password_manager.py get https://example.com
```

### Delete credentials

```bash
python password_manager.py delete https://example.com
```

### Change the master password

```bash
python password_manager.py change-master
```

The existing credentials are decrypted only in memory and immediately re-encrypted using a new key derived from the new master password. Fresh salt, verifier and encryption nonces are generated.

### Use a different vault location

```bash
python password_manager.py --vault myvault.json init
python password_manager.py --vault myvault.json add https://example.com
```

## Vault security design

The JSON vault stores metadata such as the KDF configuration, salt, encrypted password verifier, and encrypted entries. Plaintext usernames/passwords are not stored in the JSON file.

For each entry, AES-GCM produces ciphertext plus its 16-byte authentication tag. The entry's website URL is supplied as **associated authenticated data (AAD)**, so changing the website key in the JSON structure causes authentication to fail instead of silently accepting modified data.

The master password is never stored. PBKDF2 derives a 32-byte AES-256 key from the password and random salt. The encrypted verifier lets the program distinguish a correct password from an incorrect one without storing the password itself.

## Atomic writes

The vault is written to a temporary file in the same directory, flushed and synchronized, then replaced with `os.replace()`. This reduces the risk of leaving a partially-written JSON vault after an interrupted write.

## Brute-force protection

Authentication allows five failed attempts. After the fifth failure, the application waits 30 seconds before reporting that the vault is locked. This is intentionally a simple local CLI defense; it is not a replacement for OS-level account security or a hardware-backed password manager.

## Error handling

The program uses custom exceptions for validation, missing vaults, authentication failures, and decryption/tampering failures. It exits with a non-zero status when an operation fails instead of showing a Python traceback to a normal user.

## Important security note

Do not commit `vault.json` to GitHub or any other public repository. The included `.gitignore` excludes it automatically. The source code can be public, but the encrypted vault should remain private. Also avoid passing passwords through the `--password` option because command-line arguments can be visible to shell history or process listings; interactive hidden input is recommended.

## Project structure

```text
cli-password-manager/
├── password_manager.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Learning outcomes

- CLI application architecture with `argparse`
- Interactive secret entry with `getpass`
- PBKDF2 key derivation
- AES-256-GCM authenticated encryption
- JSON serialization and structured storage
- Atomic file persistence
- Brute-force protection
- Input validation and custom exceptions
- Safe handling of sensitive credentials
