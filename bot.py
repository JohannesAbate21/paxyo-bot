#!/usr/bin/env python3
"""Paxyo Order bot (@paxorder_bot).

Users order Paxyo social-media services by text/chat or by voice message,
in Amharic or English. The bot talks to the Paxyo Bot API on paxyo.et and
uses Gemini to understand what the user wants.

Money rules (hard):
  - The AI only listens and talks. All totals are computed server-side by
    the Paxyo API. This code never invents a price: it only displays the
    rate the API returned, labelled as an estimate.
  - Never place an order without an explicit Confirm tap.
  - Never sell blacklisted services (5379, 5834) or inactive services.
  - Quantity must be a multiple of 10 and inside the service min/max.

Stall-fallback (cancel/refund and move to the next-fastest service when the
picked service stalls) is a LATER phase and is NOT built in this version.
The code is structured so a status monitor can be added later: see
`fetch_order_status()` and the TODO in `main()`.

All configuration comes from environment variables. No secret is ever
written to a file or a log by this program.

Voice replies: a voice message in gets a voice message back (text in
gets text back — never the other way round). The reply voice uses
Google Cloud Text-to-Speech (am-ET voices speak real Amharic), which
returns OGG Opus directly — no ffmpeg is needed on Render. The
owner's voice-style prompt (VOICE_STYLE_PROMPT) is kept as
documentation of the desired delivery (Cloud TTS takes no style
prompt; speaking rate 1.0 and pitch 0 approximate it). The Confirm
card is always text, because a voice message cannot carry inline
buttons, and so is the post-acceptance order summary: a voice "yes"
places the order and is answered with a full text summary (service,
quantity, link, total, order id, status). Any voice failure falls
back to text silently and never breaks an order. (Gemini TTS was
tried first and verified 13 Nov 2026 to return no audio at all for
Amharic, with only 10 requests/day on the free-tier key — see README,
"Voice replies".)

Runs as a FREE Render web service, not a paid background worker: Telegram
sends updates to a webhook instead of the bot polling. On startup the bot
sets its webhook to <RENDER_EXTERNAL_URL>/<path> (path defaults to the bot
token) and serves Render's health check at GET / ("ok"). Free web services
sleep after ~15 minutes idle and wake in ~30-50s on the first message.
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
import signal
import uuid
from typing import Optional

import httpx
import tornado.web
from tornado.httpserver import HTTPServer
from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("paxorder_bot")

# ---------------------------------------------------------------- config ---

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PAXYO_API_BASE = os.environ.get("PAXYO_API_BASE", "https://paxyo.et/api/bot").rstrip("/")
BOT_API_SECRET = os.environ.get("BOT_API_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
# Google Cloud Text-to-Speech (voice replies). The API key comes from a
# Google Cloud project with the Cloud Text-to-Speech API enabled and
# billing on; the AI Studio (Gemini) key does NOT work for it.
GOOGLE_CLOUD_TTS_API_KEY = os.environ.get("GOOGLE_CLOUD_TTS_API_KEY", "")
GOOGLE_CLOUD_TTS_VOICE = os.environ.get("GOOGLE_CLOUD_TTS_VOICE", "am-ET-Wavenet-A")
GOOGLE_CLOUD_TTS_VOICE_EN = os.environ.get("GOOGLE_CLOUD_TTS_VOICE_EN", "en-US-Wavenet-D")
GOOGLE_CLOUD_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
MAX_VOICE_CHARS = 800  # TTS is only for short replies; longer text stays text

# ---------------------------------------------------------- webhook -----
# Free Render web service: Telegram pushes updates to a webhook URL
# instead of the bot polling. Render sets PORT and RENDER_EXTERNAL_URL
# for the service automatically; WEBHOOK_URL / WEBHOOK_PATH are manual
# overrides (local testing behind ngrok, etc.).

def get_webhook_port() -> int:
    """Port to listen on. Render sets PORT; 8443 is the fallback."""
    try:
        return int(os.environ.get("PORT", "8443"))
    except ValueError:
        return 8443


def get_webhook_path() -> str:
    """Secret URL path for Telegram updates. Defaults to the bot token:
    the token is secret, so the path is unguessable."""
    path = (os.environ.get("WEBHOOK_PATH") or "").strip().strip("/")
    return path or TELEGRAM_BOT_TOKEN


def get_webhook_base_url() -> str:
    """Public base URL of this service, no trailing slash.

    WEBHOOK_URL wins when set; otherwise Render's RENDER_EXTERNAL_URL,
    which Render sets automatically for every web service."""
    base = (
        os.environ.get("WEBHOOK_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or ""
    ).strip().rstrip("/")
    return base


def build_webhook_url() -> str:
    """Full Telegram webhook URL: <base>/<path>. Raises ValueError when
    no base URL is configured."""
    base = get_webhook_base_url()
    if not base:
        raise ValueError(
            "no webhook base URL: set WEBHOOK_URL, or run on Render "
            "(RENDER_EXTERNAL_URL is set automatically)"
        )
    return f"{base}/{get_webhook_path()}"

BLACKLISTED_SERVICES = {5379, 5834}
SERVICES_CACHE_SECONDS = 600  # 10 minutes
GEMINI_URL = "https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"

# ------------------------------------------------------- Gemini prompt ----
# Default system prompt for the order assistant. The owner may replace this
# text with their own Amharic prompt; the behaviour contract is: extract
# the order intent as JSON, never place an order, never discuss the
# provider or Paxyo's costs, keep replies short.
SYSTEM_PROMPT = """You are the Paxyo order assistant on Telegram. The user writes in
Amharic or English, by text or by voice transcription. Your job is only to
understand what service they want to order and to extract the intent as JSON.

