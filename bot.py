#!/usr/bin/env python3
"""Paxyo Order bot (@paxorder_bot).

Users order Paxyo social-media services by text/chat or by voice message,
in Amharic or English. The bot talks to the Paxyo Bot API on paxyo.et and
uses ChatGPT (OpenAI) to understand what the user wants, falling back to
Gemini when no OpenAI key is set.

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
# OpenAI (ChatGPT) — the primary AI since 13 Nov 2026: the Gemini
# free-tier key kept hitting its per-minute limit (429), so when
# OPENAI_API_KEY is set the bot classifies, transcribes and reads
# pictures with OpenAI instead, and only falls back to Gemini when
# no OpenAI key is set. The key is a Render env var, never in code.
# gpt-4o-mini retires 2027-01-14; the model is an env var on
# purpose, so the switch is one setting, not a code change.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1"
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
# text with their own Amharic prompt; the behaviour contract is: classify
# what the user wants as JSON, and for orders extract the order fields.
# Never place an order, never discuss the provider or Paxyo's costs, keep
# replies short. (13 Nov 2026: extended from order-only extraction to
# full intent classification, because the owner found the bot "very dumb"
# — it answered "I did not understand" to balance, order-history,
# greeting and "I don't want to" messages.)
SYSTEM_PROMPT = """You are the Paxyo order assistant on Telegram. The user writes in
Amharic or English, by text or by voice transcription. You are a smart,
friendly customer-support assistant for Paxyo: you understand normal
human talk, answer questions about Paxyo, and help the user place
orders. Your job is to classify what the user wants and, for orders,
extract the intent as JSON.

Rules:
- Reply with JSON only, no extra text, no markdown fences.
- JSON shape: {"intent": "...", "platform": "...", "service_hint": "...",
  "service_id": 123, "link": "...", "quantity": 123,
  "interval_minutes": 180,
  "amount": 10, "method": "telebirr", "phone": "099387383",
  "quantity_multiplier": 2,
  "orders": [{"platform": "...", "service_hint": "...",
              "link": "...", "quantity": 123}],
  "split": {"quantity": 5000, "count": 5, "platform": "...",
            "service_hint": "..."}}
