"""Cleanup helpers for generated temporary and cached files."""
from __future__ import annotations

import logging
import os
import shutil
import time


def cleanup_temp() -> None:
    """Remove the working temp directory when the server exits."""
    from main import TEMP_DIR
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
            logging.info("Temp directory cleaned up")
    except Exception:
        pass


def cleanup_orphaned_temp_files() -> None:
    """Remove temporary files left behind by crashes after one hour."""
    from main import TEMP_DIR
    try:
        if os.path.exists(TEMP_DIR):
            current_time = time.time()
            for item in os.listdir(TEMP_DIR):
                item_path = os.path.join(TEMP_DIR, item)
                try:
                    stat = os.stat(item_path)
                    if current_time - stat.st_mtime > 3600:
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path, ignore_errors=True)
                        logging.debug(f"Removed orphaned temp file: {item}")
                except Exception:
                    pass
            logging.info("Orphaned temp files cleanup completed")
    except Exception as exc:
        logging.warning(f"Orphaned temp cleanup failed: {exc}")
