"""Task-completion webhooks.

A caller may pass ``callback_url`` when creating a task. When the pipeline
finishes (success or failure) the server sends one small JSON POST so tools such
as n8n, Zapier or a custom backend do not have to poll ``GET /tasks/{id}``.

Design notes:
* Free and dependency-free: plain ``requests``.
* The payload carries no file paths or secrets; the receiver fetches details
  from the authenticated task API.
* Optional HMAC-SHA256 signature in ``X-MPT-Signature`` when
  ``app.webhook_secret`` is set.
* Delivery is best effort on a daemon thread with short retries and never
  raises into the task pipeline.
* Targets are checked with the SSRF guard. LAN receivers need
  ``app.callback_allow_private_hosts = true``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from typing import Any

import requests
from loguru import logger

from app import __version__
from app.config import config
from app.models import const
from app.services import state as sm
from app.utils import url_security

SIGNATURE_HEADER = "X-MPT-Signature"
EVENT_HEADER = "X-MPT-Event"
EVENT_NAME = "task.finished"
REQUEST_TIMEOUT = (5, 10)
RETRY_DELAYS = (1.0, 3.0)  # seconds between attempts; 3 attempts in total

_STATE_NAMES = {
    const.TASK_STATE_COMPLETE: "complete",
    const.TASK_STATE_FAILED: "failed",
}


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_payload(task_id: str, task: dict[str, Any] | None) -> dict[str, Any]:
    task = task or {}
    state = task.get("state")
    payload: dict[str, Any] = {
        "event": EVENT_NAME,
        "task_id": task_id,
        "status": _STATE_NAMES.get(state, "unknown"),
        "progress": task.get("progress"),
        "finished_at": int(time.time()),
        "version": __version__,
    }
    if state == const.TASK_STATE_FAILED:
        # Keep the message short; it is already user-facing task state.
        error = task.get("error") or task.get("message")
        if isinstance(error, str):
            payload["error"] = error[:500]
    return payload


def _allow_private() -> bool:
    value = config.app.get("callback_allow_private_hosts", False)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def deliver(task_id: str, callback_url: str, payload: dict[str, Any]) -> bool:
    """Send one webhook with retries. Returns True on a 2xx response."""
    try:
        url_security.assert_public_http_url(
            callback_url, allow_private=_allow_private()
        )
    except url_security.UnsafeURLError as exc:
        logger.warning(f"webhook skipped for task {task_id}: {exc}")
        return False

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"MoneyPrinterTurbo/{__version__}",
        EVENT_HEADER: EVENT_NAME,
    }
    secret = config.app.get("webhook_secret", "")
    if isinstance(secret, str) and secret:
        headers[SIGNATURE_HEADER] = sign_payload(secret, body)

    attempts = len(RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            response = requests.post(
                callback_url,
                data=body,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            )
            if 200 <= response.status_code < 300:
                logger.info(f"webhook delivered for task {task_id}")
                return True
            logger.warning(
                f"webhook for task {task_id} got HTTP {response.status_code} "
                f"(attempt {attempt + 1}/{attempts})"
            )
        except requests.RequestException as exc:
            # Do not log the URL: it may carry a token in its query string.
            logger.warning(
                f"webhook for task {task_id} failed with {type(exc).__name__} "
                f"(attempt {attempt + 1}/{attempts})"
            )
        if attempt < len(RETRY_DELAYS):
            time.sleep(RETRY_DELAYS[attempt])
    return False


def notify_task_finished(task_id: str, params: Any) -> bool:
    """Schedule a webhook if the task asked for one. Never raises."""
    try:
        callback_url = getattr(params, "callback_url", None)
        if not callback_url:
            return False
        payload = build_payload(task_id, sm.state.get_task(task_id))
        threading.Thread(
            target=deliver,
            args=(task_id, callback_url, payload),
            name=f"webhook-{task_id[:8]}",
            daemon=True,
        ).start()
        return True
    except Exception as exc:  # noqa: BLE001 - webhooks must not break tasks
        logger.warning(f"could not schedule webhook: {type(exc).__name__}")
        return False
