# Changelog

## 1.4.0

### New (free, no extra API keys)
- **Task-completion webhooks.** Pass `callback_url` when creating a task and get
  one JSON `POST` when it finishes (success or failure), so n8n/Zapier/custom
  backends no longer need to poll. Optional HMAC-SHA256 signature
  (`X-MPT-Signature`) via `app.webhook_secret`; 3 attempts with backoff;
  redirects are not followed; the URL is never stored or logged.
- **Subtitle export.** `GET /api/v1/tasks/{task_id}/subtitle?format=srt|vtt`
  downloads a task's subtitles as SRT or WebVTT (ready for HTML5 `<track>`).
- **Opt-in rate limiting.** `app.rate_limit_per_minute` limits POST requests
  under `/api/v1` per client address (also slows API-key guessing).
- **Security headers** on every response (`X-Content-Type-Options`,
  `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`).
- **SSRF guard** for outbound URLs: material downloads and webhooks refuse
  loopback, private, link-local (cloud metadata) and multicast addresses.
  Opt out with `app.allow_private_media_urls` / `app.callback_allow_private_hosts`.
- **Dependabot** (pip, GitHub Actions, Docker) and a **pip-audit** CI job.

### Fixed
- Sonilo background music: the ffmpeg proxy step passed a tuple as the
  `subprocess.run` timeout, which raises `TypeError`, so proxy generation could
  never succeed. It now uses a plain number and has a real-ffmpeg regression test.

### Already in the code base before this release (verified in review)
- Loop variable no longer shadows the `video` module in `material.py`.
- `listen_host` defaults to `127.0.0.1`; MD5 cache keys use `usedforsecurity=False`.
- Docker image: Debian bookworm, non-root user, healthcheck, no world-writable dir.
- Ruff lint in CI.

### Upgrade notes
- No breaking changes. All new settings default to previous behavior, except the
  SSRF guard, which now rejects material URLs that resolve to private networks.
  If you serve materials from a LAN host, set `allow_private_media_urls = true`.
- Queued tasks restored from Redis after an API restart lose their
  `callback_url` (it is deliberately not persisted because it may contain a token).
