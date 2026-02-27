"""API routes for local agent management."""

import logging
import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel
import qrcode
import qrcode.image.svg
from io import BytesIO
import base64
from pathlib import Path

from src.platforms import TelegramHandler

logger = logging.getLogger(__name__)

router = APIRouter()


# Helper function to get global instances
def get_globals():
    """Get global instances from main module."""
    from ..main import (
        config_manager,
        hubfeed_client,
        history_logger,
        executor,
        agent_loop,
        platform_manager
    )
    return config_manager, hubfeed_client, history_logger, executor, agent_loop, platform_manager


# Pydantic models (must be defined before routes that use them)
class ConfigUpdate(BaseModel):
    token: Optional[str] = None


class TelegramPhoneAuthStart(BaseModel):
    avatar_id: str
    phone: str


class TelegramPhoneAuthComplete(BaseModel):
    avatar_id: str
    phone: str
    code: str
    phone_code_hash: str
    password: Optional[str] = None


class TelegramQRAuthStart(BaseModel):
    avatar_id: str


class BlacklistUpdate(BaseModel):
    blacklist: Dict[str, Any]


class SourceAdd(BaseModel):
    id: str
    name: str
    type: str = "channel"
    username: Optional[str] = None
    frequency_seconds: int = 300


class SourceUpdate(BaseModel):
    frequency_seconds: Optional[int] = None


class LoginRequest(BaseModel):
    username: str
    password: str


# Authentication endpoint
@router.post("/auth/login")
async def login(request: LoginRequest):
    """Authenticate and get a session token."""
    username = os.getenv("AGENT_UI_USERNAME", "admin")
    password = os.getenv("AGENT_UI_PASSWORD", "changeme")
    
    if request.username != username or request.password != password:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )
    
    # Create a simple token (base64 encoded username:password)
    token_string = f"{request.username}:{request.password}"
    token = base64.b64encode(token_string.encode()).decode()
    
    return {
        "success": True,
        "token": token,
        "username": request.username
    }


# Config endpoints
@router.get("/config")
async def get_config():
    """Get current configuration."""
    config_manager, _, _, _, _, _ = get_globals()
    config = config_manager.get_config()
    
    # Don't expose full token
    if config.get("token"):
        config["token"] = config["token"][:12] + "..." if len(config["token"]) > 12 else "***"
    
    # Include resolved Hubfeed URL (from env var or default)
    config["hubfeed_url"] = os.environ.get("HUBFEED_API_URL", "https://hubfeed.io")

    return {
        "config": config,
        "is_configured": config_manager.is_configured(),
        "is_verified": config_manager.is_verified()
    }


@router.post("/config")
async def update_config(update: ConfigUpdate):
    """Update configuration."""
    config_manager, hubfeed_client, _, _, agent_loop, _ = get_globals()
    updates = {}

    if update.token is not None:
        updates["token"] = update.token

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    success = config_manager.update_config(**updates)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")

    # If token changed, restart agent loop to pick up the new token
    if "token" in updates and agent_loop:
        # Always close cached HTTP client so it picks up the new token
        await hubfeed_client.close()
        if agent_loop.is_running:
            logger.info("Token updated, restarting agent loop...")
            await agent_loop.stop()
            await agent_loop.start()
        elif config_manager.is_configured():
            await agent_loop.start()

    return {"success": True, "message": "Configuration updated"}


# Avatar endpoints
@router.get("/avatars")
async def get_avatars():
    """Get all avatars."""
    config_manager, _, _, _, _, _ = get_globals()
    avatars = config_manager.get_avatars()
    
    # Remove sensitive session data
    safe_avatars = []
    for avatar in avatars:
        safe_avatar = {
            "id": avatar.get("id"),
            "name": avatar.get("name"),
            "platform": avatar.get("platform"),
            "status": avatar.get("status"),
            "phone": avatar.get("phone"),
            "created_at": avatar.get("created_at"),
            "last_used_at": avatar.get("last_used_at"),
            "metadata": {
                k: v for k, v in avatar.get("metadata", {}).items()
                if k != "session_string"
            }
        }
        safe_avatars.append(safe_avatar)
    
    return {"avatars": safe_avatars}


