"""Telegram platform handler using Telethon."""

import logging
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Handles Telegram operations using Telethon."""
    
    def __init__(self, config_manager):
        """Initialize Telegram handler.
        
        Args:
            config_manager: ConfigManager instance
        """
        self.config_manager = config_manager
        self._clients: Dict[str, TelegramClient] = {}
        self._pending_auth: Dict[str, TelegramClient] = {}
        
        # Get Telegram API credentials from config
        platform_config = config_manager.get_platform_config("telegram")
        self.api_id = platform_config.get("telegram_api_id")
        self.api_hash = platform_config.get("telegram_api_hash")
        
        if not self.api_id or not self.api_hash:
            logger.warning("Telegram API credentials not configured")
    
    @staticmethod
    def _serialize_datetime(obj: Any) -> Any:
        """Recursively convert datetime objects to ISO format strings.
        
        Args:
            obj: Object to serialize (dict, list, datetime, or primitive)
            
        Returns:
            Serialized object with datetime converted to strings
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {key: TelegramHandler._serialize_datetime(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [TelegramHandler._serialize_datetime(item) for item in obj]
        elif isinstance(obj, bytes):
            # Convert bytes to base64 string for JSON serialization
            return base64.b64encode(obj).decode('utf-8')
        else:
            return obj
    
    async def _get_client(self, avatar_id: str) -> TelegramClient:
        """Get or create Telegram client for avatar.
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            Connected TelegramClient
            
        Raises:
            ValueError: If avatar not found or not authenticated
            Exception: If connection fails
        """
        # Check if client exists and is connected
        if avatar_id in self._clients:
            client = self._clients[avatar_id]
            if client.is_connected():
                return client
        
        # Get avatar data
        avatar = self.config_manager.get_avatar(avatar_id)
        if not avatar:
            raise ValueError(f"Avatar not found: {avatar_id}")
        
        if avatar.get("platform") != "telegram":
            raise ValueError(f"Avatar {avatar_id} is not a Telegram avatar")
        
        session_string = avatar.get("session_string")
        if not session_string:
            raise ValueError(f"Avatar {avatar_id} has no session (not authenticated)")
        
        # Create client with saved session
        session = StringSession(session_string)
        client = TelegramClient(session, int(self.api_id), self.api_hash)
        
        await client.connect()
        
        # Verify authentication
        if not await client.is_user_authorized():
            await client.disconnect()
            self.config_manager.update_avatar_status(avatar_id, "auth_required")
            raise Exception(f"Avatar {avatar_id} requires re-authentication")
        
        # Cache client
        self._clients[avatar_id] = client
        
        # Update last used
        self.config_manager.update_avatar_status(avatar_id, "active")
        
        return client
    
    async def start_auth(self, avatar_id: str, phone: str) -> Dict[str, Any]:
        """Start Telegram authentication flow.
        
        Args:
            avatar_id: Avatar identifier
            phone: Phone number in international format
            
        Returns:
            Dict with status and phone_code_hash
            
        Raises:
            Exception: If authentication start fails
        """
        if not self.api_id or not self.api_hash:
            raise Exception("Telegram API credentials not configured")
        
        try:
            # Create new client with empty session
            session = StringSession()
            client = TelegramClient(session, int(self.api_id), self.api_hash)
            await client.connect()
            
            # Request code
            sent_code = await client.send_code_request(phone)
            
            # Store pending auth
            self._pending_auth[avatar_id] = client
            
            logger.info(f"Authentication code sent to {phone}")
            
            # Log audit event
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="started",
                    avatar_id=avatar_id,
                    details={"method": "phone", "phone": phone}
                )
            
            return {
                "status": "code_sent",
                "phone_code_hash": sent_code.phone_code_hash,
                "phone": phone
            }
            
        except Exception as e:
            logger.error(f"Failed to start authentication: {e}")
            
            # Log audit event for failure
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="started",
                    avatar_id=avatar_id,
                    details={"method": "phone", "phone": phone, "error": str(e)},
                    status="failed",
                    error=str(e)
                )
            
            if avatar_id in self._pending_auth:
                await self._pending_auth[avatar_id].disconnect()
                del self._pending_auth[avatar_id]
            raise
    
    async def complete_auth(
        self,
        avatar_id: str,
        phone: str,
        code: str,
        phone_code_hash: str,
        password: Optional[str] = None
    ) -> Dict[str, Any]:
        """Complete Telegram authentication.
        
        Args:
            avatar_id: Avatar identifier
            phone: Phone number
            code: Verification code
            phone_code_hash: Hash from start_auth
            password: 2FA password (if enabled)
            
        Returns:
            Dict with status and session info
            
        Raises:
            Exception: If authentication fails
        """
        client = self._pending_auth.get(avatar_id)
        if not client:
            raise ValueError("No pending authentication for this avatar")
        
        try:
            # Sign in with code
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                # 2FA required
                if not password:
                    return {
                        "status": "password_required",
                        "message": "Two-factor authentication is enabled. Please provide password."
                    }
                await client.sign_in(password=password)
            except PhoneCodeInvalidError:
                raise Exception("Invalid verification code")
            except PhoneCodeExpiredError:
                raise Exception("Verification code expired")
            
            # Get session string
            session_string = client.session.save()
            
            # Get user info
            me = await client.get_me()
            
            # Save avatar
            avatar_data = {
                "id": avatar_id,
                "name": f"Telegram - {me.first_name or 'User'}",
                "platform": "telegram",
                "phone": phone,
                "session_string": session_string,
                "status": "active",
                "created_at": self.config_manager.get_avatar(avatar_id) and 
                             self.config_manager.get_avatar(avatar_id).get("created_at") or 
                             datetime.utcnow().isoformat() + "Z",
                "last_used_at": datetime.utcnow().isoformat() + "Z",
                "metadata": {
                    "user_id": me.id,
                    "username": me.username,
                    "first_name": me.first_name,
                    "last_name": me.last_name,
                    "auth_method": "phone"
                }
            }
            
            self.config_manager.save_avatar(avatar_data)
            
            # Move to active clients
            self._clients[avatar_id] = client
            del self._pending_auth[avatar_id]
            
            logger.info(f"Authentication completed for avatar {avatar_id}")
            
            # Log audit event for successful auth
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="completed",
                    avatar_id=avatar_id,
                    details={"method": "phone", "phone": phone}
                )
            
            return {
                "status": "authenticated",
                "avatar": avatar_data
            }
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            
            # Log audit event for failed auth
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="failed",
                    avatar_id=avatar_id,
                    details={"method": "phone", "phone": phone, "error": str(e)},
                    status="failed",
                    error=str(e)
                )
            
            await client.disconnect()
            del self._pending_auth[avatar_id]
            raise
    
    async def start_qr_auth(self, avatar_id: str) -> Dict[str, Any]:
        """Start QR code authentication flow.
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            Dict with QR code data (token, URL, expiration)
            
        Raises:
            Exception: If QR auth start fails
        """
        if not self.api_id or not self.api_hash:
            raise Exception("Telegram API credentials not configured")
        
        try:
            # Create new client with empty session
            session = StringSession()
            client = TelegramClient(session, int(self.api_id), self.api_hash)
            await client.connect()
            
            # Request QR login
            qr_login = await client.qr_login()
            
            # Store pending auth with QR login object
            self._pending_auth[avatar_id] = {
                'client': client,
                'qr_login': qr_login,
                'method': 'qr'
            }
            
            logger.info(f"QR code generated for avatar {avatar_id}")
            
            # Log audit event
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="started",
                    avatar_id=avatar_id,
                    details={"method": "qr"}
                )
            
            # Use the URL provided by Telethon's QRLogin object
            # Telethon formats the URL correctly for Telegram
            qr_url = qr_login.url
            
            return {
                "status": "qr_ready",
                "token": qr_login.token.hex(),  # Keep for reference
                "url": qr_url,
                "expires_at": qr_login.expires.isoformat() if hasattr(qr_login, 'expires') else None
            }
            
        except Exception as e:
            logger.error(f"Failed to start QR authentication: {e}")
            
            # Log audit event for failure
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="started",
                    avatar_id=avatar_id,
                    details={"method": "qr", "error": str(e)},
                    status="failed",
                    error=str(e)
                )
            
            if avatar_id in self._pending_auth:
                await self._pending_auth[avatar_id]['client'].disconnect()
                del self._pending_auth[avatar_id]
            raise
    
    async def wait_qr_scan(self, avatar_id: str, timeout: int = 120) -> Dict[str, Any]:
        """Wait for QR code to be scanned and complete authentication.
        
        Args:
            avatar_id: Avatar identifier
            timeout: Maximum time to wait in seconds (default: 120)
            
        Returns:
            Dict with authentication status and avatar data
            
        Raises:
            ValueError: If no pending QR auth
            Exception: If authentication fails or times out
        """
        pending = self._pending_auth.get(avatar_id)
        if not pending or pending.get('method') != 'qr':
            raise ValueError("No pending QR authentication for this avatar")
        
        client = pending['client']
        qr_login = pending['qr_login']
        
        try:
            # Wait for user to scan QR code
            import asyncio
            await asyncio.wait_for(qr_login.wait(), timeout=timeout)
            
            # QR was scanned successfully
            # Get session string
            session_string = client.session.save()
            
            # Get user info
            me = await client.get_me()
            
            # Prepare avatar data
            avatar_data = {
                "id": avatar_id,
                "name": f"Telegram - {me.first_name or 'User'}",
                "platform": "telegram",
                "phone": me.phone if hasattr(me, 'phone') else None,
                "session_string": session_string,
                "status": "active",
                "created_at": self.config_manager.get_avatar(avatar_id) and 
                             self.config_manager.get_avatar(avatar_id).get("created_at") or 
                             datetime.utcnow().isoformat() + "Z",
                "last_used_at": datetime.utcnow().isoformat() + "Z",
                "metadata": {
                    "user_id": me.id,
                    "username": me.username,
                    "first_name": me.first_name,
                    "last_name": me.last_name,
                    "auth_method": "qr"
                }
            }
            
            # Save avatar
            self.config_manager.save_avatar(avatar_data)
            
            # Move to active clients
            self._clients[avatar_id] = client
            del self._pending_auth[avatar_id]
            
            logger.info(f"QR authentication completed for avatar {avatar_id}")
            
            # Log audit event for successful QR auth
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="completed",
                    avatar_id=avatar_id,
                    details={"method": "qr"}
                )
            
            return {
                "status": "authenticated",
                "avatar": avatar_data
            }
            
        except asyncio.TimeoutError:
            logger.warning(f"QR code scan timeout for avatar {avatar_id}")
            
            # Log audit event for timeout
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="timeout",
                    avatar_id=avatar_id,
                    details={"method": "qr"},
                    status="failed",
                    error="QR code scan timed out"
                )
            
            await client.disconnect()
            del self._pending_auth[avatar_id]
            return {
                "status": "timeout",
                "message": "QR code scan timed out"
            }
        except Exception as e:
            logger.error(f"QR authentication failed: {e}")
            
            # Log audit event for failed QR auth
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_auth_event(
                    action="failed",
                    avatar_id=avatar_id,
                    details={"method": "qr", "error": str(e)},
                    status="failed",
                    error=str(e)
                )
            
            await client.disconnect()
            del self._pending_auth[avatar_id]
            raise
    
    async def cancel_qr_auth(self, avatar_id: str) -> bool:
        """Cancel pending QR code authentication.
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            True if cancelled successfully
        """
        pending = self._pending_auth.get(avatar_id)
        if pending and pending.get('method') == 'qr':
            try:
                client = pending['client']
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting during QR cancel: {e}")
            finally:
                del self._pending_auth[avatar_id]
                logger.info(f"QR authentication cancelled for avatar {avatar_id}")
                
                # Log audit event for cancelled auth
                if self.config_manager.history_logger:
                    self.config_manager.history_logger.log_auth_event(
                        action="cancelled",
                        avatar_id=avatar_id,
                        details={"method": "qr"}
                    )
                
                return True
        return False
    
    async def execute(self, avatar_id: str, command: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute a Telegram command.
        
        Args:
            avatar_id: Avatar to use
            command: Command name
            params: Command parameters
            
        Returns:
            List of result items
            
        Raises:
            ValueError: If command is unknown
            Exception: If execution fails
        """
        client = await self._get_client(avatar_id)
        
        if command == "telegram.get_messages":
            return await self._get_messages(client, params)
        elif command == "telegram.get_channel_info":
            return await self._get_channel_info(client, params)
        elif command == "telegram.list_dialogs":
            return await self._list_dialogs(client, params)
        elif command == "telegram.search_messages":
            return await self._search_messages(client, params)
        else:
            raise ValueError(f"Unknown command: {command}")
    
    async def _get_messages(self, client: TelegramClient, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get messages from a channel/group.
        
        Args:
            client: Telegram client
            params: Parameters (channel, limit, since_message_id)
            
        Returns:
            List of message dicts
            
        Raises:
            ValueError: If channel cannot be found or accessed
        """
        channel_id = params["channel"]
        limit = params.get("limit", 100)
        min_id = params.get("since_message_id", 0)
        
        # Try to get channel from dialogs first (for private channels with access hash)
        channel = None
        try:
            # First attempt: search in user's dialogs
            dialogs = await client.get_dialogs()
            for dialog in dialogs:
                # Match by ID (convert both to int for comparison)
                try:
                    dialog_id = int(dialog.id)
                    search_id = int(channel_id)
                    if dialog_id == search_id:
                        channel = dialog.entity
                        logger.debug(f"Found channel {channel_id} in dialogs")
                        break
                except (ValueError, AttributeError):
                    continue
        except Exception as e:
            logger.warning(f"Failed to search dialogs for channel {channel_id}: {e}")
        
        # If not found in dialogs, try direct entity resolution
        if not channel:
            try:
                channel = await client.get_entity(channel_id)
                logger.debug(f"Resolved channel {channel_id} via get_entity")
            except ValueError as e:
                # Provide more helpful error message
                error_msg = str(e)
                if "Cannot find any entity" in error_msg:
                    raise ValueError(
                        f"Cannot access channel {channel_id}. This could mean:\n"
                        f"1. The authenticated user has not joined this private channel\n"
                        f"2. The channel ID format is incorrect (expected: channel ID, username, or invite link)\n"
                        f"3. The channel does not exist or has been deleted\n"
                        f"\nTried searching in user's dialogs but channel not found.\n"
                        f"Please ensure the user has joined the channel in their Telegram app first."
                    ) from e
                else:
                    raise
        
        messages = await client.get_messages(
            channel,
            limit=limit,
            min_id=min_id
        )
        
        # Convert messages to dict and serialize datetime objects
        result = []
        for msg in messages:
            msg_dict = msg.to_dict()
            # Recursively convert datetime objects to ISO strings
            serialized_msg = self._serialize_datetime(msg_dict)
            result.append(serialized_msg)
        
        return result
    
    async def _get_channel_info(self, client: TelegramClient, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get channel/group information.
        
        Args:
            client: Telegram client
            params: Parameters (channel)
            
        Returns:
            List with single channel dict
        """
        channel = await client.get_entity(params["channel"])
        return [channel.to_dict()]
    
    async def _list_dialogs(self, client: TelegramClient, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List user's chats/channels.
        
        Args:
            client: Telegram client
            params: Parameters (limit)
            
        Returns:
            List of dialog dicts
        """
        limit = params.get("limit", 50)
        dialogs = await client.get_dialogs(limit=limit)
        
        result = []
        for dialog in dialogs:
            result.append({
                "id": dialog.id,
                "name": dialog.name,
                "title": dialog.title,
                "entity": dialog.entity.to_dict() if hasattr(dialog.entity, 'to_dict') else {}
            })
        
        return result
    
    async def _search_messages(self, client: TelegramClient, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search messages in a channel/group.
        
        Args:
            client: Telegram client
            params: Parameters (channel, query, limit)
            
        Returns:
            List of message dicts
        """
        channel = await client.get_entity(params["channel"])
        query = params.get("query", "")
        limit = params.get("limit", 50)
        
        messages = await client.get_messages(
            channel,
            search=query,
            limit=limit
        )
        
        return [msg.to_dict() for msg in messages]
    
    async def list_dialogs(self, avatar_id: str, limit: int = 100, download_avatars: bool = True) -> List[Dict[str, Any]]:
        """List all dialogs (chats, channels, groups) for an avatar.
        
        Args:
            avatar_id: Avatar identifier
            limit: Maximum number of dialogs to return
            download_avatars: Whether to download and cache avatar pictures
            
        Returns:
            List of dialog dicts with id, name, type, etc.
        """
        from pathlib import Path
        
        client = await self._get_client(avatar_id)
        dialogs = await client.get_dialogs(limit=limit)
        
        # Log audit event
        if self.config_manager.history_logger:
            self.config_manager.history_logger.log_system_event(
                action="listed",
                resource_type="dialogs",
                resource_id=avatar_id,
                details={"limit": limit, "count": len(dialogs)}
            )
        
        # Ensure cache directory exists
        cache_dir = Path("data/.cache/avatars")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        result = []
        for dialog in dialogs:
            # Determine dialog type
            is_group = dialog.is_group
            is_channel = dialog.is_channel
            is_user = dialog.is_user
            
            # Download avatar if requested
            avatar_cached = False
            if download_avatars:
                try:
                    avatar_path = cache_dir / f"{dialog.id}.png"
                    # Download profile photo
                    photo_path = await client.download_profile_photo(
                        dialog.entity,
                        file=str(avatar_path)
                    )
                    avatar_cached = photo_path is not None
                except Exception as e:
                    logger.debug(f"Could not download avatar for {dialog.id}: {e}")
                    avatar_cached = False
            
            result.append({
                "id": dialog.id,
                "name": dialog.name or dialog.title or "Unknown",
                "title": dialog.title,
                "is_group": is_group,
                "is_channel": is_channel,
                "is_user": is_user,
                "username": getattr(dialog.entity, 'username', None),
                "participants_count": getattr(dialog.entity, 'participants_count', None),
                "avatar_cached": avatar_cached
            })
        
        return result
    
    async def test_connection(self, avatar_id: str) -> bool:
        """Test if avatar connection is working.
        
        Args:
            avatar_id: Avatar to test
            
        Returns:
            True if connected and authorized
        """
        try:
            client = await self._get_client(avatar_id)
            me = await client.get_me()
            logger.info(f"Connection test successful for {me.first_name}")
            
            # Log audit event
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_system_event(
                    action="tested",
                    resource_type="connection",
                    resource_id=avatar_id,
                    details={"result": "success"}
                )
            
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            
            # Log audit event for failure
            if self.config_manager.history_logger:
                self.config_manager.history_logger.log_system_event(
                    action="tested",
                    resource_type="connection",
                    resource_id=avatar_id,
                    details={"result": "failed", "error": str(e)},
                    status="failed",
                    error=str(e)
                )
            
            return False
    
    async def disconnect_all(self):
        """Disconnect all Telegram clients."""
        # Disconnect active clients
        for avatar_id, client in list(self._clients.items()):
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client {avatar_id}: {e}")
        self._clients.clear()
        
        # Disconnect pending auth clients
        for avatar_id, client in list(self._pending_auth.items()):
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting pending auth {avatar_id}: {e}")
        self._pending_auth.clear()


# Import datetime for timestamps
from datetime import datetime
