import tempfile
import unittest
from pathlib import Path

from organizer import organize_directory, configure_logging


class TestOrganizer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.log = Path(self.temp.name).parent / "automated_file_organizer_test.log"
        self.logger = configure_logging(self.log)

    def tearDown(self):
        self.temp.cleanup()

    def test_categories_and_unknown_files(self):
        (self.root / "program.py").write_text("print('hello')", encoding="utf-8")
        (self.root / "notes.txt").write_text("hello", encoding="utf-8")
        (self.root / "photo.jpg").write_bytes(b"image")
        (self.root / "mystery.xyz").write_text("unknown", encoding="utf-8")

        summary = organize_directory(self.root, False, self.logger)

        self.assertEqual(summary.moved, 4)
        self.assertTrue((self.root / "Python_Code" / "program.py").exists())
        self.assertTrue((self.root / "Documents" / "notes.txt").exists())
        self.assertTrue((self.root / "Images" / "photo.jpg").exists())
        self.assertTrue((self.root / "Other" / "mystery.xyz").exists())

    def test_duplicate_names_are_not_overwritten(self):
        documents = self.root / "Documents"
        documents.mkdir()
        (documents / "old.txt").write_text("old", encoding="utf-8")
        (self.root / "old.txt").write_text("new", encoding="utf-8")

        summary = organize_directory(self.root, False, self.logger)

        self.assertEqual(summary.moved, 1)
        self.assertTrue((documents / "old.txt").exists())
        self.assertTrue((documents / "old_copy.txt").exists())
        self.assertEqual(
            (documents / "old.txt").read_text(encoding="utf-8"), "old"
        )
        self.assertEqual(
            (documents / "old_copy.txt").read_text(encoding="utf-8"), "new"
        )

    def test_dry_run_does_not_move_files(self):
        source = self.root / "a.txt"
        source.write_text("hello", encoding="utf-8")

        summary = organize_directory(self.root, True, self.logger)

        self.assertEqual(summary.planned, 1)
        self.assertEqual(summary.moved, 0)
        self.assertTrue(source.exists())

    def test_recursive_scan(self):
        nested = self.root / "nested" / "deeper"
        nested.mkdir(parents=True)
        source = nested / "deep.py"
        source.write_text("x = 1", encoding="utf-8")

        summary = organize_directory(self.root, False, self.logger)

        self.assertEqual(summary.moved, 1)
        self.assertTrue((self.root / "Python_Code" / "deep.py").exists())


if __name__ == "__main__":
    unittest.main()
