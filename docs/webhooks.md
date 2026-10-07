# Webhooks and subtitle export (v1.4)

## Task-completion webhook

Create a task as usual and add `callback_url`:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/videos \
  -H "Content-Type: application/json" -H "x-api-key: $MPT_KEY" \
  -d '{"video_subject": "Why sleep matters",
       "callback_url": "https://example.com/hooks/mpt"}'
```

When the task reaches a terminal state the server sends one `POST`:

```json
{"event": "task.finished", "task_id": "…", "status": "complete",
 "progress": 100, "finished_at": 1791345171, "version": "1.4.0"}
```

`status` is `complete` or `failed` (failures also carry a short `error`). The body never contains
file paths; fetch results with `GET /api/v1/tasks/{task_id}` and your API key.

* Headers: `X-MPT-Event: task.finished`, and `X-MPT-Signature: sha256=<hmac>` when
  `app.webhook_secret` is set.
* Delivery: 3 attempts (1 s and 3 s backoff), 2xx counts as success, redirects are not followed.
* The URL is not stored in task state and not logged (it may contain a token).
* Receivers on private/LAN/localhost addresses need `app.callback_allow_private_hosts = true`.
* Tasks restored from a Redis queue after an API restart lose their `callback_url`.

### Verifying the signature (Python)

```python
import hashlib, hmac

def is_valid(secret: str, raw_body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")
```

Always verify against the **raw** request body, before any JSON parsing.

## Subtitle export

```bash
curl -H "x-api-key: $MPT_KEY" \
  "http://127.0.0.1:8080/api/v1/tasks/<task_id>/subtitle?format=vtt" -o subtitle.vtt
```

`format` is `srt` (default) or `vtt`. WebVTT works directly in HTML5:
`<track kind="subtitles" src="subtitle.vtt" srclang="en" default>`.

## Rate limiting

Set `app.rate_limit_per_minute = 30` to allow 30 POST requests per minute per client address under
`/api/v1`; further requests get `429` with a `Retry-After` header. The limit is per process, and the
client address is the direct peer, so behind a reverse proxy apply limits there as well.
