from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from qdrant_client import QdrantClient, models

from .search import HashingEmbedder


def run_size(size: int) -> dict[str, float | int]:
    embedder = HashingEmbedder()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        client = QdrantClient(path=str(Path(directory) / "qdrant"))
        client.create_collection(
            "benchmark",
            vectors_config=models.VectorParams(size=embedder.size, distance=models.Distance.COSINE),
        )
        batch_size = 256
        for start in range(0, size, batch_size):
            points = []
            for index in range(start, min(start + batch_size, size)):
                text = f"S4-{1000 + index % 20} 产品资料 模拟知识片段 {index} 包装 质量"
                points.append(
                    models.PointStruct(
                        id=index,
                        vector=embedder.embed(text),
                        payload={"text": text, "status": "approved"},
                    )
                )
            client.upsert("benchmark", points=points, wait=True)
        indexed_seconds = time.perf_counter() - started
        latencies = []
        for index in range(100):
            query_started = time.perf_counter()
            client.query_points(
                collection_name="benchmark",
                query=embedder.embed(f"S4-{1000 + index % 20} 包装要求"),
                limit=10,
            )
            latencies.append((time.perf_counter() - query_started) * 1000)
        disk_bytes = sum(
            path.stat().st_size for path in Path(directory).rglob("*") if path.is_file()
        )
        client.close()
    latencies.sort()
    return {
        "chunks": size,
        "index_seconds": round(indexed_seconds, 3),
        "disk_mb": round(disk_bytes / 1024 / 1024, 3),
        "p50_ms": round(latencies[49], 3),
        "p95_ms": round(latencies[94], 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 50000])
    args = parser.parse_args()
    results = [run_size(size) for size in args.sizes]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