Rules:
- Reply with JSON only, no extra text, no markdown fences.
- JSON shape: {"platform": "...", "service_hint": "...", "link": "...",
  "quantity": 123}
- platform: one of instagram, tiktok, telegram, youtube, facebook, x
  (twitter). Use null when the user did not name a platform.
- service_hint: a short phrase for the service, e.g. "followers", "likes",
  "views", "members". Use null when unclear.
- link: the full link the order is for (instagram/tiktok/telegram/youtube
  post or profile link). Use null when the user did not give one.
- quantity: a whole number, or null when the user did not give one.
- Never place an order, never confirm an order, never quote a price.
- Never mention the provider, GodOfPanel, costs, or how Paxyo buys services.
- If the message is not an order at all, return {"platform": null,
  "service_hint": null, "link": null, "quantity": null}.
"""

# ------------------------------------------------------ voice style ------
# The owner's voice prompt for how the bot SPEAKS, pasted by him verbatim
# (13 Nov 2026). Google Cloud TTS takes no style prompt, so this is kept
# as documentation of the desired delivery — calm, natural, controlled
# pace, like a podcast host — and speakingRate 1.0 / pitch 0 in
# build_tts_payload() approximate it. Do not shorten it or "finish" it —
# it is complete as pasted.
VOICE_STYLE_PROMPT = """You are an expert Amharic voice actor delivering a short-form sponsor
segment. Your tone is relaxed, fast-paced informative, and naturally
engaging — like a skilled, matured person genuinely sharing something
useful, not selling or performing. You speak at a normal, controlled
pace with continuous forward momentum. You never rush, never mumble,
and never pause dramatically for effect.

Your delivery is not theatrical, not a TV commercial, not a hype reel,
not a kids storyteller, and not a radio DJ. You are closer to a calm,
confident podcast host or a YouTube educator who knows their subject
deeply and respects the listener's intelligence. The energy in your
voice comes from clarity and rhythm, not from excitement or intensity.

