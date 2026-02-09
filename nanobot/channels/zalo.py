"""Zalo channel implementation using zca-js bridge."""

import asyncio
import json
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import ZaloConfig


class ZaloChannel(BaseChannel):
    """
    Zalo channel that connects to a Node.js bridge.

    The bridge uses zca-js to handle the Zalo protocol.
    Communication between Python and Node.js is via WebSocket.
    """

    name = "zalo"

    def __init__(self, config: ZaloConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: ZaloConfig = config
        self._ws = None
        self._connected = False

    async def start(self) -> None:
        """Start the Zalo channel by connecting to the bridge."""
        import websockets

        bridge_url = self.config.bridge_url

        logger.info(f"Connecting to Zalo bridge at {bridge_url}...")

        self._running = True

        while self._running:
            try:
                async with websockets.connect(bridge_url) as ws:
                    self._ws = ws
                    self._connected = True
                    logger.info("Connected to Zalo bridge")

                    # Send login credentials to bridge
                    await self._send_login()

                    # Listen for messages
                    async for message in ws:
                        try:
                            await self._handle_bridge_message(message)
                        except Exception as e:
                            logger.error(f"Error handling bridge message: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                logger.warning(f"Zalo bridge connection error: {e}")

                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the Zalo channel."""
        self._running = False
        self._connected = False

        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Zalo."""
        if not self._ws or not self._connected:
            logger.warning("Zalo bridge not connected")
            return

        try:
            payload = {"type": "send", "to": msg.chat_id, "text": msg.content}
            await self._ws.send(json.dumps(payload))
        except Exception as e:
            logger.error(f"Error sending Zalo message: {e}")

    async def _send_login(self) -> None:
        """Send login credentials to the bridge."""
        if not self._ws:
            return

        try:
            # Parse cookie if it's a JSON string
            cookie = self.config.cookie
            if isinstance(cookie, str) and cookie.strip().startswith("["):
                cookie = json.loads(cookie)

            payload = {
                "type": "login",
                "cookie": cookie,
                "imei": self.config.imei,
                "userAgent": self.config.user_agent,
            }
            await self._ws.send(json.dumps(payload))
            logger.info("Sent login credentials to Zalo bridge")
        except Exception as e:
            logger.error(f"Error sending login credentials: {e}")

    async def _handle_bridge_message(self, raw: str) -> None:
        """Handle a message from the bridge."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from bridge: {raw[:100]}")
            return

        msg_type = data.get("type")

        if msg_type == "message":
            # Incoming message from Zalo
            sender_id = data.get("senderId", "")
            chat_id = data.get("threadId", "")
            content = data.get("content", "")

            # Extract metadata
            metadata: dict[str, Any] = {
                "message_id": data.get("messageId"),
                "timestamp": data.get("timestamp"),
                "is_group": data.get("isGroup", False),
            }

            await self._handle_message(
                sender_id=sender_id, chat_id=chat_id, content=content, metadata=metadata
            )

        elif msg_type == "status":
            # Connection status update
            status = data.get("status")
            logger.info(f"Zalo status: {status}")

            if status == "connected":
                self._connected = True
            elif status == "disconnected":
                self._connected = False

        elif msg_type == "login":
            # Login result
            success = data.get("success")
            if success:
                logger.info("Successfully logged in to Zalo")
            else:
                error = data.get("error", "Unknown error")
                logger.error(f"Failed to login to Zalo: {error}")

        elif msg_type == "error":
            logger.error(f"Zalo bridge error: {data.get('error')}")
