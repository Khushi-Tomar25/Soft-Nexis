# Soft-Nexis
# Project 1: Automated File Organizer

## Objective
Develop a Python CLI utility that scans a specified directory recursively and organizes files into category folders according to their extensions.

## Requirements covered
- Recursive directory traversal using `os.walk`
- Skips directories and symbolic links
- Extension-based file categorization
- Unknown extensions go to `Other`
- Duplicate filenames are resolved without overwriting
- Handles permission, missing-file, and OS errors
- Timestamped logging with Python's `logging` module
- Generates a summary report
- Command-line argument support through `argparse`
- `--dry-run` preview mode
- Returns a non-zero exit status when processing errors occur

## Files
- `organizer.py` — complete implementation
- `README.md` — documentation and usage
- `sample_test.py` — basic automated tests

## How to run

### 1. Check help
```bash
python organizer.py --help
```

### 2. Preview first (recommended)
```bash
python organizer.py "C:\Users\YourName\Downloads" --dry-run
```

Linux/macOS:
```bash
python organizer.py ~/Downloads --dry-run
```

### 3. Perform organization
```bash
python organizer.py "C:\Users\YourName\Downloads"
```

The program creates:
- `organizer.log`
- `organizer_report.txt`
- category folders such as `Documents`, `Images`, `Python_Code`, and `Other`

## Example
If the source directory contains:
```text
project.py
notes.txt
photo.jpg
movie.mp4
unknown.xyz
notes.txt  (duplicate)
```

The result will be approximately:
```text
Python_Code/project.py
Documents/notes.txt
Images/photo.jpg
Videos/movie.mp4
Other/unknown.xyz
Documents/notes_copy.txt
```

If `notes_copy.txt` already exists, the next duplicate becomes:
```text
notes_copy_2.txt
```

## Safety notes
1. Always use `--dry-run` before the first live run.
2. The script never intentionally overwrites an existing file.
3. Symbolic links are skipped.
4. Files that disappear or become inaccessible during processing are skipped/reported rather than crashing the complete run.
5. The category directories are excluded from recursive scanning so files are not repeatedly reorganized during the same execution.
6. The configured log and report files are also excluded, even when they are located inside the source directory.

## Submission explanation
The project demonstrates practical Python file-system automation, defensive error handling, logging, CLI development, and safe conflict resolution. It improves on the brief's example by making duplicate handling iterative, traversal recursive, symlink-aware, and reporting explicit.
