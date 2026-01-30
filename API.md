# API Reference

All endpoints are prefixed with `/api`. The agent also serves the web UI at `/` and exposes `GET /health`.

## Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/login` | Login with username and password |

## Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/config` | Get current config (token masked) |
| `POST` | `/api/config` | Update config (e.g. API token) |

## Avatars

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/avatars` | List all avatars |
| `DELETE` | `/api/avatars/{avatar_id}` | Delete an avatar |
| `GET` | `/api/cache/avatars/{filename}` | Serve cached avatar image |

## Telegram Auth — Phone

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/avatars/telegram/phone/start` | Request verification code |
| `POST` | `/api/avatars/telegram/phone/complete` | Submit code and optional 2FA password |

## Telegram Auth — QR Code

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/avatars/telegram/qr/start` | Generate QR login URL |
| `GET` | `/api/avatars/telegram/qr/status/{avatar_id}` | Poll QR scan status |
| `POST` | `/api/avatars/telegram/qr/cancel/{avatar_id}` | Cancel QR auth |

## Sources (per avatar)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/avatars/{avatar_id}/sources` | List whitelisted sources |
| `POST` | `/api/avatars/{avatar_id}/sources` | Add a source |
| `PUT` | `/api/avatars/{avatar_id}/sources/{source_id}` | Update a source |
| `DELETE` | `/api/avatars/{avatar_id}/sources/{source_id}` | Remove a source |
| `GET` | `/api/avatars/{avatar_id}/dialogs` | List Telegram dialogs (`?limit=100&refresh=false`) |

## Blacklist

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/blacklist` | Get blacklist rules |
| `PUT` | `/api/blacklist` | Update blacklist rules |

## History

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/history` | Query audit log (`?avatar_id=&job_id=&date=&limit=50`) |

## Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/control/start` | Start the polling loop |
| `POST` | `/api/control/stop` | Stop the polling loop |
| `GET` | `/api/status` | Agent status (running, verified, reachable, configured) |
