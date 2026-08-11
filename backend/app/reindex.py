from __future__ import annotations

from .db import SessionLocal, init_db
from .search import get_search_service


def main() -> None:
    init_db()
    with SessionLocal() as db:
        search = get_search_service()
        count = search.reindex_all(db)
        print(
            f"Reindexed {count} chunks with {search.embedder.model_name} "
            f"({search.embedder.size} dimensions) plus BM25."
        )


if __name__ == "__main__":
    main()
