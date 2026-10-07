"""System diagnostics ("doctor") shared by the API, CLI and WebUI.

Every check is free: it only inspects the local machine and configuration and
never calls a paid provider. Results contain no secrets and no absolute paths so
the coarse report can be exposed on an unauthenticated health endpoint.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from typing import Any

from app import __version__
from app.config import config
from app.utils import utils

OK = "ok"
WARN = "warn"
FAIL = "fail"

# Free disk space below which video rendering is likely to fail.
MIN_FREE_DISK_MB = 1024


def _check(status: str, message: str) -> dict[str, str]:
    return {"status": status, "message": message}


def check_ffmpeg() -> dict[str, str]:
    try:
        ready = utils.check_ffmpeg_ready(timeout=5)
    except Exception as exc:  # defensive: diagnostics must never raise
        return _check(FAIL, f"ffmpeg probe failed: {type(exc).__name__}")
    if ready:
        return _check(OK, "ffmpeg is available")
    return _check(FAIL, "ffmpeg not found; install it or set app.ffmpeg_path")


def check_storage() -> dict[str, str]:
    try:
        storage = utils.storage_dir(create=True)
        with tempfile.NamedTemporaryFile(dir=storage, prefix=".doctor-"):
            pass
    except OSError as exc:
        return _check(FAIL, f"storage directory is not writable ({type(exc).__name__})")
    return _check(OK, "storage directory is writable")


def check_disk_space(min_free_mb: int = MIN_FREE_DISK_MB) -> dict[str, str]:
    try:
        free_mb = shutil.disk_usage(utils.storage_dir(create=True)).free // (1024 * 1024)
    except OSError as exc:
        return _check(WARN, f"could not read disk usage ({type(exc).__name__})")
    if free_mb < min_free_mb:
        return _check(WARN, f"only {free_mb} MB free; at least {min_free_mb} MB recommended")
    return _check(OK, f"{free_mb} MB free")


def check_redis() -> dict[str, str]:
    if not config.app.get("enable_redis", False):
        return _check(OK, "redis disabled (in-memory task state)")
    try:
        import redis

        client = redis.StrictRedis(
            host=config.app.get("redis_host", "localhost"),
            port=config.app.get("redis_port", 6379),
            db=config.app.get("redis_db", 0),
            password=config.app.get("redis_password") or None,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
    except Exception as exc:
        return _check(FAIL, f"redis is enabled but unreachable ({type(exc).__name__})")
    return _check(OK, "redis reachable")


def check_api_security() -> dict[str, str]:
    api_key = config.app.get("api_key", "")
    protected = isinstance(api_key, str) and api_key != ""
    host = getattr(config, "listen_host", "127.0.0.1")
    exposed = host not in ("127.0.0.1", "localhost", "::1")
    if exposed and not protected:
        return _check(
            WARN,
            "API listens on a non-loopback address without app.api_key; "
            "anyone on the network can spend your provider credits",
        )
    if protected:
        return _check(OK, "API key authentication is enabled")
    return _check(OK, "API is local-only")


def check_llm_configured() -> dict[str, str]:
    provider = str(config.app.get("llm_provider", "") or "").strip()
    if not provider:
        return _check(WARN, "no llm_provider configured; script generation will fail")
    return _check(OK, f"llm provider: {provider}")


def check_python() -> dict[str, str]:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < (3, 11):
        return _check(WARN, f"Python {version}; 3.11+ is recommended")
    return _check(OK, f"Python {version}")


_CHECKS = {
    "python": check_python,
    "ffmpeg": check_ffmpeg,
    "storage": check_storage,
    "disk_space": check_disk_space,
    "redis": check_redis,
    "api_security": check_api_security,
    "llm": check_llm_configured,
}


def run_diagnostics() -> dict[str, Any]:
    """Run all checks. ``status`` is the worst individual status."""
    checks: dict[str, dict[str, str]] = {}
    for name, fn in _CHECKS.items():
        try:
            checks[name] = fn()
        except Exception as exc:  # one broken check must not hide the others
            checks[name] = _check(FAIL, f"check crashed: {type(exc).__name__}")

    statuses = {c["status"] for c in checks.values()}
    overall = FAIL if FAIL in statuses else WARN if WARN in statuses else OK
    return {"status": overall, "version": __version__, "checks": checks}


def coarse_report(report: dict[str, Any]) -> dict[str, Any]:
    """Strip messages so an unauthenticated endpoint leaks no configuration."""
    return {
        "status": report["status"],
        "version": report["version"],
        "checks": {name: c["status"] for name, c in report["checks"].items()},
    }


def format_report(report: dict[str, Any]) -> str:
    icons = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
    lines = [f"MoneyPrinterTurbo v{report['version']} - overall: {report['status'].upper()}"]
    for name, check in report["checks"].items():
        lines.append(f"{icons[check['status']]} {name:<13} {check['message']}")
    return "\n".join(lines)