Your Amharic should sound exactly like a fluent, matured native
speaker — natural sentence rhythm, natural word choices, never stiff,
never a direct translation feel from English. The voice and the language together"""

# ------------------------------------------------------------ replies ------
# Short replies in both languages. Amharic is written in Ethiopic fidels
# mixed with English, never Latin-letter Amharic.

TEXT = {
    "greeting": {
        "am": (
            "ሰላም! እኔ Paxyo Order bot ነኝ።\n"
            "የሚፈልጉትን service በchat ወይም በvoice ይዘዙልኝ — ለምሳሌ "
            "“1000 views እፈልጋለሁ” ብለው link ይላኩልኝ።\n"
            "Balance ለማየት /balance ይጠቀሙ።"
        ),
        "en": (
            "Hello! I am the Paxyo Order bot.\n"
            "Tell me the service you want by chat or voice — for example "
            "“I want 1000 views” with your link.\n"
            "Use /balance to check your balance."
        ),
    },
    "help": {
        "am": (
            "እንዴት እንደሚሰራ:\n"
            "1. Service, link እና quantity ይላኩልኝ።\n"
            "2. እኔ ፈጣኑን service አገኛለሁ።\n"
            "3. Confirm ካደረጉ በኋላ order ይፈጸማል።\n\n"
            "/balance — balance ማየት\n"
            "/orders — የመጨረሻ order status ማየት\n"
            "/help — እርዳታ"
        ),
        "en": (
            "How it works:\n"
            "1. Send me the service, link and quantity.\n"
            "2. I find the fastest service for you.\n"
            "3. After you tap Confirm, the order is placed.\n\n"
            "/balance — check your balance\n"
            "/orders — status of your last order\n"
            "/help — help"
        ),
    },
    "ask_link": {
        "am": "Link ይላኩልኝ — order የሚደረግበት link።",
        "en": "Please send the link the order is for.",
    },
    "ask_quantity": {
        "am": "Quantity ስንት ይሁን? (ለምሳሌ 1000)",
        "en": "How many? (for example 1000)",
    },
    "ask_platform": {
        "am": "የትኛው platform ነው? (Instagram, TikTok, Telegram, YouTube...)",
        "en": "Which platform? (Instagram, TikTok, Telegram, YouTube...)",
    },
    "not_understood": {
        "am": "አልገባኝም — እባክዎ እንደገና ይሞክሩ። ለምሳሌ: “1000 Instagram followers እፈልጋለሁ” ብለው link ይላኩልኝ።",
        "en": "I did not understand — please try again. For example: “I want 1000 Instagram followers” with your link.",
    },
    "no_service": {
        "am": "ለዚህ platform service አላገኘሁም። እባክዎ platform ይለውጡ።",
        "en": "I could not find a service for that platform. Please try another platform.",
    },
    "bad_quantity": {
        "am": "Quantity ከ {min} እስከ {max} መሆን አለበት, እና የ10 እጥፍ መሆን አለበት።",
        "en": "Quantity must be between {min} and {max}, and a multiple of 10.",
    },
    "insufficient": {
        "am": "Balance አይበቃም። Balance: {balance} ETB, ያስፈልጋል: {total} ETB። እባክዎ paxyo.et ላይ deposit ያድርጉ።",
        "en": "Not enough balance. Balance: {balance} ETB, needed: {total} ETB. Please deposit at paxyo.et.",
    },
    "order_ok": {
        "am": "Order ተፈጽሟል!\nOrder ID: {order_id}\nStatus: {status}",
        "en": "Order placed!\nOrder ID: {order_id}\nStatus: {status}",
    },
    # Full summary sent IN TEXT after an order is accepted (button tap,
    # or "yes" by voice or by text). A voice confirmation always ends
    # with this readable record of what was ordered.
    "order_summary": {
        "am": (
            "Order ተፈጽሟል!\n"
            "Service: {service}\n"
            "Quantity: {quantity}\n"
            "Link: {link}\n"
            "Total: {total} ETB\n"
            "Order ID: {order_id}\n"
            "Status: {status}"
        ),
        "en": (
            "Order placed!\n"
            "Service: {service}\n"
            "Quantity: {quantity}\n"
            "Link: {link}\n"
            "Total: {total} ETB\n"
            "Order ID: {order_id}\n"
            "Status: {status}"
        ),
    },
    "order_failed": {
        "am": "Order አልተፈጸመም። እባክዎ እንደገና ይሞክሩ።",
        "en": "The order could not be placed. Please try again.",
    },
    "cancelled": {
        "am": "Order ተሰርዟል።",
        "en": "Order cancelled.",
    },
    "no_orders": {
        "am": "ገና order የለዎትም።",
        "en": "You have no orders yet.",
    },
    "balance": {
        "am": "Balance: {balance} ETB",
        "en": "Balance: {balance} ETB",
    },
    "transcribe_failed": {
        "am": "Voice መልዕክቱን መረዳት አልቻልኩም — እባክዎ እንደገና ይሞክሩ ወይም በጽሑፍ ይላኩልኝ።",
        "en": "I could not understand the voice message — please try again or send it as text.",
    },
    "confirm_title": {
        "am": "እባክዎ ያረጋግጡ:",
        "en": "Please confirm:",
    },
}


def t(key: str, lang: str, **kw) -> str:
    """Short reply in the user's language."""
    return TEXT[key][lang].format(**kw)


def is_amharic(text: str) -> bool:
    """True when the text contains Ethiopic fidels."""
    return any("\u1200" <= ch <= "\u137f" for ch in text)


def lang_of(text: str, user_lang: str = "") -> str:
    """'am' for Amharic, otherwise 'en'."""
    if is_amharic(text or ""):
        return "am"
    if (user_lang or "").lower().startswith("am"):
        return "am"
    return "en"


# --------------------------------------------------------- pure helpers ---

def parse_average_time(text):
    """Parse a provider average-time string to minutes, or None.

    Examples: "12 minutes" -> 12, "28 hours 1 minute" -> 1681,
    "1 day" -> 1440, "New Service"/None -> None.
    """
    if not text:
        return None
    s = str(text).strip().lower()
    if s in ("new service", "none", "-", ""):
        return None
    units = {
        "day": 1440, "days": 1440,
        "hour": 60, "hours": 60, "hr": 60, "hrs": 60,
        "minute": 1, "minutes": 1, "min": 1, "mins": 1,
    }
    total = 0
    found = False
    for num, unit in re.findall(r"(\d+)\s*(days?|hours?|hrs?|minutes?|mins?)", s):
        total += int(num) * units[unit]
        found = True
    return total if found else None


