"""
ENN - File Scanner
Finds all text files in a directory, skips binaries and junk.
"""

import os
import logging

logger = logging.getLogger(__name__)

SKIP_DIRS = {
    '__pycache__', '.git', '.svn', '.hg', 'node_modules',
    '.vs', '.vscode', '.idea',
    'Debug', 'Release', 'x64', 'x86', '.cache',
    'bin', 'obj', 'dist', '.gradle', 'target',
}

SKIP_FILES = {
    'Thumbs.db', '.DS_Store', 'desktop.ini',
}

BINARY_EXTENSIONS = {
    '.exe', '.dll', '.so', '.dylib', '.o', '.obj', '.a', '.lib',
    '.pdb', '.ilk', '.exp', '.pch', '.pyc', '.class', '.wasm',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp',
    '.tiff', '.psd', '.raw', '.cr2', '.nef',
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm',
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
    '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2', '.xz',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.db', '.sqlite', '.sqlite3',
    '.ttf', '.otf', '.woff', '.woff2',
    '.iso', '.dmg', '.apk', '.deb', '.rpm',
}


def is_valid_text_file(filepath: str, max_size_mb: float = 5.0) -> bool:
    """Check if file is valid text and not too large."""
    try:
        size = os.path.getsize(filepath)
        if size == 0 or size > max_size_mb * 1024 * 1024:
            return False
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            non_text = sum(1 for b in chunk if b < 8 or (b > 13 and b < 32))
            if len(chunk) > 0 and non_text / len(chunk) > 0.3:
                return False
    except Exception:
        return False
    return True


def scan_and_filter(root_dir: str) -> dict:
    """
    Scan directory, return all text files as a flat list.
    Skips binaries, junk dirs, and oversized files.
    """
    files = []
    skipped = []
    total = 0

    for root, dirs, filenames in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]

        for filename in filenames:
            total += 1
            filepath = os.path.join(root, filename)

            if filename in SKIP_FILES:
                skipped.append(filepath)
                continue

            _, ext = os.path.splitext(filename)
            if ext.lower() in BINARY_EXTENSIONS:
                skipped.append(filepath)
                continue

            if not is_valid_text_file(filepath):
                skipped.append(filepath)
                continue

            files.append(filepath)

    return {
        "files": files,
        # Backward compat — pipeline uses these keys
        "cpp_files": [],
        "doc_files": [],
        "txt_files": files,
        "other_text": [],
        "skipped": skipped,
        "stats": {
            "total_scanned": total,
            "accepted": len(files),
            "filtered": len(skipped),
        }
    }