- intent: one of:
  - "order": the user wants to order a service (followers, likes, views,
    members...). Fill platform / service_hint / link / quantity when
    given; use null for anything not given.
  - "recurring": the user wants the same order repeated on a schedule
    ("order 1k views every 3 hours", "repeat this every day", "1k
    followers on that link every 2 hours"). Fill platform / service_hint
    / link / quantity / interval_minutes when given; use null for
    anything not given. interval_minutes is the repeat gap in minutes
    (3 hours = 180, 1 day = 1440, 30 minutes = 30). A drip-feed
    ("drip-feed 1,000 views every hour", "send 100 views every
    30 minutes") is also "recurring": quantity is the amount per drop,
    interval_minutes the gap between drops.
  - "schedules": the user asks what is repeating, what their repeating
    orders or schedules are ("what is repeating", "my schedules").
  - "stop_schedule": the user wants to stop or cancel a repeating
    order or schedule ("stop the repeating order", "cancel my schedule").
  - "balance": the user asks for their balance ("how much is my
    balance", "check my balance").
  - "orders": the user asks about their orders, order history or order
    status ("where is my order", "check my order history").
    Impatience about a placed order ("why hasn't it started yet",
    "it's been 45 seconds", "why is it taking so long") is also
    "orders".
  - "deposit": the user wants to deposit / add money to their Paxyo
    balance. Fill "amount" (the ETB amount as a number), "method"
    ("telebirr" or "cbe") and "phone" (the payment phone number) when
    given; use null for anything not given. Examples:
      "let me deposit 10 br by telebirr and my phone number is
       099387383" -> deposit, amount 10, method telebirr,
       phone 099387383
      "i wanna top up 50 birr" -> deposit, amount 50
      "add 100 etb cbe" -> deposit, amount 100, method cbe
      "deposit 20" -> deposit, amount 20
      "10 ብር ማስገባት እፈልጋለሁ" -> deposit, amount 10
      "ገንዘብ ማስገባት" -> deposit
    "br", "birr", "ብር" and "ETB" all mean ETB. "teleirr",
    "telebir", "teleberr" and "telbirr" are misspellings of Telebirr.
    A bare "how do I add money" is also "deposit" with everything null.
  - "deposit_status": the user asks whether a deposit went through,
    or says they paid and wants the deposit rechecked ("did my
    deposit go through?", "I paid but my balance didn't change",
    "check my deposit", "my deposit failed", "I deposited 10 birr,
    where is it", "ገንዘቤ ገብቷል?", "ከፍዬአለሁ ግን balanceዬ
    አልጨመረም", "I paid", "I approved it").
  - "help": the user asks for the help menu or the list of commands
    ("help", "/help", "what can you do?").
  - "how_to_order": the user does not know how to order, or asks how
    ordering works ("how do I order?", "I don't know how to order",
    "teach me how to order", "how does this work?", "what do I do
    here?", "እንዴት እዘዝ እችላለሁ?", "እንዴት ነው መግዛት?").
  - "miniapp": the user asks for the mini app ("mini app", "open the
    app", "where is the app?", "give me the mini app link", "ሚኒ አፕ").
  - "social": the user asks for Paxyo's social media or channel
    ("your social media", "paxyo social", "telegram channel", "where
    can I follow you?", "ሶሻል ሚዲያ").
  - "greeting": a greeting or small talk ("hello", "ሰላም").
  - "paxyo_info": a question about Paxyo itself — what it is, what
    services it has, prices, how it works, delivery times, support.
  - "source_question": the user asks where Paxyo's services come from,
    who supplies them, whether Paxyo resells, what Paxyo pays for
    them, or whether Paxyo is a panel ("who is your provider?",
    "where do you get the followers?", "are you a reseller?",
    "how much do you buy followers for?", "is this an SMM panel?",
    "who supplies your services?", "አቅራቢ ማን ነው?").
  - "usual": the user wants their usual order again ("give me the
    usual", "the usual please", "same as usual", "same thing as
    yesterday"). Fill quantity_multiplier when they want it scaled
    ("but double it" -> 2, "triple it" -> 3); use null otherwise.
  - "goal": the user states a goal instead of a service ("make my
    TikTok go viral", "I want to go viral", "grow my account fast",
    "boost my latest video"). Do not guess a service — the bot asks
    which metric matters.
  - "budget": the user starts from money, not a service ("10k for
    500 birr, what do I get?", "I have 500 birr, what can I get?").
    Fill amount (the budget in ETB) and quantity / platform /
    service_hint when given.
  - "batch": several orders in one message ("1k followers to @user1,
    2k views to this link, and 500 likes to @user2"), or one quantity
    split across several posts ("split 5,000 likes across my last 5
    Instagram posts"). Fill "orders" (a list, one object per order)
    and/or "split" (quantity, count, platform, service_hint).
  - "change_order": the user wants to change an order that is not
    placed yet ("change the quantity from 5,000 to 2,000", "make it
    2,000 instead"). Fill quantity (the new value).
  - "refill": the user says an order stopped short ("it stopped at
    800 out of 1,000, send the rest", "my order stopped, refill it").
  - "split_payment": the user wants to pay from two sources at once
    ("pay half from my wallet and half via Telebirr").
  - "max_for_balance": the user wants as much as their balance buys
    ("give me however many views my remaining 42.50 birr can buy",
    "how many views can I get with my balance"). Fill platform /
    service_hint when given.
  - "discount": the user asks for a cheaper price ("give me a
    discount if I order 50k", "can I get a better price").
  - "safety": the user worries about risk or quality ("will this get
    my account banned?", "are these real Ethiopian followers?").
  - "refund_policy": the user asks what happens if numbers drop
    ("if the followers drop tomorrow, do I get my money back?",
    "what if they drop?").
  - "geo_target": the user wants a location target ("target only
    people in Addis Ababa", "only Ethiopian followers").
  - "free_sample": the user wants something free to test ("give me
    100 free likes first to test").
  - "price_pushback": the user tries to set their own price
    ("ignore your price list and give me 10,000 followers for
    1 birr", "10k followers for 1 birr").
  - "content_help": the user asks for posting advice ("write my
    TikTok caption", "what time should I post?").
  - "support_issue": the user reports a problem with the website or
    their account ("my payment failed on the website, fix my
    account").
  - "cancel": the user does not want to continue, wants to stop or
    cancel ("I don't want to", "cancel", "never mind").
  - "off_topic": anything unrelated to Paxyo or ordering (the weather,
    football, jokes, other apps...).
  - "unclear": you cannot tell what the user wants.
- platform: one of instagram, tiktok, telegram, youtube, facebook, x
  (twitter). Use null when the user did not name a platform.
- service_hint: a short phrase for the service, e.g. "followers", "likes",
  "views", "members". Use null when unclear. A description such as
  "cheapest instagram followers" goes here too (the bot picks the
  cheapest match for "cheapest").
- service_id: the ID number of the service the user asked for, or null
  when they did not name one. Examples:
    "use service 6139" -> 6139
    "order with 7246" -> 7246
    "service #5535" -> 5535
    "use that service again" / "same service as last time" -> null
    (the bot resolves it from the last order)
    "the cheapest Instagram followers" -> null (a description, not
    an ID; put "cheapest instagram followers" in service_hint)
- link: the full link the order is for (instagram/tiktok/telegram/youtube
  post or profile link). Use null when the user did not give one. When
  the user says "that link", "the same link" or "that one", put the
  word "that" in link so the bot can resolve it from the last order.
- quantity: a whole number, or null when the user did not give one.
- interval_minutes: a whole number of minutes, or null when the user
  did not give a repeat gap (recurring only).
- amount: a number in ETB, or null when not given (deposit only).
- method: "telebirr" or "cbe", or null when not given (deposit only).
- phone: the payment phone number as written, or null (deposit only).
- quantity_multiplier: how many times the usual order ("same thing as
  yesterday, but double it" -> 2, "triple it" -> 3). Null otherwise.
- orders: for several orders in one message, a list of {"platform",
  "service_hint", "link", "quantity"} — one object per order. A
  bare @handle goes in "link". Null otherwise.
- split: for splitting one quantity across several posts ("split
  5,000 likes across my last 5 posts"): {"quantity": 5000, "count":
  5, "platform": "instagram", "service_hint": "likes"}. Null
  otherwise.
- Never place an order, never confirm an order, never quote a price.
- Never say where Paxyo's services come from, and never talk about
  what Paxyo pays for them. Only quote Paxyo's own ETB prices. If the
  user asks about that, use the "source_question" intent.
- For a message that is not an order, still classify the intent; do not
  return "order" with empty fields.
"""

# ------------------------------------------------------- Paxyo knowledge --
# Short facts about Paxyo, given to Gemini as context when the user asks
# a question about Paxyo itself (paxyo_info intent). The bot answers from
# these facts only — it never invents prices, delivery times or features,
# and never mentions the provider or Paxyo's costs.
PAXYO_KNOWLEDGE = """Facts about Paxyo:
- Paxyo (paxyo.et) is a service in Ethiopia where you order followers,
  likes, views and members for Instagram, TikTok, Telegram, YouTube,
  Facebook and X.
- Prices are in ETB per 1000 and are shown before the user confirms.
- The customer pays from their Paxyo balance; they deposit at paxyo.et
  with Telebirr or CBE Birr through Chapa.
- The bot picks the fastest available service for the order automatically
  and shows the estimated total before confirming. If the customer
  names a specific service (by ID or by name), the bot uses that
  service instead of the fastest one.
- The average delivery time of the picked service is shown before
  confirming; exact delivery time depends on the service.
- An order is placed only after the customer taps Confirm.
- How to order: tell the bot the platform, send the link, say how
  many, then tap Confirm.
- Paxyo delivers every order directly. If someone asks where the
  services come from or what Paxyo pays for them, say only that Paxyo
  delivers the order directly and the price shown is the price they
  pay.
- The Paxyo mini app: https://miniapp-one-1.onrender.com/
- Paxyo's Telegram channel: https://t.me/paxyo251. The customer bot
  is @paxyo_bot. Paxyo posts its updates on the Telegram channel.
- Support: this bot, or paxyo.et.
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

# Links the bot may hand out. These are the only Paxyo links the bot
# knows: the deployed mini app and the Telegram channel. Never invent
# Instagram, TikTok or other handles — Paxyo has none on file.
MINIAPP_URL = "https://miniapp-one-1.onrender.com/"
CHANNEL_URL = "https://t.me/paxyo251"

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
            "/help — እርዳታ\n\n"
            "“እንዴት እዘዝ እችላለሁ?” ብለው step-by-step መመሪያ ይጠይቁ።\n"
            "“ሚኒ አፕ” ብለው app link ያግኙ።\n"
            "“ሶሻል” ብለው Telegram channel ያግኙ።"
        ),
        "en": (
            "How it works:\n"
            "1. Send me the service, link and quantity.\n"
            "2. I find the fastest service for you.\n"
            "3. After you tap Confirm, the order is placed.\n\n"
            "/balance — check your balance\n"
            "/orders — status of your last order\n"
            "/help — help\n\n"
            "Ask “how do I order?” for a step-by-step guide.\n"
            "Ask “mini app” for the app link.\n"
            "Ask “social” for Paxyo's Telegram channel."
        ),
    },
    "how_to_order": {
        "am": (
            "እንዴት መዘዝ እንደሚቻል:\n"
            "1. Platform ይምረጡ (Instagram, TikTok, Telegram, YouTube...)።\n"
            "2. Link ይላኩ።\n"
            "3. Quantity ይንገሩኝ (ለምሳሌ 1000)።\n"
            "4. Confirm ያድርጉ — order ይፈጸማል።"
        ),
        "en": (
            "How to order:\n"
            "1. Tell me the platform (Instagram, TikTok, Telegram, YouTube...).\n"
            "2. Send your link.\n"
            "3. Tell me how many (for example 1000).\n"
            "4. Tap Confirm — I place the order and show you the order ID."
        ),
    },
    "miniapp": {
        "am": f"የPaxyo mini app እዚህ አለ: {MINIAPP_URL}",
        "en": f"Here is the Paxyo mini app: {MINIAPP_URL}",
    },
    "social": {
        "am": (
            f"Paxyo updates በTelegram channel ላይ ይለጠፋሉ: {CHANNEL_URL}\n"
            "Order ለማድረግ: @paxyo_bot"
        ),
        "en": (
            f"Paxyo posts updates on Telegram: {CHANNEL_URL}\n"
            "Order here: @paxyo_bot"
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
    "ask_deposit_amount": {
        "am": "ምን ያህል deposit ማድረግ ይፈልጋሉ? (ለምሳሌ 100)",
        "en": "How much do you want to deposit? (for example 100)",
    },
    "ask_deposit_method": {
        "am": "Telebirr ወይስ CBE?",
        "en": "Telebirr or CBE?",
    },
    "ask_deposit_phone": {
        "am": "የትኛውን ስልክ ቁጥር ልጠቀም? (ለምሳሌ 09...)",
        "en": "Which phone number should I use for the payment? (for example 09...)",
    },
    "not_understood": {
        "am": "አልገባኝም — እባክዎ እንደገና ይሞክሩ። ለምሳሌ: “1000 Instagram followers እፈልጋለሁ” ብለው link ይላኩልኝ።",
        "en": "I did not understand — please try again. For example: “I want 1000 Instagram followers” with your link.",
    },
    "gemini_busy": {
        "am": "አሁን ትንሽ ተጨናንቄያለሁ — እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ።",
        "en": "I am a bit busy right now — please try again in a moment.",
    },
    "no_service": {
        "am": "ለዚህ platform service አላገኘሁም። እባክዎ platform ይለውጡ።",
        "en": "I could not find a service for that platform. Please try another platform.",
    },
    # A service the user named by ID: it does not exist, is turned
    # off, or is blacklisted. All three offer the fastest service
    # instead, with one tap.
    "service_not_found": {
        "am": "ይህን service አላገኘሁም። ፈጣኑን ልጠቀም?",
        "en": "I couldn't find that service. Want me to use the fastest one instead?",
    },
    "service_disabled": {
        "am": "ይህ service አሁን ጠፍቷል። ፈጣኑን ልጠቀም?",
        "en": "That service is turned off right now. Want me to use the fastest one instead?",
    },
    "service_blacklisted": {
        "am": "ይህ service በPaxyo አይገኝም — እባክዎ ሌላ ይምረጡ።",
        "en": "That service isn't available on Paxyo — please choose another one.",
    },
    "use_fastest": {
        "am": "⚡ ፈጣኑን ተጠቀም",
        "en": "⚡ Use the fastest one",
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
    "deposit_too_big": {
        "am": "ይህ በጣም ብዙ ነው — በአንድ ጊዜ የሚያስገቡት ከፍተኛው 100,000 ETB ነው።",
        "en": "That's too much — the most you can deposit in one go is 100,000 ETB.",
    },
    "deposit_instructions": {
        "am": (
            "{amount} ETB በ{method} depositዎን ለማጠናቀቅ:\n"
            "{steps}\n"
            "ከከፈሉ በኋላ balance ወዲያው ይጨምራል።"
        ),
        "en": (
            "To finish your deposit of {amount} ETB by {method}:\n"
            "{steps}\n"
            "Your balance updates automatically once the payment succeeds."
        ),
    },
    "deposit_step_ussd": {
        "am": "📱 {code} ይደውሉ",
        "en": "📱 Dial {code}",
    },
    "deposit_step_pay_to": {
        "am": "ወደ: {pay_to} ይክፈሉ",
        "en": "Pay to: {pay_to}",
    },
    "deposit_step_link": {
        "am": "🔗 ይክፈቱ: {url}",
        "en": "🔗 Open: {url}",
    },
    "deposit_step_website": {
        "am": "🌐 paxyo.et ይክፈቱ → Deposit ይምረጡ",
        "en": "🌐 Open paxyo.et → Deposit",
    },
    # USSD push (Chapa Direct Charge): no code to dial, no link to open —
    # the payment prompt arrives on the user's own phone.
    "deposit_pushed": {
        "am": (
            "የ{amount} ETB በ{method} ክፍያ ጥያቄ ወደ ስልክዎ እየመጣ ነው — "
            "በ{method} PINዎ ያረጋግጡ።\n"
            "ከከፈሉ በኋላ balance ወዲያው ይጨምራል።"
        ),
        "en": (
            "A payment request for {amount} ETB by {method} is on its way "
            "to your phone — approve it with your {method} PIN.\n"
            "Your balance updates automatically once it succeeds."
        ),
    },
    "deposit_not_ready": {
        "am": "በchat deposit ገና አልተዘጋጀም — እባክዎ በpaxyo.et deposit ያድርጉ።",
        "en": "Deposit by chat is not ready yet — please deposit at paxyo.et.",
    },
    "deposit_failed": {
        "am": "Deposit መጀመር አልቻልኩም። እባክዎ እንደገና ይሞክሩ ወይም በpaxyo.et deposit ያድርጉ።",
        "en": "I couldn't start the deposit. Please try again or deposit at paxyo.et.",
    },
    # Deposit recheck ("did my deposit go through?"): the server
    # re-verifies with Chapa before answering, so the bot only
    # reports what the server says — it never invents a reason.
    "deposit_went_through": {
        "am": "አዎ — {amount} ETB depositዎ ገብቷል። Balanceዎ አሁን {balance} ETB ነው።",
        "en": "Yes — your {amount} ETB deposit went through. Your balance is now {balance} ETB.",
    },
    # Same, when the fresh balance could not be read: say the deposit
    # went through, do not guess a balance.
    "deposit_went_through_nobalance": {
        "am": "አዎ — {amount} ETB depositዎ ገብቷል።",
        "en": "Yes — your {amount} ETB deposit went through.",
    },
    "deposit_still_pending": {
        "am": "ገና አልገባም — በስልክዎ ላይ ያለው prompt ካለ በPINዎ ያጽድቁትና እንደገና ይጠይቁኝ። አጽድቀው ከሆነ ትንሽ ይጠብቁ።",
        "en": "Not yet — if the prompt is still on your phone, approve it with your PIN, then ask me again. If you already approved, give it a minute.",
    },
    "deposit_failed_reason": {
        "am": "Depositዎ አልተሳካም — {reason}። ገንዘብ አልተቀነሰብዎትም። እንደገና ይሞክሩ ወይም በpaxyo.et deposit ያድርጉ።",
        "en": "It failed — {reason}. You were not charged. Try again, or deposit at paxyo.et.",
    },
    "deposit_failed_check": {
        "am": "Depositዎ አልተሳካም። ገንዘብ አልተቀነሰብዎትም። እንደገና ይሞክሩ ወይም በpaxyo.et deposit ያድርጉ።",
        "en": "Your deposit failed. You were not charged. Try again, or deposit at paxyo.et.",
    },
    "no_deposits": {
        "am": "ገና deposit የለዎትም። deposit ማድረግ ይፈልጋሉ?",
        "en": "You have no deposits yet. Would you like to start one?",
    },
    "deposit_check_not_ready": {
        "am": "Deposit መፈተሽ ገና አልተዘጋጀም — እባክዎ በpaxyo.et Deposit History ይመልከቱ።",
        "en": "I can't check deposits yet — please check Deposit History at paxyo.et.",
    },
    # Photos: the bot reads a picture with Gemini vision and routes it
    # — a payment receipt to the deposit recheck, a profile/post
    # screenshot to the order flow, anything else to a short summary
    # plus one follow-up question.
    "photo_too_big": {
        "am": "ይህ ስዕል በጣም ትልቅ ነው — እባክዎ ትንሽ ስዕል ይላኩልኝ (ከ10 MB በታች)።",
        "en": "That picture is too big — please send a smaller one (under 10 MB).",
    },
    "photo_unreadable": {
        "am": "ይህን ስዕል ማንበብ አልቻልኩም — እባክዎ የሚያሳየውን በጽሑፍ ይላኩልኝ ወይም ግልጽ screenshot ይላኩልኝ።",
        "en": "I couldn't read that picture — can you type what it shows, or send a clearer screenshot?",
    },
    "photo_receipt_found": {
        "am": "{details} አይቻለሁ። ይህ depositዎ ነው — ገብቷል እንደሆነ ልፈትሽ?",
        "en": "I can see {details}. Is this your deposit — shall I check whether it landed?",
    },
    "photo_receipt_no_details": {
        "am": "የክፍያ screenshot አይቻለሁ፣ ግን amount ወይም reference ማንበብ አልቻልኩም። Amount በጽሑፍ ይላኩልኝ።",
        "en": "I can see a payment screenshot, but I couldn't read the amount or reference. Can you type the amount?",
    },
    "photo_order_username": {
        "am": "Profile {username} አገኘሁ — ለorder link ይላኩልኝ።",
        "en": "I found the profile {username} — please send the link for the order.",
    },
    "photo_other": {
        "am": "{summary}\nበዚህ ምን ላድርግ ይፈልጋሉ?",
        "en": "{summary}\nWhat would you like me to do with this?",
    },
    "check_deposit_button": {
        "am": "✅ አዎ, ፈትሽ",
        "en": "✅ Yes, check it",
    },
    "off_topic": {
        "am": "እኔ የPaxyo order bot ነኝ — በPaxyo order ላይ ብቻ እረዳለሁ። ምን ማዘዝ ይፈልጋሉ?",
        "en": "I'm the Paxyo order bot — I can only help with Paxyo orders. What would you like to order?",
    },
    "paxyo_info_fallback": {
        "am": "Paxyo የsocial media service ነው — followers, likes, views በpaxyo.et ይገኛሉ። ምን ማዘዝ ይፈልጋሉ?",
        "en": "Paxyo is a social media service — followers, likes and views at paxyo.et. What would you like to order?",
    },
    # Asked where the services come from, or what Paxyo pays for
    # them: one short polite deflection. It never confirms or denies
    # a supplier, never names one, and never gives a figure.
    # (Owner rule, 13 Nov 2026: the supply chain stays secret.)
    "source_question": {
        "am": (
            "Paxyo orderዎን በቀጥታ ያደርሳል — የሚያዩት ዋጋ የሚከፍሉት ዋጋ ነው። "
            "የምረዳዎት service አለ?"
        ),
        "en": (
            "Paxyo delivers your order directly — the price you see is "
            "the price you pay. Is there a service I can help you order?"
        ),
    },
    # Messy real-world inputs (owner edge-case spec, 13 Nov 2026):
    # short answers for goal/budget/trust/adversarial questions, and
    # the one-liners for mid-order changes, refills and split orders.
    # Nothing here invents a price, a time or a policy.
    "ask_metric": {
        "am": "የትኛው ይበልጥ አስፈላጊ ነው — views፣ likes፣ shares ወይስ followers?",
        "en": "Which one matters most — views, likes, shares or followers?",
    },
    "no_usual": {
        "am": "ገና የሚዘዙት 'usual' የለዎትም — platform እና link ይላኩልኝ፣ በሚቀጥለው ጊዜ አስታውሳለሁ።",
        "en": "I don't have a usual order for you yet — tell me the platform and link, and I'll remember it next time.",
    },
    "usual_note": {
        "am": "የተለመደው orderዎ:",
        "en": "Your usual:",
    },
    "usual_capped": {
        "am": "ከመጨረሻ orderዎ በእጥፍ አድርጌያለሁ — ግን ከservice ከፍተኛው ({max}) በላይ መሆን አይችልም።",
        "en": "Doubled from your last order — but capped at the service maximum ({max}).",
    },
    "split_ask_links": {
        "am": "{count} link ይላኩልኝ — አንድ በአንድ መስመር — {quantity} {metric} እካፍላለሁ ({each} ለእያንዳንዱ)።",
        "en": "Send the {count} links — one per line — and I'll split {quantity} {metric} across them ({each} each).",
    },
    "split_missing": {
        "am": "{got} ከ {count} link አገኘሁ — {missing} ገና ይቀራል።",
        "en": "I have {got} of {count} links — {missing} more to go.",
    },
    "batch_missing": {
        "am": "ተረድቻለሁ:\n{understood}\nየሚጎድል:\n{missing}",
        "en": "I understood:\n{understood}\nMissing:\n{missing}",
    },
    "batch_title": {
        "am": "{n} orders እባክዎ ያረጋግጡ:",
        "en": "Please confirm — {n} orders:",
    },
    "batch_total": {
        "am": "ጠቅላላ: {total} ETB",
        "en": "Total: {total} ETB",
    },
    "change_note": {
        "am": "Quantity ተቀይሯል: {quantity}።",
        "en": "Quantity updated: {quantity}.",
    },
    "already_placed": {
        "am": "Orderዎ አስቀድሞ ተልኳል — አሁን መቀየር አልችልም።",
        "en": "That order is already sent — I can't change it now.",
    },
    "no_order_to_change": {
        "am": "ለመቀየር የሚጠብቅ order የለዎትም — ምን ማዘዝ ይፈልጋሉ?",
        "en": "There's no order waiting to change — what would you like to order?",
    },
    "refill_running": {
        "am": "ገና እየሰራ ነው — {status}። ትንሽ ይጠብቁ።",
        "en": "Still running — {status}. Give it a little more time.",
    },
    "refill_finished": {
        "am": "Order ተጠናቋል ግን ቁጥሩ አልደረሰም — ስለ refill እባክዎ support ያነጋግሩ። እኔ ራሴ refill ወይም refund ቃል መግባት አልችልም።",
        "en": "It finished short — please contact support about a refill. I can't promise a refill or a refund myself.",
    },
    "order_wait": {
        "am": "Order {order_id}: {status}። {service} አብዛኛውን ጊዜ በ {avg} ውስጥ ይጀምራል።",
        "en": "Order {order_id}: {status}. {service} usually starts within {avg}.",
    },
    "split_payment_no": {
        "am": "በአንድ order አንድ የክፍያ ምንጭ ብቻ ነው: የTelebirr ክፍል መጀመሪያ deposit ያድርጉ፣ ከዚያ order ከwallet balance ይከፈላል።",
        "en": "One payment source per order: deposit the Telebirr half first, then the order comes from your wallet balance.",
    },
    "max_for_balance_none": {
        "am": "Balanceዎ ({balance} ETB) ለዚህ service ዝቅተኛውን አያሟላም — ትንሽ deposit ያድርጉ።",
        "en": "Your balance ({balance} ETB) doesn't cover the minimum for that service — deposit a little first.",
    },
    "max_for_balance_offer": {
        "am": "በ{balance} ETB {quantity} {metric} ማግኘት ይችላሉ። Link ይላኩልኝ — አረጋግጣለሁ።",
        "en": "Your {balance} ETB buys {quantity} {metric}. Send the link and I'll confirm.",
    },
    "discount_no": {
        "am": "ዋጋዎች ቋሚ ናቸው — ቅናሽ መስጠት አልችልም። በጣም ርካሹ {metric} {service} ነው — {price}።",
        "en": "Prices are fixed — I can't give discounts. The cheapest {metric} is {service} — {price}.",
    },
    "safety": {
        "am": "Services ቀስ በቀስ ይደርሳሉ እና በብዙ ሰዎች ጥቅም ላይ ይውላሉ፣ ግን ዜሮ risk እንደሌለ ማንም ዋስትና መስጠት አይችልም — followers ደግሞ ከአለም አቀፍ network ነው፣ እውነተኛ የኢትዮጵያ ሰዎች እንደሆኑ ዋስትና የለም። ቀስ ያለ service ልምረጥ?",
        "en": "These services deliver gradually and are widely used, but no one can guarantee zero risk — and followers come from a global network, not guaranteed to be real Ethiopian people. Want me to pick a slower, more gradual service?",
    },
    "refund_policy": {
        "am": "ቁጥር ከቀነሰ support ያነጋግሩ — የPaxyo team ይመረምራል። እኔ ራሴ refund ወይም refill ቃል መግባት አልችልም።",
        "en": "If numbers drop, contact support and the Paxyo team will review it — I can't promise a refund or a refill myself.",
    },
    "geo_no": {
        "am": "ይቅርታ — እነዚህ services Addis Ababa ብቻ target ማድረግ አይችሉም፤ በአለም አቀፍ ይደርሳሉ። ቢሆንም መቀጠል ይፈልጋሉ?",
        "en": "Sorry — these services can't target only Addis Ababa; they deliver globally. Want to go ahead anyway?",
    },
    "free_sample_no": {
        "am": "ነጻ likes መስጠት አልችልም — ትንሹ order የservice ዝቅተኛው ነው። ለመሞከር በጣም ርካሹ {service} ነው — {price}።",
        "en": "I can't give free likes — the smallest order is the service minimum. The cheapest way to test is {service} — {price}.",
    },
    "price_fixed": {
        "am": "ዋጋዎች በPaxyo ቋሚ ናቸው — በመጠየቅ አይለወጡም። በጣም ርካሹ {metric} {service} ነው — {price}።",
        "en": "Prices are fixed by Paxyo — asking can't change them. The cheapest {metric} is {service} — {price}.",
    },
    "content_help": {
        "am": "ፈጣን ምክሮች: ታዳሚዎ ሲነቃ post ያድርጉ (በኢትዮጵያ ምሽት ይሰራል)፣ caption አጭር ያድርጉት እና 2-3 hashtags ይጠቀሙ። Views/likes ማዘዝ ይፈልጋሉ?",
        "en": "Quick tips: post when your audience is awake (evenings work well in Ethiopia), keep the caption short with 2-3 hashtags. Want to order the views or likes for it?",
    },
    "support_redirect": {
        "am": "የwebsite account ራሴ ማስተካከል አልችልም — ግን deposit ከሆነ payment method እና ስልክ ቁጥር ይንገሩኝ እፈትሻለሁ፣ ወይም በpaxyo.et Deposit History ይመልከቱ። ለaccount ጉዳይ የPaxyo team ይመረምራል።",
        "en": "I can't fix the website account myself — but if it was a deposit, tell me the payment method and phone and I'll check it, or look at Deposit History at paxyo.et. The Paxyo team reviews account issues.",
    },
    "platform_mismatch": {
        "am": "ይህ link {link_platform} ነው፣ ግን {platform} ጠይቀዋል — የትኛው ትክክል ነው?",
        "en": "That link is {link_platform}, but you asked for {platform} — which one is right?",
    },
    "link_warning": {
        "am": "ማስጠንቅቂያ: private accounts እና በቅርብ የሚጠፉ stories አንዳንድ ጊዜ ይሳናሉ — link ትክክል መሆኑን እርግጠኛ ነዎት?",
        "en": "Heads up: private accounts and stories that expire soon sometimes fail — are you sure this link is right?",
    },
    "check_handle": {
        "am": "እባክዎ {handle} ስፔሊንግ ትክክል መሆኑን ይመልከቱ።",
        "en": "Please double-check the spelling of {handle} before confirming.",
    },
    "pending_reminder": {
        "am": "Orderዎ ({service} ×{quantity}) Confirm በመጠበቅ ላይ ነው።",
        "en": "Your order ({service} ×{quantity}) is still waiting for Confirm.",
    },
    "partial_reminder": {
        "am": "Order እየገነቡ ነው — {given} አለኝ።",
        "en": "You're still building an order — I have {given} so far.",
    },
    # Answers for questions about the order being built ("how fast
    # can you deliver it?", "wouldn't it drop?") — from the stored
    # service, instead of asking for the link again (13 Nov 2026).
    "pending_speed": {
        "am": "{service} በአብዛኛው በ {avg} ውስጥ ይጀምራል። Link ይላኩልኝ — orderዎን አረጋግጣለሁ።",
        "en": "{service} usually starts within {avg}. Send the link and I'll confirm your order.",
    },
    "pending_speed_unknown": {
        "am": "{service} — እስካሁን የመላኪያ ሰዓት የለኝም። Link ይላኩልኝ — orderዎን አረጋግጣለሁ።",
        "en": "{service} — I don't have a delivery time for it yet. Send the link and I'll confirm your order.",
    },
    "pending_drop": {
        "am": "{service}: {refill} Link ይላኩልኝ — orderዎን አረጋግጣለሁ።",
        "en": "{service}: {refill} Send the link and I'll confirm your order.",
    },
    "pending_no_refill": {
        "am": "refill የለውም — ቁጥር ከቀነሰ አይሞላም።",
        "en": "it has no refill — if numbers drop they are not topped up.",
    },
    "pending_has_refill": {
        "am": "refill አለው።",
        "en": "it includes a refill.",
    },
    "pending_refill_unknown": {
        "am": "ስለ refill ምንም ማስታወሻ አላየሁም።",
        "en": "I don't see a refill note on this service.",
    },
    # The fastest services are different kinds (views vs likes vs
    # comments) and no metric was named: ask which kind, instead of
    # silently picking the wrong one (13 Nov 2026 — a views order
    # got Tiktok Comment Likes).
    "ask_metric_choose": {
        "am": "የትኛውን ይፈልጋሉ — {metrics}? የሚፈልጉትን ይምረጡ።",
        "en": "Which one do you want — {metrics}? Reply with the one you want.",
    },
    "budget_ask": {
        "am": "ምን ያህል ገንዘብ አሎት? (ለምሳሌ 500 ETB)",
        "en": "How much money do you have? (for example 500 ETB)",
    },
    "budget_no_quantity": {
        "am": "በ{budget} ETB እነዚህን ማግኘት ይችላሉ — {options}። ስንት ይፈልጋሉ፣ እና የትኛውን?",
        "en": "With {budget} ETB you can afford these — {options}. How many would you like, and which one?",
    },
    "budget_options": {
        "am": "ለ{quantity} {metric}: {options}። የትኛውን?",
        "en": "For {quantity} {metric}: {options}. Which one?",
    },
    "budget_max": {
        "am": "{budget} ETB {quantity} {metric} አያገኝም — ግን እስከ {max_quantity} በ{name} ({total} ETB) ማግኘት ይችላሉ። ይህን ይፈልጋሉ?",
        "en": "Your {budget} ETB doesn't buy {quantity} {metric} — but it buys up to {max_quantity} with {name} ({total} ETB). Want that?",
    },
    "budget_too_small": {
        "am": "{budget} ETB ዝቅተኛውን አያሟላም — {minimum} {metric} በ{name} {total} ETB ያስከፍላል።",
        "en": "Your {budget} ETB doesn't cover the minimum — {minimum} {metric} costs {total} ETB with {name}.",
    },
    "safety_slow": {
        "am": "በጣም ቀስ ያለው {service} ነው — {avg}።",
        "en": "The slowest one I have is {service} — {avg}.",
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
    # Recurring orders: short, readable, never a wall of text.
    "ask_interval": {
        "am": "በየ ስንት ሰዓት ነው? (ለምሳሌ: በየ 3 ሰዓቱ)",
        "en": "How often? (for example: every 3 hours)",
    },
    "interval_too_short": {
        "am": "በጣም አጭር ነው — በትንሹ በየ 30 ደቂቃ ነው።",
        "en": "That's too often — the shortest repeat is every 30 minutes.",
    },
    "plan_started": {
        "am": (
            "ተጀምሯል! {quantity} {service} በየ {interval} እዘዝልዎታለሁ። "
            "በእያንዳንዱ order መልዕክት እልክልዎታለሁ።"
        ),
        "en": (
            "Started! I'll order {quantity} {service} every {interval}. "
            "I'll message you each time I place one."
        ),
    },
    "plan_failed": {
        "am": "Repeating order መጀመር አልቻልኩም። እባክዎ እንደገና ይሞክሩ።",
        "en": "I couldn't start the repeating order. Please try again.",
    },
    "no_schedules": {
        "am": "Repeating order የለዎትም።",
        "en": "You have no repeating orders.",
    },
    "schedule_stopped": {
        "am": "Repeating order ({service}) ቆሟል።",
        "en": "Stopped the repeating order for {service}.",
    },
    "stop_which": {
        "am": "የትኛውን ማቆም ይፈልጋሉ?",
        "en": "Which one do you want to stop?",
    },
    "stop_this_order": {
        "am": "🛑 ይህ order",
        "en": "🛑 This order",
    },
    "plan_paused": {
        "am": (
            "Repeating order ({service}) ቆሟል — balance አይበቃም። "
            "Balance: {balance} ETB, ያስፈልጋል: {total} ETB። "
            "በpaxyo.et deposit ካደረጉ በኋላ እንደገና እንዲጀምር ይንገሩኝ።"
        ),
        "en": (
            "Paused your repeating order for {service} — not enough balance. "
            "Balance: {balance} ETB, needed: {total} ETB. "
            "Deposit at paxyo.et, then tell me to start it again."
        ),
    },
    "recurring_placed": {
        "am": "Order ተፈጽሟል! {quantity} {service}\nOrder ID: {order_id}\nStatus: {status}",
        "en": "Order placed! {quantity} {service}\nOrder ID: {order_id}\nStatus: {status}",
    },
    "recurring_failed": {
        "am": "Repeating order በዚህ ዙር ማዘዝ አልቻልኩም — በሚቀጥለው ዙር እንደገና እሞክራለሁ።",
        "en": "Couldn't place your repeating order this time — I'll try again next round.",
    },
    "ask_which_schedule": {
        "am": "የትኛውን repeating order ማቆም ይፈልጋሉ?",
        "en": "Which repeating order do you want to stop?",
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


def parse_interval_minutes(text):
    """Parse a repeat gap from plain words to minutes, or None.

    Fallback for when Gemini did not return interval_minutes:
    "every 3 hours" -> 180, "every 2 days" -> 2880, "every 30
    minutes" -> 30, "hourly" -> 60, "daily" -> 1440. Returns the first
    number+unit pair found; a bare "every 3" with no unit is ignored.
    """
    if not text:
        return None
    s = str(text).strip().lower()
    if "hourly" in s or "every hour" in s:
        return 60
    if "daily" in s or "every day" in s or "each day" in s:
        return 1440
    units = {
        "day": 1440, "days": 1440,
        "hour": 60, "hours": 60, "hr": 60, "hrs": 60,
        "minute": 1, "minutes": 1, "min": 1, "mins": 1,
    }
    match = re.search(r"(\d+)\s*(days?|hours?|hrs?|minutes?|mins?)", s)
    if not match:
        return None
    return int(match.group(1)) * units[match.group(2)]


def format_interval(minutes):
    """Short human form of a repeat gap: 30 -> "30 minutes",
    180 -> "3 hours", 2880 -> "2 days"."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "?"
    if minutes <= 0:
        return "?"
    if minutes % 1440 == 0:
        n = minutes // 1440
        return f"{n} day" if n == 1 else f"{n} days"
    if minutes % 60 == 0:
        n = minutes // 60
        return f"{n} hour" if n == 1 else f"{n} hours"
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def mentions_same_service(text):
    """True when the user wants the service from their last order:
    "same service as last time", "use that service again", "the last
    service". Resolved from the most recent order, like "that link"."""
    s = " ".join((text or "").strip().lower().split())
    phrases = (
        "same service", "that service", "last service",
        "previous service", "service again", "service from last",
        "service from before",
    )
    return any(p in s for p in phrases)


SERVICE_ID_RE = re.compile(r"service\s*#?\s*(\d+)")
HASH_ID_RE = re.compile(r"#\s*(\d+)")
USE_ID_RE = re.compile(r"\b(?:use|with)\s+(\d+)\b")


def extract_service_id(text: str):
    """A service ID the user named, or None.

    Explicit forms only: "service 6139", "service #5535", "#6139",
    "use 6139", "with 7246", or a bare number. A bare number (or one
    after "use"/"with") only counts when it is at least 3 digits and
    NOT a multiple of 10, because quantities must be multiples of 10:
    "2000" is a quantity, "6139" is a service ID. Gemini's service_id
    field is the main path; this is the local fallback when it misses.
    """
    s = " ".join((text or "").strip().lower().split())
    match = SERVICE_ID_RE.search(s)
    if match:
        return int(match.group(1))
    match = HASH_ID_RE.search(s)
    if match:
        return int(match.group(1))
    match = USE_ID_RE.search(s)
    if match:
        value = int(match.group(1))
        if value >= 100 and value % 10 != 0:
            return value
    if re.fullmatch(r"\d+", s):
        value = int(s)
        if value >= 100 and value % 10 != 0:
            return value
    return None


def mentions_that_link(text):
    """True when the user refers to a link they already gave: "that
    link", "the same link", "that one", "order on that link again",
    "repeat this order". Used to resolve the link from their last
    order instead of asking for it again."""
    s = " ".join((text or "").strip().lower().split())
    phrases = (
        "that link", "same link", "that one", "the link from before",
        "last link", "same as last", "same as before", "again",
        "repeat this", "that post", "that video",
    )
    return any(p in s for p in phrases)


# --------------------------------------------- tolerant input ------
# Small explicit map of common misspellings and slang -> canonical
# words, plus Latin-letter Amharic -> fidels. This is NOT a
# spellchecker: only these known cases are fixed, so the bot tolerates
# the owner's typos ("teleirr", "blance", "amd") without guessing at
# words it has never seen.
TYPO_MAP = {
    # payment methods
    "teleirr": "telebirr", "telebir": "telebirr", "teleberr": "telebirr",
    "telbirr": "telebirr", "telebrr": "telebirr",
    "c.b.e": "cbe",
    # common typos
    "blance": "balance", "balence": "balance",
    "oder": "order", "ordr": "order",
    "histry": "history", "histroy": "history",
    "dipost": "deposit", "deposite": "deposit", "depost": "deposit",
    "amd": "and",
    "topup": "top up",
    # Latin-letter Amharic -> fidels (so "selam" reads as a greeting)
    "selam": "ሰላም",
    "ameseginalehu": "አመሰግናለሁ",
    "eshii": "እሺ",
    "awo": "አዎ",
}

# Payment method display names (same in both languages: brand names).
METHOD_LABELS = {"telebirr": "Telebirr", "cbe": "CBE Birr"}


def normalize_text(text: str) -> str:
    """Lowercase + fix known misspellings/slang, keeping URLs intact.

    URL tokens are left exactly as written — a TikTok short link is
    case-sensitive, so lowercasing the whole message would break it.
    Everything else is lowercased and run through TYPO_MAP word by
    word (punctuation around a word is kept). Chat shorthand for
    quantities is expanded too: "1k" -> "1000", "2.5k" -> "2500",
    "1m" -> "1000000". The expansion needs leading digits, so
    ordinary words ("ok") are untouched."""
    out = []
    for token in (text or "").split():
        if "://" in token or token.lower().startswith("www."):
            out.append(token)
            continue
        lead, core, trail = "", token, ""
        while core and core[0] in ".,!?;:\"'()[]{}":
            lead += core[0]
            core = core[1:]
        while core and core[-1] in ".,!?;:\"'()[]{}":
            trail = core[-1] + trail
            core = core[:-1]
        word = TYPO_MAP.get(core.lower(), core.lower())
        match = re.fullmatch(r"(\d+(?:\.\d+)?)([km])", word)
        if match:
            value = float(match.group(1)) * (
                1000 if match.group(2) == "k" else 1000000
            )
            word = str(int(value))
        out.append(lead + word + trail)
    return " ".join(out)


def normalize_phone(text):
    """Extract an Ethiopian phone number and normalize it to the
    2519xxxxxxxx / 2517xxxxxxxx form the API wants, or None.
    Accepts 09xxxxxxxx, 07xxxxxxxx, 2519xxxxxxxx, +2519xxxxxxxx
    (spaces and dashes ignored). The owner's example number
    "099387383" is one digit short of a real number, so the local
    and 251 forms accept 9 or 10 digits; the server validates the
    number for real when the deposit is created. A bare short
    number is not a phone."""
    if not text:
        return None
    compact = re.sub(r"[\s\-()]", "", str(text))
    m = re.search(r"\+?251([79]\d{7,8})", compact)
    if m:
        return "251" + m.group(1)
    m = re.search(r"0([79]\d{7,8})", compact)
    if m:
        return "251" + m.group(1)
    return None


def parse_deposit_amount(text):
    """First plausible ETB amount in the text, or None. Long digit
    runs (phone numbers) are skipped, so "deposit 10 br ... 099387383"
    gives 10, not the phone number."""
    if not text:
        return None
    for m in re.finditer(r"[\d,]+(?:\.\d+)?", str(text)):
        num = m.group(0).replace(",", "")
        if len(num.replace(".", "")) >= 9:
            continue
        try:
            value = float(num)
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def parse_money_amount(text):
    """An ETB amount that carries a currency word (br / birr / etb)
    next to it, or None. "1000 views" is a quantity, not money — a
    budget needs the currency word, so "I want 1000 views for this
    order now" is not a 1000 ETB budget, but "20 br" is. The word
    must sit right before or right after the number ("20 br",
    "br 20", "500birr"), punctuation stripped, so a currency word
    belonging to another number ("1000 views for 20 br") does not
    make the quantity look like money. Long digit runs (phone
    numbers) are skipped, like parse_deposit_amount."""
    if not text:
        return None
    s = str(text).lower()
    for m in re.finditer(r"[\d,]+(?:\.\d+)?", s):
        num = m.group(0).replace(",", "")
        if len(num.replace(".", "")) >= 9:
            continue
        try:
            value = float(num)
        except ValueError:
            continue
        if value <= 0:
            continue
        before = re.findall(r"[a-z]+", s[max(0, m.start() - 8):m.start()])
        after = re.findall(r"[a-z]+", s[m.end():m.end() + 8])
        if (before and before[-1] in ("br", "birr", "etb")) or (
            after and after[0] in ("br", "birr", "etb")
        ):
            return value
    return None


def normalize_method(text):
    """Telebirr or CBE from plain words (typos already fixed by
    normalize_text), or None when no payment method is named."""
    s = normalize_text(text)
    if "telebirr" in s:
        return "telebirr"
    if "cbe" in s or "commercial" in s:
        return "cbe"
    return None


# Words in a service description that are qualifiers, not part of a
# service name: "cheapest" also switches the ranking to price.
HINT_QUALIFIERS = {
    "cheapest", "lowest", "price", "best", "fastest", "top",
    "the", "a", "an", "one",
}


# Words that must never be shown to a user inside a service name: the
# supply chain is the owner's secret (13 Nov 2026). API service names
# can carry them, so every name is cleaned at display time only —
# matching in pick_services still uses the raw name.
_SERVICE_NAME_BANNED = (
    r"smm\s*panel", r"god\s*of\s*panel", r"\bsmm\b", r"\bpanel\b",
    r"\bprovider\b", r"\bwholesale\b", r"\bresell\w*\b",
)


def clean_service_name(name):
    """Strip supply-chain words out of a service name before showing
    it to a user. Returns "" when there is no name at all, so callers
    can fall back to the service id; returns "service" when stripping
    leaves nothing behind."""
    if not name:
        return ""
    s = str(name)
    for pattern in _SERVICE_NAME_BANNED:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    parts = [p.strip() for p in s.split("|")]
    s = " | ".join(p for p in parts if p)
    s = re.sub(r"\s+", " ", s).strip(" -–—")
    return s or "service"


def pick_services(services, platform=None, service_hint=None, limit=3):
    """Rank services for a platform, fastest average time first.

    Excludes blacklisted and inactive services. Services with no average
    time sort last. Returns at most `limit` services. A description
    hint ("cheapest instagram followers") is matched word by word
    against the service name and category — EVERY word of the hint
    must appear, so "tiktok views" never matches "TikTok Video Save"
    or "Tiktok Comment Likes" just because they say "tiktok" (13 Nov
    2026 — the bot offered saves and comment likes for a views
    order). "cheapest" ranks by price (lowest first) instead of by
    time.
    """
    wanted = (platform or "").strip().lower()
    hint = (service_hint or "").strip().lower()
    cheapest = False
    words = []
    for word in hint.split():
        if word in ("cheapest", "lowest"):
            cheapest = True
        elif word in HINT_QUALIFIERS:
            continue
        else:
            words.append(word)
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
        if words:
            hay = name + " " + category
            if not all(w in hay for w in words):
                continue
        candidates.append(s)
    if cheapest:
        candidates.sort(
            key=lambda s: (
                float(s.get("rate_etb_per_1000") or 0),
                parse_average_time(s.get("average_time")) or 0,
            )
        )
    else:
        candidates.sort(
            key=lambda s: (
                parse_average_time(s.get("average_time")) is None,
                parse_average_time(s.get("average_time")) or 0,
            )
        )
    return candidates[:limit]


def find_service_by_id(services, service_id):
    """The service with this ID, or None. No active/blacklist check —
    the caller decides what a found-but-unusable service means."""
    try:
        wanted = int(service_id)
    except (TypeError, ValueError):
        return None
    for s in services:
        try:
            if int(s.get("service", 0)) == wanted:
                return s
        except (TypeError, ValueError):
            continue
    return None


def resolve_named_service(services, service_id):
    """Validate a service the user named by ID.

    Returns (service, error): error is None on success, otherwise one
    of "blacklisted", "not_found", "disabled". The blacklist is
    checked first, so a blacklisted ID is refused even if the service
    exists and is active — a blacklisted service is never used.
    """
    try:
        wanted = int(service_id)
    except (TypeError, ValueError):
        return None, "not_found"
    if wanted in BLACKLISTED_SERVICES:
        return None, "blacklisted"
    service = find_service_by_id(services, wanted)
    if service is None:
        return None, "not_found"
    if not service.get("active", True):
        return None, "disabled"
    return service, None


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
        """GET /services, cached for SERVICES_CACHE_SECONDS.

        The API returns each service with `id` and `price` (ETB per
        1000); the bot reads `service` and `rate_etb_per_1000`.
        Normalised here, once, so every caller sees the bot's shape
        — without it every price reads 0 and the order placement
        crashes on the missing service ID.
        """
        import time

        now = time.monotonic()
        if (
            self._services_cache is not None
            and now - self._services_cached_at < SERVICES_CACHE_SECONDS
        ):
            return self._services_cache
        data = await self._send(build_api_request("GET", "/services"))
        raw = data.get("services", data) if isinstance(data, dict) else data
        services = []
        for s in raw or []:
            if not isinstance(s, dict):
                continue
            services.append({
                **s,
                "service": s.get("service", s.get("id")),
                "rate_etb_per_1000": s.get(
                    "rate_etb_per_1000", s.get("price", 0)
                ),
            })
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

    async def recent_orders(self, telegram_id: int, limit: int = 5):
        """GET /orders?telegram_id=&limit= — the user's most recent
        orders, newest first. The bot's memory of the last link lives
        here (server-side, so it survives restarts): "that link" and
        "order on that link again" resolve from the newest order.
        A 404 means the endpoint is not live yet — returns []."""
        try:
            data = await self._send(
                build_api_request(
                    "GET", f"/orders?telegram_id={telegram_id}&limit={limit}"
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /orders returned 404 (endpoint not live yet)")
                return []
            raise
        if isinstance(data, dict):
            orders = data.get("orders", [])
        else:
            orders = data
        return orders if isinstance(orders, list) else []

    # --------------------------------------------- recurring orders ----
    # Contract (server side, built in parallel): a recurring_orders
    # table with id, user_id (telegram id), service_id, link, quantity,
    # interval_minutes, next_run_at, active. All calls carry the
    # X-Bot-Secret header like the rest of the client.

    async def create_recurring(self, telegram_id: int, service_id: int,
                               link: str, quantity: int, interval_minutes: int):
        """POST /recurring -> {"id", "next_run_at"}."""
        return await self._send(
            build_api_request(
                "POST",
                "/recurring",
                {
                    "telegram_id": telegram_id,
                    "service_id": service_id,
                    "link": link,
                    "quantity": quantity,
                    "interval_minutes": interval_minutes,
                },
            )
        )

    async def list_recurring(self, telegram_id: int):
        """GET /recurring?telegram_id= -> active schedules, newest first."""
        data = await self._send(
            build_api_request("GET", f"/recurring?telegram_id={telegram_id}")
        )
        if isinstance(data, dict):
            schedules = data.get("schedules", data.get("recurring", []))
        else:
            schedules = data
        return schedules if isinstance(schedules, list) else []

    async def cancel_recurring(self, schedule_id, telegram_id: int):
        """POST /recurring/{id}/cancel {telegram_id}."""
        return await self._send(
            build_api_request(
                "POST", f"/recurring/{schedule_id}/cancel",
                {"telegram_id": telegram_id},
            )
        )

    async def pause_recurring(self, schedule_id, telegram_id: int):
        """POST /recurring/{id}/pause {telegram_id} — balance too low."""
        return await self._send(
            build_api_request(
                "POST", f"/recurring/{schedule_id}/pause",
                {"telegram_id": telegram_id},
            )
        )

    async def due_recurring(self):
        """GET /recurring/due (secret-only) -> active schedules whose
        next_run_at is now or past. Used by the scheduler loop."""
        data = await self._send(build_api_request("GET", "/recurring/due"))
        if isinstance(data, dict):
            schedules = data.get("schedules", data.get("due", []))
        else:
            schedules = data
        return schedules if isinstance(schedules, list) else []

    async def mark_recurring_ran(self, schedule_id, telegram_id: int, order_id):
        """POST /recurring/{id}/ran {telegram_id, order_id} — the server
        advances next_run_at from NOW (never from a stale time, so a
        schedule that slept only ever runs once on wake)."""
        return await self._send(
            build_api_request(
                "POST", f"/recurring/{schedule_id}/ran",
                {"telegram_id": telegram_id, "order_id": order_id},
            )
        )

    # --------------------------------------------- deposits by chat ----
    # Contract (server side, built in parallel): POST /deposits creates
    # a Chapa checkout for the user; the server credits the balance
    # only after Chapa confirms the payment. The bot never credits
    # anything itself — it only shows the payment instructions.

    async def create_deposit(self, telegram_id: int, amount, method: str, phone: str):
        """POST /deposits {telegram_id, amount, method, phone} ->
        {"deposit_id","checkout_url","ussd_code","pay_to","status"}.
        ussd_code / pay_to may be null when Chapa only gives a
        checkout link. A 404 means the endpoint is not live yet —
        returns None so the caller can say deposit-by-chat is not
        ready yet."""
        try:
            return await self._send(
                build_api_request(
                    "POST",
                    "/deposits",
                    {
                        "telegram_id": telegram_id,
                        "amount": amount,
                        "method": method,
                        "phone": phone,
                    },
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("POST /deposits returned 404 (endpoint not live yet)")
                return None
            raise

    async def list_deposits(self, telegram_id: int, limit: int = 5):
        """GET /deposits?telegram_id=&limit= — the user's most recent
        deposits, newest first. A 404 means the endpoint is not live
        yet — returns None (distinct from []: no deposits at all)."""
        try:
            data = await self._send(
                build_api_request(
                    "GET", f"/deposits?telegram_id={telegram_id}&limit={limit}"
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /deposits returned 404 (endpoint not live yet)")
                return None
            raise
        if isinstance(data, dict):
            deposits = data.get("deposits", [])
        else:
            deposits = data
        return deposits if isinstance(deposits, list) else []

    async def deposit_status(self, deposit_id, telegram_id: int):
        """GET /deposits/{id}?telegram_id= — the deposit record. The
        server re-verifies with Chapa when the deposit is still
        pending before answering, so this call IS the recheck: the
        bot never credits anything itself. A 404 means the endpoint
        is not live yet — returns None."""
        try:
            data = await self._send(
                build_api_request(
                    "GET", f"/deposits/{deposit_id}?telegram_id={telegram_id}"
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /deposits/{id} returned 404 (endpoint not live yet)")
                return None
            raise
        if isinstance(data, dict):
            deposit = data.get("deposit", data)
        else:
            deposit = data
        return deposit if isinstance(deposit, dict) else None


async def _gemini_post(payload: dict) -> dict:
    """One POST to the Gemini API, with retries on rate limits.

    The free-tier key trips its per-minute limit easily when several
    messages arrive at once (429) or the model is overloaded (503),
    so those two statuses retry after 5s then 15s. Any other error
    raises at once — the caller decides what the user hears. The
    client shape is kept exactly as the three callers used it
    (timeout 120s, trust_env False, params key, json payload), so
    tests that mock the client still pass.
    """
    url = GEMINI_URL.format(model=GEMINI_MODEL)
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, params={"key": GEMINI_API_KEY}, json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 503) and attempt < 2:
                log.warning("Gemini %s, retrying (attempt %d of 3)", status, attempt + 2)
                continue
            raise


async def gemini_generate(prompt: str, system: str = None) -> str:
    """One Gemini text call. Returns the reply text (may be empty)."""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    data = await _gemini_post(payload)
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
    data = await _gemini_post(payload)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return ""


# ------------------------------------------------------- Gemini vision ----
# Photos: a customer sends a picture (payment receipt, profile/post
# screenshot, error screenshot) and the bot reads it with Gemini
# vision. The picture bytes stay in memory only — they are never
# written to disk, and are sent nowhere except this one Gemini call
# the user implicitly asked for by sending the picture to the bot.
VISION_PROMPT = """You are the Paxyo order bot. Read this picture a customer sent.
Extract: any text, amounts in ETB, phone numbers, transaction
references, usernames, profile/post links, error messages. Then say
in one or two lines what the customer most likely wants (e.g.
'payment receipt for a deposit', 'screenshot of an Instagram profile
to order followers for', 'error screenshot'). Reply as compact JSON:
{"summary": ..., "amount": ..., "phone": ..., "tx_ref": ...,
"link": ..., "username": ...,
"want": "deposit_receipt"|"order"|"support"|"other"}"""

MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB: larger pictures are refused


async def gemini_vision(image_bytes: bytes, prompt: str = VISION_PROMPT) -> str:
    """Read a picture with Gemini vision. Returns the reply text (may
    be empty). Telegram photos are JPEG, so the image is sent as
    image/jpeg inline data, same shape as gemini_transcribe's audio.
    Raises on HTTP errors — the caller turns that into one short
    "couldn't read that picture" reply and never retries in a loop."""
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode(),
                        }
                    },
                ]
            }
        ]
    }
    data = await _gemini_post(payload)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return ""


# -------------------------------------------------------- OpenAI ------
# ChatGPT is the primary AI (13 Nov 2026): the Gemini free-tier key
# kept hitting its per-minute limit, so when OPENAI_API_KEY is set
# the bot classifies, transcribes and reads pictures with OpenAI
# instead. The three functions mirror the Gemini ones exactly (same
# inputs, same outputs, same retry shape), and the ai_* wrappers
# below pick OpenAI first and Gemini second — so with no OpenAI key
# the bot behaves exactly as before.

async def _openai_post(path: str, headers=None, json=None, data=None,
                       files=None) -> dict:
    """One POST to the OpenAI API, with retries on rate limits and
    server errors. Same shape as _gemini_post (two retries, after
    5s then 15s; 500 joins 429/503 here because OpenAI returns it
    for overloaded models). The client shape is identical (timeout
    120s, trust_env False). `files` values are bytes, so a retried
    multipart upload re-sends cleanly."""
    url = OPENAI_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(
                    url, headers=headers, json=json, data=data, files=files
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning("OpenAI %s, retrying (attempt %d of 3)", status, attempt + 2)
                continue
            raise


def _openai_headers() -> dict:
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"}


async def openai_generate(prompt: str, system: str = None) -> str:
    """One ChatGPT text call. Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _openai_post(
        "/chat/completions",
        headers=_openai_headers(),
        json={"model": OPENAI_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


async def openai_transcribe(audio_bytes: bytes) -> str:
    """Transcribe a Telegram voice message (.ogg) with Whisper."""
    data = await _openai_post(
        "/audio/transcriptions",
        headers=_openai_headers(),
        data={"model": "whisper-1"},
        files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
    )
    return str(data.get("text") or "").strip()


async def openai_vision(image_bytes: bytes, prompt: str = VISION_PROMPT) -> str:
    """Read a picture with ChatGPT vision. Returns the reply text
    (may be empty). Telegram photos are JPEG, sent as a base64 data
    URI — the same picture bytes the Gemini call used to get."""
    data = await _openai_post(
        "/chat/completions",
        headers=_openai_headers(),
        json={
            "model": OPENAI_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,"
                                   + base64.b64encode(image_bytes).decode(),
                        },
                    },
                ],
            }],
        },
    )
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


async def ai_generate(prompt: str, system: str = None) -> str:
    """Text from the AI: ChatGPT when OPENAI_API_KEY is set, else
    Gemini. Every caller uses this, so the provider switch is one
    env var and the fallback is automatic."""
    if OPENAI_API_KEY:
        return await openai_generate(prompt, system=system)
    return await gemini_generate(prompt, system=system)


async def ai_transcribe(audio_bytes: bytes) -> str:
    """Voice transcription: Whisper when OPENAI_API_KEY is set, else
    Gemini."""
    if OPENAI_API_KEY:
        return await openai_transcribe(audio_bytes)
    return await gemini_transcribe(audio_bytes)


async def ai_vision(image_bytes: bytes, prompt: str = VISION_PROMPT) -> str:
    """Picture reading: ChatGPT vision when OPENAI_API_KEY is set,
    else Gemini vision."""
    if OPENAI_API_KEY:
        return await openai_vision(image_bytes, prompt=prompt)
    return await gemini_vision(image_bytes, prompt=prompt)


def parse_vision_result(text: str):
    """Parse Gemini vision output into a dict, or None when it has no
    usable JSON. Unknown/missing "want" becomes "other"; "amount" is
    coerced to a float when it parses. All fields default to None."""
    obj = extract_json(text)
    if obj is None:
        return None
    want = str(obj.get("want") or "").strip().lower()
    if want not in ("deposit_receipt", "order", "support", "other"):
        want = "other"
    amount = obj.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    return {
        "summary": obj.get("summary"),
        "amount": amount,
        "phone": obj.get("phone"),
        "tx_ref": obj.get("tx_ref"),
        "link": obj.get("link"),
        "username": obj.get("username"),
        "want": want,
    }


def platform_from_link(link: str):
    """Platform from a link's domain, or None. Used when a photo
    gives a profile/post link: the order flow can then skip the
    'which platform?' question and go straight to 'how many?'."""
    if not link:
        return None
    host = str(link).strip().lower()
    for domain, platform in (
        ("instagram.com", "instagram"),
        ("tiktok.com", "tiktok"),
        ("t.me", "telegram"),
        ("youtube.com", "youtube"),
        ("youtu.be", "youtube"),
        ("facebook.com", "facebook"),
        ("fb.com", "facebook"),
        ("x.com", "x"),
        ("twitter.com", "x"),
    ):
        if domain in host:
            return platform
    return None


_PLATFORMS = ("instagram", "tiktok", "telegram", "youtube", "facebook", "x")
_METRICS = (
    "followers", "likes", "views", "subscribers", "members", "shares",
    "comments",
)


def local_intent(text: str) -> dict:
    """Best-effort intent without Gemini — the silence fallback.

    Used only when the Gemini call itself fails (rate limit, outage).
    Reads the message with the same local helpers the order flow
    already uses: links, phone, amount, method, interval, service ID.
    Deliberately conservative: anything it cannot pin down stays
    None, and the caller answers with the busy line instead of going
    silent. Same shape as extract_intent's dict, plus
    "gemini_failed": True.
    """
    intent = {
        "intent": None, "platform": None, "service_hint": None,
        "service_id": None, "link": None, "quantity": None,
        "interval_minutes": None, "amount": None, "method": None,
        "phone": None, "quantity_multiplier": None, "orders": None,
        "split": None, "gemini_failed": True,
    }
    s = normalize_text(text)
    words = set(re.findall(r"[a-z]+", s.lower()))
    links = extract_links(text)
    if links:
        intent["link"] = links[0]
        intent["platform"] = platform_from_link(links[0])
    if intent["platform"] is None:
        intent["platform"] = next(
            (w for w in _PLATFORMS if w in words), None
        )
    metric = next((w for w in _METRICS if w in words), None)
    if intent["platform"] or metric:
        intent["service_hint"] = " ".join(
            p for p in (intent["platform"], metric) if p
        )
    for m in re.finditer(r"\d[\d,]*", s):
        try:
            value = int(m.group(0).replace(",", ""))
        except ValueError:
            continue
        if 10 <= value <= 1000000 and value % 10 == 0:
            intent["quantity"] = value
            break
    intent["service_id"] = extract_service_id(text)
    # A budget amount is the currency-aware one when there is one:
    # "10k for 500 birr" budgets 500, not 10000. Otherwise the first
    # plausible number, as before.
    money = parse_money_amount(s)
    intent["amount"] = money if money is not None else parse_deposit_amount(s)
    intent["method"] = normalize_method(text)
    intent["phone"] = normalize_phone(text)
    interval = parse_interval_minutes(text)
    if interval:
        intent["interval_minutes"] = interval
    if "double" in words:
        intent["quantity_multiplier"] = 2
    elif "triple" in words:
        intent["quantity_multiplier"] = 3
    if is_paid_phrase(text) or any(
        p in s for p in (
            "did my deposit", "my deposit go", "check my deposit",
            "deposit failed", "deposit not",
        )
    ):
        intent["intent"] = "deposit_status"
    elif any(
        p in s for p in (
            "deposit", "top up", "add money", "recharge", "add balance",
        )
    ):
        intent["intent"] = "deposit"
    elif "balanc" in s:
        intent["intent"] = "balance"
    elif any(
        p in s for p in (
            "my orders", "order history", "order status", "show orders",
            "my order", "latest order", "last order",
        )
    ):
        intent["intent"] = "orders"
    elif "the usual" in s or "same as yesterday" in s or "same as last" in s:
        intent["intent"] = "usual"
    elif "mini app" in s or "miniapp" in s:
        intent["intent"] = "miniapp"
    elif "social" in s:
        intent["intent"] = "social"
    elif any(
        p in s for p in (
            "how do i order", "how to order", "how can i order",
            "how do i buy",
        )
    ):
        intent["intent"] = "how_to_order"
    elif "stop" in words and (
        "repeat" in words or "recurr" in s or "every" in words
    ):
        intent["intent"] = "stop_schedule"
    elif "cancel" in s:
        intent["intent"] = "cancel"
    elif "my schedule" in s or "my schedules" in s or "recurring orders" in s:
        intent["intent"] = "schedules"
    elif "every" in words and interval:
        intent["intent"] = "recurring"
    elif "viral" in words:
        intent["intent"] = "goal"
    elif (
        money is not None
        and (intent["platform"] or metric)
        and ("how much" in s or "how many" in s or "can i" in s)
        and "for" not in words
    ):
        # "If I have 100 etb how much tiktok views can I order" —
        # money they have, a platform/metric, a how-much question,
        # and no "for <money>" budget phrasing: the bot
        # reverse-calculates from the real balance.
        intent["intent"] = "max_for_balance"
    elif (
        money is not None
        and intent["quantity"] is not None
        and ("for" in words or "how much" in s or "how many" in s)
    ):
        # A budget needs a currency word on the amount: "1000 views
        # for this order" is a quantity, not 1000 ETB. "How much can
        # 20 br get me" has the currency word and the how-much
        # phrasing, so it is a budget even without "for".
        intent["intent"] = "budget"
    elif (
        links
        or intent["quantity"] is not None
        or intent["platform"]
        or metric
        or intent["service_id"] is not None
    ):
        intent["intent"] = "order"
    elif s.strip() in ("hi", "hello", "hey", "selam", "ሰላም") or any(
        s.strip().startswith(prefix)
        for prefix in ("hi ", "hello ", "hey ", "selam ")
    ):
        intent["intent"] = "greeting"
    elif is_source_question(text):
        intent["intent"] = "source_question"
    return intent


async def extract_intent(text: str) -> dict:
    """Ask the AI (ChatGPT when configured, else Gemini) to classify
    the message and extract the order intent.

    The text is normalised first (typos/slang fixed, URLs kept
    verbatim), so "let me deposit 10 br by teleirr" still classifies
    as a deposit. Returns {"intent": ..., "platform": ...,
    "service_hint": ..., "service_id": ..., "link": ..., "quantity": ...,
    "interval_minutes": ..., "amount": ..., "method": ...,
    "phone": ..., "quantity_multiplier": ..., "orders": ...,
    "split": ...}. intent is one of order, recurring, schedules,
    stop_schedule, balance, orders, deposit, deposit_status, help,
    how_to_order, miniapp, social, greeting, paxyo_info,
    source_question, usual, goal, budget, batch, change_order,
    refill, split_payment, max_for_balance, discount, safety,
    refund_policy, geo_target, free_sample, price_pushback,
    content_help, support_issue, cancel, off_topic, unclear — or
    None when the model output had no usable JSON.
    """
    try:
        reply = await ai_generate(normalize_text(text), system=SYSTEM_PROMPT)
    except Exception:
        # The AI is unreachable (rate limit, outage). Answer from the
        # message itself instead of going silent — see local_intent.
        log.warning("AI classify failed, using local fallback", exc_info=True)
        return local_intent(text)
    intent = extract_json(reply)
    if intent is None:
        return {
            "intent": None,
            "platform": None,
            "service_hint": None,
            "service_id": None,
            "link": None,
            "quantity": None,
            "interval_minutes": None,
            "amount": None,
            "method": None,
            "phone": None,
            "quantity_multiplier": None,
            "orders": None,
            "split": None,
        }
    # "that" is not a link — the prompt puts it there when the user
    # says "that link". Normalise it to None so the caller resolves
    # it from the user's last order instead of ordering "that".
    link = intent.get("link")
    if isinstance(link, str) and link.strip().lower() in (
        "that", "that link", "the same link", "same link",
    ):
        link = None
    amount = intent.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    method = intent.get("method")
    if isinstance(method, str):
        method = normalize_method(method)
    else:
        method = None
    phone = intent.get("phone")
    if isinstance(phone, str):
        phone = normalize_phone(phone)
    else:
        phone = None
    service_id = intent.get("service_id")
    try:
        service_id = int(service_id) if service_id is not None else None
    except (TypeError, ValueError):
        service_id = None
    # "Double it" on the usual order: how many times the last order.
    multiplier = intent.get("quantity_multiplier")
    try:
        multiplier = float(multiplier) if multiplier is not None else None
    except (TypeError, ValueError):
        multiplier = None
    if multiplier is not None and multiplier <= 0:
        multiplier = None
    # Several orders in one message: a list of small order dicts.
    # Quantities are coerced to ints; anything unusable is dropped
    # here so the batch handler only sees clean drafts.
    orders = intent.get("orders")
    clean_orders = None
    if isinstance(orders, list):
        clean_orders = []
        for entry in orders:
            if not isinstance(entry, dict):
                continue
            qty = entry.get("quantity")
            try:
                qty = int(qty) if qty is not None else None
            except (TypeError, ValueError):
                qty = None
            clean_orders.append({
                "platform": entry.get("platform"),
                "service_hint": entry.get("service_hint"),
                "link": entry.get("link"),
                "quantity": qty,
            })
        if not clean_orders:
            clean_orders = None
    split = intent.get("split")
    if not isinstance(split, dict):
        split = None
    return {
        "intent": intent.get("intent"),
        "platform": intent.get("platform"),
        "service_hint": intent.get("service_hint"),
        "service_id": service_id,
        "link": link,
        "quantity": intent.get("quantity"),
        "interval_minutes": intent.get("interval_minutes"),
        "amount": amount,
        "method": method,
        "phone": phone,
        "quantity_multiplier": multiplier,
        "orders": clean_orders,
        "split": split,
    }


async def answer_paxyo_question(text: str, lang: str) -> str:
    """Answer a question about Paxyo itself (paxyo_info intent).

    The AI answers from PAXYO_KNOWLEDGE only, in the user's language,
    in 1-3 short sentences. Falls back to a short canned line when the
    model gives nothing usable. Never mentions the provider or costs.
    """
    system = (
        PAXYO_KNOWLEDGE
        + "\nAnswer the user's question using only these facts, in "
        + ("Amharic (Ethiopic fidels mixed with English) — " if lang == "am"
           else "English — ")
        + "1-3 short sentences. If the question is about something outside "
        "Paxyo, answer in one short line steering back to ordering. "
        "Never say where Paxyo's services come from, and never talk "
        "about what Paxyo pays for them. Never quote a price; say "
        "prices are shown in ETB per 1000 before confirming."
    )
    try:
        reply = await ai_generate(text, system=system)
    except Exception as exc:
        log.warning("paxyo_info answer failed: %s", exc)
        return t("paxyo_info_fallback", lang)
    answer = (reply or "").strip()
    return answer if answer else t("paxyo_info_fallback", lang)


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
# A named service that turned out unusable (not found / disabled /
# blacklisted): token -> {"user_id", "merged"} of the order being
# built, so the one-tap "Use the fastest one" button can resume it
# with the fastest service instead. Dropped when the button is used.
FASTEST_FALLBACK = {}
LAST_ORDER = {}  # telegram_id -> order_id
# Multi-turn order state: telegram_id -> {"platform", "service_hint",
# "link", "quantity"} of the order being built. The bot asks for one
# missing piece at a time (platform -> link -> quantity); what the user
# already gave is remembered here, so a bare "2000" after a link, or a
# bare link after a service, completes the order instead of the bot
# answering "I did not understand". Cleared when the Confirm card is
# created (the order then lives in PENDING), when the user cancels, or
# when a different platform starts a new order.
PARTIAL = {}  # telegram_id -> {"platform", "service_hint", "link", "quantity"}
# Recurring-order plan being built, same shape plus "interval_minutes".
# Cleared when the plan Confirm card is created (the plan then lives
# in PENDING_RECURRING), when the user cancels, or when a different
# platform starts a new plan.
RECURRING_DRAFT = {}  # telegram_id -> {"platform", "service_hint", "link", "quantity", "interval_minutes"}
# Awaiting Confirm: confirm_id -> {"user_id", "service", "link",
# "quantity", "interval_minutes", "total"}. No recurring plan is
# created on the server until the user taps Confirm (or says yes).
PENDING_RECURRING = {}
# Deposit being built, same pattern as PARTIAL: telegram_id ->
# {"amount", "method", "phone"}. Cleared when the Confirm card is
# created (the deposit then lives in PENDING_DEPOSIT) or on cancel.
DEPOSIT_DRAFT = {}
# Awaiting Confirm: confirm_id -> {"user_id", "amount", "method",
# "phone"}. Nothing is created on the server until the user taps
# Confirm (or says yes).
PENDING_DEPOSIT = {}
# Most recent deposit created in this session: telegram_id ->
# deposit_id. The recheck prefers this id; after a restart the list
# endpoint is the fallback, so "did my deposit go through?" still
# works. Set in start_deposit on success.
LAST_DEPOSIT = {}
# A payment receipt the user sent as a photo and was offered a
# recheck for: telegram_id -> {"amount", "tx_ref"}. A bare "yes" (or
# the "Yes, check it" button) rechecks the most recent deposit;
# cleared when answered or when a new receipt offer replaces it.
RECEIPT_OFFER = {}
# Several orders in one Confirm card: confirm_id -> {"user_id",
# "orders": [{"service", "link", "quantity", "total"}]}. One Confirm
# places them all, each with its own idempotency key.
PENDING_BATCH = {}
# A split order waiting for its links: telegram_id -> {"platform",
# "service_hint", "quantity", "count", "links": [...]}. Cleared when
# the split is confirmed or the user cancels.
SPLIT_DRAFT = {}
# The budget options just shown: telegram_id -> {"platform",
# "service_hint", "quantity", "options": [service, ...]} in the
# order shown, so "first one" / "second one" / "1" / "2" picks the
# shown service instead of starting a new order. Cleared when the
# choice is used, when the order is confirmed, or on cancel.
BUDGET_OPTIONS = {}
# Telegram sometimes redelivers an update when the handler was slow
# (13 Nov 2026: one message got two identical "send the link"
# replies). Seen update_ids are remembered here, bounded so memory
# stays flat; a redelivery is answered once. Updates without an id
# (offline tests) are never treated as duplicates.
SEEN_UPDATES = set()
MAX_SEEN_UPDATES = 1000


def _update_seen(update) -> bool:
    """True when this Telegram update was already handled: the
    caller skips it. Records the id otherwise. Returns False for
    updates without an id."""
    update_id = getattr(update, "update_id", None)
    if update_id is None:
        return False
    if update_id in SEEN_UPDATES:
        return True
    if len(SEEN_UPDATES) >= MAX_SEEN_UPDATES:
        SEEN_UPDATES.clear()
    SEEN_UPDATES.add(update_id)
    return False
# A single deposit over this is refused in one line.
MAX_DEPOSIT_ETB = 100000


async def resolve_last_order(user_id: int):
    """The user's most recent order from the Paxyo API, or None.

    This is the bot's durable memory of the last link: it lives in
    Paxyo's orders table, so it survives bot restarts. Returns None
    when the user has no orders or the endpoint is not live yet.
    """
    try:
        orders = await paxyo.recent_orders(user_id, limit=5)
    except Exception as exc:
        log.warning("recent_orders failed: %s", exc)
        return None
    if not orders:
        return None
    return orders[0]


# ------------------------------------------------- edge-case helpers ----
# Messy real-world inputs (owner spec, 13 Nov 2026): the helpers the
# new intent handlers share. All of them are pure except the ones
# that read the in-memory order state.

def confirm_card_text(lang: str, service, quantity, total, link,
                      note: str = None) -> str:
    """The Confirm card for one order: service, quantity, link and
    total, always in that order, with an optional one-line note on
    top (a quantity change, a doubled usual, a link warning)."""
    lines = [t("confirm_title", lang), ""]
    if note:
        lines.append(note)
        lines.append("")
    lines.extend([
        f"{clean_service_name(service.get('name'))} (#{service.get('service')})",
        f"⏱ {service.get('average_time') or '—'}",
        f"💰 {format_money(service.get('rate_etb_per_1000', 0))} ETB / 1000",
        f"🔢 {quantity}",
        f"🧾 {format_money(total)} ETB (estimated)",
        f"🔗 {link}",
    ])
    return "\n".join(lines)


def pending_note(user_id: int, lang: str) -> str:
    """One line telling the user where their order stands, or "".

    A Confirm card waiting for Confirm is named first; otherwise a
    half-built order (what the bot already has). Used after an
    interruption (a question mid-flow) so the user is never left
    wondering whether their order survived it."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        return t(
            "pending_reminder", lang,
            service=clean_service_name(pending["service"].get("name")),
            quantity=pending["quantity"],
        )
    partial = PARTIAL.get(user_id) or {}
    given = [k for k in ("platform", "link", "quantity") if partial.get(k)]
    if given:
        return t("partial_reminder", lang, given=", ".join(given))
    return ""


def with_pending_note(user_id: int, lang: str, text: str) -> str:
    """A reply plus the where-your-order-stands line, when there is
    one. Interruptions (questions, trust, pricing) never silently
    drop a half-built order."""
    note = pending_note(user_id, lang)
    return f"{text}\n{note}" if note else text


def cheapest_service(services, platform=None, service_hint=None):
    """The cheapest usable service for a platform/metric, or None.

    Used when the user haggles, wants a free sample, or asks what
    their money buys: the answer is always a real service at its
    real Paxyo price — never a negotiated number."""
    picks = pick_services(services, platform=platform,
                          service_hint=service_hint, limit=100)
    if not picks:
        return None
    return min(picks, key=lambda s: float(s.get("rate_etb_per_1000", 0) or 0))


def slowest_service(services, platform=None, service_hint=None):
    """The slowest usable service (longest average time), or None.

    Offered when the user worries about safety: a slower, more
    gradual service is the honest alternative to a fast one."""
    picks = pick_services(services, platform=platform,
                          service_hint=service_hint, limit=100)
    if not picks:
        return None
    timed = [s for s in picks if parse_average_time(s.get("average_time"))]
    pool = timed if timed else picks
    return max(pool, key=lambda s: parse_average_time(s.get("average_time")) or 0)


def extract_links(text: str):
    """URLs (and bare t.me links) in a message, in order, de-duped.

    Used when the user pastes several links at once for a split or a
    batch order. Shortened links (vt.tiktok.com, bit.ly) are kept
    as-is — the provider resolves them."""
    found = re.findall(r"https?://\S+|t\.me/\S+", text or "")
    seen = set()
    out = []
    for link in found:
        link = link.rstrip(".,!?)]}")
        if link and link not in seen:
            seen.add(link)
            out.append(link)
    return out


# Impatience about a placed order: "why hasn't it started yet",
# "it's been 45 seconds". Answered with the real status plus the
# service's average time — never a bare "soon".
WAIT_QUESTION_PATTERNS = (
    "why hasn't", "why hasnt", "why is it taking", "hasn't started",
    "hasnt started", "not started yet", "still not started",
    "how long", "been 45 seconds", "been a minute", "taking so long",
    "taking too long", "when will it start", "why is my order",
)


def is_wait_question(text: str) -> bool:
    """True when the user is asking why a placed order has not
    started yet (as opposed to asking for its status in general)."""
    s = " ".join((text or "").strip().lower().split())
    return any(p in s for p in WAIT_QUESTION_PATTERNS)


# A question about the order being built, rather than new order
# details: speed ("how fast can you deliver it?") or drops
# ("wouldn't it drop?"). Answered from the stored service instead
# of asking for the link again (13 Nov 2026 — both questions got
# "Please send the link the order is for.").
_PENDING_SPEED_PHRASES = (
    "how fast", "how long", "how soon", "when will", "when does",
    "when do", "deliver", "delivery", "how quickly",
)
_PENDING_DROP_PHRASES = (
    "drop", "disappear", "refill", "fall off", "decrease", "go down",
)


def pending_order_question(text: str):
    """'speed' / 'drop' / None: is this message a question about an
    order being built? A question carries no link and no
    quantity-like number, and is not a service choice ("use the
    fastest one")."""
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return None
    if extract_links(text):
        return None
    if "fastest" in s or "cheapest" in s or "use the" in s:
        return None
    for m in re.finditer(r"\d[\d,]*", s):
        try:
            value = int(m.group(0).replace(",", ""))
        except ValueError:
            continue
        if 10 <= value <= 1000000 and value % 10 == 0:
            return None
    if any(p in s for p in _PENDING_DROP_PHRASES):
        return "drop"
    if any(p in s for p in _PENDING_SPEED_PHRASES):
        return "speed"
    return None


def link_needs_warning(text: str, link: str) -> bool:
    """True when the link may fail: a private account, or a story
    that expires soon. Shortened links are fine — the provider
    resolves them — so they do not trigger a warning."""
    s = " ".join((text or "").strip().lower().split())
    l = str(link or "").lower()
    return (
        "private" in s or "story" in s or "stories" in s
        or "/stories/" in l or "/story/" in l
    )


def pending_batch_for_user(user_id: int):
    """(confirm_id, batch) of the user's most recent batch awaiting
    Confirm, or (None, None)."""
    for confirm_id, batch in reversed(list(PENDING_BATCH.items())):
        if batch["user_id"] == user_id:
            return confirm_id, batch
    return None, None


def stop_schedule_keyboard(schedules):
    """Inline buttons to stop one of several repeating orders."""
    buttons = []
    for sched in schedules:
        label = (
            f"🛑 {clean_service_name(sched.get('service_name')) or sched.get('service_id')} "
            f"every {format_interval(sched.get('interval_minutes'))}"
        )
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"stoprec:{sched.get('id')}")]
        )
    return InlineKeyboardMarkup(buttons)


def fastest_fallback_keyboard(token: str, lang: str) -> InlineKeyboardMarkup:
    """One button under a bad-service reply: resume the same order
    with the fastest service instead."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("use_fastest", lang),
                               callback_data=f"usefastest:{token}")]]
    )


def confirm_keyboard(confirm_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{confirm_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{confirm_id}"),
            ]
        ]
    )


def start_order_keyboard(lang: str) -> InlineKeyboardMarkup:
    """One button under the how-to guide: starts a fresh order by
    asking for the platform."""
    label = "▶️ ጀምር" if lang == "am" else "▶️ Start an order"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data="start_order")]]
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


async def balance_text(user_id: int, lang: str) -> str:
    """Balance line for a user. Shared by /balance and the balance
    intent, so both answer the same way."""
    try:
        data = await paxyo.balance(user_id)
    except Exception as exc:
        log.warning("balance failed: %s", exc)
        return t("not_understood", lang)
    if not data.get("found"):
        return t("greeting", lang)
    return t("balance", lang, balance=format_money(data.get("balance", 0)))


async def last_order_status_text(user_id: int, lang: str) -> str:
    """Status line for the user's last order. Shared by /orders and
    the orders intent. The in-memory LAST_ORDER is checked first; when
    it is empty (e.g. after a bot restart) the last order is resolved
    from the Paxyo API instead, so "where is my order" still works."""
    order_id = LAST_ORDER.get(user_id)
    if not order_id:
        last = await resolve_last_order(user_id)
        if not last:
            return t("no_orders", lang)
        order_id = last.get("id") or last.get("order_id")
        if not order_id:
            return t("no_orders", lang)
        LAST_ORDER[user_id] = order_id
    try:
        data = await paxyo.order_status(order_id, user_id)
    except Exception as exc:
        log.warning("order_status failed: %s", exc)
        return t("not_understood", lang)
    status = data.get("status") or data.get("order", {}).get("status", "?")
    return t("order_ok", lang, order_id=order_id, status=status)


async def schedules_text(user_id: int, lang: str) -> str:
    """Short list of the user's active repeating orders, or the
    no-schedules line. Shared by the schedules intent and /schedules."""
    try:
        schedules = await paxyo.list_recurring(user_id)
    except Exception as exc:
        log.warning("list_recurring failed: %s", exc)
        return t("not_understood", lang)
    if not schedules:
        return t("no_schedules", lang)
    lines = []
    for i, sched in enumerate(schedules, 1):
        name = clean_service_name(sched.get("service_name")) or f"service {sched.get('service_id')}"
        lines.append(
            f"{i}. {name} ×{sched.get('quantity')} "
            f"every {format_interval(sched.get('interval_minutes'))}"
        )
    return "\n".join(lines)


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = lang_of("", user.language_code)
    await update.message.reply_text(await balance_text(user.id, lang))


async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status of the user's last order (tracked in memory)."""
    user = update.effective_user
    lang = lang_of("", user.language_code)
    await update.message.reply_text(await last_order_status_text(user.id, lang))


async def schedules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List the user's active repeating orders."""
    user = update.effective_user
    lang = lang_of("", user.language_code)
    await update.message.reply_text(await schedules_text(user.id, lang))


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
        "service": clean_service_name(service.get("name")),
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


def pending_recurring_for_user(user_id: int):
    """(confirm_id, draft) of the user's most recent repeating-order
    plan awaiting Confirm, or (None, None)."""
    for confirm_id, draft in reversed(list(PENDING_RECURRING.items())):
        if draft["user_id"] == user_id:
            return confirm_id, draft
    return None, None


async def start_recurring_plan(draft, user_id: int):
    """Create a repeating order on the server from a confirmed draft.

    Returns (schedule, error_key): schedule is the server's record
    ({"id", "next_run_at", ...}), error_key is "plan_failed" or None.
    """
    try:
        result = await paxyo.create_recurring(
            user_id,
            int(draft["service"]["service"]),
            draft["link"],
            draft["quantity"],
            draft["interval_minutes"],
        )
    except Exception as exc:
        log.warning("create_recurring failed: %s", exc)
        return None, "plan_failed"
    schedule = result.get("schedule", result) if isinstance(result, dict) else {}
    return schedule, None


def pending_deposit_for_user(user_id: int):
    """(confirm_id, draft) of the user's most recent deposit awaiting
    Confirm, or (None, None)."""
    for confirm_id, draft in reversed(list(PENDING_DEPOSIT.items())):
        if draft["user_id"] == user_id:
            return confirm_id, draft
    return None, None


async def start_deposit(draft, user_id: int):
    """Call POST /deposits for a confirmed draft.

    Returns (result, error): result is the server's record
    ({"deposit_id","pushed","auth_type","checkout_url","ussd_code",
    "pay_to","status"} — pushed/auth_type "ussd" means a USSD prompt
    was sent to the user's phone, no link needed),
    error is None on success, "deposit_not_ready" when the endpoint
    is not live yet (404), a server message string when the API
    rejected it (e.g. amount below the minimum), or "deposit_failed".
    """
    try:
        result = await paxyo.create_deposit(
            user_id, draft["amount"], draft["method"], draft["phone"]
        )
    except httpx.HTTPStatusError as exc:
        log.warning("create_deposit rejected: %s", exc.response.status_code)
        try:
            data = exc.response.json()
        except Exception:
            data = {}
        message = None
        if isinstance(data, dict):
            message = data.get("error") or data.get("message")
        return None, message or "deposit_failed"
    except Exception as exc:
        log.warning("create_deposit failed: %s", exc)
        return None, "deposit_failed"
    if result is None:  # 404: the endpoint is not live yet
        return None, "deposit_not_ready"
    # Remember the deposit id so "did my deposit go through?" /
    # "I paid" can recheck this deposit without listing first.
    deposit_id = result.get("deposit_id") if isinstance(result, dict) else None
    if deposit_id is not None:
        LAST_DEPOSIT[user_id] = deposit_id
    return result, None


def deposit_instructions_text(result, amount, method, lang: str) -> str:
    """Short payment instructions from the server's deposit record.

    USSD push first (Chapa Direct Charge): the prompt arrives on the
    user's phone, so there is no code to dial and no link to open.
    Then the USSD code to dial and/or the checkout link, when the
    server returns them. Never claims the money is credited — the
    server credits the balance only after Chapa confirms the payment."""
    if result.get("pushed") or result.get("auth_type") == "ussd":
        return t(
            "deposit_pushed", lang,
            amount=format_money(amount),
            method=METHOD_LABELS.get(method, method),
        )
    steps = []
    ussd = result.get("ussd_code")
    pay_to = result.get("pay_to")
    url = result.get("checkout_url")
    if ussd:
        steps.append(t("deposit_step_ussd", lang, code=ussd))
    if pay_to:
        steps.append(t("deposit_step_pay_to", lang, pay_to=pay_to))
    if url:
        steps.append(t("deposit_step_link", lang, url=url))
    if not steps:
        steps.append(t("deposit_step_website", lang))
    return t(
        "deposit_instructions", lang,
        amount=format_money(amount),
        method=METHOD_LABELS.get(method, method),
        steps="\n".join(steps),
    )


# Bare "I paid" / "I approved it" (text is already normalised).
# Only the exact phrases count: a longer message goes through the
# classifier instead, so "I paid for the order" is not hijacked.
PAID_WORDS = frozenset({
    "i paid", "i have paid", "i've paid", "i paid already",
    "i approved it", "i have approved it", "i approved",
    "paid", "approved",
    "ከፍዬአለሁ", "ከፈልኩ", "ከፍያለሁ",
})


# Questions about where the services come from / what Paxyo pays for
# them (owner rule, 13 Nov 2026: the supply chain stays secret).
# Caught locally, before Gemini is even called, so the model is never
# given a chance to name a supplier. Amharic "አቅራቢ" is the word for
# a supplier; other Amharic phrasings go through the classifier's
# "source_question" intent instead.
SOURCE_QUESTION_PATTERNS = (
    "provider", "supplier", "supplies", "resell", "smm", "wholesale",
    "middleman", "where do you get", "where do you buy",
    "who gives you", "who supplies", "who is behind",
    "how much do you buy", "how much did you buy",
    "are you a panel", "is this a panel", "is paxyo a panel",
    "አቅራቢ",
)


def is_source_question(text: str) -> bool:
    """True when the message asks where Paxyo's services come from,
    who supplies them, or what Paxyo pays for them."""
    s = normalize_text(text or "")
    return any(p in s for p in SOURCE_QUESTION_PATTERNS)


def is_paid_phrase(text: str) -> bool:
    """True when the message is just 'I paid' / 'I approved it' —
    the user saying the payment is done and asking whether it went
    through."""
    s = " ".join((text or "").strip().lower().split())
    s = s.strip(" .!,?።፣")
    return s in PAID_WORDS


async def deposit_status_text(user_id: int, lang: str) -> str:
    """Recheck the user's most recent deposit and say what happened,
    in one short message.

    The most recent in-session deposit (LAST_DEPOSIT) is checked
    first; after a restart the newest deposit from the list endpoint
    is used instead. The status call IS the recheck — the server
    re-verifies a pending deposit with Chapa before answering — so
    the bot never credits anything itself; it only reports what the
    server says, and never invents a failure reason."""
    deposit_id = LAST_DEPOSIT.get(user_id)
    deposit = None
    if deposit_id is not None:
        try:
            deposit = await paxyo.deposit_status(deposit_id, user_id)
        except Exception as exc:
            log.warning("deposit_status failed: %s", exc)
            return t("not_understood", lang)
        if deposit is None:  # 404: the endpoint is not live yet
            return t("deposit_check_not_ready", lang)
    else:
        try:
            deposits = await paxyo.list_deposits(user_id)
        except Exception as exc:
            log.warning("list_deposits failed: %s", exc)
            return t("not_understood", lang)
        if deposits is None:  # 404: the endpoint is not live yet
            return t("deposit_check_not_ready", lang)
        if not deposits:
            return t("no_deposits", lang)
        newest = deposits[0]
        try:
            deposit = await paxyo.deposit_status(newest.get("id"), user_id)
        except Exception as exc:
            log.warning("deposit_status failed: %s", exc)
            return t("not_understood", lang)
        if deposit is None:  # 404: the endpoint is not live yet
            return t("deposit_check_not_ready", lang)
    status = str(deposit.get("status") or "").strip().lower()
    amount = deposit.get("amount")
    amount_text = format_money(amount) if amount is not None else "?"
    if status in ("completed", "success", "paid"):
        try:
            data = await paxyo.balance(user_id)
            balance = data.get("balance") if data.get("found") else None
        except Exception as exc:
            log.warning("balance failed after deposit recheck: %s", exc)
            balance = None
        if balance is None:
            return t("deposit_went_through_nobalance", lang, amount=amount_text)
        return t(
            "deposit_went_through", lang,
            amount=amount_text, balance=format_money(balance),
        )
    if status in ("failed", "cancelled", "canceled", "expired", "rejected"):
        reason = (
            deposit.get("message") or deposit.get("error")
            or deposit.get("reason")
        )
        if isinstance(reason, str) and reason.strip():
            return t(
                "deposit_failed_reason", lang,
                amount=amount_text, reason=reason.strip(),
            )
        return t("deposit_failed_check", lang, amount=amount_text)
    return t("deposit_still_pending", lang, amount=amount_text)


async def stop_one_schedule(update, sched, lang, voice=False):
    """Cancel one repeating order and confirm it in one short line."""
    user = update.effective_user
    try:
        await paxyo.cancel_recurring(sched.get("id"), user.id)
    except Exception as exc:
        log.warning("cancel_recurring failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    name = clean_service_name(sched.get("service_name")) or f"service {sched.get('service_id')}"
    await reply_message(
        update.message, t("schedule_stopped", lang, service=name), lang, voice=voice
    )


async def stop_schedules_flow(update, schedules, lang, voice=False):
    """One active schedule -> cancel it directly; several -> buttons
    so the user picks which one to stop."""
    if len(schedules) == 1:
        await stop_one_schedule(update, schedules[0], lang, voice=voice)
        return
    await reply_message(
        update.message, t("ask_which_schedule", lang), lang, voice=voice,
        reply_markup=stop_schedule_keyboard(schedules),
    )


async def handle_stop_schedule(update, lang, voice=False):
    """'Stop the repeating order' / 'cancel my schedule'."""
    user = update.effective_user
    try:
        schedules = await paxyo.list_recurring(user.id)
    except Exception as exc:
        log.warning("list_recurring failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    if not schedules:
        await reply_message(update.message, t("no_schedules", lang), lang, voice=voice)
        return
    await stop_schedules_flow(update, schedules, lang, voice=voice)


async def handle_recurring_text(update, text, intent, lang, voice=False):
    """Build a repeating-order plan over several turns, then show the
    plan summary with a Confirm card. Nothing is created on the server
    until the user taps Confirm (or says yes): a plan that runs by
    itself must never start on a misunderstood message.

    Missing pieces are asked in order: platform -> link -> quantity ->
    interval. The link is resolved from the user's most recent order
    when they say "that link" or give no link at all — the summary
    shows the link, and Confirm is the safety net.
    """
    user = update.effective_user
    stored = RECURRING_DRAFT.get(user.id) or {}
    new_platform = (intent.get("platform") or "").strip().lower()
    stored_platform = (stored.get("platform") or "").strip().lower()
    if new_platform and stored_platform and new_platform != stored_platform:
        stored = {}
    merged = {}
    for key in ("platform", "service_hint", "link", "quantity", "interval_minutes"):
        value = intent.get(key)
        merged[key] = value if value is not None else stored.get(key)
    if merged.get("interval_minutes") is None:
        merged["interval_minutes"] = parse_interval_minutes(text)
    try:
        interval = (
            int(merged["interval_minutes"])
            if merged.get("interval_minutes") is not None
            else None
        )
    except (TypeError, ValueError):
        interval = None
    merged["interval_minutes"] = interval
    if interval is not None and interval < MIN_RECURRING_MINUTES:
        RECURRING_DRAFT.pop(user.id, None)
        await reply_message(update.message, t("interval_too_short", lang), lang, voice=voice)
        return
    last_service_id = None
    if not merged.get("link"):
        last = await resolve_last_order(user.id)
        if last and last.get("link"):
            merged["link"] = last.get("link")
            last_service_id = last.get("service_id")
    if not merged.get("platform") and not merged.get("service_hint") and last_service_id is None:
        RECURRING_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_platform", lang), lang, voice=voice)
        return
    if not merged.get("link"):
        RECURRING_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_link", lang), lang, voice=voice)
        return
    if not merged.get("quantity"):
        RECURRING_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_quantity", lang), lang, voice=voice)
        return
    if not merged.get("interval_minutes"):
        RECURRING_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_interval", lang), lang, voice=voice)
        return

    # Complete plan: pick the service and show the summary with Confirm.
    RECURRING_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("services fetch failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    service = None
    if (
        last_service_id is not None
        and not merged.get("platform")
        and not merged.get("service_hint")
    ):
        for s in services:
            try:
                if int(s.get("service", 0)) == int(last_service_id):
                    service = s
                    break
            except (TypeError, ValueError):
                continue
    if service is None:
        picks = pick_services(
            services, platform=merged.get("platform"),
            service_hint=merged.get("service_hint"),
        )
        if not picks:
            await reply_message(update.message, t("no_service", lang), lang, voice=voice)
            return
        service = picks[0]
    error = validate_quantity(merged.get("quantity"), service)
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
    quantity = int(merged["quantity"])
    rate = float(service.get("rate_etb_per_1000", 0))
    total = estimated_total_etb(rate, quantity)
    confirm_id = uuid.uuid4().hex[:12]
    RECURRING_DRAFT.pop(user.id, None)
    PENDING_RECURRING[confirm_id] = {
        "user_id": user.id,
        "service": service,
        "link": merged["link"],
        "quantity": quantity,
        "interval_minutes": merged["interval_minutes"],
        "total": total,
    }
    lines = [
        t("confirm_title", lang),
        "",
        f"{clean_service_name(service.get('name'))}",
        f"🔢 {quantity}",
        f"🔁 every {format_interval(merged['interval_minutes'])}",
        f"🧾 {format_money(total)} ETB per order",
        f"🔗 {merged['link']}",
    ]
    # Plan summary: always text — it carries the Confirm buttons.
    await reply_message(
        update.message, "\n".join(lines), lang,
        reply_markup=confirm_keyboard(confirm_id),
    )


async def handle_deposit_text(update, text, intent, lang, voice=False):
    """Build a deposit over several turns (amount -> method -> phone),
    then show a Confirm summary. Nothing is created on the server
    until the user taps Confirm (or says yes): money must never move
    on a misunderstood message. The server creates the Chapa checkout
    and credits the balance only after Chapa confirms the payment;
    the bot never credits anything itself."""
    user = update.effective_user
    stored = DEPOSIT_DRAFT.get(user.id) or {}
    amount = intent.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    if amount is None:
        amount = parse_deposit_amount(text)
    if amount is None:
        amount = stored.get("amount")
    method = intent.get("method")
    if not isinstance(method, str):
        method = None
    if method is None:
        method = normalize_method(text)
    if method is None:
        method = stored.get("method")
    phone = intent.get("phone")
    if isinstance(phone, str):
        phone = normalize_phone(phone)
    else:
        phone = None
    if phone is None:
        phone = normalize_phone(text)
    if phone is None:
        phone = stored.get("phone")
    merged = {"amount": amount, "method": method, "phone": phone}
    if amount is not None and (amount <= 0 or amount > MAX_DEPOSIT_ETB):
        DEPOSIT_DRAFT[user.id] = {
            k: v for k, v in merged.items() if v is not None and k != "amount"
        }
        await reply_message(update.message, t("deposit_too_big", lang), lang, voice=voice)
        return
    if amount is None:
        DEPOSIT_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_deposit_amount", lang), lang, voice=voice)
        return
    if method is None:
        DEPOSIT_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_deposit_method", lang), lang, voice=voice)
        return
    if phone is None:
        DEPOSIT_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_deposit_phone", lang), lang, voice=voice)
        return
    # Complete: Confirm card, always text — it carries the buttons.
    DEPOSIT_DRAFT.pop(user.id, None)
    PARTIAL.pop(user.id, None)
    RECURRING_DRAFT.pop(user.id, None)
    confirm_id = uuid.uuid4().hex[:12]
    PENDING_DEPOSIT[confirm_id] = {
        "user_id": user.id,
        "amount": amount,
        "method": method,
        "phone": phone,
    }
    lines = [
        t("confirm_title", lang),
        "",
        f"💰 {format_money(amount)} ETB",
        f"📱 {METHOD_LABELS.get(method, method)}",
        f"📞 {phone}",
    ]
    await reply_message(
        update.message, "\n".join(lines), lang,
        reply_markup=confirm_keyboard(confirm_id),
    )


async def complete_order(message, user_id, merged, lang, voice=False,
                         named_service_id=None, last_service_id=None,
                         note: str = None, ask_metric: bool = True):
    """Fetch services, pick/validate the service, show the Confirm card.

    The order being built stays in PARTIAL until the card is shown,
    then it lives in PENDING. Returns True when the Confirm card was
    shown. A service the user named by ID is used as-is (validated:
    it must exist, be active and not be blacklisted); a bad named
    service is refused in one line with a one-tap "Use the fastest
    one" button, and the order stays in PARTIAL. Otherwise the
    fastest service is picked as before — including the last order's
    service for "order on that link again". A blacklisted service is
    never used, whichever path picked it. `note` is a one-line
    warning on the card (a quantity change, a doubled usual, a
    risky link, a handle to double-check). When no metric was named
    and the fastest services are different kinds (views vs likes
    vs comments), the bot asks which kind instead of silently
    picking the wrong one — the order stays in PARTIAL, so the
    answer completes it. `ask_metric=False` skips that question
    (the "Use the fastest one" button: the user already chose).
    """
    PARTIAL[user_id] = {k: v for k, v in merged.items() if v is not None}
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("services fetch failed: %s", exc)
        await reply_message(message, t("not_understood", lang), lang, voice=voice)
        return False

    service = None
    if named_service_id is not None:
        service, svc_error = resolve_named_service(services, named_service_id)
        if svc_error is not None:
            token = uuid.uuid4().hex[:12]
            FASTEST_FALLBACK[token] = {
                "user_id": user_id,
                "merged": {k: v for k, v in merged.items() if v is not None},
            }
            key = {
                "blacklisted": "service_blacklisted",
                "not_found": "service_not_found",
                "disabled": "service_disabled",
            }[svc_error]
            await reply_message(
                message, t(key, lang), lang, voice=voice,
                reply_markup=fastest_fallback_keyboard(token, lang),
            )
            return False
    if (
        service is None
        and last_service_id is not None
        and not merged.get("platform")
        and not merged.get("service_hint")
    ):
        # "Order on that link again": reuse the last order's service —
        # unless it is now blacklisted or turned off, in which case
        # the fastest pick below takes over.
        found = find_service_by_id(services, last_service_id)
        if found is not None and found.get("active", True):
            try:
                usable = int(found.get("service", 0)) not in BLACKLISTED_SERVICES
            except (TypeError, ValueError):
                usable = False
            if usable:
                service = found
    if service is None:
        picks = pick_services(
            services, platform=merged.get("platform"), service_hint=merged.get("service_hint")
        )
        if not picks:
            await reply_message(message, t("no_service", lang), lang, voice=voice)
            return False
        if ask_metric and not merged.get("service_hint"):
            # No metric was named and the fastest services are
            # different kinds (views vs likes vs comments): ask
            # which kind instead of silently picking the wrong one
            # (13 Nov 2026 — a views order got Comment Likes).
            # When the metric is known (a hint), the fastest pick
            # still applies with no question.
            metrics = []
            for pick in picks:
                hay = (
                    str(pick.get("name") or "") + " "
                    + str(pick.get("category") or "")
                ).lower()
                found = next((m for m in _METRICS if m in hay), None)
                if found and found not in metrics:
                    metrics.append(found)
            if len(metrics) > 1:
                await reply_message(
                    message,
                    t("ask_metric_choose", lang, metrics=", ".join(metrics)),
                    lang, voice=voice,
                )
                return False
        service = picks[0]
    error = validate_quantity(merged.get("quantity"), service)
    if error:
        await reply_message(
            message,
            t(
                "bad_quantity",
                lang,
                min=service.get("min"),
                max=service.get("max"),
            ),
            lang,
            voice=voice,
        )
        return False

    quantity = int(merged["quantity"])
    rate = float(service.get("rate_etb_per_1000", 0))
    total = estimated_total_etb(rate, quantity)

    confirm_id = uuid.uuid4().hex[:12]
    PARTIAL.pop(user_id, None)  # the order now lives in PENDING
    BUDGET_OPTIONS.pop(user_id, None)  # a budget choice is spent now
    DEPOSIT_DRAFT.pop(user_id, None)  # a half-built deposit is stale now
    PENDING[confirm_id] = {
        "user_id": user_id,
        "service": service,
        "link": merged["link"],
        "quantity": quantity,
        "total": total,
    }
    # Confirm card: always text — a voice message cannot carry buttons.
    await reply_message(
        message,
        confirm_card_text(lang, service, quantity, total, merged["link"],
                          note=note),
        lang,
        reply_markup=confirm_keyboard(confirm_id),
    )
    return True


# ------------------------------------------- edge-case handlers ------
# Messy real-world inputs (owner spec, 13 Nov 2026). Each handler
# answers one kind of messy message and either shows a Confirm card
# (never placing anything itself) or a one-line answer. Prices always
# come from the server's service list — never from the user's words.

async def handle_usual(update, text, intent, lang, voice=False):
    """'Give me the usual' — the last order as a Confirm card.

    Service + link + quantity come from the most recent order on the
    server. A multiplier ("double it") scales the quantity, capped
    at the service maximum (and the cap is said out loud). No last
    order -> ask what they usually order."""
    user = update.effective_user
    last = await resolve_last_order(user.id)
    if not last or not last.get("link"):
        await reply_message(update.message, t("no_usual", lang), lang, voice=voice)
        return
    quantity = last.get("quantity")
    try:
        quantity = int(quantity) if quantity is not None else None
    except (TypeError, ValueError):
        quantity = None
    if quantity is None:
        await reply_message(update.message, t("no_usual", lang), lang, voice=voice)
        return
    multiplier = intent.get("quantity_multiplier")
    try:
        multiplier = float(multiplier) if multiplier is not None else 1
    except (TypeError, ValueError):
        multiplier = 1
    wanted = int(quantity * multiplier)
    service_id = last.get("service_id")
    service_name = str(last.get("service_name") or "")
    platform = None
    if service_id is None:
        # No service id on the last order: guess the platform from
        # the service name so the flow can still pick a service.
        for p in ("instagram", "tiktok", "telegram", "youtube", "facebook", "x"):
            if p in service_name.lower():
                platform = p
                break
    note = t("usual_note", lang)
    if service_id is not None:
        try:
            services = await paxyo.services()
            found = find_service_by_id(services, service_id)
            if found is not None:
                max_qty = int(found.get("max", 0) or 0)
                if max_qty > 0 and wanted > max_qty:
                    wanted = (max_qty // 10) * 10
                    note = (
                        f"{t('usual_note', lang)}\n"
                        f"{t('usual_capped', lang, max=max_qty)}"
                    )
        except Exception as exc:
            log.warning("usual cap lookup failed: %s", exc)
    merged = {
        "platform": platform,
        "service_hint": None,
        "link": last.get("link"),
        "quantity": wanted,
    }
    await complete_order(
        update.message, user.id, merged, lang, voice=voice,
        named_service_id=service_id, last_service_id=service_id,
        note=note,
    )


_BUDGET_ORDINALS = {
    "first": 0, "1st": 0, "1": 0,
    "second": 1, "2nd": 1, "2": 1,
    "third": 2, "3rd": 2, "3": 2,
}


def budget_choice_index(text: str):
    """Index of the budget option the user picked ("first one",
    "second one", "1", "2"), or None. Only the bare words match, so
    "first one" picks option 0 but "first order" does not."""
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return None
    for word, idx in _BUDGET_ORDINALS.items():
        if s in (word, f"{word} one", f"the {word} one", f"{word} option"):
            return idx
    return None


async def handle_budget_text(update, text, intent, lang, voice=False):
    """Budget-first ordering: '10k for 500 birr, what do I get?'

    Lists the cheapest and the fastest option for the asked quantity
    with their real Paxyo prices, and asks which one. When the budget
    does not buy the asked quantity, says the most it buys instead.
    Never invents a price and never negotiates one."""
    user = update.effective_user
    budget = intent.get("amount")
    try:
        budget = float(budget) if budget is not None else None
    except (TypeError, ValueError):
        budget = None
    if budget is None:
        await reply_message(update.message, t("budget_ask", lang), lang, voice=voice)
        return
    quantity = intent.get("quantity")
    try:
        quantity = int(quantity) if quantity is not None else None
    except (TypeError, ValueError):
        quantity = None
    platform = (intent.get("platform") or "").strip().lower() or None
    hint = intent.get("service_hint")
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("budget services failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    picks = pick_services(services, platform=platform, service_hint=hint, limit=100)
    if not picks:
        await reply_message(update.message, t("no_service", lang), lang, voice=voice)
        return
    metric = hint or platform or "service"
    cheapest = min(picks, key=lambda s: float(s.get("rate_etb_per_1000", 0) or 0))

    def _avg(s):
        v = parse_average_time(s.get("average_time"))
        return v if v is not None else 10 ** 9

    fastest = min(picks, key=_avg)
    options = []
    seen = set()
    for svc in (cheapest, fastest):
        sid = svc.get("service")
        if sid in seen:
            continue
        seen.add(sid)
        options.append(svc)
    if quantity is None:
        option_text = "; ".join(
            f"{clean_service_name(s.get('name'))} — "
            f"{format_money(s.get('rate_etb_per_1000', 0))} ETB per 1000"
            for s in options
        )
        # Remember what was shown, in order, so "first one" /
        # "second one" picks it instead of starting a new order.
        BUDGET_OPTIONS[user.id] = {
            "platform": platform, "service_hint": hint,
            "quantity": None, "options": options,
        }
        await reply_message(
            update.message,
            t("budget_no_quantity", lang, budget=format_money(budget),
              options=option_text),
            lang, voice=voice,
        )
        return
    cheapest_total = estimated_total_etb(
        float(cheapest.get("rate_etb_per_1000", 0)), quantity
    )
    if cheapest_total <= budget:
        option_text = "; ".join(
            f"{clean_service_name(s.get('name'))} — "
            f"{format_money(estimated_total_etb(float(s.get('rate_etb_per_1000', 0)), quantity))} ETB"
            for s in options
        )
        # Remember what was shown, in order, so "first one" /
        # "second one" picks it instead of starting a new order.
        BUDGET_OPTIONS[user.id] = {
            "platform": platform, "service_hint": hint,
            "quantity": quantity, "options": options,
        }
        await reply_message(
            update.message,
            t("budget_options", lang, quantity=quantity, metric=metric,
              options=option_text),
            lang, voice=voice,
        )
        return
    rate = float(cheapest.get("rate_etb_per_1000", 0) or 0)
    if rate <= 0:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    max_qty = int(budget / (rate / 1000))
    max_qty = (max_qty // 10) * 10
    min_qty = int(cheapest.get("min", 0) or 0)
    if max_qty >= min_qty and max_qty > 0:
        await reply_message(
            update.message,
            t(
                "budget_max", lang, budget=format_money(budget),
                quantity=quantity, metric=metric, max_quantity=max_qty,
                name=clean_service_name(cheapest.get("name")),
                total=format_money(
                    estimated_total_etb(rate, max_qty)
                ),
            ),
            lang, voice=voice,
        )
        return
    await reply_message(
        update.message,
        t(
            "budget_too_small", lang, budget=format_money(budget),
            minimum=min_qty, metric=metric,
            name=clean_service_name(cheapest.get("name")),
            total=format_money(estimated_total_etb(rate, min_qty)),
        ),
        lang, voice=voice,
    )


async def resolve_batch_drafts(drafts, user_id):
    """Resolve each draft to a real service. Returns (ready, missing):
    ready is [{service, link, quantity, total}], missing is a list of
    one-line problems. (None, None) means the services fetch failed.
    A draft with no link or no quantity is missing, not guessed."""
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("batch services failed: %s", exc)
        return None, None
    ready, missing = [], []
    for d in drafts:
        link = (d.get("link") or "").strip()
        qty = d.get("quantity")
        label = d.get("service_hint") or d.get("platform") or "order"
        if not link:
            missing.append(f"{label} — no link")
            continue
        if qty is None:
            missing.append(f"{link} — no quantity")
            continue
        service = None
        named = d.get("service_id")
        if named is not None:
            service, svc_error = resolve_named_service(services, named)
            if svc_error is not None:
                missing.append(f"{link} — service {named} is not available")
                continue
        if service is None:
            picks = pick_services(
                services, platform=d.get("platform"),
                service_hint=d.get("service_hint"),
            )
            if not picks:
                missing.append(f"{link} — no service found")
                continue
            service = picks[0]
        error = validate_quantity(qty, service)
        if error:
            missing.append(
                f"{link} — quantity must be between "
                f"{service.get('min')} and {service.get('max')}"
            )
            continue
        ready.append({
            "service": service,
            "link": link,
            "quantity": int(qty),
            "total": estimated_total_etb(
                float(service.get("rate_etb_per_1000", 0)), int(qty)
            ),
        })
    return ready, missing


async def show_batch_confirm(message, user_id, ready, lang, voice=False):
    """One Confirm card listing every order in the batch, with the
    combined total. One Confirm places them all."""
    confirm_id = uuid.uuid4().hex[:12]
    PENDING_BATCH[confirm_id] = {"user_id": user_id, "orders": ready}
    total = sum(o["total"] for o in ready)
    lines = [t("batch_title", lang, n=len(ready)), ""]
    for i, o in enumerate(ready, 1):
        lines.append(
            f"{i}. {clean_service_name(o['service'].get('name'))} "
            f"×{o['quantity']} → {o['link']} — "
            f"{format_money(o['total'])} ETB"
        )
    lines.append("")
    lines.append(t("batch_total", lang, total=format_money(total)))
    # Batch Confirm card: always text — it carries the buttons.
    await reply_message(
        message, "\n".join(lines), lang, voice=voice,
        reply_markup=confirm_keyboard(confirm_id),
    )


async def place_batch(batch, user_id):
    """Place every order in a confirmed batch. Returns (results, error):
    results is [(draft, order_id or None, error or None)]. The balance
    is checked once against the batch total first; a failure on one
    order never stops the others, and each order gets its own
    idempotency key so a retry cannot double-charge it."""
    orders = batch["orders"]
    total = sum(o["total"] for o in orders)
    try:
        bal = await paxyo.balance(user_id)
    except Exception as exc:
        log.warning("batch balance check failed: %s", exc)
        return None, ("not_understood",)
    if not bal.get("found") or float(bal.get("balance", 0)) < total:
        return None, ("insufficient", bal.get("balance", 0), total)
    results = []
    for draft in orders:
        try:
            result = await paxyo.create_order(
                user_id,
                int(draft["service"]["service"]),
                draft["link"],
                draft["quantity"],
                uuid.uuid4().hex,
            )
        except httpx.HTTPStatusError as exc:
            log.warning("batch create_order rejected: %s", exc.response.status_code)
            results.append((draft, None, "order_failed"))
            continue
        except Exception as exc:
            log.warning("batch create_order failed: %s", exc)
            results.append((draft, None, "order_failed"))
            continue
        order = result.get("order", result) if isinstance(result, dict) else {}
        order_id = order.get("id") or order.get("order_id") or "?"
        LAST_ORDER[user_id] = order_id
        results.append((draft, order_id, None))
    return results, None


def batch_result_text(results, lang: str) -> str:
    """One short line per order in a placed batch: ✅ with the order
    id, or ❌ when that one could not be placed."""
    lines = []
    for draft, order_id, error in results:
        name = clean_service_name(draft["service"].get("name"))
        if error is None:
            lines.append(f"✅ {draft['quantity']} {name} → Order {order_id}")
        else:
            lines.append(f"❌ {draft['quantity']} {name} — could not be placed")
    return "\n".join(lines)


async def handle_split_text(update, text, split, lang, voice=False):
    """Split one quantity across several posts: 'split 5,000 likes
    across my last 5 Instagram posts'.

    The bot cannot fetch the user's posts, so it asks for the links
    (they can be pasted together), counts them, and says how many are
    still missing. When all links are in, each gets an equal share
    (rounded down to a multiple of 10) and the batch Confirm card
    shows the split."""
    user = update.effective_user
    stored = SPLIT_DRAFT.get(user.id) or {}
    quantity = split.get("quantity") or stored.get("quantity")
    count = split.get("count") or stored.get("count")
    platform = split.get("platform") or stored.get("platform")
    hint = split.get("service_hint") or stored.get("service_hint")
    links = list(stored.get("links") or [])
    for link in extract_links(text):
        if link not in links:
            links.append(link)
    try:
        quantity = int(quantity) if quantity is not None else None
        count = int(count) if count is not None else None
    except (TypeError, ValueError):
        quantity = count = None
    if quantity is None or count is None or count <= 0:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    metric = hint or platform or "likes"
    each = (quantity // count // 10) * 10
    if each <= 0:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    if len(links) < count:
        SPLIT_DRAFT[user.id] = {
            "platform": platform,
            "service_hint": hint,
            "quantity": quantity,
            "count": count,
            "links": links,
        }
        if not links:
            await reply_message(
                update.message,
                t("split_ask_links", lang, count=count, quantity=quantity,
                  metric=metric, each=each),
                lang, voice=voice,
            )
        else:
            await reply_message(
                update.message,
                t("split_missing", lang, got=len(links), count=count,
                  missing=count - len(links)),
                lang, voice=voice,
            )
        return
    SPLIT_DRAFT.pop(user.id, None)
    drafts = [
        {"platform": platform, "service_hint": hint, "link": link, "quantity": each}
        for link in links[:count]
    ]
    ready, missing = await resolve_batch_drafts(drafts, user.id)
    if ready is None:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    if missing:
        understood = "\n".join(
            f"{clean_service_name(o['service'].get('name'))} ×{o['quantity']} → {o['link']}"
            for o in ready
        ) or "—"
        await reply_message(
            update.message,
            t("batch_missing", lang, understood=understood,
              missing="\n".join(missing)),
            lang, voice=voice,
        )
        return
    await show_batch_confirm(update.message, user.id, ready, lang, voice=voice)


async def handle_batch_text(update, text, intent, lang, voice=False):
    """Several orders in one message, or one quantity split across
    posts. Each order is resolved to a real service and shown on one
    batch Confirm card; one Confirm places them all. Anything the
    bot could not parse is listed back and asked about — never
    guessed."""
    user = update.effective_user
    split = intent.get("split")
    if split:
        await handle_split_text(update, text, split, lang, voice=voice)
        return
    orders = intent.get("orders")
    if not orders:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    ready, missing = await resolve_batch_drafts(orders, user.id)
    if ready is None:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    if missing:
        understood = "\n".join(
            f"{clean_service_name(o['service'].get('name'))} ×{o['quantity']} → {o['link']}"
            for o in ready
        ) or "—"
        await reply_message(
            update.message,
            t("batch_missing", lang, understood=understood,
              missing="\n".join(missing)),
            lang, voice=voice,
        )
        return
    await show_batch_confirm(update.message, user.id, ready, lang, voice=voice)


async def handle_change_order(update, text, intent, lang, voice=False):
    """'Change the quantity from 5,000 to 2,000 before it starts.'

    A Confirm card waiting for Confirm is edited in place (new
    quantity, new total, updated card). A half-built order takes the
    new quantity and continues. An order that is already placed
    cannot be changed — the live status is shown instead."""
    user = update.effective_user
    new_qty = intent.get("quantity")
    try:
        new_qty = int(new_qty) if new_qty is not None else None
    except (TypeError, ValueError):
        new_qty = None
    if new_qty is None:
        # "change the quantity from 5,000 to 2,000": the last number
        # in the message is the new value.
        nums = re.findall(r"\d[\d,]*", text or "")
        if nums:
            try:
                new_qty = int(nums[-1].replace(",", ""))
            except ValueError:
                new_qty = None
    if new_qty is None:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    confirm_id, pending = pending_for_user(user.id)
    if pending is not None:
        service = pending["service"]
        error = validate_quantity(new_qty, service)
        if error:
            await reply_message(
                update.message,
                t("bad_quantity", lang, min=service.get("min"),
                  max=service.get("max")),
                lang, voice=voice,
            )
            return
        pending["quantity"] = new_qty
        pending["total"] = estimated_total_etb(
            float(service.get("rate_etb_per_1000", 0)), new_qty
        )
        await reply_message(
            update.message,
            confirm_card_text(
                lang, service, new_qty, pending["total"], pending["link"],
                note=t("change_note", lang, quantity=new_qty),
            ),
            lang,
            reply_markup=confirm_keyboard(confirm_id),
        )
        return
    partial = PARTIAL.get(user.id)
    if partial:
        partial["quantity"] = new_qty
        merged = {
            k: partial.get(k)
            for k in ("platform", "service_hint", "link", "quantity", "service_id")
        }
        if merged.get("link") and merged.get("quantity"):
            await complete_order(
                update.message, user.id, merged, lang, voice=voice,
                note=t("change_note", lang, quantity=new_qty),
            )
            return
        PARTIAL[user.id] = {k: v for k, v in merged.items() if v is not None}
        if not merged.get("link"):
            await reply_message(update.message, t("ask_link", lang), lang, voice=voice)
        else:
            await reply_message(update.message, t("ask_platform", lang), lang, voice=voice)
        return
    # Already placed (or nothing at all): the live status decides.
    order_id = LAST_ORDER.get(user.id)
    if order_id is None:
        last = await resolve_last_order(user.id)
        if last:
            order_id = last.get("id") or last.get("order_id")
    if order_id is not None:
        await reply_message(
            update.message,
            f"{t('already_placed', lang)}\n"
            f"{await last_order_status_text(user.id, lang)}",
            lang, voice=voice,
        )
        return
    await reply_message(update.message, t("no_order_to_change", lang), lang, voice=voice)


async def handle_refill(update, text, intent, lang, voice=False):
    """'It stopped at 800 out of 1,000, send the rest now.'

    The live status is checked first. Still running -> say so with
    the status. Finished short -> point at support for a refill.
    The bot never promises a refill or a refund, and never places a
    second order without Confirm."""
    user = update.effective_user
    order_id = LAST_ORDER.get(user.id)
    if order_id is None:
        last = await resolve_last_order(user.id)
        if last:
            order_id = last.get("id") or last.get("order_id")
    if order_id is None:
        await reply_message(update.message, t("no_orders", lang), lang, voice=voice)
        return
    try:
        data = await paxyo.order_status(order_id, user.id)
    except Exception as exc:
        log.warning("refill order_status failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    status = str(
        data.get("status") or data.get("order", {}).get("status", "?")
    ).strip().lower()
    if status in ("pending", "in_progress", "processing", "partial",
                  "in progress"):
        await reply_message(
            update.message, t("refill_running", lang, status=status),
            lang, voice=voice,
        )
        return
    if status in ("completed", "complete", "done"):
        await reply_message(update.message, t("refill_finished", lang), lang, voice=voice)
        return
    await reply_message(
        update.message, await last_order_status_text(user.id, lang),
        lang, voice=voice,
    )


async def handle_order_wait(update, text, lang, voice=False):
    """'Why hasn't it started yet? It's been 45 seconds.'

    The real status plus the service's average time, so the answer
    is a real start window — never a bare 'soon'. Falls back to the
    plain status line when no average time is known."""
    user = update.effective_user
    last = await resolve_last_order(user.id)
    order_id = LAST_ORDER.get(user.id)
    if order_id is None and last:
        order_id = last.get("id") or last.get("order_id")
    if order_id is None:
        await reply_message(update.message, t("no_orders", lang), lang, voice=voice)
        return
    try:
        data = await paxyo.order_status(order_id, user.id)
    except Exception as exc:
        log.warning("order wait status failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    status = str(
        data.get("status") or data.get("order", {}).get("status", "?")
    ).strip()
    service_id = (last or {}).get("service_id")
    service_name = (last or {}).get("service_name")
    avg = None
    if service_id is not None:
        try:
            services = await paxyo.services()
            found = find_service_by_id(services, service_id)
            if found is not None:
                avg = found.get("average_time")
                service_name = found.get("name")
        except Exception as exc:
            log.warning("order wait services failed: %s", exc)
    if avg:
        await reply_message(
            update.message,
            t(
                "order_wait", lang, order_id=order_id, status=status,
                service=clean_service_name(service_name)
                or f"service {service_id}",
                avg=avg,
            ),
            lang, voice=voice,
        )
        return
    await reply_message(
        update.message, await last_order_status_text(user.id, lang),
        lang, voice=voice,
    )


async def handle_max_for_balance(update, text, intent, lang, voice=False):
    """'Give me however many views my remaining 42.50 birr can buy.'

    Reverse-calculates from the real balance: floor(balance /
    price-per-unit), rounded down to a multiple of 10, capped by the
    service min/max. Shown on a Confirm card like any other order.
    When the balance buys less than the minimum, say so and suggest
    a deposit."""
    user = update.effective_user
    try:
        data = await paxyo.balance(user.id)
    except Exception as exc:
        log.warning("max-for-balance failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    if not data.get("found"):
        await reply_message(update.message, t("greeting", lang), lang, voice=voice)
        return
    balance = float(data.get("balance", 0))
    platform = (intent.get("platform") or "").strip().lower() or None
    hint = intent.get("service_hint")
    last_service_id = None
    if not platform and not hint:
        last = await resolve_last_order(user.id)
        if last and last.get("service_id"):
            last_service_id = last.get("service_id")
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("max-for-balance services failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    service = None
    if last_service_id is not None:
        service = find_service_by_id(services, last_service_id)
        if service is not None and not service.get("active", True):
            service = None
    if service is None:
        picks = pick_services(services, platform=platform, service_hint=hint)
        if not picks:
            await reply_message(update.message, t("no_service", lang), lang, voice=voice)
            return
        service = picks[0]
    rate = float(service.get("rate_etb_per_1000", 0) or 0)
    if rate <= 0:
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    max_qty = int(balance / (rate / 1000))
    max_qty = (max_qty // 10) * 10
    max_qty = min(max_qty, int(service.get("max", 0) or max_qty))
    if max_qty < int(service.get("min", 0) or 0):
        await reply_message(
            update.message,
            t("max_for_balance_none", lang, balance=format_money(balance)),
            lang, voice=voice,
        )
        return
    metric = hint or clean_service_name(service.get("name"))
    link = intent.get("link")
    note = t(
        "max_for_balance_offer", lang, balance=format_money(balance),
        quantity=max_qty, metric=metric,
    )
    if link:
        merged = {
            "platform": platform, "service_hint": hint,
            "link": link, "quantity": max_qty,
        }
        await complete_order(
            update.message, user.id, merged, lang, voice=voice,
            named_service_id=service.get("service"), note=note,
        )
        return
    # No link yet: remember the computed quantity and ask for it.
    PARTIAL[user.id] = {
        "platform": platform, "service_hint": hint, "quantity": max_qty,
    }
    await reply_message(update.message, note, lang, voice=voice)


async def handle_cheapest_reply(update, intent, lang, voice, key):
    """One real answer for haggling, free samples and price pushback:
    the cheapest real service at its real Paxyo price. Prices are
    fixed — the bot never negotiates and never applies a
    user-supplied price anywhere."""
    user = update.effective_user
    platform = (intent.get("platform") or "").strip().lower() or None
    hint = intent.get("service_hint")
    quantity = intent.get("quantity")
    try:
        quantity = int(quantity) if quantity is not None else None
    except (TypeError, ValueError):
        quantity = None
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("cheapest lookup failed: %s", exc)
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    service = cheapest_service(services, platform=platform, service_hint=hint)
    if service is None:
        await reply_message(update.message, t("no_service", lang), lang, voice=voice)
        return
    metric = hint or clean_service_name(service.get("name"))
    if quantity is None:
        quantity = int(service.get("min", 0) or 0)
    service_max = int(service.get("max", 0) or 0)
    if service_max and quantity > service_max:
        # Never offer a quantity the service cannot take.
        quantity = service_max
    price = (
        f"{format_money(estimated_total_etb(float(service.get('rate_etb_per_1000', 0)), quantity))} "
        f"ETB for {quantity}"
    )
    await reply_message(
        update.message,
        with_pending_note(
            user.id, lang,
            t(
                key, lang, metric=metric,
                service=clean_service_name(service.get("name")),
                price=price,
            ),
        ),
        lang, voice=voice,
    )


async def handle_order_text(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            text: str, voice: bool = False, intent: dict = None):
    """Shared flow for text messages and transcribed voice messages.

    Reply rules (owner, 13 Nov 2026):
    - Text in -> text out, always. Voice in -> voice out, except the
      Confirm card and the post-acceptance summary, which are always
      text (a voice message cannot carry buttons, and a voice
      confirmation must end with a readable text record of the order).
    - A bare acceptance ("yes", "confirm", "አዎ", ...) while an order
      is pending places that order — no new intent is extracted.
    - Gemini first classifies the message (order, recurring, schedules,
      stop_schedule, balance, orders, deposit, deposit_status,
      how_to_order, miniapp, social, help, greeting,
      paxyo_info, source_question, usual, goal, budget, batch,
      change_order, refill, split_payment, max_for_balance, discount,
      safety, refund_policy, geo_target, free_sample, price_pushback,
      content_help, support_issue, cancel, off_topic, unclear).
      Conversational intents are answered before the order flow, so the bot talks like
      customer support instead of only understanding orders;
      off-topic talk is steered back to ordering in one line.
    - Asked where the services come from, or what Paxyo pays for them,
      the bot deflects in one short line (local guard first, then the
      "source_question" intent) — it never names a supplier, never
      gives a figure, and never says the supply chain's name.
    - Deposits are built over several turns (amount -> method ->
      phone) and shown as a Confirm summary; nothing is created
      until confirmed. Typos and slang are normalised first
      ("teleirr" -> "telebirr"), so misspelled messages still
      classify.
    - Orders are built over several turns: what the user already gave
      (platform, service, link, quantity) is remembered per user in
      PARTIAL, so a bare "2000" after a link completes the order. A
      different platform starts a new order; cancelling clears it.
    - A service the user names ("use service 6139", "the cheapest
      Instagram followers", "same service as last time") is used for
      that order instead of the fastest one — validated first (it must
      exist, be active and not be blacklisted). A bad named service is
      refused in one line with a one-tap "Use the fastest one" button.
    - "That link" resolves from the user's most recent order (the
      Paxyo API, so it survives restarts), and a repeating-order plan
      ("every 3 hours") is built the same way, then shown as a plan
      summary with Confirm — nothing repeats until confirmed.
    - Orders work in Amharic and English, by text and by voice.
    """
    user = update.effective_user
    # Tolerate typos and slang before anything else: the classifier,
    # the acceptance check and the follow-up parsers all see the
    # cleaned text. URLs are kept verbatim (case-sensitive links).
    text = normalize_text(text)
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
        # A "yes" can also confirm a repeating-order plan awaiting
        # Confirm: create the schedule and answer with a short text
        # confirmation (a plan summary is always text).
        rec_id, rec_draft = pending_recurring_for_user(user.id)
        if rec_draft is not None:
            PENDING_RECURRING.pop(rec_id, None)
            schedule, error = await start_recurring_plan(rec_draft, user.id)
            if error:
                await update.message.reply_text(t("plan_failed", lang))
                return
            await update.message.reply_text(
                t(
                    "plan_started",
                    lang,
                    quantity=rec_draft["quantity"],
                    service=clean_service_name(rec_draft["service"].get("name")),
                    interval=format_interval(rec_draft["interval_minutes"]),
                )
            )
            return
        # A "yes" can also confirm a deposit awaiting Confirm: start
        # it and answer with the payment instructions IN TEXT (they
        # carry a link/code the user must read, so voice is wrong).
        dep_id, dep_draft = pending_deposit_for_user(user.id)
        if dep_draft is not None:
            PENDING_DEPOSIT.pop(dep_id, None)
            result, error = await start_deposit(dep_draft, user.id)
            if error:
                if error in ("deposit_not_ready", "deposit_failed"):
                    await update.message.reply_text(t(error, lang))
                else:
                    await update.message.reply_text(error)
                return
            await update.message.reply_text(
                deposit_instructions_text(
                    result, dep_draft["amount"], dep_draft["method"], lang
                )
            )
            return
        # A "yes" can also confirm a batch of orders awaiting Confirm:
        # place them all and answer with one short line per order.
        batch_id, batch = pending_batch_for_user(user.id)
        if batch is not None:
            PENDING_BATCH.pop(batch_id, None)
            results, error = await place_batch(batch, user.id)
            if error:
                key = error[0]
                if key == "insufficient":
                    await update.message.reply_text(
                        t(
                            "insufficient",
                            lang,
                            balance=format_money(error[1]),
                            total=format_money(error[2]),
                        )
                    )
                else:
                    await update.message.reply_text(t(key, lang))
                return
            await update.message.reply_text(batch_result_text(results, lang))
            return
        # A "yes" can also accept the offer to check a payment receipt
        # the user sent as a photo: recheck the most recent deposit
        # with Chapa and say what happened.
        if user.id in RECEIPT_OFFER:
            RECEIPT_OFFER.pop(user.id, None)
            await reply_message(
                update.message, await deposit_status_text(user.id, lang),
                lang, voice=voice,
            )
            return
        # No pending order: fall through; the normal flow answers
        # "not understood".

    # "I paid" / "I approved it" while a deposit is pending: the user
    # is asking whether the deposit went through — recheck it with
    # Chapa instead of classifying the message. Skipped while a
    # deposit Confirm card is still open (that deposit has not been
    # created yet, so there is nothing to recheck).
    if is_paid_phrase(text):
        _dep_id, _dep_draft = pending_deposit_for_user(user.id)
        if _dep_draft is None:
            await reply_message(
                update.message, await deposit_status_text(user.id, lang),
                lang, voice=voice,
            )
            return

    # Asked where the services come from, or what Paxyo pays for
    # them: deflect at once, without calling Gemini. Skipped when the
    # intent was injected by the photo handler (already classified).
    if intent is None and is_source_question(text):
        await reply_message(update.message, t("source_question", lang), lang, voice=voice)
        return

    # `intent` is injected by the photo handler (a picture's link is
    # already classified by Gemini vision, so a second text
    # classification of the bare link would be wasted and could
    # misread it). Otherwise the text is classified here.
    if intent is None:
        intent = await extract_intent(text)
    intent_type = (intent.get("intent") or "unclear").strip().lower()

    # "First one" / "second one" after a budget list: the user picked
    # one of the options just shown. Resolve it to that service and
    # ask for the link — the order continues from the picked service
    # instead of the reply being misread as a new order.
    if user.id in BUDGET_OPTIONS:
        choice = budget_choice_index(text)
        if choice is not None:
            stored_options = BUDGET_OPTIONS.get(user.id) or {}
            options = stored_options.get("options") or []
            if 0 <= choice < len(options):
                BUDGET_OPTIONS.pop(user.id, None)
                service = options[choice]
                merged = {
                    "platform": stored_options.get("platform"),
                    "service_hint": stored_options.get("service_hint"),
                    "link": None,
                    "quantity": stored_options.get("quantity"),
                    "service_id": service.get("service"),
                }
                PARTIAL[user.id] = {k: v for k, v in merged.items() if v is not None}
                await reply_message(update.message, t("ask_link", lang), lang, voice=voice)
                return

    # --- conversational intents: answered before the order flow ---
    if intent_type == "cancel":
        # "I don't want to" / "cancel": drop any pending order and any
        # order being built, and say so. When BOTH a pending order and
        # repeating orders exist, "cancel" is ambiguous — ask which one
        # to stop instead of guessing.
        confirm_id, pending = pending_for_user(user.id)
        rec_id, rec_draft = pending_recurring_for_user(user.id)
        if rec_draft is not None and pending is None:
            PENDING_RECURRING.pop(rec_id, None)
            RECURRING_DRAFT.pop(user.id, None)
            await reply_message(update.message, t("cancelled", lang), lang, voice=voice)
            return
        dep_id, dep_draft = pending_deposit_for_user(user.id)
        if dep_draft is not None and pending is None and rec_draft is None:
            PENDING_DEPOSIT.pop(dep_id, None)
            DEPOSIT_DRAFT.pop(user.id, None)
            await reply_message(update.message, t("cancelled", lang), lang, voice=voice)
            return
        batch_id, batch = pending_batch_for_user(user.id)
        if batch is not None and pending is None and rec_draft is None and dep_draft is None:
            PENDING_BATCH.pop(batch_id, None)
            SPLIT_DRAFT.pop(user.id, None)
            await reply_message(update.message, t("cancelled", lang), lang, voice=voice)
            return
        if pending is not None:
            try:
                schedules = await paxyo.list_recurring(user.id)
            except Exception:
                schedules = []
            if schedules:
                buttons = [[
                    InlineKeyboardButton(
                        t("stop_this_order", lang),
                        callback_data=f"cancel:{confirm_id}",
                    )
                ]]
                for sched in schedules:
                    label = (
                        f"🛑 {clean_service_name(sched.get('service_name')) or sched.get('service_id')} "
                        f"every {format_interval(sched.get('interval_minutes'))}"
                    )
                    buttons.append([InlineKeyboardButton(
                        label, callback_data=f"stoprec:{sched.get('id')}"
                    )])
                await reply_message(
                    update.message, t("stop_which", lang), lang, voice=voice,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
                return
            PENDING.pop(confirm_id, None)
            PARTIAL.pop(user.id, None)
            BUDGET_OPTIONS.pop(user.id, None)
            await reply_message(update.message, t("cancelled", lang), lang, voice=voice)
            return
        # No pending order: the user may mean a repeating order.
        try:
            schedules = await paxyo.list_recurring(user.id)
        except Exception:
            schedules = []
        if schedules:
            await stop_schedules_flow(update, schedules, lang, voice=voice)
            return
        PARTIAL.pop(user.id, None)
        RECURRING_DRAFT.pop(user.id, None)
        DEPOSIT_DRAFT.pop(user.id, None)
        SPLIT_DRAFT.pop(user.id, None)
        BUDGET_OPTIONS.pop(user.id, None)
        dep_id, _dep = pending_deposit_for_user(user.id)
        if dep_id is not None:
            PENDING_DEPOSIT.pop(dep_id, None)
        batch_id, _batch = pending_batch_for_user(user.id)
        if batch_id is not None:
            PENDING_BATCH.pop(batch_id, None)
        await reply_message(update.message, t("cancelled", lang), lang, voice=voice)
        return
    if intent_type == "recurring":
        await handle_recurring_text(update, text, intent, lang, voice=voice)
        return
    if intent_type == "schedules":
        await reply_message(
            update.message, await schedules_text(user.id, lang), lang, voice=voice
        )
        return
    if intent_type == "stop_schedule":
        await handle_stop_schedule(update, lang, voice=voice)
        return
    if intent_type == "balance":
        await reply_message(
            update.message, await balance_text(user.id, lang), lang, voice=voice
        )
        return
    if intent_type == "orders":
        # "Why hasn't it started yet?" gets the real status plus the
        # service's average time; a plain status question gets the
        # plain status line.
        if is_wait_question(text):
            await handle_order_wait(update, text, lang, voice=voice)
            return
        await reply_message(
            update.message, await last_order_status_text(user.id, lang),
            lang, voice=voice,
        )
        return
    if intent_type == "deposit":
        await handle_deposit_text(update, text, intent, lang, voice=voice)
        return
    if intent_type == "deposit_status":
        await reply_message(
            update.message, await deposit_status_text(user.id, lang),
            lang, voice=voice,
        )
        return
    # --- messy real-world inputs (owner edge-case spec, 13 Nov 2026) ---
    if intent_type == "usual":
        await handle_usual(update, text, intent, lang, voice=voice)
        return
    if intent_type == "goal":
        # A goal is not a service: ask which metric matters, then
        # build the order from the answer.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("ask_metric", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "budget":
        await handle_budget_text(update, text, intent, lang, voice=voice)
        return
    if intent_type == "batch":
        await handle_batch_text(update, text, intent, lang, voice=voice)
        return
    if intent_type == "change_order":
        await handle_change_order(update, text, intent, lang, voice=voice)
        return
    if intent_type == "refill":
        await handle_refill(update, text, intent, lang, voice=voice)
        return
    if intent_type == "split_payment":
        # One payment source per order: the Telebirr half is deposited
        # first, then the order comes from the wallet balance.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("split_payment_no", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "max_for_balance":
        await handle_max_for_balance(update, text, intent, lang, voice=voice)
        return
    if intent_type == "discount":
        await handle_cheapest_reply(update, intent, lang, voice, "discount_no")
        return
    if intent_type == "free_sample":
        await handle_cheapest_reply(update, intent, lang, voice, "free_sample_no")
        return
    if intent_type == "price_pushback":
        # Prices are fixed by Paxyo — the bot never applies a
        # user-supplied price anywhere; it offers the cheapest real
        # option instead.
        await handle_cheapest_reply(update, intent, lang, voice, "price_fixed")
        return
    if intent_type == "safety":
        # Honest, never overpromising: gradual and widely used, but
        # no zero-risk guarantee, and followers are not guaranteed
        # real Ethiopian people. A slower service is offered when the
        # platform is known.
        safety_text = t("safety", lang)
        platform = (intent.get("platform") or "").strip().lower() or None
        hint = intent.get("service_hint")
        if platform or hint:
            try:
                services = await paxyo.services()
                slow = slowest_service(
                    services, platform=platform, service_hint=hint
                )
                if slow is not None and slow.get("average_time"):
                    safety_text += "\n" + t(
                        "safety_slow", lang,
                        service=clean_service_name(slow.get("name")),
                        avg=slow.get("average_time"),
                    )
            except Exception as exc:
                log.warning("safety slowest lookup failed: %s", exc)
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, safety_text),
            lang, voice=voice,
        )
        return
    if intent_type == "refund_policy":
        # Never invent a refund policy: support reviews it, the bot
        # promises nothing itself.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("refund_policy", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "geo_target":
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("geo_no", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "content_help":
        # Brief general tips are allowed, then back to ordering.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("content_help", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "support_issue":
        # The bot cannot fix the website account itself: point at the
        # deposit recheck and the Paxyo team.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("support_redirect", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "help":
        await reply_message(update.message, t("help", lang), lang, voice=voice)
        return
    if intent_type == "how_to_order":
        # Short numbered guide + a Start button that begins the order
        # flow (asks for the platform). The button forces text: a
        # voice message cannot carry buttons.
        await reply_message(
            update.message, t("how_to_order", lang), lang, voice=voice,
            reply_markup=start_order_keyboard(lang),
        )
        return
    if intent_type == "miniapp":
        await reply_message(update.message, t("miniapp", lang), lang, voice=voice)
        return
    if intent_type == "social":
        await reply_message(update.message, t("social", lang), lang, voice=voice)
        return
    if intent_type == "greeting":
        await reply_message(update.message, t("greeting", lang), lang, voice=voice)
        return
    if intent_type == "source_question":
        await reply_message(update.message, t("source_question", lang), lang, voice=voice)
        return
    if intent_type == "paxyo_info":
        await reply_message(
            update.message, await answer_paxyo_question(text, lang),
            lang, voice=voice,
        )
        return
    if intent_type == "off_topic":
        # One short polite line steering back to ordering — never
        # preachy, never long, never a lecture about the topic itself.
        await reply_message(update.message, t("off_topic", lang), lang, voice=voice)
        return

    # Mid-deposit follow-up: the user is answering the bot's deposit
    # question ("50", "telebirr", "099387383"). Gemini may call a bare
    # answer "unclear", so fill the deposit draft from the message
    # itself when it carries a deposit field. A phone number or a
    # method word is unambiguous; a bare number only counts when no
    # order is being built at the same time.
    if intent_type == "unclear" and user.id in DEPOSIT_DRAFT:
        phone = normalize_phone(text)
        method = normalize_method(text)
        amount = parse_deposit_amount(text)
        if phone is not None or method is not None or (
            amount is not None and not PARTIAL.get(user.id)
        ):
            merged_intent = {
                "intent": "deposit",
                "platform": None, "service_hint": None, "link": None,
                "quantity": None, "interval_minutes": None,
                "amount": amount, "method": method, "phone": phone,
            }
            await handle_deposit_text(update, text, merged_intent, lang, voice=voice)
            return

    # The user is answering the split-links question: feed the pasted
    # links into the waiting split instead of starting a single order
    # with the first link.
    if user.id in SPLIT_DRAFT and extract_links(text):
        stored_split = SPLIT_DRAFT.get(user.id) or {}
        await handle_split_text(update, text, {
            "quantity": stored_split.get("quantity"),
            "count": stored_split.get("count"),
            "platform": stored_split.get("platform"),
            "service_hint": stored_split.get("service_hint"),
        }, lang, voice=voice)
        return

    # --- order flow: multi-turn state ---
    # What the user already gave is remembered per user in PARTIAL, so a
    # bare "2000" after a link, or a bare link after a service, completes
    # the order instead of "I did not understand". A message naming a
    # different platform starts a new order and drops the stored pieces.
    stored = PARTIAL.get(user.id) or {}
    new_platform = (intent.get("platform") or "").strip().lower()
    stored_platform = (stored.get("platform") or "").strip().lower()
    if new_platform and stored_platform and new_platform != stored_platform:
        stored = {}
    merged = {}
    for key in ("platform", "service_hint", "link", "quantity", "service_id"):
        value = intent.get(key)
        merged[key] = value if value is not None else stored.get(key)

    # A service the user named: Gemini's service_id first, the local
    # ID regex as fallback ("service 6139", "#6139", a bare "6139").
    # A bare number is a service ID, not a quantity — quantities must
    # be multiples of 10 — so "6139" alone never becomes quantity 6139.
    named_service_id = merged.get("service_id")
    if named_service_id is None:
        named_service_id = extract_service_id(text)
    if named_service_id is not None:
        merged["service_id"] = named_service_id
        bare = re.sub(r"[.!?]+$", "", text.strip())
        if re.fullmatch(r"\d+", bare) and merged.get("quantity") == named_service_id:
            merged["quantity"] = None

    # "That link" / "same service": resolve from the user's most
    # recent order, which lives on the server and survives restarts.
    # "Same service" names the last order's service for this order,
    # even when a fresh link was given.
    last_service_id = None
    same_service = mentions_same_service(text)
    if (not merged.get("link") and mentions_that_link(text)) or same_service:
        last = await resolve_last_order(user.id)
        if last:
            if not merged.get("link") and mentions_that_link(text):
                merged["link"] = last.get("link")
                last_service_id = last.get("service_id")
            if same_service and named_service_id is None:
                last_service_id = last.get("service_id")
                if last_service_id is not None:
                    named_service_id = last_service_id
                    merged["service_id"] = named_service_id

    # A link for the wrong platform ("YouTube subscribers" to a
    # TikTok URL): point it out and wait for the correction — never
    # place a mismatched order. Handles (@user1) have no domain, so
    # they never trigger this.
    merged_platform = (merged.get("platform") or "").strip().lower()
    merged_link_platform = (
        platform_from_link(merged["link"]) if merged.get("link") else None
    )
    if (
        merged_platform
        and merged_link_platform
        and merged_platform != merged_link_platform
    ):
        PARTIAL[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(
            update.message,
            t(
                "platform_mismatch", lang,
                link_platform=merged_link_platform,
                platform=merged_platform,
            ),
            lang, voice=voice,
        )
        return

    # Nothing to work with at all: not understood. (A bare number or a
    # bare link with no context still counts as something: it is stored
    # and the bot asks for the next missing piece below.)
    if (
        intent_type != "order"
        and not merged.get("platform")
        and not merged.get("service_hint")
        and not merged.get("link")
        and not merged.get("quantity")
        and not merged.get("service_id")
    ):
        if intent.get("gemini_failed"):
            await reply_message(update.message, t("gemini_busy", lang), lang, voice=voice)
        else:
            await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    # A named service implies its platform, so the bot asks for the
    # link next instead of the platform.
    if (
        not merged.get("platform")
        and not merged.get("service_hint")
        and last_service_id is None
        and not merged.get("service_id")
    ):
        PARTIAL[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_platform", lang), lang, voice=voice)
        return
    # A question about the order being built ("how fast can you
    # deliver it?", "wouldn't it drop?") is answered from the stored
    # service instead of asking for the link again. Only when the
    # order is actually waiting for its link and the message carries
    # no new order details — the helper checks that. The partial
    # stays open, so the next message still completes the order.
    if not merged.get("link") and (stored.get("platform") or stored.get("service_hint")):
        question = pending_order_question(text)
        if question is not None:
            try:
                services = await paxyo.services()
            except Exception as exc:
                log.warning("pending-question services failed: %s", exc)
                services = []
            picks = pick_services(
                services, platform=stored.get("platform"),
                service_hint=stored.get("service_hint"),
            ) if services else []
            if picks:
                service = picks[0]
                name = clean_service_name(service.get("name"))
                if question == "speed":
                    avg = service.get("average_time")
                    if parse_average_time(avg) is not None:
                        answer = t("pending_speed", lang, service=name, avg=avg)
                    else:
                        answer = t("pending_speed_unknown", lang, service=name)
                else:
                    low = str(service.get("name") or "").lower()
                    if "no refill" in low:
                        refill = t("pending_no_refill", lang)
                    elif "refill" in low:
                        refill = t("pending_has_refill", lang)
                    else:
                        refill = t("pending_refill_unknown", lang)
                    answer = t("pending_drop", lang, service=name, refill=refill)
                await reply_message(update.message, answer, lang, voice=voice)
                return
    if not merged.get("link"):
        PARTIAL[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_link", lang), lang, voice=voice)
        return
    if not merged.get("quantity"):
        PARTIAL[user.id] = {k: v for k, v in merged.items() if v is not None}
        await reply_message(update.message, t("ask_quantity", lang), lang, voice=voice)
        return

    # Complete order: fetch services, use the named service (or the
    # fastest one), and show the Confirm card. A handle target is
    # shown exactly as typed with a spelling double-check, and a
    # private account or expiring story link gets a one-line warning
    # on the card. Shortened links need no warning — the provider
    # resolves them.
    notes = []
    if merged.get("link") and str(merged["link"]).strip().startswith("@"):
        notes.append(t("check_handle", lang, handle=str(merged["link"]).strip()))
    if link_needs_warning(text, merged.get("link")):
        notes.append(t("link_warning", lang))
    await complete_order(
        update.message, user.id, merged, lang, voice=voice,
        named_service_id=named_service_id,
        last_service_id=last_service_id,
        note="\n".join(notes) if notes else None,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Text in -> text out, always. The bot never answers a text
    # message with a voice message (handle_order_text gets voice=False).
    if _update_seen(update):
        return
    await handle_order_text(update, context, update.message.text or "")


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _update_seen(update):
        return
    user = update.effective_user
    lang = lang_of("", user.language_code)
    try:
        voice_file = await update.message.voice.get_file()
        audio = bytes(await voice_file.download_as_bytearray())
        text = await ai_transcribe(audio)
    except Exception as exc:
        log.warning("voice handling failed: %s", exc)
        await update.message.reply_text(t("transcribe_failed", lang))
        return
    if not text:
        await update.message.reply_text(t("transcribe_failed", lang))
        return
    await handle_order_text(update, context, text, voice=True)


# ------------------------------------------------------------ photos ------
# A picture in gets a picture-reading reply, not "I did not
# understand". The largest size is downloaded (in memory only — never
# written to disk) and sent to Gemini vision, which returns compact
# JSON (see VISION_PROMPT). Routing:
# - deposit_receipt: what was found is shown and the user is offered
#   a recheck of their most recent deposit (button or a bare "yes").
#   That recheck is the same deposit_status_text the text flow uses,
#   so the server re-verifies with Chapa before answering.
# - order: the extracted link starts the order flow with the intent
#   already built (no second Gemini call). A photo of a profile/post
#   while an order is being built fills the missing link the same
#   way a typed link would, because handle_order_text merges PARTIAL.
# - support/other: the summary plus one short follow-up question.
# A vision failure, timeout or unreadable result gets one short
# fallback line — never a retry loop.

def receipt_keyboard(lang: str) -> InlineKeyboardMarkup:
    """One button: "Yes, check it" — recheck the deposit the receipt
    is about. The button is text-only, like the Confirm card."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("check_deposit_button", lang),
                               callback_data="checkdep:")]]
    )


async def route_photo_result(update, result: dict, lang: str):
    """Act on a parsed vision result, in the user's language."""
    user = update.effective_user
    want = result.get("want") or "other"
    if want == "deposit_receipt":
        amount = result.get("amount")
        tx_ref = result.get("tx_ref")
        if amount is None and not tx_ref:
            # A payment screenshot the model could not read: say so
            # and ask for the amount in text.
            await update.message.reply_text(t("photo_receipt_no_details", lang))
            return
        # What was found, then offer the recheck. The recheck does
        # not need the tx_ref — deposit_status_text rechecks the
        # user's most recent deposit — but the ref is remembered in
        # case the user quotes it, and shown so they can confirm it
        # is theirs.
        details = "a payment"
        if amount is not None:
            details = f"a {format_money(amount)} ETB payment"
        if tx_ref:
            details += f", ref {tx_ref}"
        RECEIPT_OFFER[user.id] = {"amount": amount, "tx_ref": tx_ref}
        await update.message.reply_text(
            t("photo_receipt_found", lang, details=details),
            reply_markup=receipt_keyboard(lang),
        )
        return
    if want == "order":
        link = result.get("link")
        if link:
            # The link is already classified by vision: inject the
            # intent so the order flow starts without a second
            # Gemini call. Platform from the link's domain, so the
            # flow goes straight to "how many?".
            intent = {
                "intent": "order",
                "platform": platform_from_link(link),
                "service_hint": None,
                "link": link,
                "quantity": None,
                "interval_minutes": None,
                "amount": None,
                "method": None,
                "phone": None,
            }
            await handle_order_text(
                update, None, link, intent=intent
            )
            return
        username = result.get("username")
        if username:
            await update.message.reply_text(
                t("photo_order_username", lang, username=username)
            )
            return
        await update.message.reply_text(t("photo_unreadable", lang))
        return
    # support / other: the summary plus one short follow-up question.
    summary = (result.get("summary") or "").strip()
    if not summary:
        await update.message.reply_text(t("photo_unreadable", lang))
        return
    await update.message.reply_text(t("photo_other", lang, summary=summary))


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _update_seen(update):
        return
    user = update.effective_user
    message = update.message
    # Language from the caption when there is one, else the
    # Telegram account language; default English.
    lang = lang_of(message.caption or "", user.language_code)
    photos = message.photo or []
    if not photos:
        await message.reply_text(t("photo_unreadable", lang))
        return
    # The largest size is last.
    photo = photos[-1]
    size = getattr(photo, "file_size", None)
    if size is not None and size > MAX_PHOTO_BYTES:
        await message.reply_text(t("photo_too_big", lang))
        return
    try:
        photo_file = await photo.get_file()
        image = bytes(await photo_file.download_as_bytearray())
    except Exception as exc:
        log.warning("photo download failed: %s", exc)
        await message.reply_text(t("photo_unreadable", lang))
        return
    if len(image) > MAX_PHOTO_BYTES:
        await message.reply_text(t("photo_too_big", lang))
        return
    try:
        raw = await ai_vision(image)
    except Exception as exc:
        log.warning("ai_vision failed: %s", exc)
        await message.reply_text(t("photo_unreadable", lang))
        return
    result = parse_vision_result(raw)
    if result is None:
        await message.reply_text(t("photo_unreadable", lang))
        return
    await route_photo_result(update, result, lang)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _update_seen(update):
        return
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    lang = lang_of(query.message.text or "", user.language_code)
    action, _, arg = (query.data or "").partition(":")

    if action == "checkdep":
        # "Yes, check it" on a payment-receipt photo: recheck the
        # most recent deposit and replace the receipt message with
        # the result (same recheck the text flow uses).
        RECEIPT_OFFER.pop(user.id, None)
        await query.edit_message_text(await deposit_status_text(user.id, lang))
        return

    if action == "start_order":
        # "Start an order" from the how-to guide: drop any half-built
        # order or plan and ask which platform, so the next message
        # starts a fresh order.
        PARTIAL.pop(user.id, None)
        RECURRING_DRAFT.pop(user.id, None)
        await query.edit_message_text(t("ask_platform", lang))
        return

    if action == "usefastest":
        # "Use the fastest one" after a named service turned out
        # unusable: resume the same order with the fastest pick.
        # The Confirm card arrives as a new message (the error message
        # stays above it, so the user sees what happened).
        fallback = FASTEST_FALLBACK.pop(arg, None)
        if fallback is None or fallback["user_id"] != user.id:
            await query.edit_message_text(t("cancelled", lang))
            return
        merged = dict(fallback["merged"])
        merged.pop("service_id", None)
        # The user already chose "the fastest one" — do not ask
        # which metric; the fastest pick is what they tapped for.
        await complete_order(query.message, user.id, merged, lang,
                             ask_metric=False)
        return

    if action == "stoprec":
        # Stop one repeating order from a button.
        try:
            schedules = await paxyo.list_recurring(user.id)
        except Exception as exc:
            log.warning("list_recurring failed: %s", exc)
            await query.edit_message_text(t("not_understood", lang))
            return
        sched = next(
            (s for s in schedules if str(s.get("id")) == arg), None
        )
        if sched is None:
            await query.edit_message_text(t("no_schedules", lang))
            return
        try:
            await paxyo.cancel_recurring(sched.get("id"), user.id)
        except Exception as exc:
            log.warning("cancel_recurring failed: %s", exc)
            await query.edit_message_text(t("not_understood", lang))
            return
        name = clean_service_name(sched.get("service_name")) or f"service {sched.get('service_id')}"
        await query.edit_message_text(
            t("schedule_stopped", lang, service=name)
        )
        return

    # Single order first, then a repeating-order plan: both use the
    # same Confirm/Cancel buttons, distinguished by which store holds
    # the id.
    pending = PENDING.pop(arg, None)
    if pending is not None:
        if pending["user_id"] != user.id:
            await query.edit_message_text(t("cancelled", lang))
            return
        if action == "cancel":
            await query.edit_message_text(t("cancelled", lang))
            return
        # Button tap: place the order and replace the Confirm card with
        # the full order summary IN TEXT — the same summary a voice
        # acceptance gets as a new message (see send_order_result).
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
        return

    rec_draft = PENDING_RECURRING.pop(arg, None)
    if rec_draft is not None:
        if rec_draft["user_id"] != user.id:
            await query.edit_message_text(t("cancelled", lang))
            return
        if action == "cancel":
            await query.edit_message_text(t("cancelled", lang))
            return
        # Confirm tap: create the repeating order on the server and
        # replace the plan summary with a short confirmation (text).
        schedule, error = await start_recurring_plan(rec_draft, user.id)
        if error:
            await query.edit_message_text(t("plan_failed", lang))
            return
        await query.edit_message_text(
            t(
                "plan_started",
                lang,
                quantity=rec_draft["quantity"],
                service=clean_service_name(rec_draft["service"].get("name")),
                interval=format_interval(rec_draft["interval_minutes"]),
            )
        )
        return

    dep_draft = PENDING_DEPOSIT.pop(arg, None)
    if dep_draft is not None:
        if dep_draft["user_id"] != user.id:
            await query.edit_message_text(t("cancelled", lang))
            return
        if action == "cancel":
            await query.edit_message_text(t("cancelled", lang))
            return
        # Confirm tap: start the deposit and replace the summary with
        # the payment instructions (text — they carry a link/code the
        # user must read).
        result, error = await start_deposit(dep_draft, user.id)
        if error:
            if error in ("deposit_not_ready", "deposit_failed"):
                await query.edit_message_text(t(error, lang))
            else:
                await query.edit_message_text(error)
            return
        await query.edit_message_text(
            deposit_instructions_text(
                result, dep_draft["amount"], dep_draft["method"], lang
            )
        )
        return

    batch = PENDING_BATCH.pop(arg, None)
    if batch is not None:
        if batch["user_id"] != user.id:
            await query.edit_message_text(t("cancelled", lang))
            return
        if action == "cancel":
            await query.edit_message_text(t("cancelled", lang))
            return
        # Confirm tap: place every order in the batch and replace the
        # card with one short line per order.
        results, error = await place_batch(batch, user.id)
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
        await query.edit_message_text(batch_result_text(results, lang))
        return

    await query.edit_message_text(t("cancelled", lang))


# ------------------------------------------- recurring scheduler ----
# A background loop that runs the repeating orders. It wakes every 60
# seconds and asks the server which schedules are due. The free tier
# sleeps after ~15 minutes idle, so a schedule can be hours late: it
# still runs ONCE on wake (the server advances next_run_at from now,
# never from the stale time), never once per missed interval. A run is
# placed with an idempotency key per schedule+slot, so even if the
# server did not advance the time, a retry returns the same order
# instead of a second charge.

RECURRING_CHECK_SECONDS = 60
MIN_RECURRING_MINUTES = 30


async def notify_user(app, user_id: int, text: str):
    """Send a plain text message to a user from the scheduler. Never
    raises — a failed send must not kill the loop."""
    try:
        await app.bot.send_message(chat_id=user_id, text=text)
    except Exception as exc:
        log.warning("notify_user %s failed: %s", user_id, exc)


async def run_one_schedule(app, sched, services_by_id):
    """Place one due repeating order, or pause it when the balance is
    short. One due schedule = at most one order per cycle."""
    schedule_id = sched.get("id")
    user_id = sched.get("user_id")
    try:
        service_id = int(sched.get("service_id"))
    except (TypeError, ValueError):
        service_id = None
    service = services_by_id.get(service_id) if service_id is not None else None
    if service is None:
        log.warning(
            "recurring %s: service %s not found, skipping",
            schedule_id, sched.get("service_id"),
        )
        return
    try:
        quantity = int(sched.get("quantity") or 0)
    except (TypeError, ValueError):
        quantity = 0
    if quantity <= 0:
        log.warning("recurring %s: bad quantity, skipping", schedule_id)
        return
    total = estimated_total_etb(float(service.get("rate_etb_per_1000", 0)), quantity)
    try:
        bal = await paxyo.balance(user_id)
    except Exception as exc:
        log.warning("recurring %s: balance check failed: %s", schedule_id, exc)
        return  # retry next cycle; nothing placed, nothing sent
    balance = float(bal.get("balance", 0)) if bal.get("found") else 0.0
    name = clean_service_name(service.get("name"))
    if balance < total:
        # Never place an order the user cannot pay for: pause the
        # schedule on the server and tell the user why, once.
        try:
            await paxyo.pause_recurring(schedule_id, user_id)
        except Exception as exc:
            log.warning("recurring %s: pause failed: %s", schedule_id, exc)
        await notify_user(
            app, user_id,
            t(
                "plan_paused", "en", service=name,
                balance=format_money(balance), total=format_money(total),
            ),
        )
        return
    slot = sched.get("next_run_at") or ""
    key = f"rec-{schedule_id}-{slot}"
    try:
        result = await paxyo.create_order(
            user_id, int(service["service"]), sched.get("link"), quantity, key
        )
    except Exception as exc:
        log.warning("recurring %s: order failed: %s", schedule_id, exc)
        await notify_user(app, user_id, t("recurring_failed", "en"))
        return
    order = result.get("order", result) if isinstance(result, dict) else {}
    order_id = order.get("id") or order.get("order_id") or "?"
    status = order.get("status", "pending")
    try:
        await paxyo.mark_recurring_ran(schedule_id, user_id, order_id)
    except Exception as exc:
        # The order is placed; the idempotency key (schedule+slot)
        # means a retry next cycle returns the same order, not a
        # second charge. Log and move on.
        log.warning("recurring %s: mark_ran failed: %s", schedule_id, exc)
    await notify_user(
        app, user_id,
        t(
            "recurring_placed", "en", quantity=quantity, service=name,
            order_id=order_id, status=status,
        ),
    )


async def run_scheduler_cycle(app):
    """One pass over due repeating orders. Never raises."""
    try:
        due = await paxyo.due_recurring()
    except Exception as exc:
        log.warning("recurring due fetch failed: %s", exc)
        return
    if not due:
        return
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("recurring services fetch failed: %s", exc)
        return
    by_id = {}
    for s in services or []:
        try:
            by_id[int(s.get("service"))] = s
        except (TypeError, ValueError):
            continue
    for sched in due:
        if not isinstance(sched, dict):
            continue
        await run_one_schedule(app, sched, by_id)


async def scheduler_loop(app):
    """Background loop: run the due repeating orders every 60 seconds
    until the task is cancelled (on shutdown). Started next to the
    webhook server in serve_webhook()."""
    while True:
        await run_scheduler_cycle(app)
        await asyncio.sleep(RECURRING_CHECK_SECONDS)


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
    app.add_handler(CommandHandler("schedules", schedules_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
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
    # The repeating-orders scheduler runs next to the webhook server.
    # It only places orders the server says are due, and it tolerates
    # the free tier sleeping: a late schedule runs once on wake.
    scheduler_task = asyncio.create_task(scheduler_loop(app))
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
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
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
