from __future__ import annotations

import asyncio
import logging

from .db import SessionLocal, init_db
from .ingestion import process_pending_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def worker_loop() -> None:
    init_db()
    while True:
        with SessionLocal() as db:
            processed = process_pending_jobs(db, limit=5)
        if processed:
            logger.info("Processed %s ingestion jobs", processed)
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(worker_loop())