@router.delete("/avatars/{avatar_id}")
async def delete_avatar(avatar_id: str):
    """Delete an avatar."""
    config_manager, hubfeed_client, _, _, _, _ = get_globals()
    success = config_manager.delete_avatar(avatar_id)

    if not success:
        raise HTTPException(status_code=404, detail="Avatar not found")

    # Sync remaining avatars with Hubfeed so backend knows this avatar is gone
    if config_manager.is_configured():
        try:
            avatars = config_manager.get_avatars()
            await hubfeed_client.sync_avatars(avatars)
            logger.info(f"Synced avatars with Hubfeed after deleting avatar {avatar_id}")
        except Exception as e:
            logger.warning(f"Failed to sync avatars with Hubfeed: {e}")

    return {"success": True, "message": f"Avatar {avatar_id} deleted"}


# Cache endpoints
@router.get("/cache/avatars/{filename}")
async def get_cached_avatar(filename: str):
    """Serve cached avatar images."""
    # Validate filename to prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    avatar_path = Path("data/.cache/avatars") / filename
    
    if not avatar_path.exists():
        # Return static placeholder image
        placeholder_path = Path("ui/avatar_placeholder.png")
        
        if not placeholder_path.exists():
            raise HTTPException(status_code=404, detail="Placeholder image not found")
        
        return FileResponse(placeholder_path, media_type="image/png")
    
    return FileResponse(avatar_path, media_type="image/png")


# Telegram authentication endpoints
@router.post("/avatars/telegram/phone/start")
async def telegram_phone_auth_start(data: TelegramPhoneAuthStart):
    """Start Telegram phone authentication."""
    config_manager, _, _, _, _, platform_manager = get_globals()
    telegram_handler = platform_manager.get_handler('telegram')
    
    try:
        result = await telegram_handler.start_auth(data.avatar_id, data.phone)
        return result
    except Exception as e:
        logger.error(f"Phone auth start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/avatars/telegram/phone/complete")
async def telegram_phone_auth_complete(data: TelegramPhoneAuthComplete):
    """Complete Telegram phone authentication."""
    config_manager, hubfeed_client, _, _, agent_loop, platform_manager = get_globals()
    telegram_handler = platform_manager.get_handler('telegram')
    
    try:
        result = await telegram_handler.complete_auth(
            data.avatar_id,
            data.phone,
            data.code,
            data.phone_code_hash,
            data.password
        )
        
        # Sync avatar with Hubfeed if configured
        if config_manager.is_configured() and result.get("status") == "authenticated":
            try:
                await hubfeed_client.sync_avatars([result["avatar"]])
            except Exception as e:
                logger.warning(f"Failed to sync avatar with Hubfeed: {e}")

            # Refresh agent config from backend
            if agent_loop and agent_loop.is_running:
                try:
                    await agent_loop.refresh_config()
                except Exception as e:
                    logger.warning(f"Failed to refresh config after auth: {e}")

        return result
    except Exception as e:
        logger.error(f"Phone auth complete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/avatars/telegram/qr/start")
async def telegram_qr_auth_start(data: TelegramQRAuthStart):
    """Start Telegram QR code authentication."""
    config_manager, _, _, _, _, platform_manager = get_globals()
    telegram_handler = platform_manager.get_handler('telegram')
    
    try:
        result = await telegram_handler.start_qr_auth(data.avatar_id)
        
        # Generate QR code image as base64
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(result["url"])
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        result["qr_code_image"] = f"data:image/png;base64,{img_str}"
        
        return result
    except Exception as e:
        logger.error(f"QR auth start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/avatars/telegram/qr/status/{avatar_id}")
async def telegram_qr_auth_status(avatar_id: str, timeout: int = 30):
    """Check QR code authentication status."""
    config_manager, hubfeed_client, _, _, agent_loop, platform_manager = get_globals()
    telegram_handler = platform_manager.get_handler('telegram')
    
    try:
        result = await telegram_handler.wait_qr_scan(avatar_id, timeout=timeout)
        
        # Sync avatar with Hubfeed if configured
        if config_manager.is_configured() and result.get("status") == "authenticated":
            try:
                await hubfeed_client.sync_avatars([result["avatar"]])
            except Exception as e:
                logger.warning(f"Failed to sync avatar with Hubfeed: {e}")

            # Refresh agent config from backend
            if agent_loop and agent_loop.is_running:
                try:
                    await agent_loop.refresh_config()
                except Exception as e:
                    logger.warning(f"Failed to refresh config after auth: {e}")

        return result
    except Exception as e:
        logger.error(f"QR auth status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/avatars/telegram/qr/cancel/{avatar_id}")
