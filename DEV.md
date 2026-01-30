# Development

## Project Structure

```
agent/
├── src/
│   ├── main.py                 # FastAPI entry point, lifespan, CLI args
│   ├── __version__.py          # Version string
│   ├── api/
│   │   └── routes.py           # All REST endpoints
│   ├── core/
│   │   ├── loop.py             # Polling loop (verify → sync → poll → execute → submit)
│   │   ├── executor.py         # Job dispatcher + blacklist filtering
│   │   └── hubfeed_client.py   # HTTP client for the Hubfeed backend
│   ├── config/
│   │   ├── manager.py          # Config, avatar, source, and blacklist management
│   │   └── storage.py          # Thread-safe atomic JSON persistence
│   ├── platforms/
│   │   ├── manager.py          # Platform handler factory
│   │   └── telegram.py         # Telethon-based Telegram handler
│   ├── blacklist/
│   │   └── filter.py           # Keyword / sender / channel filtering
│   └── history/
│       └── logger.py           # Audit trail with daily file rotation
│
├── ui/                          # Web interface (vanilla HTML/CSS/JS)
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
├── tests/
│   ├── conftest.py              # Shared fixtures
│   └── unit/
│       ├── test_config_manager.py
│       ├── test_config_storage.py
│       ├── test_blacklist_filter.py
│       ├── test_executor.py
│       ├── test_history_logger.py
│       ├── test_hubfeed_client.py
│       ├── test_loop.py
│       └── test_routes.py
│
├── data/                        # Runtime data (created automatically)
│   ├── config.json
│   ├── avatars.json
│   ├── blacklist.json
│   └── logs/                    # Daily audit logs (history_YYYY-MM-DD.json)
│
├── .github/
│   └── workflows/
│       └── docker-publish.yml   # CI/CD → GitHub Container Registry
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pytest.ini
```

## CI/CD

The agent includes a GitHub Actions workflow (`.github/workflows/docker-publish.yml`) that publishes Docker images to the GitHub Container Registry (GHCR).

- **Triggers**: push to `main` branch or version tags (`v*.*.*`)
- **Platforms**: `linux/amd64`, `linux/arm64`
- **Tags**: `latest` for default branch, semver tags (`v1.2.3`, `1.2`, `1`)
- **Features**: Docker BuildKit caching, build attestation

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html --cov-report=term

# Run by marker
pytest -m unit
pytest -m integration
pytest -m e2e
```

Test markers are defined in `pytest.ini`: `unit`, `integration`, `e2e`, `slow`.

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `httpx` | Async HTTP client (backend communication) |
| `telethon` | Telegram MTProto client |
| `pydantic` | Request/response validation |
| `cryptography` | Session encryption |
| `qrcode` + `Pillow` | QR code generation for Telegram auth |
| `aiofiles` | Async file I/O |

## Code Patterns

- **Dependency injection** — Core components (`ConfigManager`, `HistoryLogger`, etc.) are constructed in `main.py`'s lifespan and passed to consumers
- **Atomic writes** — `JSONStorage` uses a write-then-rename pattern with `RLock` for thread safety
- **Async throughout** — FastAPI handlers, Telethon calls, and the polling loop are all async/await
- **Factory pattern** — `PlatformManager` creates platform handlers on demand, allowing future platform support
