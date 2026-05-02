import asyncio
import hashlib
import os
from typing import List
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROVIDER_CHOICES = [
    ("edge", "Edge Neural"),
    ("google", "Google legacy"),
]

EDGE_VOICE_CHOICES = [
    ("fr-FR-DeniseNeural", "Edge - Denise FR"),
    ("fr-FR-HenriNeural", "Edge - Henri FR"),
    ("fr-CA-SylvieNeural", "Edge - Sylvie FR-CA"),
    ("en-US-JennyNeural", "Edge - Jenny EN-US"),
    ("en-GB-SoniaNeural", "Edge - Sonia EN-GB"),
    ("es-ES-ElviraNeural", "Edge - Elvira ES"),
    ("it-IT-ElsaNeural", "Edge - Elsa IT"),
    ("de-DE-KatjaNeural", "Edge - Katja DE"),
    ("pt-PT-RaquelNeural", "Edge - Raquel PT"),
    ("ja-JP-NanamiNeural", "Edge - Nanami JA"),
]

GOOGLE_VOICE_CHOICES = [
    ("fr", "Francais"),
    ("fr-CA", "Francais canadien"),
    ("en", "Anglais"),
    ("en-GB", "Anglais britannique"),
    ("en-US", "Anglais americain"),
    ("es", "Espagnol"),
    ("it", "Italien"),
    ("de", "Allemand"),
    ("pt", "Portugais"),
    ("ja", "Japonais"),
]

VOICE_CHOICES = EDGE_VOICE_CHOICES + GOOGLE_VOICE_CHOICES

STYLE_CHOICES = [
    ("normal", "Normal"),
    ("slow", "Lent"),
    ("cheerful", "Enjoue"),
    ("question", "Question"),
    ("announcement", "Annonce"),
]

DEFAULT_PROVIDER = "edge"
DEFAULT_VOICE = "fr-FR-DeniseNeural"
DEFAULT_GOOGLE_VOICE = "fr"
DEFAULT_STYLE = "normal"


def tts_audio_resources(
    text: str,
    voice: str = DEFAULT_VOICE,
    style: str = DEFAULT_STYLE,
    provider: str = DEFAULT_PROVIDER,
) -> List[str]:
    provider = normalize_provider(provider)
    if provider == "edge":
        return edge_tts_audio_resources(text, voice, style)
    return google_tts_audio_resources(text, voice, style)


def edge_tts_audio_resources(
    text: str, voice: str = DEFAULT_VOICE, style: str = DEFAULT_STYLE
) -> List[str]:
    voice = normalize_edge_voice(voice)
    style = normalize_style(style)
    styled_text = apply_style(text, style)
    rate = edge_rate(style)
    pitch = edge_pitch(style)
    digest = hashlib.sha1(
        f"edge|{voice}|{rate}|{pitch}|{styled_text}".encode("utf8")
    ).hexdigest()  # nosec B324
    path = f"/tmp/nabtts-edge-{digest}.mp3"
    if not os.path.isfile(path):
        asyncio.run(_edge_tts_save(styled_text, voice, rate, pitch, path))
    return [path]


async def _edge_tts_save(text, voice, rate, pitch, path):
    try:
        import edge_tts  # type: ignore
    except ImportError as err:
        raise RuntimeError(
            "edge-tts is not installed. Run ./venv/bin/pip install edge-tts"
        ) from err
    communicate = edge_tts.Communicate(
        text,
        voice=voice,
        rate=rate,
        pitch=pitch,
    )
    await communicate.save(path)


def google_tts_audio_resources(
    text: str, lang: str = DEFAULT_GOOGLE_VOICE, style: str = DEFAULT_STYLE
) -> List[str]:
    resources = []
    for index, url in enumerate(google_tts_audio_urls(text, lang, style)):
        digest = hashlib.sha1(url.encode("utf8")).hexdigest()  # nosec B324
        path = f"/tmp/nabtts-{index}-{digest}.mp3"
        if not os.path.isfile(path):
            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; Nabaztag Text to Speech)"
                    )
                },
            )
            with urlopen(request, timeout=10) as response:  # nosec B310
                with open(path, "wb") as output:
                    output.write(response.read())
        resources.append(path)
    return resources


def google_tts_audio_urls(
    text: str, lang: str = DEFAULT_GOOGLE_VOICE, style: str = DEFAULT_STYLE
) -> List[str]:
    urls = []
    lang = normalize_google_voice(lang)
    style = normalize_style(style)
    speed_value = style_speed_query_value(style)
    styled_text = apply_style(text, style)
    for part in split_tts_text(styled_text):
        query = urlencode(
            {
                "ie": "UTF-8",
                "client": "tw-ob",
                "tl": lang,
                "ttsspeed": speed_value,
                "q": part,
            }
        )
        urls.append(f"https://translate.google.com/translate_tts?{query}")
    return urls


def split_tts_text(text: str, limit: int = 180) -> List[str]:
    words = text.split()
    parts = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def apply_style(text: str, style: str) -> str:
    text = " ".join(str(text or "").split())
    style = normalize_style(style)
    if style == "cheerful":
        return cheerful_text(text)
    if style == "question":
        return question_text(text)
    if style == "announcement":
        return announcement_text(text)
    return text


def cheerful_text(text: str) -> str:
    if not text:
        return text
    if text[-1] in ".!?":
        text = text[:-1]
    return f"{text} !"


def question_text(text: str) -> str:
    if not text:
        return text
    if text[-1] in ".!?":
        text = text[:-1]
    return f"{text} ?"


def announcement_text(text: str) -> str:
    if not text:
        return text
    parts = []
    for sentence in text.replace("!", ".").replace("?", ".").split("."):
        sentence = sentence.strip()
        if sentence:
            parts.append(sentence)
    return ". ".join(parts) + "."


def normalize_voice(voice: str) -> str:
    voices = [value for value, label in VOICE_CHOICES]
    if voice in voices:
        return voice
    return DEFAULT_VOICE


def normalize_provider(provider: str) -> str:
    providers = [value for value, label in PROVIDER_CHOICES]
    if provider in providers:
        return provider
    return DEFAULT_PROVIDER


def normalize_voice_for_provider(voice: str, provider: str) -> str:
    provider = normalize_provider(provider)
    if provider == "edge":
        return normalize_edge_voice(voice)
    return normalize_google_voice(voice)


def normalize_edge_voice(voice: str) -> str:
    voices = [value for value, label in EDGE_VOICE_CHOICES]
    if voice in voices:
        return voice
    return DEFAULT_VOICE


def normalize_google_voice(voice: str) -> str:
    voices = [value for value, label in GOOGLE_VOICE_CHOICES]
    if voice in voices:
        return voice
    return DEFAULT_GOOGLE_VOICE


def normalize_style(style: str) -> str:
    styles = [value for value, label in STYLE_CHOICES]
    if style in styles:
        return style
    return DEFAULT_STYLE


def style_speed_query_value(style: str) -> str:
    style = normalize_style(style)
    if style in ("slow", "announcement"):
        return "0.24"
    return "1"


def edge_rate(style: str) -> str:
    style = normalize_style(style)
    if style in ("slow", "announcement"):
        return "-25%"
    if style == "cheerful":
        return "+8%"
    return "+0%"


def edge_pitch(style: str) -> str:
    style = normalize_style(style)
    if style == "cheerful":
        return "+8Hz"
    if style == "announcement":
        return "-2Hz"
    return "+0Hz"