async def telegram_qr_auth_cancel(avatar_id: str):
    """Cancel QR code authentication."""
    config_manager, _, _, _, _, platform_manager = get_globals()
    telegram_handler = platform_manager.get_handler('telegram')
    
    try:
        success = await telegram_handler.cancel_qr_auth(avatar_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"QR auth cancel failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Browser authentication endpoints ---

class BrowserAuthStart(BaseModel):
    avatar_id: str
    platform: str       # 'x', etc.
    username: str
    password: str


class BrowserChallengeResponse(BaseModel):
    avatar_id: str
    response: str       # 2FA code, phone number, etc.


@router.get("/platforms/browser/available")
async def get_available_browser_platforms():
    """List available browser platforms (from backend login flows)."""
    config_manager, _, _, _, _, _ = get_globals()
    browser_config = config_manager.get_platform_config("browser")

    if not browser_config or not browser_config.get("login_flows"):
        return {"platforms": []}

    platforms = []
    for flow in browser_config["login_flows"]:
        platforms.append({
            "platform": flow.get("platform") if isinstance(flow, dict) else flow.platform,
            "display_name": flow.get("display_name") if isinstance(flow, dict) else flow.display_name,
            "credential_fields": flow.get("credential_fields", ["username", "password"]) if isinstance(flow, dict) else getattr(flow, 'credential_fields', ["username", "password"]),
        })

    return {"platforms": platforms}


@router.post("/avatars/browser/auth/start")
async def browser_auth_start(data: BrowserAuthStart):
    """Start browser authentication for a new avatar."""
    config_manager, hubfeed_client, _, executor, agent_loop, _ = get_globals()

    try:
        result = await executor.browser_handler.start_auth(
            data.avatar_id,
            data.platform,
            {"username": data.username, "password": data.password}
        )

        # Sync avatar with backend on success
        if config_manager.is_configured() and result.get("status") == "authenticated":
            try:
                avatars = config_manager.get_avatars()
                await hubfeed_client.sync_avatars(avatars)
            except Exception as e:
                logger.warning(f"Failed to sync avatar with Hubfeed: {e}")

            # Refresh agent config from backend
            if agent_loop and agent_loop.is_running:
                try:
                    await agent_loop.refresh_config()
                except Exception as e:
                    logger.warning(f"Failed to refresh config after auth: {e}")

        return result
    except Exception as e:
        logger.error(f"Browser auth start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/avatars/browser/auth/challenge")
async def browser_auth_challenge(data: BrowserChallengeResponse):
    """Submit challenge response (2FA, phone verification)."""
    config_manager, hubfeed_client, _, executor, agent_loop, _ = get_globals()

    try:
        result = await executor.browser_handler.submit_challenge(
            data.avatar_id, data.response
        )

        if config_manager.is_configured() and result.get("status") == "success":
            try:
                avatars = config_manager.get_avatars()
                await hubfeed_client.sync_avatars(avatars)
            except Exception as e:
                logger.warning(f"Failed to sync avatars with Hubfeed: {e}")

            # Refresh agent config from backend
            if agent_loop and agent_loop.is_running:
                try:
                    await agent_loop.refresh_config()
                except Exception as e:
                    logger.warning(f"Failed to refresh config after auth: {e}")

        return result
    except Exception as e:
        logger.error(f"Browser auth challenge failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/avatars/browser/auth/challenge/{avatar_id}")
async def browser_get_pending_challenge(avatar_id: str):
    """Get pending challenge info for an avatar."""
    _, _, _, executor, _, _ = get_globals()

    challenge = executor.browser_handler.get_pending_challenge(avatar_id)
    if not challenge:
        return {"has_challenge": False}

    return {
        "has_challenge": True,
        "challenge_prompt": challenge.get("challenge_prompt"),
        "step_id": challenge.get("step_id"),
    }


@router.post("/avatars/browser/test/{avatar_id}")
async def browser_test_connection(avatar_id: str):
    """Test if browser avatar is still logged in."""
    config_manager, _, _, executor, _, _ = get_globals()

    avatar = config_manager.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")

    try:
        session = await executor.browser_handler._get_session(avatar_id)
        is_logged_in = await session.check_login_state()
        return {"logged_in": is_logged_in, "avatar_id": avatar_id}
    except Exception as e:
        return {"logged_in": False, "avatar_id": avatar_id, "error": str(e)}


# Blacklist endpoints
@router.get("/blacklist")
async def get_blacklist():
    """Get blacklist configuration."""
    config_manager, _, _, _, _, _ = get_globals()
    blacklist = config_manager.get_blacklist()
    return {"blacklist": blacklist}


@router.put("/blacklist")
async def update_blacklist(data: BlacklistUpdate):
    """Update blacklist configuration."""
    config_manager, hubfeed_client, _, _, _, _ = get_globals()
    success = config_manager.save_blacklist(data.blacklist)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update blacklist")
    
    # Sync all avatars with Hubfeed if configured (blacklist affects all avatars)
    if config_manager.is_configured():
        try:
            avatars = config_manager.get_avatars()
            if avatars:
                await hubfeed_client.sync_avatars(avatars)
                logger.info(f"Synced {len(avatars)} avatars with Hubfeed after blacklist update")
        except Exception as e:
            logger.warning(f"Failed to sync avatars with Hubfeed: {e}")
    
    return {"success": True, "message": "Blacklist updated"}


# History endpoints
@router.get("/history")
async def get_history(
    avatar_id: Optional[str] = None,
    job_id: Optional[str] = None,
    date: Optional[str] = None,
    limit: int = 50
):
    """Get execution history."""
    _, _, history_logger, _, _, _ = get_globals()
    try:
        history = await history_logger.query_history(
            avatar_id=avatar_id,
            job_id=job_id,
            date=date,
            limit=limit
        )
        return {"history": history}
    except Exception as e:
        logger.error(f"History query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Status endpoint
@router.get("/status")
async def get_status():
    """Get agent status."""
    _, _, _, _, agent_loop, _ = get_globals()
    if not agent_loop:
        return {
            "status": "not_initialized",
            "message": "Agent loop not initialized"
        }
    
    health = await agent_loop.health_check()
    
    return {
        "status": "running" if health["running"] else "stopped",
        "version": "1.0.0",  # TODO: Import from __version__
        **health
    }


# Control endpoints
@router.post("/control/start")
async def start_agent():
    """Start the agent polling loop."""
    config_manager, _, _, _, agent_loop, _ = get_globals()
    if not config_manager.is_configured():
        raise HTTPException(
            status_code=400,
            detail="Agent not configured. Please set agent token first."
        )
    
    if agent_loop.is_running:
        return {"success": True, "message": "Agent already running"}
    
    await agent_loop.start()
    return {"success": True, "message": "Agent started"}


@router.post("/control/stop")
async def stop_agent():
    """Stop the agent polling loop."""
    _, _, _, _, agent_loop, _ = get_globals()
    if not agent_loop.is_running:
        return {"success": True, "message": "Agent already stopped"}
    
    await agent_loop.stop()
    return {"success": True, "message": "Agent stopped"}


# Source management endpoints
@router.get("/avatars/{avatar_id}/sources")
async def get_avatar_sources(avatar_id: str):
    """Get sources configuration for an avatar."""
    config_manager, _, _, _, _, _ = get_globals()
    
    avatar = config_manager.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    
    sources = config_manager.get_avatar_sources(avatar_id)
    return {
        "avatar_id": avatar_id,
        "sources": sources,
        "frequency_presets": config_manager.FREQUENCY_PRESETS
    }


@router.post("/avatars/{avatar_id}/sources")
async def add_source(avatar_id: str, source: SourceAdd):
    """Add a source to an avatar's whitelist."""
    config_manager, hubfeed_client, _, _, _, _ = get_globals()
    
    avatar = config_manager.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    
    source_data = {
        "id": source.id,
        "name": source.name,
        "type": source.type,
        "frequency_seconds": source.frequency_seconds
    }
    if source.username:
        source_data["username"] = source.username
    success = config_manager.add_source(avatar_id, source_data)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to add source (may already exist)")
    
    # Sync avatar with Hubfeed if configured
    if config_manager.is_configured():
        try:
            updated_avatar = config_manager.get_avatar(avatar_id)
            await hubfeed_client.sync_avatars([updated_avatar])
            logger.info(f"Synced avatar {avatar_id} with Hubfeed after adding source")
        except Exception as e:
            logger.warning(f"Failed to sync avatar with Hubfeed: {e}")
    
    return {"success": True, "message": f"Source {source.name} added"}


@router.put("/avatars/{avatar_id}/sources/{source_id}")
async def update_source(avatar_id: str, source_id: str, update: SourceUpdate):
    """Update a source's settings."""
    config_manager, hubfeed_client, _, _, _, _ = get_globals()
    
    avatar = config_manager.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    
    updates = {}
    if update.frequency_seconds is not None:
        updates["frequency_seconds"] = update.frequency_seconds
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    success = config_manager.update_source(avatar_id, source_id, updates)
    
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # Sync avatar with Hubfeed if configured
    if config_manager.is_configured():
        try:
            updated_avatar = config_manager.get_avatar(avatar_id)
            await hubfeed_client.sync_avatars([updated_avatar])
            logger.info(f"Synced avatar {avatar_id} with Hubfeed after updating source")
        except Exception as e:
            logger.warning(f"Failed to sync avatar with Hubfeed: {e}")
    
    return {"success": True, "message": "Source updated"}


@router.delete("/avatars/{avatar_id}/sources/{source_id}")
async def remove_source(avatar_id: str, source_id: str):
    """Remove a source from an avatar's whitelist."""
    config_manager, hubfeed_client, _, _, _, _ = get_globals()
    
    avatar = config_manager.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    
    success = config_manager.remove_source(avatar_id, source_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove source")
    
    # Sync avatar with Hubfeed if configured
    if config_manager.is_configured():
        try:
            updated_avatar = config_manager.get_avatar(avatar_id)
            await hubfeed_client.sync_avatars([updated_avatar])
            logger.info(f"Synced avatar {avatar_id} with Hubfeed after removing source")
        except Exception as e:
            logger.warning(f"Failed to sync avatar with Hubfeed: {e}")
    
    return {"success": True, "message": "Source removed"}


@router.get("/avatars/{avatar_id}/dialogs")
async def get_avatar_dialogs(avatar_id: str, limit: int = 100, refresh: bool = False):
    """List Telegram dialogs (chats, channels, groups) for source selection.
    
    Args:
        avatar_id: Avatar identifier
        limit: Maximum number of dialogs to return
        refresh: If True, fetch fresh data from Telegram. If False, return cached data if available.
    """
    config_manager, _, _, _, _, platform_manager = get_globals()
    
    avatar = config_manager.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    
    if avatar.get("status") != "active":
        raise HTTPException(status_code=400, detail="Avatar not authenticated")
    
    # Check for cached dialogs
    cached_dialogs = avatar.get("cached_dialogs", [])
    
    if not refresh and cached_dialogs:
        # Return cached data
        return {"dialogs": cached_dialogs, "cached": True}
    
    # Fetch fresh data from Telegram
    telegram_handler = platform_manager.get_handler('telegram')
    
    try:
        dialogs = await telegram_handler.list_dialogs(avatar_id, limit=limit, download_avatars=True)
        
        # Format dialogs for source selection
        formatted = []
        for dialog in dialogs:
            dialog_type = "channel"
            if dialog.get("is_group"):
                dialog_type = "group"
            elif dialog.get("is_user"):
                dialog_type = "user"
            
            dialog_id = str(dialog.get("id"))
            avatar_url = f"/api/cache/avatars/{dialog_id}.png" if dialog.get("avatar_cached") else None
            
            formatted.append({
                "id": dialog_id,
                "name": dialog.get("name", dialog.get("title", "Unknown")),
                "type": dialog_type,
                "username": dialog.get("username"),
                "members_count": dialog.get("participants_count"),
                "avatar_url": avatar_url,
                "avatar_cached": dialog.get("avatar_cached", False)
            })
        
        # Cache the dialogs in avatar config
        avatar["cached_dialogs"] = formatted
        config_manager.save_avatar(avatar)
        
        return {"dialogs": formatted, "cached": False}
    except Exception as e:
        logger.error(f"Failed to list dialogs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
