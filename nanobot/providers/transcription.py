"""Voice transcription provider using Groq."""

import io
import os
from pathlib import Path

import requests
from loguru import logger
from pydub import AudioSegment


class GroqTranscriptionProvider:
    """
    Voice transcription provider using Groq's Whisper API.

    Groq offers extremely fast transcription with a generous free tier.
    """

    def __init__(self, api_key: str | None = None, api_base: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = f"{api_base or 'https://api.groq.com/openai/v1'}/audio/transcriptions"

    async def transcribe(self, file_path: str | Path) -> str:
        """
        Transcribe an audio file using Groq.

        Args:
            file_path: Path to the audio file.

        Returns:
            Transcribed text.
        """
        if not self.api_key:
            logger.warning("Groq API key not configured for transcription")
            return ""

        path = Path(file_path)
        if not path.exists():
            logger.error(f"Audio file not found: {file_path}")
            return ""

        try:
            audio = AudioSegment.from_file(str(path))
            byte_stream = io.BytesIO()
            audio.export(byte_stream, format="wav")
            byte_stream.seek(0)

            response = requests.request(
                "POST",
                self.api_url,
                data={"model": "whisper-1"},
                files=[("file", ("audio.wav", byte_stream, "audio/wav"))],
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("text", "")
        except Exception as e:
            logger.error(f"Groq transcription error: {e}")
            return ""


if __name__ == "__main__":
    import asyncio

    async def main():
        transcriber = GroqTranscriptionProvider(
            api_key="sk-toandev95", api_base="https://api.senile.codes/v1"
        )
        transcription = await transcriber.transcribe(
            "C:\\Users\\toandev\\.nanobot\\media\\zalo_1dc98ca676cf79cc.aac"
        )
        print(transcription)

    asyncio.run(main())
