# generate_landing_voice.py

import asyncio
import shutil
from pathlib import Path

import app.tts.parler_service as parler_module

from app.tts.cache import audio_path, cache_key
from app.tts.text_cleaner import clean_tts_text
from app.tts.voice_profiles import PRIYA_STYLE_VERSION
from app.config import settings


# Short + playful + Indian/Hinglish
WELCOME_TEXT = (
    "Hi! Main Miss Julie hoon. Welcome to Talkora! "
    "English bolne, seekhne aur masti karne ke liye ready? "
    "Chalo, let's go!"
)


PRIYA_LANDING_STYLE = """
A sweet, cheerful young Indian female teacher speaking natural Hinglish.

She has a warm Indian English accent with natural Hindi influence.

Her voice sounds friendly, youthful, playful and smiling.

This is for children, so the delivery is lively, exciting and welcoming.

Speak quickly at a natural conversational pace.

Use short pauses only.

Do not sound formal.
Do not sound like a narrator.
Do not sound robotic.
Do not use an American or British accent.
Do not speak slowly.

The Hindi words should sound naturally Indian.

The English words should have a polished Indian English accent.

"Hi!" is bright and happy.

"Welcome to Talkora!" sounds exciting.

"ready?" sounds playful.

"Chalo, let's go!" is energetic, quick and joyful.

Clean studio-quality female voice.
""".strip()


async def main():

    # Landing-only voice style
    parler_module.PRIYA_STYLE = (
        PRIYA_LANDING_STYLE
    )

    normalized = clean_tts_text(
        WELCOME_TEXT
    )

    key = cache_key(
        normalized,
        settings.tts_voice,
        settings.tts_language,
        PRIYA_STYLE_VERSION,
        settings.tts_model,
    )

    path = audio_path(
        key,
        settings.tts_voice,
        settings.tts_language,
    )

    # Force regeneration
    path.unlink(
        missing_ok=True
    )

    metadata_path = Path(
        str(path) + ".json"
    )

    metadata_path.unlink(
        missing_ok=True
    )

    print("Generating new Hinglish Miss Julie...")
    print(WELCOME_TEXT)

    result = await (
        parler_module
        .parler_service
        .synthesize(
            WELCOME_TEXT
        )
    )

    root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    destination = (
        root
        / "client"
        / "public"
        / "assets"
        / "audio"
        / "miss-julie-welcome.wav"
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        result.path,
        destination,
    )

    print()
    print("DONE")
    print(
        f"Duration: "
        f"{result.duration_seconds:.2f}s"
    )

    print(destination)


if __name__ == "__main__":
    asyncio.run(main())