def pick_services(services, platform=None, service_hint=None, limit=3):
    """Rank services for a platform, fastest average time first.

    Excludes blacklisted and inactive services. Services with no average
    time sort last. Returns at most `limit` services.
    """
    wanted = (platform or "").strip().lower()
    hint = (service_hint or "").strip().lower()
    candidates = []
    for s in services:
        if not s.get("active", True):
            continue
        try:
            sid = int(s.get("service", 0))
        except (TypeError, ValueError):
            continue
        if sid in BLACKLISTED_SERVICES:
            continue
        category = str(s.get("category") or "").lower()
        name = str(s.get("name") or "").lower()
        if wanted and wanted not in category and wanted not in name:
            continue
        if hint and hint not in name and hint not in category:
            continue
        candidates.append(s)
    candidates.sort(
        key=lambda s: (
            parse_average_time(s.get("average_time")) is None,
            parse_average_time(s.get("average_time")) or 0,
        )
    )
    return candidates[:limit]


def validate_quantity(quantity, service):
    """Return an error code, or None when the quantity is valid."""
    if quantity is None:
        return "missing"
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        return "invalid"
    if qty <= 0:
        return "invalid"
    if qty % 10 != 0:
        return "not_multiple_of_10"
    if qty < int(service.get("min", 0)):
        return "below_min"
    if qty > int(service.get("max", 0)):
        return "above_max"
    return None


def estimated_total_etb(rate_etb_per_1000, quantity):
    """Display-only estimate from the API's own rate. The server computes
    the real total on order creation; this is never the charged amount."""
    return round(float(rate_etb_per_1000) * int(quantity) / 1000, 2)


def extract_json(text: str):
    """Pull the first JSON object out of model output, tolerating fences
    and surrounding prose. Returns a dict, or None."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def format_money(value) -> str:
    return f"{float(value):,.2f}"


# ------------------------------------------------------- API clients ------

def build_api_request(method: str, path: str, json_body=None) -> httpx.Request:
    """Build (never send) an authenticated Paxyo API request. Used by the
    client below and by the offline self-test."""
    return httpx.Request(
        method,
        PAXYO_API_BASE + path,
        headers={"X-Bot-Secret": BOT_API_SECRET},
        json=json_body,
    )


class PaxyoClient:
    """Async client for the Paxyo Bot API (https://paxyo.et/api/bot)."""

    def __init__(self):
        # trust_env=False: ignore any proxy env vars so the client talks
        # directly to paxyo.et (Render services have direct egress).
        self._client = httpx.AsyncClient(timeout=30.0, trust_env=False)
        self._services_cache = None
        self._services_cached_at = 0.0

    async def _send(self, request: httpx.Request):
        import time

        response = await self._client.send(request)
        response.raise_for_status()
        return response.json()

    async def services(self):
        """GET /services, cached for SERVICES_CACHE_SECONDS."""
        import time

        now = time.monotonic()
        if (
            self._services_cache is not None
            and now - self._services_cached_at < SERVICES_CACHE_SECONDS
        ):
            return self._services_cache
        data = await self._send(build_api_request("GET", "/services"))
        services = data.get("services", data) if isinstance(data, dict) else data
        self._services_cache = services
        self._services_cached_at = now
        return services

    async def balance(self, telegram_id: int):
        return await self._send(
            build_api_request("GET", f"/balance?telegram_id={telegram_id}")
        )

    async def create_user(self, telegram_id: int, username=None, first_name=None):
        """POST /users (create the account on /start).

        The endpoint is new; a 404 means it is not deployed yet. That is
        handled gracefully: the caller treats the user as new and continues.
        """
        try:
            return await self._send(
                build_api_request(
                    "POST",
                    "/users",
                    {
                        "telegram_id": telegram_id,
                        "username": username,
                        "first_name": first_name,
                    },
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("POST /users returned 404 (endpoint not live yet)")
                return None
            raise

    async def create_order(
        self, telegram_id: int, service_id: int, link: str, quantity: int, idempotency_key: str
    ):
        return await self._send(
            build_api_request(
                "POST",
                "/orders",
                {
                    "telegram_id": telegram_id,
                    "service_id": service_id,
                    "link": link,
                    "quantity": quantity,
                    "idempotency_key": idempotency_key,
                },
            )
        )

    async def order_status(self, order_id, telegram_id: int):
        """GET /orders/{id}?telegram_id= — used by /orders and by a future
        stall monitor (see TODO in main())."""
        return await self._send(
            build_api_request("GET", f"/orders/{order_id}?telegram_id={telegram_id}")
        )


async def gemini_generate(prompt: str, system: str = None) -> str:
    """One Gemini text call. Returns the reply text (may be empty)."""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    url = GEMINI_URL.format(model=GEMINI_MODEL)
    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
        resp = await client.post(url, params={"key": GEMINI_API_KEY}, json=payload)
        resp.raise_for_status()
        data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return ""


async def gemini_transcribe(audio_bytes: bytes) -> str:
    """Transcribe a Telegram voice message (.ogg) with Gemini."""
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Transcribe this voice message exactly, in the language spoken."},
                    {
                        "inlineData": {
                            "mimeType": "audio/ogg",
                            "data": base64.b64encode(audio_bytes).decode(),
                        }
                    },
                ]
            }
        ]
    }
    url = GEMINI_URL.format(model=GEMINI_MODEL)
    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
        resp = await client.post(url, params={"key": GEMINI_API_KEY}, json=payload)
        resp.raise_for_status()
        data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return ""


