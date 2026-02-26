"""Browser platform handler using NoDriver (undetected-chromedriver).

Provides browser-based data collection for platforms like X (Twitter).
Login flows are configured on the backend and executed generically by this handler.
Session persistence is achieved via Chrome profile directories.
"""

import asyncio
import json
import logging
import base64
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

import nodriver as uc
from nodriver import cdp

logger = logging.getLogger(__name__)

# Platform-specific CSRF cookies that become stale between browser restarts.
# Clearing these before navigation forces the server to issue fresh tokens.
PLATFORM_CSRF_COOKIES: Dict[str, List[Dict[str, str]]] = {
    "x": [
        {"name": "ct0", "domain": ".x.com"},
        {"name": "ct0", "domain": ".twitter.com"},
    ],
    "twitter": [
        {"name": "ct0", "domain": ".x.com"},
        {"name": "ct0", "domain": ".twitter.com"},
    ],
}


class BrowserSession:
    """Manages a single NoDriver browser instance with a persistent profile."""

    def __init__(
        self,
        avatar_id: str,
        platform: str,
        profile_path: Path,
        login_flow: Dict[str, Any]
    ):
        self.avatar_id = avatar_id
        self.platform = platform
        self.profile_path = profile_path
        self.login_flow = login_flow

        self._browser = None
        self._tab = None

    async def launch(self):
        """Launch browser with persistent profile directory."""
        self.profile_path.mkdir(parents=True, exist_ok=True)

        headless = os.environ.get("BROWSER_HEADLESS", "true").lower() == "true"
        headless = False
        self._browser = await uc.start(
            user_data_dir=str(self.profile_path),
            headless=headless,
        )
        self._tab = await self._browser.get("about:blank")
        logger.info(f"Browser launched for avatar {self.avatar_id} (headless={headless})")

    def is_alive(self) -> bool:
        """Check if browser process is still running."""
        try:
            return (
                self._browser is not None
                and self._tab is not None
                and self._browser._process is not None
                and self._browser._process.returncode is None
            )
        except Exception:
            return False

    async def check_login_state(self) -> bool:
        """Navigate to the platform and check if session cookies are valid.

        Returns:
            True if the user appears to be logged in.
        """
        login_url = self.login_flow["login_url"]
        success_pattern = self.login_flow["success_url_pattern"]

        try:
            self._tab = await self._browser.get(login_url)
            await asyncio.sleep(5)  # Wait for redirects

            current_url = str(self._tab.target.url).lower()
            is_logged_in = success_pattern.lower() in current_url
            logger.info(
                f"Login state check for {self.avatar_id}: "
                f"{'logged in' if is_logged_in else 'not logged in'} "
                f"(url={current_url})"
            )
            return is_logged_in
        except Exception as e:
            logger.error(f"Login state check failed for {self.avatar_id}: {e}")
            return False

    async def _clear_csrf_cookies(self):
        """Delete stale CSRF cookies for this platform via CDP.

        Forces the server to issue fresh CSRF tokens on the next navigation.
        Necessary when resuming from a persistent Chrome profile where
        short-lived CSRF cookies have expired while auth cookies remain valid.
        """
        csrf_entries = PLATFORM_CSRF_COOKIES.get(self.platform, [])
        for entry in csrf_entries:
            try:
                await self._tab.send(
                    cdp.network.delete_cookies(
                        name=entry["name"],
                        domain=entry["domain"],
                    )
                )
            except Exception as e:
                logger.debug(
                    f"Could not clear CSRF cookie {entry['name']} "
                    f"for avatar {self.avatar_id}: {e}"
                )
        if csrf_entries:
            logger.debug(f"Cleared CSRF cookies for avatar {self.avatar_id}")

    async def execute_login(self, credentials: Dict[str, str]) -> Dict[str, Any]:
        """Execute the login flow using backend-provided steps.

        Args:
            credentials: Dict mapping credential_field names to values.

        Returns:
            Dict with 'status' key: 'success', 'failed', or 'challenge_required'.
        """
        login_url = self.login_flow["login_url"]
        success_pattern = self.login_flow["success_url_pattern"]
        steps = self.login_flow["steps"]

        # Navigate to login page
        self._tab = await self._browser.get(login_url)
        await asyncio.sleep(3)

        for step in steps:
            step_type = step["type"]
            step_id = step.get("id", "unknown")

            try:
                if step_type == "wait":
                    await asyncio.sleep(step.get("wait_seconds", 1))

                elif step_type == "input":
                    element = await self._find_element(
                        step.get("selector"),
                        step.get("selector_fallback")
                    )
                    if not element:
                        if step.get("optional"):
                            logger.debug(f"Optional input step {step_id} skipped (element not found)")
                            continue
                        return {"status": "failed", "error": f"Element not found for step {step_id}"}

                    cred_field = step.get("credential_field")
                    value = credentials.get(cred_field, "")
                    await element.send_keys(value)

                    if step.get("press_enter"):
                        await asyncio.sleep(0.3)
                        await self._press_enter()

                elif step_type == "click":
                    find_text = step.get("find_text")
                    selector = step.get("selector")

                    element = None
                    if find_text:
                        try:
                            element = await self._tab.find(find_text, best_match=True)
                        except Exception:
                            pass
                    if not element and selector:
                        element = await self._find_element(selector, step.get("selector_fallback"))

                    if not element:
                        if step.get("optional"):
                            logger.debug(f"Optional click step {step_id} skipped (element not found)")
                            continue
                        return {"status": "failed", "error": f"Button not found for step {step_id}"}

                    await element.click()

                elif step_type == "check_challenge":
                    challenge = step.get("challenge", {})
                    challenge_sel = challenge.get("selector")
                    if challenge_sel:
                        try:
                            element = await self._tab.select(challenge_sel)
                            if element:
                                return {
                                    "status": "challenge_required",
                                    "challenge_prompt": challenge.get("prompt", "Verification required"),
                                    "challenge_selector": challenge_sel,
                                    "submit_text": challenge.get("submit_text"),
                                    "step_id": step_id,
                                }
                        except Exception:
                            pass  # No challenge, continue

                # Post-step delay
                wait = step.get("wait_seconds", 0)
                if wait:
                    await asyncio.sleep(wait)

            except Exception as e:
                if step.get("optional"):
                    logger.warning(f"Optional step {step_id} failed: {e}")
                    continue
                return {"status": "failed", "error": f"Step {step_id} failed: {str(e)}"}

        # Check success
        await asyncio.sleep(2)
        current_url = str(self._tab.target.url).lower()
        if success_pattern.lower() in current_url:
            logger.info(f"Login successful for avatar {self.avatar_id}")
            return {"status": "success"}
        else:
            logger.warning(
                f"Login may have failed for {self.avatar_id}. "
                f"Current URL: {self._tab.target.url}"
            )
            return {
                "status": "failed",
                "error": f"Login may have failed. Current URL: {self._tab.target.url}"
            }

    async def extract_platform_identity(self) -> Optional[Dict[str, str]]:
        """Extract platform-native user ID after a successful login.

        Returns:
            Dict with 'platform_user_id' and optionally 'handle', or None.
        """
        try:
            if self.platform in ("x", "twitter"):
                return await self._extract_twitter_identity()
        except Exception as e:
            logger.warning(f"Failed to extract platform identity for {self.platform}: {e}")
        return None

    async def _extract_twitter_identity(self) -> Optional[Dict[str, str]]:
        """Extract numeric user ID from X's twid cookie."""
        import urllib.parse
        cookies = await self._tab.send(cdp.network.get_cookies())
        for cookie in cookies:
            if cookie.name == "twid":
                value = urllib.parse.unquote(cookie.value)
                if value.startswith("u="):
                    user_id = value[2:]
                    logger.info(f"Extracted X user ID: {user_id}")
                    return {"platform_user_id": user_id}
        logger.warning("twid cookie not found after X login")
        return None

    async def submit_challenge_response(
        self,
        response: str,
        challenge_selector: str,
        submit_text: Optional[str] = None,
        submit_enter: bool = False,
    ) -> Dict[str, Any]:
        """Submit a challenge response (2FA code, phone number, etc.).

        Args:
            response: The user's response text.
            challenge_selector: CSS selector for the challenge input.
            submit_text: Text to find for the submit button.
            submit_enter: If True, press Enter instead of finding a submit button.

        Returns:
            Dict with 'status' key.
        """
        success_pattern = self.login_flow["success_url_pattern"]

        try:
            element = await self._tab.select(challenge_selector)
            if not element:
                return {"status": "failed", "error": "Challenge input not found"}

            await element.send_keys(response)
            await asyncio.sleep(0.5)

            if submit_enter:
                await self._press_enter()
            elif submit_text:
                try:
                    btn = await self._tab.find(submit_text, best_match=True)
                    if btn:
                        await btn.click()
                except Exception:
                    # Try generic submit button
                    try:
                        btn = await self._tab.select("button[type='submit']")
                        if btn:
                            await btn.click()
                    except Exception:
                        pass

            await asyncio.sleep(5)

            current_url = str(self._tab.target.url).lower()
            if success_pattern.lower() in current_url:
                return {"status": "success"}
            else:
                return {
                    "status": "failed",
                    "error": f"Challenge may have failed. URL: {self._tab.target.url}"
                }

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    async def capture_xhr(
        self,
        url: str,
        targets: List[str],
        wait_seconds: int = 10,
        max_captures: int = 5,
        scroll_count: int = 0,
        scroll_distance: int = 800,
    ) -> List[Dict[str, Any]]:
        """Navigate to URL and capture XHR responses matching targets.

        Args:
            url: URL to navigate to.
            targets: URL substrings to match against XHR responses.
            wait_seconds: How long to wait for captures.
            max_captures: Maximum number of responses to capture.
            scroll_count: Number of times to scroll down during capture.
                Scrolling triggers infinite-scroll pages to load more content.
                0 = no scrolling (passive wait only).
            scroll_distance: Pixels to scroll per step (default 800).

        Returns:
            List of captured response dicts.
        """
        captures = []
        capture_event = asyncio.Event()
        matched_requests = {}  # request_id -> {url, target, status_code}

        # Enable network monitoring
        await self._tab.send(cdp.network.enable())

        # Clear stale CSRF cookies to force fresh tokens on navigation
        await self._clear_csrf_cookies()

        async def on_response(event: cdp.network.ResponseReceived, tab):
            """Match response URLs and store request IDs for body retrieval."""
            response_url = event.response.url
            matched = next((t for t in targets if t in response_url), None)
            if not matched:
                return
            if len(captures) >= max_captures:
                return
            matched_requests[event.request_id] = {
                "url": response_url,
                "target": matched,
                "status_code": event.response.status,
            }

        async def on_loading_finished(event: cdp.network.LoadingFinished, tab):
            """Fetch response body once fully downloaded."""
            nonlocal captures
            meta = matched_requests.pop(event.request_id, None)
            if not meta:
                return
            if len(captures) >= max_captures:
                return
            try:
                body, base64_encoded = await tab.send(
                    cdp.network.get_response_body(event.request_id)
                )
                if base64_encoded:
                    body = base64.b64decode(body).decode("utf-8")

                data = json.loads(body)

                # Detect CSRF errors for observability
                if isinstance(data, dict) and "errors" in data:
                    error_codes = [
                        e.get("code") for e in data.get("errors", [])
                        if isinstance(e, dict)
                    ]
                    if 353 in error_codes:
                        logger.warning(
                            f"CSRF error (353) in XHR for {meta['target']}, "
                            f"avatar {self.avatar_id}"
                        )

                captures.append({
                    "url": meta["url"],
                    "target": meta["target"],
                    "body": data,
                    "captured_at": datetime.utcnow().isoformat() + "Z",
                    "status_code": meta["status_code"],
                })
                logger.info(
                    f"Captured XHR: {meta['target']} ({len(captures)}/{max_captures}) "
                    f"for avatar {self.avatar_id}"
                )

                if len(captures) >= max_captures:
                    capture_event.set()

            except Exception as e:
                logger.warning(f"Failed to capture XHR body for {meta['target']}: {e}")

        # Register handlers on the current tab
        self._tab.add_handler(cdp.network.ResponseReceived, on_response)
        self._tab.add_handler(cdp.network.LoadingFinished, on_loading_finished)

        # Navigate using the current tab (not browser.get which creates a new tab)
        try:
            await self._tab.get(url)
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return captures

        # Wait for captures, scrolling periodically to trigger infinite-scroll loading
        if scroll_count > 0:
            interval = wait_seconds / (scroll_count + 1)
            for i in range(scroll_count + 1):
                try:
                    await asyncio.wait_for(capture_event.wait(), timeout=interval)
                    break  # max_captures reached
                except asyncio.TimeoutError:
                    if i < scroll_count:
                        await self._tab.evaluate(
                            f"window.scrollBy(0, {scroll_distance})", await_promise=False
                        )
                        logger.debug(
                            f"Scroll {i + 1}/{scroll_count} "
                            f"for avatar {self.avatar_id}"
                        )
        else:
            try:
                await asyncio.wait_for(capture_event.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                pass

        if len(captures) < max_captures:
            logger.info(
                f"XHR capture finished after {wait_seconds}s, "
                f"got {len(captures)} captures for avatar {self.avatar_id}"
            )

        return captures

    async def _find_element(self, selector: str, fallback: Optional[str] = None):
        """Find element by CSS selector with optional fallback."""
        if selector:
            try:
                element = await self._tab.select(selector)
                if element:
                    return element
            except Exception:
                pass

        if fallback:
            try:
                element = await self._tab.select(fallback)
                if element:
                    return element
            except Exception:
                pass

        return None

    async def _press_enter(self):
        """Dispatch Enter key via CDP (language-independent form submission)."""
        await self._tab.send(cdp.input_.dispatch_key_event(
            type_="rawKeyDown", key="Enter", code="Enter",
            windows_virtual_key_code=13, native_virtual_key_code=13,
            text="\r",
        ))
        await self._tab.send(cdp.input_.dispatch_key_event(
            type_="char", key="Enter", code="Enter",
            windows_virtual_key_code=13, native_virtual_key_code=13,
            text="\r",
        ))
        await self._tab.send(cdp.input_.dispatch_key_event(
            type_="keyUp", key="Enter", code="Enter",
            windows_virtual_key_code=13, native_virtual_key_code=13,
        ))

    async def close(self):
        """Close browser instance. Profile directory persists on disk."""
        if self._browser:
            try:
                self._browser.stop()
            except Exception as e:
                logger.warning(f"Error stopping browser for {self.avatar_id}: {e}")
            self._browser = None
            self._tab = None
            logger.info(f"Browser closed for avatar {self.avatar_id}")


class BrowserHandler:
    """Handles browser-based platform operations using NoDriver.

    Manages multiple browser sessions (one per avatar), login flows
    from the backend, and XHR capture jobs.
    """

    def __init__(self, config_manager):
        self.config_manager = config_manager

        # Active browser sessions: {avatar_id: BrowserSession}
        self._sessions: Dict[str, BrowserSession] = {}

        # Login flows from backend: {platform: flow_dict}
        self._login_flows: Dict[str, Dict[str, Any]] = {}

        # Pending interactive auth: {avatar_id: {session, challenge}}
        self._pending_auth: Dict[str, Dict[str, Any]] = {}

        # Base directory for Chrome profiles
        data_dir = getattr(config_manager, 'data_dir', 'data')
        self._profiles_dir = Path(data_dir) / "browser_profiles"
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Browser handler initialized")

    def update_login_flows(self, flows: List[Dict[str, Any]]):
        """Update login flow configs from backend verify response."""
        self._login_flows = {}
        for f in flows:
            # Accept both dict and pydantic model-like objects
            if hasattr(f, 'model_dump'):
                f = f.model_dump()
            elif hasattr(f, 'dict'):
                f = f.dict()
            self._login_flows[f['platform']] = f
        logger.info(f"Updated login flows for platforms: {list(self._login_flows.keys())}")

    def get_available_platforms(self) -> List[Dict[str, Any]]:
        """List available browser platforms from loaded login flows."""
        platforms = []
        for platform, flow in self._login_flows.items():
            platforms.append({
                "platform": platform,
                "display_name": flow.get("display_name", platform),
                "credential_fields": flow.get("credential_fields", ["username", "password"]),
            })
        return platforms

    # --- Session Management ---

    async def _get_session(self, avatar_id: str) -> BrowserSession:
        """Get or create browser session for avatar.

        Launches browser with avatar's profile directory.
        Checks login state. Re-logs in if needed.
        """
        # Don't launch a new browser if a challenge is pending
        if avatar_id in self._pending_auth:
            raise Exception(
                f"Login challenge pending for avatar {avatar_id}. "
                f"Resolve via /avatars/browser/auth/challenge before retrying."
            )

        if avatar_id in self._sessions:
            session = self._sessions[avatar_id]
            if session.is_alive():
                return session
            else:
                # Browser died, clean up
                await session.close()
                del self._sessions[avatar_id]

        avatar = self.config_manager.get_avatar(avatar_id)
        if not avatar:
            raise ValueError(f"Avatar not found: {avatar_id}")

        platform = avatar.get("platform")
        if platform not in self._login_flows:
            raise ValueError(f"No login flow configured for platform: {platform}")

        # Get or create profile directory
        profile_dir_name = avatar.get("metadata", {}).get("profile_dir")
        if not profile_dir_name:
            profile_dir_name = f"{platform}_{avatar_id}"
            avatar.setdefault("metadata", {})["profile_dir"] = profile_dir_name
            self.config_manager.save_avatar(avatar)

        profile_path = self._profiles_dir / profile_dir_name

        # Launch browser with profile
        session = BrowserSession(
            avatar_id=avatar_id,
            platform=platform,
            profile_path=profile_path,
            login_flow=self._login_flows[platform],
        )
        await session.launch()

        # Check if we're logged in
        is_logged_in = await session.check_login_state()

        if is_logged_in:
            # Restore status to active (may have been auth_required)
            self.config_manager.update_avatar_status(avatar_id, "active")
        else:
            credentials = avatar.get("credentials", {})
            if not credentials:
                fail_status = self.config_manager.get_auth_failure_status(avatar_id)
                self.config_manager.update_avatar_status(avatar_id, fail_status)
                await session.close()
                raise Exception(
                    f"Avatar {avatar_id} has no credentials and is not logged in"
                )

            # Browser may have crashed during login check; relaunch if dead
            if not session.is_alive():
                logger.warning(f"Browser died after login check for {avatar_id}, relaunching")
                await session.close()
                await session.launch()

            login_result = await session.execute_login(credentials)

            if login_result.get("status") == "challenge_required":
                self._pending_auth[avatar_id] = {
                    "session": session,
                    "challenge": login_result,
                }
                fail_status = self.config_manager.get_auth_failure_status(avatar_id)
                self.config_manager.update_avatar_status(avatar_id, fail_status)
                raise Exception(
                    f"Login challenge required: {login_result.get('challenge_prompt')}"
                )

            if login_result.get("status") != "success":
                await session.close()
                fail_status = self.config_manager.get_auth_failure_status(avatar_id)
                self.config_manager.update_avatar_status(avatar_id, fail_status)
                raise Exception(f"Login failed: {login_result.get('error', 'unknown')}")

            self.config_manager.update_avatar_status(avatar_id, "active")

        self._sessions[avatar_id] = session
        return session

    # --- Job Execution ---

    async def execute(
        self, avatar_id: str, command: str, params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute a browser command.

        Commands:
            browser.xhr_capture -- Navigate and capture XHR responses
        """
        session = await self._get_session(avatar_id)

        if command == "browser.xhr_capture":
            return await self._xhr_capture(session, params)
        else:
            raise ValueError(f"Unknown browser command: {command}")

    async def _xhr_capture(
        self, session: BrowserSession, params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Navigate to URL and capture matching XHR responses."""
        navigate_url = params.get("navigate_url")
        xhr_targets = params.get("xhr_targets", [])
        wait_seconds = params.get("wait_seconds", 10)
        max_captures = params.get("max_captures", 5)
        scroll_count = params.get("scroll_count", 0)
        scroll_distance = params.get("scroll_distance", 800)

        if not navigate_url or not xhr_targets:
            raise ValueError("navigate_url and xhr_targets are required")

        return await session.capture_xhr(
            url=navigate_url,
            targets=xhr_targets,
            wait_seconds=wait_seconds,
            max_captures=max_captures,
            scroll_count=scroll_count,
            scroll_distance=scroll_distance,
        )

    # --- Auth Flow ---

    async def start_auth(
        self,
        avatar_id: str,
        platform: str,
        credentials: Dict[str, str]
    ) -> Dict[str, Any]:
        """Start browser authentication for a new avatar.

        Args:
            avatar_id: Unique avatar identifier.
            platform: Platform key (e.g., 'x').
            credentials: Dict with credential values (e.g., username, password).

        Returns:
            Auth result dict.
        """
        if platform not in self._login_flows:
            raise ValueError(f"No login flow for platform: {platform}")

        flow = self._login_flows[platform]
        profile_dir_name = f"{platform}_{avatar_id}"
        profile_path = self._profiles_dir / profile_dir_name

        session = BrowserSession(
            avatar_id=avatar_id,
            platform=platform,
            profile_path=profile_path,
            login_flow=flow,
        )
        await session.launch()

        login_result = await session.execute_login(credentials)

        if login_result.get("status") == "challenge_required":
            # Persist avatar now so challenge resolution can update it later
            avatar_data = {
                "id": avatar_id,
                "handle": credentials.get("username", ""),
                "name": f"{flow.get('display_name', platform)} - {credentials.get('username', 'User')}",
                "platform": platform,
                "credentials": credentials,
                "status": "auth_required",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "last_used_at": datetime.utcnow().isoformat() + "Z",
                "metadata": {
                    "username": credentials.get("username"),
                    "auth_method": "browser_login",
                    "profile_dir": profile_dir_name,
                },
            }
            self.config_manager.save_avatar(avatar_data)
            self._pending_auth[avatar_id] = {
                "session": session,
                "challenge": login_result,
                "credentials": credentials,
                "profile_dir_name": profile_dir_name,
            }
            return login_result

        if login_result.get("status") == "success":
            # Extract platform-native user ID for stable avatar_id
            handle = credentials.get("username", "")
            identity = await session.extract_platform_identity()
            if identity and identity.get("platform_user_id"):
                stable_avatar_id = f"{platform}_{identity['platform_user_id']}"
            else:
                # Fallback to username-based ID
                stable_avatar_id = f"{platform}_{handle}"

            # Save avatar with stable ID
            avatar_data = {
                "id": stable_avatar_id,
                "handle": handle,
                "name": f"{flow.get('display_name', platform)} - {handle or 'User'}",
                "platform": platform,
                "credentials": credentials,
                "status": "active",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "last_used_at": datetime.utcnow().isoformat() + "Z",
                "metadata": {
                    "username": handle,
                    "platform_user_id": identity.get("platform_user_id") if identity else None,
                    "auth_method": "browser_login",
                    "profile_dir": profile_dir_name,
                },
            }
            self.config_manager.save_avatar(avatar_data)
            self._sessions[stable_avatar_id] = session
            return {"status": "authenticated", "avatar_id": stable_avatar_id}

        await session.close()
        return login_result

    async def submit_challenge(
        self,
        avatar_id: str,
        challenge_response: str
    ) -> Dict[str, Any]:
        """Submit response to a login challenge (2FA, phone verification).

        Args:
            avatar_id: Avatar with pending challenge.
            challenge_response: The user's response text.

        Returns:
            Result dict with status.
        """
        pending = self._pending_auth.get(avatar_id)
        if not pending:
            raise ValueError("No pending challenge for this avatar")

        session = pending["session"]
        challenge = pending["challenge"]

        result = await session.submit_challenge_response(
            response=challenge_response,
            challenge_selector=challenge.get("challenge_selector", ""),
            submit_text=challenge.get("submit_text"),
            submit_enter=challenge.get("submit_enter", False),
        )

        if result.get("status") == "success":
            credentials = pending.get("credentials", {})
            profile_dir_name = pending.get("profile_dir_name")
            handle = credentials.get("username", "")

            # Extract platform-native user ID for stable avatar_id
            identity = await session.extract_platform_identity()
            if identity and identity.get("platform_user_id"):
                stable_avatar_id = f"{session.platform}_{identity['platform_user_id']}"
            else:
                stable_avatar_id = f"{session.platform}_{handle}"

            # Update avatar with stable ID
            avatar = self.config_manager.get_avatar(avatar_id) or {}
            avatar["id"] = stable_avatar_id
            avatar["handle"] = handle
            avatar["status"] = "active"
            avatar["last_used_at"] = datetime.utcnow().isoformat() + "Z"
            avatar.setdefault("metadata", {})["platform_user_id"] = (
                identity.get("platform_user_id") if identity else None
            )
            self.config_manager.save_avatar(avatar)

            del self._pending_auth[avatar_id]
            self._sessions[stable_avatar_id] = session
            result["avatar_id"] = stable_avatar_id

        return result

    def get_pending_challenge(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """Get pending challenge info for an avatar."""
        pending = self._pending_auth.get(avatar_id)
        if pending:
            return pending["challenge"]
        return None

    # --- Cleanup ---

    async def disconnect_all(self):
        """Close all browser sessions."""
        for avatar_id, session in list(self._sessions.items()):
            try:
                await session.close()
            except Exception as e:
                logger.error(f"Error closing browser session {avatar_id}: {e}")
        self._sessions.clear()

        for avatar_id, pending in list(self._pending_auth.items()):
            try:
                await pending["session"].close()
            except Exception as e:
                logger.error(f"Error closing pending auth session {avatar_id}: {e}")
        self._pending_auth.clear()

        logger.info("All browser sessions disconnected")
