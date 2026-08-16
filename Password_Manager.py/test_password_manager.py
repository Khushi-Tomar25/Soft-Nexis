import getpass
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import password_manager as pm

class PasswordManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "vault.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_encrypt_decrypt_and_tamper_detection(self):
        key = pm.derive_key("correct horse battery", b"1" * 16)
        encrypted = pm.encrypt_json(key, {"password": "secret"}, b"https://example.com")
        self.assertEqual(pm.decrypt_json(key, encrypted, b"https://example.com")["password"], "secret")
        encrypted["ciphertext"] = encrypted["ciphertext"][:-2] + ("AA" if encrypted["ciphertext"][-2:] != "AA" else "BB")
        with self.assertRaises(pm.DecryptionError):
            pm.decrypt_json(key, encrypted, b"https://example.com")

    def test_atomic_vault_creation_and_authentication(self):
        vault, key = pm.new_vault("masterpassword")
        pm.atomic_write_json(self.vault, vault)
        loaded = pm.load_vault(self.vault)
        self.assertEqual(len(key), 32)
        self.assertEqual(len(pm.authenticate(loaded, "masterpassword")), 32)
        with self.assertRaises(pm.AuthenticationError):
            pm.authenticate(loaded, "wrong-password")

    def test_crud(self):
        vault, key = pm.new_vault("masterpassword")
        pm.save_entry(vault, key, "https://example.com", "alice", "secret")
        entry = pm.get_entry(vault, key, "https://example.com")
        self.assertEqual(entry["username"], "alice")
        self.assertEqual(entry["password"], "secret")
        del vault["entries"]["https://example.com"]
        self.assertEqual(vault["entries"], {})

    def test_change_master_reencrypts(self):
        old_vault, old_key = pm.new_vault("oldpassword")
        pm.save_entry(old_vault, old_key, "https://example.com", "alice", "secret")
        new_vault, new_key = pm.new_vault("newpassword")
        for site, encrypted in old_vault["entries"].items():
            entry = pm.decrypt_json(old_key, encrypted, site.encode())
            new_vault["entries"][site] = pm.encrypt_json(new_key, entry, site.encode())
        self.assertEqual(pm.get_entry(new_vault, new_key, "https://example.com")["password"], "secret")
        with self.assertRaises(pm.AuthenticationError):
            pm.authenticate(new_vault, "oldpassword")

    def test_url_validation(self):
        self.assertEqual(pm.validate_website(" https://example.com "), "https://example.com")
        with self.assertRaises(pm.ValidationError):
            pm.validate_website("example.com")

if __name__ == "__main__":
    unittest.main()
