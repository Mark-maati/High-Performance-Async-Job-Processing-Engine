# app/workers/handlers/data_cleaning_handler.py
import asyncio
import logging
import random

logger = logging.getLogger(__name__)


async def handle_data_cleaning(payload: dict) -> dict:
    """Simulate data cleaning / ETL task."""
    source = payload.get("source", "unknown")
    row_count = payload.get("row_count", 1000)
    operations = payload.get("operations", ["dedup", "normalize", "validate"])

    logger.info(f"Cleaning data from '{source}': {row_count} rows, ops={operations}")

    # Simulate work
    await asyncio.sleep(0.2 + row_count * 0.0001)

    if payload.get("simulate_failure"):
        raise RuntimeError("Data source connection lost (simulated)")

    cleaned = int(row_count * random.uniform(0.85, 0.99))
    removed = row_count - cleaned

    return {
        "source": source,
        "original_rows": row_count,
        "cleaned_rows": cleaned,
        "removed_rows": removed,
        "operations_applied": operations,
        "quality_score": round(random.uniform(0.90, 1.0), 3),
    }
