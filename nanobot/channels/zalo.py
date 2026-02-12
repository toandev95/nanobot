"""Zalo channel implementation using zca-js bridge."""

import asyncio
import json
from pathlib import Path
from typing import Any

import aiohttp
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

    def __init__(
        self,
        config: ZaloConfig,
        bus: MessageBus,
        groq_api_key: str = "",
        groq_api_base: str | None = None,
    ):
        super().__init__(config, bus)
        self.config: ZaloConfig = config
        self.groq_api_key = groq_api_key
        self.groq_api_base = groq_api_base
        self._ws = None
        self._connected = False
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id -> typing loop task

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

        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Zalo."""
        if not self._ws or not self._connected:
            logger.warning("Zalo bridge not connected")
            return

        # Stop typing indicator for this chat
        self._stop_typing(msg.chat_id)

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
            content_raw = data.get("content", "")

            # Extract metadata
            metadata: dict[str, Any] = {
                "message_id": data.get("messageId"),
                "timestamp": data.get("timestamp"),
                "is_group": data.get("isGroup", False),
            }

            media_paths = []
            if isinstance(content_raw, str):
                content = content_raw
            elif isinstance(content_raw, dict) and content_raw.get("type") == "attachment":
                content, media_path = await self._handle_attachment_content(content_raw)
                if media_path:
                    media_paths.append(media_path)
            else:
                content = "[empty message]"

            # Start typing indicator before processing
            self._start_typing(chat_id)

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                media=media_paths,
                metadata=metadata,
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

    async def _handle_attachment_content(self, content: dict[str, Any]) -> tuple[str, str | None]:
        """Download attachment and return content description and file path."""
        href = content.get("href", "")

        logger.info(f"Received attachment: {href}")

        if not href:
            return "[attachment: no URL]", None

        # Download the file
        try:
            # Create media directory
            media_dir = Path.home() / ".nanobot" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique filename
            import hashlib

            file_hash = hashlib.md5(href.encode()).hexdigest()[:16]

            # Download file first to get content type
            async with aiohttp.ClientSession() as session:
                async with session.get(href) as response:
                    if response.status == 200:
                        content_data = await response.read()
                        content_type = response.headers.get("Content-Type", "").lower()

                        # Get extension from MIME type
                        ext = self._get_extension_from_mime(content_type)
                        file_path = media_dir / f"zalo_{file_hash}{ext}"

                        file_path.write_bytes(content_data)
                        logger.info(f"Downloaded file to {file_path} (type: {content_type})")

                        # Check if it's audio based on MIME type
                        is_audio = content_type.startswith("audio/") or "audio" in content_type

                        # Handle audio transcription
                        if is_audio:
                            try:
                                from nanobot.providers.transcription import (
                                    GroqTranscriptionProvider,
                                )

                                transcriber = GroqTranscriptionProvider(
                                    api_key=self.groq_api_key, api_base=self.groq_api_base
                                )
                                transcription = await transcriber.transcribe(file_path)
                                if transcription:
                                    logger.info(f"Transcribed audio: {transcription[:50]}...")
                                    return f"[transcription: {transcription}]", str(file_path)
                            except Exception as e:
                                logger.error(f"Failed to transcribe audio: {e}")

                        # Determine file type for display
                        if content_type.startswith("image/"):
                            file_type = "image"
                        elif content_type.startswith("video/"):
                            file_type = "video"
                        elif is_audio:
                            file_type = "audio"
                        else:
                            file_type = "file"

                        return f"[{file_type}: {file_path}]", str(file_path)
                    else:
                        logger.error(f"Failed to download file: HTTP {response.status}")
                        return "[attachment: download failed]", None

        except Exception as e:
            logger.error(f"Error downloading attachment: {e}")
            return f"[attachment: {href}]", None

    def _get_extension_from_mime(self, mime_type: str) -> str:
        """Get file extension from MIME type."""
        mime_map = {
            # Images
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/svg+xml": ".svg",
            "image/tiff": ".tiff",
            "image/x-icon": ".ico",
            # Audio
            "audio/ogg": ".ogg",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/mp4": ".m4a",
            "audio/wav": ".wav",
            "audio/wave": ".wav",
            "audio/x-wav": ".wav",
            "audio/aac": ".aac",
            "audio/webm": ".weba",
            "audio/flac": ".flac",
            "audio/x-m4a": ".m4a",
            # Video
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/avi": ".avi",
            "video/x-msvideo": ".avi",
            "video/mpeg": ".mpeg",
            "video/quicktime": ".mov",
            "video/x-matroska": ".mkv",
            "video/3gpp": ".3gp",
            "video/x-flv": ".flv",
            # Documents
            "application/pdf": ".pdf",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.ms-excel": ".xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/vnd.ms-powerpoint": ".ppt",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "text/plain": ".txt",
            "text/csv": ".csv",
            "text/html": ".html",
            "application/json": ".json",
            "application/xml": ".xml",
            "text/xml": ".xml",
            # Archives
            "application/zip": ".zip",
            "application/x-zip-compressed": ".zip",
            "application/x-rar-compressed": ".rar",
            "application/x-7z-compressed": ".7z",
            "application/x-tar": ".tar",
            "application/gzip": ".gz",
            # Other
            "application/octet-stream": ".bin",
        }
        # Extract main MIME type (before semicolon)
        mime_type = mime_type.split(";")[0].strip()
        return mime_map.get(mime_type, "")

    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' event until cancelled."""
        if not self._ws or not self._connected:
            return

        try:
            while self._ws and self._connected:
                payload = {"type": "typing", "to": chat_id}
                await self._ws.send(json.dumps(payload))
                await asyncio.sleep(4)  # Send typing every 4 seconds
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Typing indicator stopped for {chat_id}: {e}")
