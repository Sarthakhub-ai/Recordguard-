"""RecordGuard Core entry point.

Full RecordGuard functionality with the same workspace/navigation structure
as the polished project, but a deliberately lightweight visual layer for
functional testing.
"""
from pathlib import Path
import traceback

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "startup_log.txt"


def main():
    try:
        from database import initialize_database
        from core_ui import launch_app
        initialize_database()
        launch_app()
    except Exception as exc:
        try:
            LOG_PATH.write_text(
                "RecordGuard Core startup failed\n==============================\n\n"
                + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                encoding="utf-8",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