async def extract_intent(text: str) -> dict:
    """Ask Gemini to extract the order intent from user text."""
    reply = await gemini_generate(text, system=SYSTEM_PROMPT)
    intent = extract_json(reply)
    if intent is None:
        return {"platform": None, "service_hint": None, "link": None, "quantity": None}
    return {
        "platform": intent.get("platform"),
        "service_hint": intent.get("service_hint"),
        "link": intent.get("link"),
        "quantity": intent.get("quantity"),
    }


# ------------------------------------------------------- voice replies ----

def voice_for_lang(lang: str) -> Optional[tuple]:
    """(languageCode, voiceName) for a reply language, or None.

    Only 'am' and 'en' have a voice. Anything else returns None so the
    caller falls back to text — never guess a voice for a language.
    """
    if lang == "am":
        return ("am-ET", GOOGLE_CLOUD_TTS_VOICE)
    if lang == "en":
        return ("en-US", GOOGLE_CLOUD_TTS_VOICE_EN)
    return None


def build_tts_payload(text: str, lang: str) -> Optional[dict]:
    """Build the Google Cloud Text-to-Speech request for a reply.

    Returns None when the language has no voice (the caller falls back
    to text). speakingRate 1.0 and pitch 0 approximate the delivery in
    VOICE_STYLE_PROMPT — calm, natural, controlled pace; Cloud TTS
    takes no style prompt of its own.
    """
    voice = voice_for_lang(lang)
    if voice is None:
        return None
    language_code, voice_name = voice
    return {
        "input": {"text": text},
        "voice": {"languageCode": language_code, "name": voice_name},
        "audioConfig": {
            "audioEncoding": "OGG_OPUS",
            "speakingRate": 1.0,
            "pitch": 0,
        },
    }


async def cloud_tts_speak(text: str, lang: str) -> Optional[bytes]:
    """Synthesize speech with Google Cloud Text-to-Speech.

    Returns OGG Opus bytes (what Telegram voice messages need — no
    conversion step), or None when the key is missing, the language has
    no voice, or the call fails. The caller treats None as "answer by
    text instead"; it never raises.
    """
    if not GOOGLE_CLOUD_TTS_API_KEY:
        log.warning("cloud_tts_speak: no GOOGLE_CLOUD_TTS_API_KEY set")
        return None
    payload = build_tts_payload(text, lang)
    if payload is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.post(
                GOOGLE_CLOUD_TTS_URL,
                headers={"x-goog-api-key": GOOGLE_CLOUD_TTS_API_KEY},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        audio = data.get("audioContent")
        if not audio:
            return None
        return base64.b64decode(audio)
    except Exception as exc:
        log.warning("cloud_tts_speak failed: %s", exc)
        return None


async def speak_reply(text: str, lang: str) -> Optional[bytes]:
    """Full voice pipeline: Cloud TTS straight to OGG Opus bytes.

    Returns OGG bytes ready for Telegram send_voice, or None when voice
    is not possible (unsupported language, no API key, any error, or a
    reply too long to speak). The caller falls back to text.
    """
    if len(text) > MAX_VOICE_CHARS:
        return None
    return await cloud_tts_speak(text, lang)


async def reply_message(message, text: str, lang: str, voice: bool = False,
                        reply_markup=None):
    """Send a reply as a voice message when asked and possible, else text.

    Voice is only used for plain replies. Anything with an inline
    keyboard (the Confirm card) is always text, because a voice message
    cannot carry buttons. Any voice failure falls back to text silently
    — the user always gets an answer.
    """
    if voice and reply_markup is None:
        ogg = await speak_reply(text, lang)
        if ogg:
            try:
                await message.reply_voice(
                    voice=InputFile(io.BytesIO(ogg), filename="reply.ogg")
                )
                return
            except Exception as exc:
                log.warning("reply_voice failed, falling back to text: %s", exc)
    await message.reply_text(text, reply_markup=reply_markup)


# ------------------------------------------------------------ bot state ----

# Created in main(), not at import time, so importing this module (e.g.
# for the offline self-test) never opens a network client.
paxyo = None
PENDING = {}  # confirm_id -> {user_id, service, link, quantity, total}
LAST_ORDER = {}  # telegram_id -> order_id


def confirm_keyboard(confirm_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{confirm_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{confirm_id}"),
            ]
        ]
    )


