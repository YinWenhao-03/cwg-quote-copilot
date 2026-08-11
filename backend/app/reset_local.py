from __future__ import annotations

import shutil

from .config import get_settings


def reset_local() -> None:
    settings = get_settings()
    database_path = settings.database_url.removeprefix("sqlite:///")
    if settings.database_url.startswith("sqlite"):
        from pathlib import Path

        Path(database_path).unlink(missing_ok=True)
    for path in (
        settings.qdrant_path,
        settings.index_dir,
        settings.documents_dir,
        settings.quotes_dir,
    ):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    print("Local database, indexes and generated artifacts were reset.")


if __name__ == "__main__":
    reset_local()
