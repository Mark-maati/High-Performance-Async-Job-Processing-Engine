# app/workers/handlers/email_handler.py
import asyncio
import logging

logger = logging.getLogger(__name__)


async def handle_email(payload: dict) -> dict:
    """Simulate sending an email."""
    to = payload.get("to", "unknown@example.com")
    subject = payload.get("subject", "No Subject")
    body = payload.get("body", "")

    logger.info(f"Sending email to={to} subject='{subject}'")

    # Simulate network I/O
    await asyncio.sleep(0.5)

    # Simulate occasional failure for demo
    if payload.get("simulate_failure"):
        raise RuntimeError("SMTP connection refused (simulated)")

    return {
        "status": "sent",
        "to": to,
        "subject": subject,
        "message_id": f"msg-{id(payload)}",
        "characters": len(body),
    }