# ------------------------------------------------------------- handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = "am" if (user.language_code or "").lower().startswith("am") else "en"
    try:
        await paxyo.create_user(
            user.id, username=user.username, first_name=user.first_name
        )
    except Exception as exc:  # account creation must never block /start
        log.warning("create_user failed (continuing): %s", exc)
    await update.message.reply_text(t("greeting", lang))


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = lang_of("", user.language_code)
    try:
        data = await paxyo.balance(user.id)
    except Exception as exc:
        log.warning("balance failed: %s", exc)
        await update.message.reply_text(t("not_understood", lang))
        return
    if not data.get("found"):
        await update.message.reply_text(t("greeting", lang))
        return
    await update.message.reply_text(
        t("balance", lang, balance=format_money(data.get("balance", 0)))
    )


async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status of the user's last order (tracked in memory)."""
    user = update.effective_user
    lang = lang_of("", user.language_code)
    order_id = LAST_ORDER.get(user.id)
    if not order_id:
        await update.message.reply_text(t("no_orders", lang))
        return
    try:
        data = await paxyo.order_status(order_id, user.id)
    except Exception as exc:
        log.warning("order_status failed: %s", exc)
        await update.message.reply_text(t("not_understood", lang))
        return
    status = data.get("status") or data.get("order", {}).get("status", "?")
    await update.message.reply_text(
        t("order_ok", lang, order_id=order_id, status=status)
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = lang_of("", user.language_code)
    await update.message.reply_text(t("help", lang))


# ------------------------------------------------------- order accept ---
# A bare acceptance ("yes", "confirm", "አዎ", ...) while an order is
# pending places that order. Only a bare acceptance counts: a new order
# message never matches, because it names a service.
ACCEPT_WORDS = frozenset({
    "yes", "yeah", "yep", "ok", "okay", "confirm", "confirmed",
    "place it", "do it", "go ahead", "proceed", "sure",
    "አዎ", "እሺ", "ይሁን", "አረጋግጥ", "ፈጽም", "ቀጥል", "እሺ ይሁን",
})


def is_acceptance(text: str) -> bool:
    """True when the message is just an acceptance of a pending order."""
    s = " ".join((text or "").strip().lower().split())
    s = s.strip(" .!,?።፣")
    return s in ACCEPT_WORDS


def pending_for_user(user_id: int):
    """(confirm_id, pending) of the user's most recent pending order,
    or (None, None) when they have none."""
    for confirm_id, pending in reversed(list(PENDING.items())):
        if pending["user_id"] == user_id:
            return confirm_id, pending
    return None, None


async def place_pending_order(pending, user_id: int):
    """Balance check + create order for a pending order.

    Returns (result, error). On success result is a dict with the order
    id, status, service name, quantity, link and total, and error is
    None. On failure result is None and error is ("insufficient",
    balance, total), ("order_failed",) or ("not_understood",).
    """
    service = pending["service"]
    quantity = pending["quantity"]
    total = pending["total"]
    try:
        bal = await paxyo.balance(user_id)
    except Exception as exc:
        log.warning("balance check failed: %s", exc)
        return None, ("not_understood",)
    if not bal.get("found") or float(bal.get("balance", 0)) < total:
        return None, ("insufficient", bal.get("balance", 0), total)
    try:
        result = await paxyo.create_order(
            user_id,
            int(service["service"]),
            pending["link"],
            quantity,
            uuid.uuid4().hex,
        )
    except httpx.HTTPStatusError as exc:
        log.warning("create_order rejected: %s", exc.response.status_code)
        return None, ("order_failed",)
    except Exception as exc:
        log.warning("create_order failed: %s", exc)
        return None, ("order_failed",)
    order = result.get("order", result) if isinstance(result, dict) else {}
    order_id = order.get("id") or order.get("order_id") or "?"
    status = order.get("status", "pending")
    LAST_ORDER[user_id] = order_id
    return {
        "order_id": order_id,
        "status": status,
        "service": service.get("name"),
        "quantity": quantity,
        "link": pending["link"],
        "total": total,
    }, None


async def send_order_result(message, lang: str, pending, user_id: int):
    """Place a pending order and send the full summary as a new TEXT
    message. Used when the user accepts by voice or by text: the
    summary is always text, even when the user spoke."""
    result, error = await place_pending_order(pending, user_id)
    if error:
        key = error[0]
        if key == "insufficient":
            await message.reply_text(
                t(
                    "insufficient",
                    lang,
                    balance=format_money(error[1]),
                    total=format_money(error[2]),
                )
            )
        else:
            await message.reply_text(t(key, lang))
        return
    await message.reply_text(
        t(
            "order_summary",
            lang,
            service=result["service"],
            quantity=result["quantity"],
            link=result["link"],
            total=format_money(result["total"]),
            order_id=result["order_id"],
            status=result["status"],
        )
    )


async def handle_order_text(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            text: str, voice: bool = False):
    """Shared flow for text messages and transcribed voice messages.

    Reply rules (owner, 13 Nov 2026):
    - Text in -> text out, always. Voice in -> voice out, except the
      Confirm card and the post-acceptance summary, which are always
      text (a voice message cannot carry buttons, and a voice
      confirmation must end with a readable text record of the order).
    - A bare acceptance ("yes", "confirm", "አዎ", ...) while an order
      is pending places that order — no new intent is extracted.
    - Orders work in Amharic and English, by text and by voice.
    """
    user = update.effective_user
    lang = lang_of(text, user.language_code)

    # Bare acceptance of a pending order: place it and answer with the
    # full order summary IN TEXT. Checked before intent extraction, so
    # a "yes" is never misread as a new order.
    if is_acceptance(text):
        confirm_id, pending = pending_for_user(user.id)
        if pending is not None:
            PENDING.pop(confirm_id, None)
            await send_order_result(update.message, lang, pending, user.id)
            return
        # No pending order: fall through; the normal flow answers
        # "not understood".

    intent = await extract_intent(text)

    if not intent.get("platform") and not intent.get("service_hint"):
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    if not intent.get("link"):
        await reply_message(update.message, t("ask_link", lang), lang, voice=voice)
        return
    if not intent.get("quantity"):
        await reply_message(update.message, t("ask_quantity", lang), lang, voice=voice)
        return

    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("services fetch failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return

    picks = pick_services(
        services, platform=intent.get("platform"), service_hint=intent.get("service_hint")
    )
    if not picks:
        await reply_message(update.message, t("no_service", lang), lang, voice=voice)
        return

    service = picks[0]
    error = validate_quantity(intent.get("quantity"), service)
    if error:
        await reply_message(
            update.message,
            t(
                "bad_quantity",
                lang,
                min=service.get("min"),
                max=service.get("max"),
            ),
            lang,
            voice=voice,
        )
        return

    quantity = int(intent["quantity"])
    rate = float(service.get("rate_etb_per_1000", 0))
    total = estimated_total_etb(rate, quantity)
    avg = service.get("average_time") or "—"

    confirm_id = uuid.uuid4().hex[:12]
    PENDING[confirm_id] = {
        "user_id": user.id,
        "service": service,
        "link": intent["link"],
        "quantity": quantity,
        "total": total,
    }
    lines = [
        t("confirm_title", lang),
        "",
        f"{service.get('name')}",
        f"⏱ {avg}",
        f"💰 {format_money(rate)} ETB / 1000",
        f"🔢 {quantity}",
        f"🧾 {format_money(total)} ETB (estimated)",
    ]
    # Confirm card: always text — a voice message cannot carry buttons.
    await reply_message(
        update.message, "\n".join(lines), lang,
        reply_markup=confirm_keyboard(confirm_id),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Text in -> text out, always. The bot never answers a text
    # message with a voice message (handle_order_text gets voice=False).
    await handle_order_text(update, context, update.message.text or "")


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = lang_of("", user.language_code)
    try:
        voice_file = await update.message.voice.get_file()
        audio = bytes(await voice_file.download_as_bytearray())
        text = await gemini_transcribe(audio)
    except Exception as exc:
        log.warning("voice handling failed: %s", exc)
        await update.message.reply_text(t("transcribe_failed", lang))
        return
    if not text:
        await update.message.reply_text(t("transcribe_failed", lang))
        return
    await handle_order_text(update, context, text, voice=True)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    lang = lang_of(query.message.text or "", user.language_code)
    action, _, confirm_id = (query.data or "").partition(":")
    pending = PENDING.pop(confirm_id, None)
    if pending is None or pending["user_id"] != user.id:
        await query.edit_message_text(t("cancelled", lang))
        return
    if action == "cancel":
        await query.edit_message_text(t("cancelled", lang))
        return

    # Button tap: place the order and replace the Confirm card with the
    # full order summary IN TEXT — the same summary a voice acceptance
    # gets as a new message (see send_order_result).
    result, error = await place_pending_order(pending, user.id)
    if error:
        key = error[0]
        if key == "insufficient":
            await query.edit_message_text(
                t(
                    "insufficient",
                    lang,
                    balance=format_money(error[1]),
                    total=format_money(error[2]),
                )
            )
        else:
            await query.edit_message_text(t(key, lang))
        return
    await query.edit_message_text(
        t(
            "order_summary",
            lang,
            service=result["service"],
            quantity=result["quantity"],
            link=result["link"],
            total=format_money(result["total"]),
            order_id=result["order_id"],
            status=result["status"],
        )
    )


# ------------------------------------------- webhook (Render web service) ---

class HealthHandler(tornado.web.RequestHandler):
    """GET / -> 200 'ok'. Render's health check hits this path."""

    def get(self):
        self.set_status(200)
        self.set_header("Content-Type", "text/plain")
        self.write("ok")


def build_webhook_app(app):
    """Tornado app serving the Telegram webhook AND Render's health check.

    PTB's own run_webhook server only serves the webhook path (POST), so
    GET / would 404 and Render's healthCheckPath would fail the deploy.
    This reuses PTB's TelegramHandler for the webhook path (the same code
    run_webhook uses internally) and adds GET / -> 200 'ok' next to it.
    """
    from telegram.ext._utils.webhookhandler import WebhookAppClass

    tornado_app = WebhookAppClass(f"/{get_webhook_path()}", app.bot, app.update_queue, None)
    tornado_app.add_handlers(r".*", [(r"/", HealthHandler)])
    return tornado_app


def build_application():
    """Build the PTB Application with all handlers. No network calls."""
    # trust_env=False so the Telegram clients ignore any proxy env vars
    # and talk directly to api.telegram.org (same as the API clients).
    telegram_request = HTTPXRequest(httpx_kwargs={"trust_env": False})
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(telegram_request)
        .get_updates_request(telegram_request)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("orders", orders_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(CallbackQueryHandler(on_callback))
    return app


async def serve_webhook(app, port: int, stop_event=None):
    """Start the app, set the Telegram webhook, serve HTTP until stopped.

    Mirrors what Application.run_webhook does, except the HTTP server
    also answers Render's health check (GET /). Order matches PTB's
    run_webhook: initialize -> set webhook -> start update processing.
    `stop_event` is for tests; in production the process stops on
    SIGINT/SIGTERM (Render sends SIGTERM on deploy/shutdown).
    """
    await app.initialize()
    webhook_url = build_webhook_url()
    await app.bot.set_webhook(url=webhook_url, max_connections=40)
    # Log only the base URL: the full webhook URL contains the bot token
    # as its path, and the token must never appear in a log.
    log.info("Telegram webhook set (base %s)", get_webhook_base_url())
    await app.start()
    server = HTTPServer(build_webhook_app(app))
    server.listen(port, address="0.0.0.0")
    log.info(
        "Listening on 0.0.0.0:%s (webhook /%s, health GET /)",
        port, get_webhook_path(),
    )
    stop = stop_event or asyncio.Event()
    if stop_event is None:
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, ValueError, RuntimeError):
            pass  # signals unavailable (tests / non-main thread)
    await stop.wait()
    server.stop()
    await app.stop()
    await app.shutdown()


def run_webhook_server(app, port: int):
    """Blocking entry point: run the webhook server until stopped."""
    asyncio.run(serve_webhook(app, port))


# ----------------------------------------------------------------- main ---

def main():
    missing = [
        name
        for name, value in [
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("BOT_API_SECRET", BOT_API_SECRET),
            ("GEMINI_API_KEY", GEMINI_API_KEY),
        ]
        if not value
    ]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        raise SystemExit(1)
    if not get_webhook_base_url():
        log.error(
            "No webhook base URL: set WEBHOOK_URL, or run on Render where "
            "RENDER_EXTERNAL_URL is set automatically"
        )
        raise SystemExit(1)

    global paxyo
    paxyo = PaxyoClient()
    app = build_application()

    # TODO (later phase): a stall monitor that polls fetch_order_status()
    # via paxyo.order_status() for recent orders and, when the picked
    # service stalls, cancels/refunds and moves to the next-fastest service
    # from the same category. Not built in this version.

    log.info(
        "Paxyo Order bot starting (webhook %s, model %s, cloud-tts am %s / en %s)",
        build_webhook_url(), GEMINI_MODEL,
        GOOGLE_CLOUD_TTS_VOICE, GOOGLE_CLOUD_TTS_VOICE_EN,
    )
    run_webhook_server(app, get_webhook_port())


if __name__ == "__main__":
    main()
