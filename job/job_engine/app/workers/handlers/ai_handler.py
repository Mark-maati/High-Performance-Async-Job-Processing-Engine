# app/workers/handlers/ai_handler.py
import asyncio
import logging
import random

logger = logging.getLogger(__name__)


async def handle_ai_task(payload: dict) -> dict:
    """Simulate an AI processing task (summarization, classification, etc.)."""
    task_type = payload.get("task", "classification")
    input_text = payload.get("input", "")

    logger.info(f"Running AI task: {task_type}, input_length={len(input_text)}")

    # Simulate processing time proportional to input
    processing_time = min(0.3 + len(input_text) * 0.001, 5.0)
    await asyncio.sleep(processing_time)

    if payload.get("simulate_failure"):
        raise RuntimeError("Model inference timeout (simulated)")

    # Simulated results
    results = {
        "classification": {
            "label": random.choice(["positive", "negative", "neutral"]),
            "confidence": round(random.uniform(0.7, 0.99), 3),
        },
        "summarization": {
            "summary": input_text[:100] + "..." if len(input_text) > 100 else input_text,
            "compression_ratio": 0.3,
        },
    }

    return {
        "task_type": task_type,
        "processing_time_sec": round(processing_time, 2),
        "result": results.get(task_type, {"output": "processed"}),
    }
