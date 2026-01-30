[![Hubfeed Banner](../frontend/public/images/banner.jpg)](https://hubfeed.io)

# Hubfeed Agent

A lightweight, privacy-focused Docker application that runs on your machine, enabling secure access to your private channels and groups through the Hubfeed platform using your own accounts (BYOD).

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Install](#install)
- [Configuration](#configuration)
- [Features](#features)
- [API Reference](#api-reference)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

## Overview

- **Privacy First** — credentials and sessions never leave your machine
- **RPC Architecture** — The agent executes commands dispatched by Hubfeed.io; all orchestration logic lives server-side
- **Local Control** — Manage avatars, source whitelists, blacklist filters, and audit history through a built-in web UI
- **Transparent** — Every job execution, auth event, and configuration change is recorded in a local audit log
- **Extensible** — Platform handler system designed for future support beyond Telegram

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Web UI (Browser)                         │
│               HTML / CSS / Vanilla JavaScript                │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP/JSON
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
│                                                              │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ API Routes │  │ Agent Loop   │  │ Platform Manager     │  │
│  │ (routes.py)│  │ (loop.py)    │  │ ┌──────────────────┐ │  │
│  └─────┬──────┘  │ poll → exec  │  │ │ TelegramHandler  │ │  │
│        │         │ → submit     │  │ │ (Telethon)       │ │  │
│        ▼         └──────┬───────┘  │ └──────────────────┘ │  │
│  ┌─────────────┐        │          └──────────┬───────────┘  │
│  │ Config Mgr  │        ▼                     │              │
│  │ (JSON files)│  ┌─────────────┐             │              │
│  └─────────────┘  │ Job Executor│─────────────┘              │
│  ┌─────────────┐  │ → dispatch  │                            │
│  │ History Log │  │ → filter    │                            │
│  │ (daily rot.)│  │ → log       │                            │
│  └─────────────┘  └──────┬──────┘                            │
└──────────────────────────┼───────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     ┌────────────────┐      ┌──────────────────┐
     │ Hubfeed SaaS   │      │ Telegram API     │
     │ (task queue,   │      │ (via Telethon)   │
     │  results)      │      │                  │
     └────────────────┘      └──────────────────┘
```

**Data flow:** The agent loop polls the Hubfeed backend for pending jobs, dispatches each job to the appropriate platform handler (Telegram), applies local blacklist filters to the results, logs the execution to the audit history, and submits filtered results back to the backend.

## Install

### Docker (Recommended)

Docker is the recommended way to run the Hubfeed Agent in production. You need [Docker](https://docs.docker.com/get-started/get-docker/) installed on your machine.

#### Option 1: Docker Compose

1. **Set environment variables** (optional but recommended):
```bash
cat > .env << EOF
AGENT_UI_USERNAME=yourusername
AGENT_UI_PASSWORD=yoursecurepassword
EOF
```

2. **Build and start**:
```bash
docker-compose up -d
```

3. **Access the UI** at `http://localhost:8080`

4. **View logs**:
```bash
docker-compose logs -f hubfeed-agent
```

5. **Stop**:
```bash
docker-compose down
```

#### Option 2: Docker Directly

```bash
# Build
docker build -t hubfeed-agent .

# Run
docker run -d \
  --name hubfeed-agent \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -e AGENT_UI_USERNAME=admin \
  -e AGENT_UI_PASSWORD=changeme \
  --restart unless-stopped \
  hubfeed-agent
```

#### Persistent Data

Two directories are mounted as Docker volumes:

| Directory | Contents |
|-----------|----------|
| `data/` | `config.json`, `avatars.json`, `blacklist.json` |
| `data/logs/` | Daily-rotated audit logs (`history_YYYY-MM-DD.json`) |

#### Default Credentials

- **Username**: `admin`
- **Password**: `changeme`

> **Warning**: Change these before deploying to production.

### Local Environment

For development or running without Docker. Requires Python 3.11+.

1. Create virtual environment:
```bash
cd agent
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the agent:
```bash
# Basic usage
python -m src.main

# With custom credentials
python -m src.main --username admin --password admin

# With custom host and port
python -m src.main --host 127.0.0.1 --port 8989

# All options
python -m src.main --username admin --password admin --host 127.0.0.1 --port 8989
```

4. Access the web UI at `http://localhost:8080`

#### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--username` | Override `AGENT_UI_USERNAME` env var | `admin` |
| `--password` | Override `AGENT_UI_PASSWORD` env var | `changeme` |
| `--host` | Bind address | `0.0.0.0` |
| `--port` | Bind port | `8080` |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_UI_USERNAME` | Web UI login username | `admin` |
| `AGENT_UI_PASSWORD` | Web UI login password | `changeme` |
| `HUBFEED_API_URL` | Hubfeed backend URL | `https://hubfeed.io` |

### First Time Setup

1. Open the web UI at `http://localhost:8080`
2. Log in with the default credentials
3. Navigate to the **Setup** tab
4. Enter your Hubfeed API token (generated from your Hubfeed account)
5. The agent verifies the token, fetches platform configuration, and syncs avatar data

### Adding Telegram Avatars

The agent supports two authentication methods:

**Phone Number:**
1. Click **Add Avatar**
2. Enter a friendly name
3. Enter your phone number in international format (`+1234567890`)
4. Enter the verification code sent to your Telegram app
5. If 2FA is enabled, enter your password

**QR Code:**
1. Click **Add Avatar** and select QR code authentication
2. Scan the displayed QR code with Telegram on your phone
3. The agent polls for scan completion and logs you in automatically

## Features

### Avatar Management
- Add multiple Telegram accounts via phone or QR code
- View session status and connectivity
- Per-avatar source whitelists
- Remove avatars and their sessions

### Source / Whitelist Management
- Define which Telegram channels and groups each avatar monitors
- Browse available dialogs directly from the UI
- Set per-source polling frequency: `5m`, `10m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `24h`
- Track last-checked timestamps and message IDs

### Local Blacklist
- Filter messages **before** they are sent to the Hubfeed backend
- Filtered items are counted and logged but never transmitted

### Audit History
- Every operation recorded with structured event data
- Event types: `job_execution`, `avatar_*`, `source_*`, `auth_*`, `system_*`
- Daily file rotation with a max of 1000 entries per file
- Query by avatar, job ID, date, event type, or resource
- Summary statistics available via API

### Agent Control
- Start/stop the polling loop from the web UI
- Health check endpoint for monitoring
- Automatic token re-verification every 24 hours
- Avatar sync to backend every 5 minutes

## Security

- **Local-only credentials** — Telegram sessions and login details are stored in `data/` on your machine and never transmitted to the Hubfeed backend
- **Token authentication** — The agent authenticates with the backend using a user-generated API token; the token is verified every 24 hours
- **HTTPS** — All communication with the Hubfeed backend uses HTTPS
- **Local filtering** — Blacklisted content is stripped locally before any data reaches the backend
- **Encrypted sessions** — Telegram sessions are persisted using Telethon's encrypted `StringSession` format
- **UI authentication** — The web UI requires username/password login; credentials are configurable via environment variables

## Troubleshooting

### Agent not connecting to Hubfeed
- Verify your API token is correct in the Setup tab
- Check network connectivity to `https://hubfeed.io`
- Review agent logs: `docker-compose logs -f` or `data/logs/history_*.json`

### Telegram authentication fails
- Ensure phone number is in international format (`+1234567890`)
- Check your Telegram app for the verification code
- If using QR code, ensure your phone has internet access
- Verify 2FA password if enabled

### Jobs not executing
- Confirm the polling loop is started (green status in the Status tab)
- Check that avatars have active sessions
- Verify sources are configured for each avatar
- Review the History tab for error details

### Avatar shows as disconnected
- Telegram sessions can expire; re-authenticate the avatar
- Check if the Telegram account was logged out from another device

### Need more help?

Contact our support team at [support@hubfeed.io](mailto:support@hubfeed.io).


## Development

See [DEV.md](DEV.md) for project structure, CI/CD, tests, dependencies, and code patterns.

## API Reference

See [API.md](API.md) for the full endpoint reference.