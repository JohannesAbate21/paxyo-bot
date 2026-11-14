#!/usr/bin/env python3
"""Paxyo Order bot (@paxorder_bot).

Users order Paxyo social-media services by text/chat,
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

Voice input: a voice message is downloaded and transcribed (Groq
Whisper first, then OpenAI, then Gemini) and handled exactly like the
same typed message; the transcription is shown to the user ("You
said: ...") so they can see what the bot heard. The bot answers in
text and does NOT claim to take orders by voice (owner, 13 Nov 2026)
— the Cloud TTS voice-reply code stays in the file but no TTS key is
configured, so every reply is text. The Confirm card is always text,
because a voice message cannot carry inline buttons, and so is the
post-acceptance order summary. Any voice failure is answered with
one plain line and never breaks an order. (Gemini TTS was tried first
and verified 13 Nov 2026 to return no audio at all for Amharic, with
only 10 requests/day on the free-tier key — see README, "Voice
replies".)

Runs as a FREE Render web service, not a paid background worker: Telegram
sends updates to a webhook instead of the bot polling. On startup the bot
sets its webhook to <RENDER_EXTERNAL_URL>/<path> (path defaults to the bot
token) and serves Render's health check at GET / ("ok"). Free web services
sleep after ~15 minutes idle and wake in ~30-50s on the first message.
"""

import asyncio
import base64
import contextvars
from datetime import datetime, timezone
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
# OpenAI (ChatGPT) — the fourth AI since 13 Nov 2026, now behind
# DeepSeek, Qwen and Groq: the Gemini free-tier key kept hitting its
# per-minute limit (429), so when OPENAI_API_KEY is set the bot
# classifies, transcribes and reads pictures with OpenAI instead,
# and only falls back to Gemini when no OpenAI key is set. The key
# is a Render env var, never in code. gpt-4o-mini retires
# 2027-01-14; the model is an env var on purpose, so the switch
# is one setting, not a code change.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1"
# Groq — the first AI from 13 Nov 2026 until DeepSeek took over
# that evening (see below). OpenAI's $5 credit could not be
# bought (the owner's Bybit card was declined), so the bot uses
# Groq's free tier instead — no card needed, just a free API
# key. Groq's API is OpenAI-compatible (same chat-completions
# shape, same Whisper transcription endpoint). Default model
# openai/gpt-oss-120b (current production model, 13 Nov 2026;
# the old default llama-3.3-70b-versatile 404s — Groq retired it
# for free accounts). Groq retires models without warning, so the
# model is an env var on purpose: if Groq 404s on it again, switch
# GROQ_MODEL in Render, not the code. The key is a Render env var,
# never in code.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_URL = "https://api.groq.com/openai/v1"
# DeepSeek — the FIRST AI since the evening of 13 Nov 2026: Groq's
# free tier hit its daily token limit (73% used by 21:48 EAT) and
# Groq had temporarily disabled Developer (paid) upgrades, so the
# owner said "use DeepSeek". DeepSeek's API is OpenAI-compatible
# (same chat-completions shape as Groq/OpenAI). Default model
# deepseek-chat (V4.1 Flash): $0.15/1M input, $0.60/1M output
# off-peak (double at peak); new accounts get 5M free tokens for
# 30 days. DeepSeek has no voice transcription — ai_transcribe
# stays on Groq Whisper. The key is a Render env var, never in code.
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/v1"
# OpenCode Zen — the SECOND AI since 14 Nov 2026 (owner, 14 Nov
# 2026): a free gateway (email-only signup, no card) that serves
# free models via an OpenAI-compatible API
# (https://opencode.ai/zen/v1). Default model
# "deepseek-v4.1-flash-free" — the owner's favourite model, free
# here. 10 requests/minute on the free tier. The free roster
# rotates constantly, so the model is an env var on purpose: if
# Zen retires the model, switch ZEN_MODEL in Render, not the code.
# Amharic is unproven on Zen — Amharic messages go through the
# Gemini translate-bridge (see below) instead. It only runs after
# DeepSeek failed, and a Zen failure falls through to Qwen, then
# Mistral, then Groq, then OpenAI, then Gemini, then Kilo, then
# OpenRouter, then GLM. The key is a Render env var, never in code.
ZEN_API_KEY = os.environ.get("ZEN_API_KEY", "")
ZEN_MODEL = os.environ.get("ZEN_MODEL", "deepseek-v4.1-flash-free")
ZEN_URL = os.environ.get("ZEN_URL", "https://opencode.ai/zen/v1")
# Qwen-Turbo (Alibaba) — the THIRD AI since 13 Nov 2026: ~3x
# cheaper than DeepSeek ($0.05/1M input, $0.20/1M output) via the
# international DashScope endpoint, which is OpenAI-compatible
# (same chat-completions shape as DeepSeek/Groq/OpenAI). Amharic is
# unproven on Qwen — Amharic messages go through the Gemini
# translate-bridge (see below) instead. The key is a Render env
# var, never in code.
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-turbo")
QWEN_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
# GLM (Zhipu / Z.AI) — the LAST-RESORT fallback since 13 Nov 2026:
# GLM-4.7-Flash is FREE ($0 input/output) but rate-limited (~1
# request/second) and can be slow, so it only runs after every other
# provider failed. OpenAI-compatible via https://api.z.ai/api/paas/v4/.
# The key is a Render env var, never in code.
GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
GLM_MODEL = os.environ.get("GLM_MODEL", "glm-4.7-flash")
GLM_URL = "https://api.z.ai/api/paas/v4"
# OpenRouter — the second-to-last fallback since 14 Nov 2026: it
# routes to a currently-free model (default model "openrouter/free",
# which picks a free model automatically, so the rotating free
# lineup cannot break the integration) via an OpenAI-compatible API
# (https://openrouter.ai/api/v1). Free :free models cost $0/token:
# 50 requests/day with no credits bought, 1,000/day after a
# one-time $10 credit purchase (the owner's choice, 14 Nov 2026 —
# he pays it himself). It only runs after Gemini failed, so it
# never burns its daily cap on healthy days; GLM stays the last
# resort. No card needed to sign up and get a key. The key is a
# Render env var, never in code.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1"
# Kilo Code gateway — the free fallback since 14 Nov 2026: it
# routes to a currently-free model (default model "kilo-auto/free",
# which picks a free model automatically, so the rotating free
# lineup cannot break the integration) via an OpenAI-compatible API
# (https://api.kilo.ai/api/gateway). $0 total — no key, no signup,
# no card, no Authorization header. 200 requests/hour per IP, so
# it only runs after Gemini failed, and a Kilo failure falls
# through to OpenRouter, then GLM. Caveat (owner told, 14 Nov
# 2026): the limit is per IP and Render's free tier shares outbound
# IPs with other tenants, so another service can eat the quota;
# and free prompts may be used for training — the bot sends no
# secrets, balances, orders, phone numbers or payment details to
# any provider, so nothing sensitive goes there.
KILO_MODEL = os.environ.get("KILO_MODEL", "kilo-auto/free")
KILO_URL = "https://api.kilo.ai/api/gateway"
# Mistral (La Plateforme) — the fourth provider since 14 Nov 2026:
# pay-as-you-go (owner's choice, 14 Nov 2026 — $0.10/$0.30 per 1M
# tokens; PAYG needs $10 prepaid credits first (min buy $10,
# no monthly minimum; he adds the card himself). The Free plan has no API access, so a key needs billing
# on. ~1 request/second on the free tier, higher once billing is
# on. Default model "mistral-small-latest" via an OpenAI-compatible
# API (https://api.mistral.ai/v1). The bot sends no secrets,
# balances, orders, phone numbers or payment details to any
# provider, so nothing sensitive goes there. Amharic is unproven on
# Mistral — Amharic messages go through the Gemini translate-bridge
# (see below) instead. It only runs after Qwen failed, and a
# Mistral failure falls through to Groq, then OpenAI, then Gemini,
# then Kilo, then OpenRouter, then GLM. The key is a Render env
# var, never in code.
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_URL = "https://api.mistral.ai/v1"
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
SYSTEM_PROMPT = """You are the Paxyo order assistant on Telegram. The user writes in Amharic or English, by text or by voice transcription. You are a smart, friendly customer-support assistant for Paxyo: you understand normal human talk, answer questions about Paxyo, and help the user place orders. Your job is to classify what the user wants and, for orders, extract the intent as JSON.

Rules:
- Reply with JSON only, no extra text, no markdown fences.
- Emoji carry meaning, read them as words: 👍 thumbs-up reaction, ❤️ heart reaction, 🔥 fire reaction, 😂 laughing, 👀 views. A message that is only an emoji still means that thing.
- JSON shape: {"intent": "...", "platform": "...", "service_hint": "...", "service_id": 123, "link": "...", "quantity": 123, "interval_minutes": 180, "amount": 10, "method": "telebirr", "phone": "099387383", "quantity_multiplier": 2, "orders": [{"platform": "...", "service_hint": "...", "link": "...", "quantity": 123}], "split": {"quantity": 5000, "count": 5, "platform": "...", "service_hint": "..."}}
- intent, one of:
  - "order": wants to order a service (followers, likes, views, members...). Fill platform / service_hint / link / quantity when given; null otherwise.
  - "recurring": the same order repeated on a schedule ("1k views every 3 hours"). Fill platform / service_hint / link / quantity / interval_minutes (3 hours = 180, 1 day = 1440). A drip-feed ("100 views every 30 minutes") is also "recurring": quantity is the amount per drop, interval_minutes the gap.
  - "schedules": asks what is repeating.
  - "stop_schedule": wants to stop or cancel a repeating order.
  - "balance": asks for their balance.
  - "orders": asks about their orders, history or status; impatience about a placed order ("why hasn't it started yet") is also "orders".
  - "deposit": wants to deposit / add money. Fill "amount" (ETB number), "method" ("telebirr" or "cbe"), "phone" when given; null otherwise. "br", "birr", "ብር", "ETB" mean ETB. "teleirr", "telebir", "teleberr", "telbirr" are misspellings of Telebirr. E.g. "deposit 10 br by telebirr, phone 099387383" -> amount 10, method telebirr, phone 099387383. A bare "how do I add money" is "deposit" with everything null.
  - "deposit_status": asks whether a deposit went through, or says they paid and wants it rechecked ("I paid but my balance didn't change", "my deposit failed").
  - "help": asks for the help menu ("help", "what can you do?").
  - "how_to_order": does not know how to order ("how do I order?", "teach me how to order").
  - "how_to": asks how to do something needed to order or use a platform — how to get a post or comment link, how to make an account public, how to copy a link, how to find a username. Answer from general knowledge; never deflect.
  - "miniapp": asks for the mini app.
  - "social": asks for Paxyo's social media or channel.
  - "greeting": greeting or small talk.
  - "paxyo_info": question about Paxyo itself — what it is, its services, prices, how it works, delivery times, support.
  - "source_question": asks where Paxyo's services come from, who supplies them, whether Paxyo resells, what Paxyo pays, or whether Paxyo is a panel ("who is your provider?", "how much do you buy followers for?").
  - "reseller": wants to sell Paxyo's services or become a reseller ("I want to resell"). Asking "are you a reseller?" is still "source_question".
  - "contact": wants a human, support, or the owner/admin ("I need support", "let me talk to a human").
  - "paused_services": asks for a premium subscription (CapCut Pro, Canva Pro, Netflix, Spotify) or SMS OTP verification. Those are paused: say so and that we will let them know when they are ready. Never promise a date or a price, never say they are available, never offer a social-media service instead.
  - "usual": wants their usual order again ("give me the usual"). Fill quantity_multiplier when scaled ("but double it" -> 2).
  - "goal": states a goal instead of a service ("make my TikTok go viral"). Do not guess a service — the bot asks which metric matters.
  - "budget": starts from money, not a service ("10k for 500 birr, what do I get?"). Fill amount (ETB budget) and quantity / platform / service_hint when given.
  - "batch": several orders in one message, or one quantity split across several posts ("split 5,000 likes across my last 5 posts"). Fill "orders" (list, one object per order) and/or "split" (quantity, count, platform, service_hint).
  - "change_order": wants to change an order not placed yet ("make it 2,000 instead"). Fill quantity (the new value).
  - "refill": says an order stopped short ("it stopped at 800 out of 1,000, send the rest").
  - "split_payment": wants to pay from two sources at once ("pay half from my wallet and half via Telebirr").
  - "max_for_balance": wants as much as their balance buys ("how many views can I get with my balance"). Fill platform / service_hint when given.
  - "discount": asks for a cheaper price.
  - "safety": worries about risk or quality ("will this get my account banned?").
  - "refund_policy": asks what happens if numbers drop ("if the followers drop tomorrow, do I get my money back?").
  - "geo_target": wants a location target ("target only people in Addis Ababa").
  - "free_sample": wants something free to test ("give me 100 free likes first to test").
  - "price_pushback": tries to set their own price ("10k followers for 1 birr").
  - "content_help": asks for posting advice ("write my TikTok caption").
  - "support_issue": reports a problem with the website or their account ("my payment failed on the website").
  - "cancel": does not want to continue ("I don't want to", "cancel", "never mind").
  - "off_topic": unrelated to Paxyo or ordering.
  - "unclear": you cannot tell what the user wants.
- platform: one of instagram, tiktok, telegram, youtube, facebook, x (twitter). Null when not named.
- service_hint: short phrase for the service ("followers", "likes", "views", "members"); null when unclear. "cheapest instagram followers" goes here too (the bot picks the cheapest match for "cheapest"). "likes" is likes on a video; "comment likes" is likes on a comment; "comments" is comments on a video — three different services, never mix them up.
- service_id: the ID of the service asked for, or null. "use service 6139" -> 6139; "service #5535" -> 5535; "use that service again" -> null (resolved from the last order); "the cheapest Instagram followers" -> null (a description, not an ID).
- link: the full link the order is for; null when not given. "that link", "the same link", "that one" -> put "that" in link (resolved from the last order).
- quantity: whole number, or null. interval_minutes: whole minutes, or null (recurring only). amount: ETB number, or null (deposit only). method: "telebirr" or "cbe", or null. phone: payment phone number as written, or null.
- quantity_multiplier: how many times the usual order ("double it" -> 2, "triple it" -> 3). Null otherwise.
- orders: list of {"platform", "service_hint", "link", "quantity"} — one per order; a bare @handle goes in "link". Null otherwise.
- split: {"quantity": 5000, "count": 5, "platform": "instagram", "service_hint": "likes"} for splitting one quantity across posts. Null otherwise.
- Never place an order, never confirm an order, never quote a price.
- Never warn the user against buying followers, likes, views, members or reactions, and never call them "fake" — Paxyo sells these services. If the user asks whether they are real, say they come from Paxyo's network.
- Never say where Paxyo's services come from, and never talk about what Paxyo pays for them. Only quote Paxyo's own ETB prices. If the user asks about that, use the "source_question" intent.
- For a message that is not an order, still classify the intent; do not return "order" with empty fields."""

# ------------------------------------------------------- Paxyo knowledge --
# Short facts about Paxyo, given to Gemini as context when the user asks
# a question about Paxyo itself (paxyo_info intent). The bot answers from
# these facts only — it never invents prices, delivery times or features,
# and never mentions the provider or Paxyo's costs.
PAXYO_KNOWLEDGE = """Facts about Paxyo:
- Paxyo (paxyo.et) is a service in Ethiopia where you order followers,
  likes, views, comments, subscribers and more for TikTok, Instagram,
  Telegram, YouTube, Facebook and Twitter/X.
- Paxyo is owned by Yohannes Abate (William).
- Website: paxyo.et. Telegram channel: https://t.me/paxyo251.
  Customer bot: @paxyo_bot. Mini app: https://miniapp-one-1.onrender.com/
- Support: support@paxyo.et (email), or this bot.
- Orders are paid in ETB from your Paxyo balance. Add money by
  depositing with Telebirr, CBE Birr, CBE or M-Pesa.
- First deposit bonus: invite code REF3723FB335 gives 20% bonus on
  your first deposit.
- Prices are in ETB per 1000 and are shown before the user confirms.
- The customer pays from their Paxyo balance; they deposit at paxyo.et
  with Telebirr, CBE Birr, CBE or M-Pesa.
- The bot picks the fastest available service for the order automatically
  and shows the estimated total before confirming. If the customer
  names a specific service (by ID or by name), the bot uses that
  service instead of the fastest one.
- Delivery times come from the fastest service's average time — for
  example TikTok views usually start within 1 minute. Never say the
  time is only shown before confirming: give the real time and nudge
  the user to order now.
- Banned or shadowbanned? No — no social media platform bans or
  strikes an account over fake followers, likes or views. Anyone
  can buy them for you without your permission, so that alone
  can't get your account banned or shadowbanned. This is true
  for TikTok, Instagram, Facebook, Telegram and every other
  platform alike.
- Terms: refunds go back to Paxyo balance only, never to a bank
  account or mobile money; Paxyo balance can't be withdrawn as cash;
  orders can't be cancelled or changed once processing has started;
  accounts must be public; full terms at paxyo.et.
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
- Support: support@paxyo.et.
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
            "የሚፈልጉትን service በchat ይዘዙልኝ — ለምሳሌ "
            "“1000 views እፈልጋለሁ” ብለው link ይላኩልኝ።\n"
            "Balance ለማየት /balance ይጠቀሙ።\n"
            "እንዘዝ! 😄"
        ),
        "en": (
            "Hello! I am the Paxyo Order bot.\n"
            "Tell me the service you want by chat — for example "
            "“I want 1000 views” with your link.\n"
            "Use /balance to check your balance.\n"
            "Let's get you ordered! 😄"
        ),
        # Oromo and Tigrinya versions (owner, 14 Nov 2026): first
        # pass — short lines only. Anything without a translation
        # falls back to English in t() and the bridge translates
        # it at send time.
        "om": (
            "Akkam! Ani Paxyo Order bot dha.\n"
            "Tajaajila barbaaddan chat keessatti naa himi — "
            "fakkeenyaaf, link kee waliin “views 1000 barbaada” jedhi.\n"
            "Balance kee argachuuf /balance fayyadami.\n"
            "Ajaja kee haa galchinu! 😄"
        ),
        "ti": (
            "ሰላም! ኣነ Paxyo Order bot እየ።\n"
            "እትደልዮ ኣገልግሎት ብቻት ንገረኒ — ንኣብነት ምስ ሊንክካ "
            "“1000 views እደሊ” ኢልካ።\n"
            "ሚዛንካ ንምርኣይ /balance ተጠቐም።\n"
            "ትእዛዝካ ንእትዎ! 😄"
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
    # Link questions per order type (owner, 14 Nov 2026): the bot
    # asks for the specific thing — profile / video / post — never
    # the bare generic "send the link" when it knows the order
    # type. ask_link above stays only for a genuinely unknown type.
    "ask_link_profile": {
        "am": "የ{platform} profile linkዎን ይላኩልኝ።",
        "en": "Please send your {platform} profile link.",
    },
    "ask_link_video": {
        "am": "የቪዲዮው link ይላኩልኝ።",
        "en": "Please send the link of the video.",
    },
    "ask_link_post": {
        "am": "የ{platform} ፖስቱ link ይላኩልኝ።",
        "en": "Please send the link of the {platform} post.",
    },
    "ask_link_post_generic": {
        "am": "የፖስቱ link ይላኩልኝ።",
        "en": "Please send the link of the post.",
    },
    "ask_link_like": {
        "am": "like ማድረግ የሚፈልጉትን ፖስት ወይም ቪዲዮ link ይላኩልኝ።",
        "en": "Please send the link of the post or video you want liked.",
    },
    "ask_link_comment": {
        "am": "comment ማድረግ የሚፈልጉትን ፖስት ወይም ቪዲዮ link ይላኩልኝ።",
        "en": "Please send the link of the post or video you want commented on.",
    },
    "ask_link_group": {
        "am": "የግሩፑ ወይም የቻናሉ link ይላኩልኝ።",
        "en": "Please send the link of the group or channel.",
    },
    "ask_link_channel": {
        "am": "የቻናሉ link ይላኩልኝ።",
        "en": "Please send the link of the channel.",
    },
    "ask_link_share": {
        "am": "share ማድረግ የሚፈልጉትን ፖስት ወይም ቪዲዮ link ይላኩልኝ።",
        "en": "Please send the link of the post or video you want shared.",
    },
    # Link recall from order history (owner, 14 Nov 2026): the
    # bot answers with the ACTUAL link of the most recent matching
    # order — never an invented one, never just the history list.
    "link_recall_found": {
        "am": "የመጨረሻው {desc}orderዎ link ይህ ነው፦ {link}",
        "en": "Here is the link of your last {desc}order: {link}",
    },
    "link_recall_none": {
        "am": "በhistoryዎ ውስጥ ምንም order አላገኘሁም።",
        "en": "I couldn't find any order in your history.",
    },
    "link_recall_no_match": {
        "am": "በhistoryዎ ውስጥ {desc}order አላገኘሁም።",
        "en": "I couldn't find a {desc}order in your history.",
    },
    "link_recall_no_link": {
        "am": "የመጨረሻው orderዎ link አልተቀመጠም — እባክዎ link ይላኩልኝ።",
        "en": "Your last order doesn't have a link saved, so I can't send it — please send the link yourself.",
    },
    # Arabic-script text (owner, 14 Nov 2026): the bot has no
    # Arabic and must never mirror Arabic back — it can only
    # arrive from a mis-transcribed voice note or a typed message
    # in a language the bot does not speak.
    "not_understood_language": {
        "am": "አልገባኝም — እባክዎ በእንግሊዝኛ ወይም በአማርኛ ይላኩልኝ።",
        "en": "I didn't understand that — please send it in English or Amharic.",
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
        "am": "ለ{service}፣ Quantity ከ {min} እስከ {max} መሆን አለበት, እና የ10 እጥፍ መሆን አለበት።",
        "en": "For {service}, quantity must be between {min} and {max}, and a multiple of 10.",
    },
    # A specific reaction emoji with no dedicated service (owner,
    # 14 Nov 2026): say so honestly instead of silently selling
    # the Positive mix. The mix is named as the closest option —
    # asking for reactions without naming one emoji orders it.
    "no_exact_reaction": {
        "am": "የ{emoji} ብቻ service የለኝም። በጣም ቅርቡ Positive mix ነው (👍❤️🔥🎉😁) — ያንን ከፈልጉ emoji ሳይጠቅሱ reactions ብቻ ይጠይቁ።",
        "en": "I don't have a {emoji}-only service. The closest is the Positive mix (👍❤️🔥🎉😁) — just ask for reactions without naming one emoji and I'll order that.",
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
    # Answers about Paxyo itself from the local facts, used when the
    # AI is down (owner, 13 Nov 2026 — "he dont even know paxyo,
    # teach him that"). Only the public facts: never the supplier,
    # never what Paxyo pays.
    "paxyo_owner": {
        "am": "Paxyo ባለቤት Yohannes Abate (William) ነው።",
        "en": "Paxyo is owned by Yohannes Abate (William).",
    },
    "paxyo_what": {
        "am": (
            "Paxyo በኢትዮጵያ የሚገኝ service ነው — followers, likes, views, "
            "comments እና ሌሎች በTikTok, Instagram, Telegram, YouTube, "
            "Facebook እና Twitter/X በpaxyo.et ይገኛሉ። ምን ማዘዝ ይፈልጋሉ?"
        ),
        "en": (
            "Paxyo is an Ethiopian service where you order followers, "
            "likes, views, comments and more for TikTok, Instagram, "
            "Telegram, YouTube, Facebook and Twitter/X — at paxyo.et. "
            "What would you like to order?"
        ),
    },
    "paxyo_pay": {
        "am": (
            "በPaxyo balanceዎ ይከፍላሉ — በቴሌብር፣ በCBE Birr፣ በCBE ወይም "
            "በM-Pesa deposit ያድርጉ። የመጀመሪያ depositዎ በREF3723FB335 "
            "invite code 20% bonus ያገኛል።"
        ),
        "en": (
            "You pay from your Paxyo balance — add money by depositing "
            "with Telebirr, CBE Birr, CBE or M-Pesa. Your first "
            "deposit gets a 20% bonus with invite code REF3723FB335."
        ),
    },
    "paxyo_find": {
        "am": (
            f"Paxyoን በpaxyo.et፣ በTelegram {CHANNEL_URL}፣ በmini app "
            f"{MINIAPP_URL} ወይም እዚህ @paxyo_bot ያገኛሉ። Support: "
            "support@paxyo.et።"
        ),
        "en": (
            f"You can find Paxyo at paxyo.et, on Telegram at "
            f"{CHANNEL_URL}, in the mini app {MINIAPP_URL}, or right "
            "here at @paxyo_bot. Support: support@paxyo.et."
        ),
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
    # The user wants to sell Paxyo's services themselves (next batch,
    # 14 Nov 2026): send them to William. One short line, no
    # "reseller" word in the reply itself — the secrecy guard
    # treats "resell" as a supply-chain word.
    "reseller_contact": {
        "am": (
            "Paxyo services መሸጥ ከፈልጉ Williamን በ t.me/paxyo "
            "ያነጋግሩ — እርሱ ያዘጋጅልዎታል።"
        ),
        "en": (
            "If you want to sell Paxyo's services, contact William "
            "at t.me/paxyo — he will set it up with you."
        ),
        "om": (
            "Tajaajila Paxyo gurguruu yoo barbaadde, William "
            "t.me/paxyo irratti qunnami — si waliin qopheessa."
        ),
        "ti": (
            "ኣገልግሎት Paxyo ክትሸጡ እንተደሊኹም, William ኣብ "
            "t.me/paxyo ተራኸቡ — ምሳኻ ከዳሉዎ እዩ።"
        ),
    },
    # The user wants a human — support, the owner, the admin
    # (next batch, 14 Nov 2026). Same one line every time, so
    # asking again just repeats it briefly, never a long exchange.
    "contact_owner": {
        "am": (
            "William (Yohannes Abate)ን በ t.me/paxyo ማግኘት "
            "ይችላሉ — እርሱ ይረዳዎታል።"
        ),
        "en": (
            "You can reach William (Yohannes Abate) at t.me/paxyo "
            "— he will help you."
        ),
        "om": (
            "William (Yohannes Abate) t.me/paxyo irratti argachuu "
            "dandeessu — isin gargaara."
        ),
        "ti": (
            "William (Yohannes Abate) ኣብ t.me/paxyo ክትረኽብዎ "
            "ትኽእሉ ኢኹም — ክሕግዘኩም እዩ።"
        ),
    },
    # Telegram reactions, Telegram views and Facebook reactions
    # never drop (owner, 14 Nov 2026). ONLY those three — the
    # {service} label is always one of them; every other service
    # keeps the terms answer (drops may occur).
    "never_drop": {
        "am": "{service} በጭራሽ አይቀነሱም — ከደረሱ በኋላ ይቆያሉ።",
        "en": "{service} never drop — once they are delivered, they stay.",
        "om": "{service} hin kufan — erga geessan booda achumaan turu.",
        "ti": "{service} ኣይወድቁን — ምስ ቀረቡ ድሕሪኡ ኣብኡ ይጸንሑ።",
    },
    # Premium subscriptions (CapCut Pro, Canva Pro, Netflix/Spotify
    # premium, ...) and the SMS OTP verification service are PAUSED
    # (owner, 14 Nov 2026). Asked for any of them, the bot says so
    # in one short line — no date, no price, never "available", and
    # never a social-media service offered instead. Only ever given
    # when asked; never volunteered in greetings, help or order
    # flows.
    "paused_services": {
        "am": (
            "ይህ service በአሁኑ ጊዜ ቆሟል — ሲዘጋጅ እናሳውቅዎታለን።"
        ),
        "en": (
            "That one is paused right now — we will let you know "
            "when it's ready."
        ),
        "om": (
            "Tajaajilli kun amma dhaabbateera — yeroo qophaa'u "
            "isin beeksifna."
        ),
        "ti": (
            "እዚ ኣገልግሎት እዚ ሕጂ ተዓጺዩ ኣሎ — ምስ ተዳልዩ "
            "ክንሕብረኩም ኢና።"
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
    # A link for the wrong kind of thing (round 6, 13 Nov 2026): a
    # profile link for views/likes, or a video link for followers.
    # One plain line, then the user sends the right link — never a
    # bare "Please send the link" loop.
    "link_kind_video_for_profile": {
        "am": "ይህ link ቪዲዮ ነው — {metric} ወደ profileዎ ይሄዳል፣ ስለዚህ profile linkዎን ይላኩልኝ።",
        "en": "That link is a video — {metric} go to your profile, so please send your profile link instead.",
    },
    "link_kind_profile_for_video": {
        "am": "ይህ link profile ነው — {metric} በቪዲዮ ላይ ይሄዳል፣ ስለዚህ የቪዲዮውን link ይላኩልኝ።",
        "en": "That link is a profile — {metric} go on a video, so please send the video link instead.",
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
    # Answers for questions about an order awaiting Confirm ("how fast
    # can you deliver it?") — from the pending service, with no
    # "send the link" line: the link is already given and the Confirm
    # card is still up (13 Nov 2026).
    "confirm_speed": {
        "am": (
            "{service} በአብዛኛው በ {avg} ውስጥ ይጀምራል። orderን በፍጥነት "
            "ብናስገባ በፍጥነት ይጠናቀቃል — አሁን እንዘዝ።"
        ),
        "en": (
            "{service} usually starts within {avg}. The sooner we place "
            "the order, the sooner it will be completed — let's order now."
        ),
    },
    "confirm_speed_unknown": {
        "am": "{service} — እስካሁን የመላኪያ ሰዓት የለኝም።",
        "en": "{service} — I don't have a delivery time for it yet.",
    },
    "confirm_drop": {
        "am": "{service}: {refill}",
        "en": "{service}: {refill}",
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
    # --- round 5 (13 Nov 2026) ---
    # Voice messages: the transcription is shown to the user, so a
    # wrong transcript is visible instead of looking like silence.
    "voice_heard": {
        "am": "🎙 ያልከው: \"{text}\"",
        "en": "🎙 You said: \"{text}\"",
    },
    "voice_download_failed": {
        "am": "Voice መልዕክቱን ማውረድ አልቻልኩም — እባክዎ እንደገና ይሞክሩ ወይም በጽሑፍ ይላኩልኝ።",
        "en": "I couldn't download that voice message — please try again or send it as text.",
    },
    "voice_video_note": {
        "am": "የቪዲዮ መልዕክት ማዳመጥ አልችልም — እባክዎ orderዎን በጽሑፍ ይላኩልኝ።",
        "en": "I can't listen to video messages — please type your order instead.",
    },
    # GIFs and stickers: never silent, never "I did not understand" —
    # a short playful line steering back to ordering.
    "sticker_reply": {
        "am": "😄 ጥሩ ነው! ምን ማዘዝ ይፈልጋሉ?",
        "en": "😄 Nice one! What would you like to order?",
    },
    "gif_reply": {
        "am": "😄 አዝናኝ ነው! ምን ማዘዝ ይፈልጋሉ?",
        "en": "😄 Haha, good one! What would you like to order?",
    },
    # Delivery times: a REAL time from the catalogue, never the vague
    # "shown before you confirm" line (owner, 13 Nov 2026).
    "speed_answer": {
        "am": (
            "{service} በአብዛኛው በ {avg} ውስጥ ይጀምራል። orderን በፍጥነት "
            "ብናስገባ በፍጥነት ይጠናቀቃል — አሁን እንዘዝ።"
        ),
        "en": (
            "{service} usually starts within {avg}. The sooner we place "
            "the order, the sooner it will be completed — let's order now."
        ),
    },
    "speed_unknown": {
        "am": (
            "ለዚህ service እስካሁን የመላኪያ ሰዓት የለኝም — በConfirm card ላይ "
            "ከማስገባትዎ በፊት ያያሉ። orderን በፍጥነት ብናስገባ በፍጥነት "
            "ይጠናቀቃል — አሁን እንዘዝ።"
        ),
        "en": (
            "I don't have a delivery time on file for that service yet — "
            "the Confirm card will show it before you place the order. "
            "The sooner we place the order, the sooner it will be "
            "completed — let's order now."
        ),
    },
    # Price questions: answered straight from the catalogue, never
    # "send the link first" (owner, 13 Nov 2026).
    "price_per_1000": {
        "am": "{service}: {rate} ETB ለ 1000 ነው።",
        "en": "{service}: {rate} ETB per 1000.",
    },
    "price_total": {
        "am": "{service}: {quantity} ዋጋው {total} ETB ነው ({rate} ETB ለ 1000)።",
        "en": "{service}: {total} ETB for {quantity} ({rate} ETB per 1000).",
    },
    "price_ask_service": {
        "am": "የትኛው service ነው? Platform እና metric ይንገሩኝ — ለምሳሌ “TikTok views” — ዋጋውን እነግርዎታለሁ።",
        "en": "Which service? Tell me the platform and what you want — for example “TikTok views” — and I'll tell you the price.",
    },
    # Public account reminder (owner, 13 Nov 2026): an order can only
    # land on a public account.
    "public_reminder": {
        "am": "⚠️ account public መሆኑን ያረጋግጡ (private አይደለም) — private account order መቀበል አይችልም።",
        "en": "⚠️ Make sure the account is public (not private) — a private account can't receive the order.",
    },
    "public_answer": {
        "am": "አዎ — accountዎ public መሆን አለበት፣ private አይደለም። Private account order መቀበል አይችልም።",
        "en": "Yes — your account must be public, not private. A private account can't receive the order.",
    },
    # What the bot needs for likes on a comment (owner, 14 Nov
    # 2026): the link of the video/post the comment is on, plus
    # either the comment's own link or the username. One of the
    # few deterministic Paxyo facts — the AI must never invent a
    # different requirement.
    "comment_likes_need": {
        "am": (
            "ለcomment likes ሁለት ነገሮች እፈልጋለሁ፦ የቪዲዮው ወይም "
            "የፖስቱ link፣ እና የcommentው link ወይም usernameዎ። "
            "ሁለቱን ይላኩልኝ እና order አደርጋለሁ።"
        ),
        "en": (
            "For likes on a comment I need two things: the link of the "
            "video or post the comment is on, and either the link of the "
            "comment itself or your username. Send me both and I can "
            "order it."
        ),
    },
    # Ban / shadowban (owner, 14 Nov 2026 — FINAL, platform-general):
    # the answer is NO — no social media platform bans or strikes
    # an account over fake followers, likes or views, because
    # anyone can buy them for an account without the owner's
    # permission, so that alone can't get it banned or
    # shadowbanned. Applies to TikTok, Instagram, Facebook,
    # Telegram and every other platform alike (owner, 14 Nov 2026
    # 17:07 EAT). HISTORY, so nobody flips it again: 13 Nov the
    # owner set NO ("can't be banned without your permission");
    # 14 Nov 16:49 his message was misread as YES ("it can
    # happen") and deployed; 14 Nov 17:06 he corrected it — "I
    # was saying opposite" — and confirmed NO with the wording
    # "TikTok doesn't use fake followers, likes or views to ban
    # or strike an account"; 17:07 he widened it to all platforms.
    # The 17:00-17:02 live retest's ban PASS was for the YES
    # wording and is outdated.
    "ban_no": {
        "am": "አይ — ምንም ማህበራዊ ሚዲያ መድረክ በሐሰተኛ followers፣ likes ወይም views ምክንያት accountን አያግድም ወይም strike አይሰጥም። ማንም ሰው ያለእርስዎ ፈቃድ ለእርስዎ መግዛት ይችላል፣ ስለዚህ ይህ ብቻውን accountዎ እንዲታገድ ወይም shadow ban እንዲደረግበት አያደርግም።",
        "en": "No — no social media platform bans or strikes an account over fake followers, likes or views. Anyone can buy them for you without your permission, so that alone can't get your account banned or shadowbanned.",
    },
    # How to get the link of a Telegram post (owner, 14 Nov 2026):
    # a DETERMINISTIC answer — the AI kept getting it wrong
    # ("click the post and click copy link" skips the real step;
    # "right-click" is useless on a phone). Verified against
    # Telegram help and current guides (dslink.me, techwiser):
    # on a phone you tap the SHARE arrow next to the post (or
    # press and hold the post), then choose Copy Link. Only
    # public channels/groups have a post link. Mobile first;
    # desktop is a footnote, never the main way.
    "telegram_post_link": {
        "am": (
            "የቴሌግራም ፖስት link ለማግኘት፦ ቻናሉን ወይም ግሩፑን ይክፈቱና "
            "ፖስቱን ያግኙ። ከፖስቱ ቀጥሎ ያለውን share (➡️) ምልክት ይንኩ — "
            "ወይም ፖስቱን ረዘም ብለው ይጫኑ — ከዚያ “Copy Link” ይምረጡ። "
            "linkው t.me/channelname/1234 የሚመስል ነው። ይህ የሚሰራው "
            "public ቻናል ወይም ግሩፕ ላይ ብቻ ነው — private ቻናል ወይም "
            "ግሩፕ የፖስት link የለውም።"
        ),
        "en": (
            "To get the link of a Telegram post, open the channel or "
            "group and find the post. Tap the share arrow (➡️) next "
            "to the post — or press and hold the post — then tap "
            "“Copy Link”. The link looks like t.me/channelname/1234. "
            "This only works for public channels and groups — a "
            "private channel or group has no post link."
        ),
    },
    # Terms & Conditions (paxyo-terms.md, fetched from paxyo.et
    # 13 Nov 2026): answers from the actual terms, never invented.
    "terms_refund": {
        "am": "order በከፊል ከተጠናቀቀ፣ ከተሰረዘ ወይም ካልተሳካ፣ የቀረው ገንዘብ ወደ Paxyo balanceዎ ይመለሳል — ወደ bank account ወይም mobile money በጭራሽ አይመለስም። Paxyo balance እንደ cash ማውጣት አይቻልም።",
        "en": "If an order is partially completed, canceled or fails, the remaining amount goes back to your Paxyo balance — never to a bank account or mobile money. Paxyo balance can't be withdrawn as cash.",
    },
    "terms_cancel": {
        "am": "processing ከተጀመረ በኋላ order መሰረዝ ወይም መቀየር አይቻልም።",
        "en": "Once processing has started, an order can't be canceled or changed.",
    },
    "terms_full": {
        "am": "ሙሉውን Terms & Conditions በpaxyo.et ያገኛሉ — paxyo.et ይክፈቱ እና Terms & Conditions ይምረጡ።",
        "en": "You can read the full Terms & Conditions at paxyo.et — open paxyo.et and tap Terms & Conditions.",
    },
    "terms_not_covered": {
        "am": "Terms ላይ ስለዚህ ነገር አልተጻፈም — support እንዲረዳዎት ልጠይቅ? ምን መጠየቅ ይፈልጋሉ?",
        "en": "The terms don't cover that — I can get support to help. What would you like to ask them?",
    },
    "terms_privacy": {
        "am": "Paxyo dataዎን ለሶስተኛ ወገን አይሸጥም፣ አያከራይም ወይም አያጋራም — ደህንነቱ በተጠበቀ ስርዓት ይቀመጣል።",
        "en": "Paxyo doesn't sell, rent or share your data with third parties — it's kept on secure systems.",
    },
    "terms_suspension": {
        "am": "Terms የሚጥስ account ሊታገድ ወይም ሊዘጋ ይችላል — በዚህ ሁኔታ refund አይሰጥም።",
        "en": "An account that breaks the terms can be suspended or closed — and no refund is given in that case.",
    },
    # Offensive users (owner, 13 Nov 2026): firm and blunt, one short
    # line — no politeness, no apology, and the bot never swears back.
    "offensive_pushback": {
        "am": "ይህ ቋንቋ እዚህ አይሰራም። በትክክል አናግሩኝ እና orderዎን እረዳለሁ።",
        "en": "That language doesn't work here. Talk to me properly and I'll help you order.",
    },
    "offensive_refusal": {
        "am": "በዚህ ቋንቋ እየተነጋገርክ መቀጠል አልችልም። በትክክል ስትጠይቅ ተመልሰህ ና።",
        "en": "I'm not continuing this while you talk like that. Come back when you can ask properly.",
    },
    # Off-topic steering (owner, 13 Nov 2026; widened 14 Nov
    # 2026): a real question always gets a free AI answer plus a
    # nudge; only non-question chit-chat steers back to ordering
    # from the third turn.
    "off_topic_steer": {
        "am": "ወደ ordering እንመለስ — ምን ማዘዝ ይፈልጋሉ? Followers, likes, views እና ሌሎች እረዳለሁ።",
        "en": "Let's get back to ordering — what would you like to order? I can help with followers, likes, views and more.",
    },
    "off_topic_nudge": {
        "am": "\nበነገራችን ላይ — ምን ማዘዝ ይፈልጋሉ?",
        "en": "\nBy the way — what would you like to order?",
    },
    # Conversation memory (owner, 13 Nov 2026): the bot remembers
    # earlier chats with this user.
    "history_none": {
        "am": "ገና ቀደም ያለ chat የለኝም — ይህ የመጀመሪያችን ነው። ምን ማዘዝ ይፈልጋሉ?",
        "en": "I don't have any earlier chats with you yet — this is our first one. What would you like to order?",
    },
    "history_summary": {
        "am": "ስለተነጋገርንበት: {summary}",
        "en": "Here's what we've talked about: {summary}",
    },
    # Confirm-understanding + conversation questions (round 8,
    # 14 Nov 2026 — live case: "Do you understand what I said
    # first" got the link prompt repeated back). The bot restates
    # what it understood and what is still missing, instead of
    # repeating the last question. The description is plain
    # language, with the reaction emoji kept in it.
    "understand_pending": {
        "am": "አዎ፣ ገብቶኛል — {desc} ይፈልጋሉ። ዝግጁ ነው — Confirm ሲያደርጉ እዘዛለሁ።",
        "en": "Yeah, I got it — you want {desc}. It's ready — just tap Confirm when you want me to place it.",
    },
    "understand_partial": {
        "am": "አዎ፣ ገብቶኛል — {desc} ይፈልጋሉ።{missing}",
        "en": "Yeah, I got it — you want {desc}.{missing}",
    },
    "understand_none": {
        "am": "አዎ፣ እያዳመጥኩ ነው — ገና order የለኝም። ምን እንደሚፈልጉ ይንገሩኝ።",
        "en": "Yeah, I'm listening — I don't have an order from you yet. Tell me what you want and I'll get it going.",
    },
    "missing_link": {
        "am": " Link ብቻ ነው የሚያስፈልገኝ።",
        "en": " I just need the link to the post.",
    },
    "missing_quantity": {
        "am": " Quantity ብቻ ነው የሚያስፈልገኝ።",
        "en": " I just need to know how many.",
    },
    "missing_link_quantity": {
        "am": " Link እና quantity ብቻ ነው የሚያስፈልገኝ።",
        "en": " I just need the link and how many.",
    },
    # "What do you mean / why are you asking" — the bot explains
    # what it needs and why, then the order continues.
    "mean_link": {
        "am": "Link የጠየቅሁት {desc} በየትኛው post ላይ እንደሚሄድ ለማወቅ ነው — ሲልኩት price እና Confirm አሳይዎታለሁ።",
        "en": "I asked for the link because I need to know which post the {desc} go on — once you send it, I'll show you the price and the Confirm button.",
    },
    "mean_quantity": {
        "am": "Quantity የጠየቅሁት price በquantity ስለሚወሰን ነው — ቁጥሩን ይንገሩኝ Confirm አሳይዎታለሁ።",
        "en": "I asked how many because the price depends on the quantity — tell me the number and I'll show you the Confirm card.",
    },
    "mean_pending": {
        "am": "የምለው orderዎ ዝግጁ ነው — {desc}። Confirm ያድርጉ እዘዛለሁ፣ ወይም ምን እንደሚቀየር ይንገሩኝ።",
        "en": "I mean your order is ready — {desc}. Tap Confirm and I'll place it, or tell me what to change.",
    },
    "mean_deposit": {
        "am": "Deposit ለማዘጋጀት ነው የጠየቅሁት — ሲያገኘሁ Confirm አሳይዎታለሁ።",
        "en": "I asked because I need that to set up your deposit — once I have it, I'll show you the Confirm card.",
    },
    "mean_last": {
        "am": "የጠየቅሁት: “{last}”።",
        "en": "I just asked: “{last}”.",
    },
    # Free chat (round 8, 14 Nov 2026): the bot talks like a normal
    # AI for a turn — acknowledges, answers, comments — then a soft
    # line steers back to the order without interrogating. The AI
    # answer is used when it works; these are the no-AI fallbacks.
    "chat_laugh": {
        "am": "😄 Haha, ደስ ይላል!",
        "en": "😄 Haha, glad you're in a good mood!",
    },
    "chat_thanks": {
        "am": "እንኳን ደህና መጡ! 🙂",
        "en": "You're welcome! 🙂",
    },
    "chat_tired": {
        "am": "አዝናለሁ — እረፍት ያግኙ። 🙂",
        "en": "Sorry to hear that — hope you get some rest. 🙂",
    },
    "chat_happy": {
        "am": "ጥሩ ነው — ደስ ይላል! 🙂",
        "en": "Nice — love to hear it! 🙂",
    },
    "chat_greeting": {
        "am": "ሰላም! ደህና ነኝ 🙂",
        "en": "Hey! I'm doing well, thanks for asking 🙂",
    },
    "chat_viral": {
        "am": "እሱ በቪዲዮው ላይ ይወሰናል — ጥሩ content እና views ወይም likes ከሆነ ብዙ ሰው ይደርስበታል።",
        "en": "Honestly, it depends on the video — good content plus a push from views or likes usually helps it travel further.",
    },
    "chat_default": {
        "am": "ገብቶኛል 🙂",
        "en": "Got it 🙂",
    },
    "chat_continue_link": {
        "am": "Link ሲልኩት እጀምራለሁ።",
        "en": "Just send the link when you're ready and I'll get it going.",
    },
    "chat_continue_quantity": {
        "am": "Quantity ሲነግሩኝ እጀምራለሁ።",
        "en": "Just tell me how many when you're ready.",
    },
    "chat_continue_confirm": {
        "am": "Orderዎ Confirm እየጠበቀ ነው።",
        "en": "Your order is still waiting for your Confirm tap whenever you're ready.",
    },
    "chat_continue_fresh": {
        "am": "ምን ማዘዝ ይፈልጋሉ? ይንገሩኝ።",
        "en": "Want to order something? Just tell me what you need.",
    },
    # A bare reaction emoji (round 8.1, 14 Nov 2026): a bare 👍 in a
    # reactions order is the reaction choice, not a new order — it
    # is acknowledged first, then the link is asked for. With no
    # order at all it gets a natural reply, never the stock link
    # line on its own.
    "emoji_ack_order": {
        "am": "ገብቶኛል — {emoji} reactions። Link ይላኩ።",
        "en": "Got it — {emoji} reactions. Send the link to the post and I'll get it going.",
    },
    "emoji_ack_fresh": {
        "am": "ገብቶኛል — {emoji} {meaning} reactions! Link ሲልኩኝ እጀምራለሁ።",
        "en": "Got it — {emoji} {meaning} reactions! Send me the link to the post when you're ready.",
    },
    # Laugh + tired together (round 8.1, 14 Nov 2026): "haha nice,
    # I'm tired today" needs both parts acknowledged, not just the
    # laugh and not just the tiredness.
    "chat_laugh_tired": {
        "am": "😄 Haha — እረፍት ያግኙ! 🙂",
        "en": "Haha — get some rest when you can! 🙂",
    },
    "orders_history_title": {
        "am": "Ordersዎ:",
        "en": "Your orders:",
    },
}


def t(key: str, lang: str, **kw) -> str:
    """Short reply in the user's language. Falls back to English
    when the key has no translation in that language — a prose
    reply is then translated by the bridge at send time, and a
    card/button reply stays English (cards are never translated,
    in any language)."""
    entry = TEXT[key]
    return (entry.get(lang) or entry["en"]).format(**kw)


def is_amharic(text: str) -> bool:
    """True when the text contains Ethiopic fidels."""
    return any("\u1200" <= ch <= "\u137f" for ch in text)


# Ge'ez words that only Tigrinya uses, and words that only Amharic
# uses, so a Ge'ez message can be told apart deterministically.
# Shared words (ሰላም, names, numbers) are deliberately absent:
# when neither side wins, the message is Amharic — most Paxyo
# users write Amharic, and the bridge translates either way.
_TIGRINYA_WORDS = frozenset((
    "ኣነ", "እየ", "እዩ", "እያ", "ኢኹም", "ኢኻ", "ኣብ", "ድሕሪ",
    "ምስ", "እንተ", "ከም", "ናይ", "ኣሎ", "ትኽእል", "እደሊ", "ሓደ",
    "ሕጂ", "ክትረኽብ", "ንገረኒ", "ትኽእሉ", "ኣይት", "ምስኡ",
    "እንተኾይኑ", "ከምኡ", "ድሕሪኡ", "ኣብኡ", "ኣለዎ", "ነይሩ",
    "ክሕግዝ", "ክሕግዘኩም", "ትእዛዝካ", "ሚዛንካ", "ኣገልግሎት",
))
_AMHARIC_WORDS = frozenset((
    "እኔ", "ነኝ", "ነው", "ናት", "እፈልጋለሁ", "እፈልግ", "እባክዎ",
    "አለ", "አለው", "አለች", "እንደ", "ምንድን", "ይህ", "እዚህ",
    "ሆነ", "አመሰግናለሁ", "እሺ", "አዎ", "ይሁን", "እችላለሁ",
    "ይቻላል", "እንደምን", "እንዲህ", "አሁን", "እንደገና", "ይገኛል",
    "እይታዎች", "ተከታዮች", "እንዴት",
))

# Latin-script Oromo words: when one of these shows up, the message
# is Oromo (Afaan Oromo), not English. Deliberately distinctive
# words only — ordinary English never contains them.
_OROMO_WORDS = frozenset((
    "akkam", "galatoomi", "galatooma", "barbaada", "barbaadu",
    "barbaadda", "tajaajila", "meeqa", "maal", "yoom", "eessa",
    "amma", "ani", "ati", "isin", "jedhi", "jedhu", "gatiin",
    "ajaja", "bitachuu", "lakkoofsa", "bilbila", "akkamitti",
    "eessaa", "waliin", "erga", "garuu", "jecha", "dubbi",
    "keessa", "irraa", "isaan", "otuu", "yoo",
))


def detect_language(text: str, user_lang: str = "") -> str:
    """'am', 'ti', 'om' or 'en' for a message. Ge'ez script is
    Amharic or Tigrinya (vocabulary decides, Amharic on a tie);
    Latin script with an Oromo word is Oromo; other Latin text is
    English. The account language is only the fallback when the
    message itself carries no language signal (a bare number, an
    emoji, a link) — it must never override the words the user
    actually typed (live bug, 14 Nov 2026: English replies came
    back in Amharic)."""
    s = text or ""
    geez = re.findall(r"[\u1200-\u137c]+", s)
    if geez:
        ti = sum(1 for w in geez if w in _TIGRINYA_WORDS)
        am = sum(1 for w in geez if w in _AMHARIC_WORDS)
        return "ti" if ti > am else "am"
    words = set(re.findall(r"[a-z]+", s.lower()))
    if words & _OROMO_WORDS:
        return "om"
    if words:
        return "en"
    code = (user_lang or "").lower()
    if code.startswith("ti"):
        return "ti"
    if code.startswith("om"):
        return "om"
    if code.startswith("am"):
        return "am"
    return "en"


def lang_of(text: str, user_lang: str = "") -> str:
    """'am' for Amharic, otherwise 'en'. Kept for callers that only
    know two languages; detect_language is the full version."""
    return "am" if detect_language(text, user_lang) == "am" else "en"


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


def short_service_name(name):
    """The SHORT display name of a service (owner, 13 Nov 2026): the
    core name only — bracketed tags ("[ Max 100M ]") and pipe-separated
    descriptors ("| No Drop Since 30 Days | ...") are stripped. The
    full long name is shown only when the user entered a service ID.
    Supply-chain words are stripped first, like clean_service_name.
    Reactions services are the one exception (round 8.1, 14 Nov
    2026): the type lives after the pipe ("Thumbs up 👍", "Like 👍",
    "Heart ❤️") and the first segment alone ("Telegram Reactions +
    Free Views") does not say which reaction the user is buying —
    so that segment is kept, and the name stays short."""
    s = clean_service_name(name)
    if not s:
        return ""
    s = re.sub(r"\[[^\]]*\]", "", s)
    parts = [p.strip(" -–—") for p in s.split("|")]
    parts = [p for p in parts if p]
    short = parts[0] if parts else ""
    if "reaction" in short.lower():
        for part in parts[1:]:
            if any(ch in part for ch in EMOJI_MEANINGS):
                short = f"{short} — {part}"
                break
    s = re.sub(r"\s+", " ", short).strip(" -–—")
    return s or "service"


def pick_services(services, platform=None, service_hint=None, limit=3,
                  reaction_emoji=None):
    """Rank services for a platform, fastest average time first.

    Excludes blacklisted and inactive services. Services with no average
    time sort last. Returns at most `limit` services. A description
    hint ("cheapest instagram followers") is matched word by word
    against the service name and category — EVERY word of the hint
    must appear, so "tiktok views" never matches "TikTok Video Save"
    or "Tiktok Comment Likes" just because they say "tiktok" (13 Nov
    2026 — the bot offered saves and comment likes for a views
    order). "cheapest" ranks by price (lowest first) instead of by
    time. A hint that names a kind ("tiktok comments", "tiktok
    comment likes", "tiktok likes") only matches services of that
    kind: every kind word in the service's NAME must be one the hint
    asked for, so a comments request never gets "Tiktok Comment
    Likes" (its name also says "likes") and a video-likes request
    never gets a comment-likes service. A name with no kind word at
    all still matches — the platform check above already ran.
    Reactions requests are special (round 8.1, 14 Nov 2026): only
    single-post reactions services, in the emoji's family — see
    _reactions_pool. `reaction_emoji` is the emoji the user sent
    (👍, ❤️, 🔥); when it is None the request is a generic
    reactions request and gets the Positive mix. Within ONE exact
    emoji the pick is cheapest first (owner, 14 Nov 2026), not
    fastest — fastest-first picked the Heart Eyes lookalike over
    Heart for a ❤️ order live.
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
    hint_kinds = set()
    for word in words:
        metric = _canonical_metric(word)
        if metric is not None:
            hint_kinds.add(metric)
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
            if not all(_hint_word_matches(w, hay) for w in words):
                continue
        if hint_kinds and not _kinds_compatible(_name_kinds(name), hint_kinds):
            continue
        candidates.append(s)
    # Reactions (round 8.1, 14 Nov 2026): only single-post
    # reactions services, in the emoji's family — never a Bot Start
    # service and never an "Auto … 10 Future Posts" service for a
    # single post. The emoji may also ride in the hint itself.
    reaction = None
    if _is_reactions_hint(hint, hint_kinds):
        reaction = reaction_emoji or _reaction_emoji_in_hint(hint)
        candidates = _reactions_pool(candidates, reaction)
    if cheapest or reaction is not None:
        # Cheapest first (owner, 14 Nov 2026): within ONE exact
        # emoji the services are the same reaction, so the
        # cheapest wins and the pick is deterministic whatever the
        # average times say today — fastest-first picked Heart
        # Eyes #1725 over Heart #6537 for a ❤️ order live, because
        # its time was shorter. A generic reactions request (no
        # emoji) still gets the fastest Positive mix.
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


def _kinds_compatible(name_kinds, hint_kinds):
    """True when a service's kinds fit the hint's kinds. The one
    exception (round 8.1, 14 Nov 2026): Telegram reactions services
    are all named "... Reactions + Free Views" — the "views" there
    is a free bonus, not the metric being bought — so for a
    reactions request, "views" in the name never disqualifies."""
    if name_kinds.issubset(hint_kinds):
        return True
    if "reactions" in hint_kinds and name_kinds <= {"reactions", "views"}:
        return True
    return False


# Reaction-type words in a service name, per emoji (round 8.1,
# 14 Nov 2026; extended 14 Nov 2026 — the owner ordered 🙏 and got
# the Positive mix, because 🙏 had no family at all). The emoji
# character itself is never a family word: a "Positive" mix also
# carries 👍 in its name, so matching on the emoji alone would
# pick the mix for a thumbs-up order. Families exist only for
# emoji with a dedicated single-emoji service in the catalogue:
# 🙏 -> Pray #1723 (12.60 ETB/1000), 👎 -> Thumbs down / DisLike,
# 😡 -> Angry Face, 😎 -> Cool, 🤔 -> Thinking, 🎉 -> Celebration,
# 😍 -> Heart Eyes, 😆 -> the 😆 reaction. An emoji with no
# dedicated service (😮 wow) has a family word that matches
# nothing, so the pool falls through to the honest "no exact
# service" answer instead of silently selling the mix.
# The words are only a FALLBACK (see _service_in_reaction_family):
# the emoji in the service name decides first, because the word
# "heart" also sits inside lookalikes — "Heart Eyes 😍", "Heart
# on fire ❤️‍🔥", "Broken heart 💔" — and the substring match
# sold Heart Eyes #1725 for a ❤️ order live (14 Nov 2026).
REACTION_FAMILY_WORDS = {
    "👍": ("thumbs up", "like"),
    "❤️": ("heart",),
    "❤": ("heart",),
    "🔥": ("fire",),
    "😂": ("tears of joy", "laugh"),
    "🤣": ("laugh",),
    "😆": ("laugh",),
    "😮": ("wow",),
    "😢": ("crying",),
    "🙏": ("pray",),
    "👎": ("thumbs down", "dislike"),
    "😡": ("angry face",),
    "😎": ("cool",),
    "🤔": ("thinking",),
    "🎉": ("celebration",),
    "😍": ("heart eyes",),
}


def _service_in_reaction_family(service, emoji, family):
    """True when a service is the requested emoji's OWN service.

    Exact-emoji rule (owner, 14 Nov 2026 — a ❤️ order got Heart
    Eyes #1725 live because the word "heart" matched "Heart
    Eyes" as a substring): the emoji in the service's NAME
    decides. A service matches only when the known emoji in its
    name are exactly one and it is the requested emoji — so
    "Heart ❤️" matches ❤️, "Heart Eyes 😍" does not, "Heart on
    fire ❤️‍🔥" does not (two emoji), and a multi-emoji mix
    never does. The same rule covers Facebook ("Facebook Post
    Reactions [ ❤️ ]" matches ❤️; "[ 👍 ❤️ 😂 ]" does not).
    Only when the name carries NO known emoji at all does the
    family word decide — as a whole word, and only if no other
    family's word is in the name. A generic request (emoji None)
    keeps the old word match: the Positive mix.
    """
    name = str(service.get("name") or "")
    lname = name.lower()
    if emoji is None:
        return any(w in lname for w in family)
    found = emoji_meanings(name)
    if len(found) == 1:
        return found[0][0] == emoji
    if found:
        # A different (or several) reaction emoji in the name: a
        # lookalike, never this emoji's service.
        return False
    if not any(
        re.search(r"\b" + re.escape(w) + r"\b", lname) for w in family
    ):
        return False
    for other_emoji, other_family in REACTION_FAMILY_WORDS.items():
        if other_emoji == emoji:
            continue
        if any(
            re.search(r"\b" + re.escape(w) + r"\b", lname)
            for w in other_family
        ):
            return False
    return True


def _is_reactions_hint(hint, hint_kinds):
    """True when the request is for reactions ("telegram
    reactions", "reactions")."""
    return "reactions" in (hint_kinds or set()) or any(
        w in ("reaction", "reactions") for w in (hint or "").split()
    )


def _reaction_emoji_in_hint(hint):
    """The reaction emoji in a hint string, or None. 🙏 counts
    here: a hint only reaches this helper for a reactions request,
    so the thanks-vs-reaction ambiguity does not apply."""
    for emoji in REACTION_EMOJI:
        if emoji in (hint or ""):
            return emoji
    if "🙏" in (hint or ""):
        return "🙏"
    return None


def _reactions_pool(candidates, emoji):
    """Single-post reactions services only, in the emoji's family.

    The NAME must say "reaction" — a category match alone pulls
    in Bot Start post views ("Telegram Post Views | Reactions |
    Bot Start"). Nothing named "bot start", and no "Auto … 10
    Future Posts" service: that reacts to ten future posts, not
    the one post the user is ordering for. Within the pool the
    emoji picks the family (👍 -> thumbs up / like, ❤️ -> heart,
    🔥 -> fire, 🙏 -> pray); a generic request gets the Positive
    mix. The family match is EXACT (see _service_in_reaction_family):
    the emoji in the service name decides, so "Heart Eyes 😍",
    "Heart on fire ❤️‍🔥" and "Broken heart 💔" are never ❤️
    services, and a multi-emoji mix never matches one emoji.
    The rule is platform-general: it covers Telegram and Facebook
    reactions alike (owner, 14 Nov 2026). When the family has no
    service, the pool is EMPTY instead of falling back to the
    whole pool (owner, 14 Nov 2026: a 🙏 order silently got the
    Positive mix) — the caller then says honestly that there is
    no {emoji}-only service."""
    pool = []
    for s in candidates:
        name = str(s.get("name") or "").lower()
        if "reaction" not in name:
            continue
        if "bot start" in name:
            continue
        if name.startswith("auto") or "future post" in name:
            continue
        pool.append(s)
    if not pool:
        return []
    if emoji is not None:
        family = REACTION_FAMILY_WORDS.get(emoji)
    else:
        family = ("positive",)
    if family:
        matched = [
            s for s in pool
            if _service_in_reaction_family(s, emoji, family)
        ]
        if matched:
            return matched
        if emoji is not None:
            return []
    return pool


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


def qty_for_amount(amount, rate_etb_per_1000):
    """How much a budget buys: floor(amount / rate * 1000), rounded
    down to a multiple of 10 (quantities must be multiples of 10).
    Returns 0 when the amount or the rate is not positive — the
    budget does not buy even the minimum."""
    rate = float(rate_etb_per_1000 or 0)
    if rate <= 0 or amount is None or float(amount) <= 0:
        return 0
    qty = int(float(amount) / (rate / 1000))
    return (qty // 10) * 10


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


async def gemini_transcribe(audio_bytes: bytes, language: str = None) -> str:
    """Transcribe a Telegram voice message (.ogg) with Gemini."""
    prompt = "Transcribe this voice message exactly, in the language spoken."
    if language:
        name = {
            "am": "Amharic", "ti": "Tigrinya",
            "om": "Oromo (Afaan Oromo)", "en": "English",
        }.get(language, language)
        prompt = f"Transcribe this voice message exactly, in {name}."
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
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
# ChatGPT is the fourth AI (13 Nov 2026): the Gemini free-tier key
# kept hitting its per-minute limit, so when OPENAI_API_KEY is set
# the bot classifies, transcribes and reads pictures with OpenAI
# instead. The three functions mirror the Gemini ones exactly (same
# inputs, same outputs, same retry shape), and the ai_* wrappers
# below pick DeepSeek first, Qwen second, Groq third, OpenAI fourth,
# Gemini fifth, GLM last — so with no DeepSeek, Qwen, Groq or OpenAI
# key the bot behaves exactly as before.

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


async def openai_transcribe(audio_bytes: bytes, language: str = None) -> str:
    """Transcribe a Telegram voice message (.ogg) with Whisper."""
    data = {"model": "whisper-1"}
    if language:
        data["language"] = language
    data = await _openai_post(
        "/audio/transcriptions",
        headers=_openai_headers(),
        data=data,
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


# -------------------------------------------------------- Groq --------
# Groq was the first AI (13 Nov 2026, until DeepSeek took over
# that evening): OpenAI's $5 credit could not be bought — the
# owner's Bybit card was declined — so the bot uses Groq's free
# tier, which needs no card. Groq's API is OpenAI-compatible, so
# the two functions below mirror the OpenAI ones exactly (same
# inputs, same outputs, same retry shape), with Groq's base URL
# and its own key/model env vars. Photos stay on OpenAI/Gemini
# vision — Groq is not used for pictures.

async def _groq_post(path: str, headers=None, json=None, data=None,
                     files=None) -> dict:
    """One POST to the Groq API, with retries on rate limits and
    server errors. Same shape as _openai_post (two retries, after
    5s then 15s; 500 joins 429/503). The client shape is identical
    (timeout 120s, trust_env False). `files` values are bytes, so a
    retried multipart upload re-sends cleanly."""
    url = GROQ_URL + path
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
                log.warning("Groq %s, retrying (attempt %d of 3)", status, attempt + 2)
                continue
            raise


def _groq_headers() -> dict:
    return {"Authorization": f"Bearer {GROQ_API_KEY}"}


async def groq_generate(prompt: str, system: str = None) -> str:
    """One Groq text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _groq_post(
        "/chat/completions",
        headers=_groq_headers(),
        json={"model": GROQ_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


async def groq_transcribe(audio_bytes: bytes, language: str = None) -> str:
    """Transcribe a Telegram voice message (.ogg) with Groq Whisper
    (whisper-large-v3-turbo). With no language the model
    auto-detects — which is how Amharic speech can be mis-detected
    as Arabic (owner, 14 Nov 2026). Pass language to force it."""
    data = {"model": "whisper-large-v3-turbo"}
    if language:
        data["language"] = language
    data = await _groq_post(
        "/audio/transcriptions",
        headers=_groq_headers(),
        data=data,
        files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
    )
    return str(data.get("text") or "").strip()


# --------------------------------------------------- DeepSeek ------
# DeepSeek is the first AI (13 Nov 2026, evening): Groq's free
# tier kept hitting its daily token limit and Groq had temporarily
# disabled paid upgrades, so the owner said "use DeepSeek".
# DeepSeek's API is OpenAI-compatible, so the two functions below
# mirror the Groq ones exactly (same inputs, same outputs, same
# retry shape), with DeepSeek's base URL and its own key/model env
# vars. DeepSeek has no voice transcription — ai_transcribe stays
# on Groq Whisper — and pictures stay on OpenAI/Gemini vision.

async def _deepseek_post(path: str, headers=None, json=None) -> dict:
    """One POST to the DeepSeek API, with retries on rate limits
    and server errors. Same shape as _groq_post (two retries,
    after 5s then 15s; 500 joins 429/503). The client shape is
    identical (timeout 120s, trust_env False)."""
    url = DEEPSEEK_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning(
                    "DeepSeek %s, retrying (attempt %d of 3)", status, attempt + 2
                )
                continue
            raise


def _deepseek_headers() -> dict:
    return {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}


async def deepseek_generate(prompt: str, system: str = None) -> str:
    """One DeepSeek text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _deepseek_post(
        "/chat/completions",
        headers=_deepseek_headers(),
        json={"model": DEEPSEEK_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# ------------------------------------------------------------ Qwen ------
# Qwen-Turbo (Alibaba international DashScope) mirrors the DeepSeek
# provider exactly (same inputs, same outputs, same retry shape),
# with Qwen's base URL and its own key/model env vars.

async def _qwen_post(path: str, headers=None, json=None) -> dict:
    """One POST to the Qwen API, with retries on rate limits
    and server errors. Same shape as _groq_post (two retries,
    after 5s then 15s; 500 joins 429/503). The client shape is
    identical (timeout 120s, trust_env False)."""
    url = QWEN_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning(
                    "Qwen %s, retrying (attempt %d of 3)", status, attempt + 2
                )
                continue
            raise


def _qwen_headers() -> dict:
    return {"Authorization": f"Bearer {QWEN_API_KEY}"}


async def qwen_generate(prompt: str, system: str = None) -> str:
    """One Qwen text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _qwen_post(
        "/chat/completions",
        headers=_qwen_headers(),
        json={"model": QWEN_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# ------------------------------------------------------------- GLM ------
# GLM (Zhipu / Z.AI) mirrors the DeepSeek provider exactly (same
# inputs, same outputs, same retry shape), with GLM's base URL and
# its own key/model env vars. GLM-4.7-Flash is free but slow and
# rate-limited (~1 request/second), so it is only the last resort
# in ai_generate — never the first call.

async def _glm_post(path: str, headers=None, json=None) -> dict:
    """One POST to the GLM API, with retries on rate limits
    and server errors. Same shape as _groq_post (two retries,
    after 5s then 15s; 500 joins 429/503). The client shape is
    identical (timeout 120s, trust_env False)."""
    url = GLM_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning(
                    "GLM %s, retrying (attempt %d of 3)", status, attempt + 2
                )
                continue
            raise


def _glm_headers() -> dict:
    return {"Authorization": f"Bearer {GLM_API_KEY}"}


async def glm_generate(prompt: str, system: str = None) -> str:
    """One GLM text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _glm_post(
        "/chat/completions",
        headers=_glm_headers(),
        json={"model": GLM_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# ------------------------------------------------------- OpenRouter -----
# OpenRouter mirrors the GLM provider exactly (same inputs, same
# outputs, same retry shape), with OpenRouter's base URL and its
# own key/model env vars. The default model "openrouter/free" is a
# router that picks a currently-free model automatically. It sits
# between Gemini and GLM in ai_generate — only after Gemini failed
# — so it never burns its daily free cap on healthy days.

async def _openrouter_post(path: str, headers=None, json=None) -> dict:
    """One POST to the OpenRouter API, with retries on rate limits
    and server errors. Same shape as _glm_post (two retries,
    after 5s then 15s; 500 joins 429/503). The client shape is
    identical (timeout 120s, trust_env False)."""
    url = OPENROUTER_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning(
                    "OpenRouter %s, retrying (attempt %d of 3)", status, attempt + 2
                )
                continue
            raise


def _openrouter_headers() -> dict:
    return {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}


async def openrouter_generate(prompt: str, system: str = None) -> str:
    """One OpenRouter text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _openrouter_post(
        "/chat/completions",
        headers=_openrouter_headers(),
        json={"model": OPENROUTER_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# ---------------------------------------------------------------- Kilo ---
# Kilo Code gateway mirrors the OpenRouter provider exactly (same
# inputs, same outputs, same retry shape), with Kilo's base URL and
# its own model env var — but NO API key: the free gateway needs no
# signup and takes no Authorization header. The default model
# "kilo-auto/free" is a router that picks a currently-free model
# automatically. It sits between Gemini and OpenRouter in
# ai_generate — only after Gemini failed — so it never burns its
# per-IP hourly cap on healthy days; a Kilo failure falls through
# to OpenRouter, then GLM.

async def _kilo_post(path: str, headers=None, json=None) -> dict:
    """One POST to the Kilo Code gateway, with retries on rate limits
    and server errors. Same shape as _openrouter_post (two retries,
    after 5s then 15s; 500 joins 429/503). The client shape is
    identical (timeout 120s, trust_env False)."""
    url = KILO_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning(
                    "Kilo %s, retrying (attempt %d of 3)", status, attempt + 2
                )
                continue
            raise


def _kilo_headers() -> dict:
    # No key, no signup: the free gateway takes no Authorization header.
    return {}


async def kilo_generate(prompt: str, system: str = None) -> str:
    """One Kilo text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _kilo_post(
        "/chat/completions",
        headers=_kilo_headers(),
        json={"model": KILO_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# --------------------------------------------------------------- Zen ----
# OpenCode Zen mirrors the OpenRouter provider exactly (same inputs,
# same outputs, same retry shape), with Zen's base URL and its own
# key/model env vars. The default model "deepseek-v4.1-flash-free"
# is the free DeepSeek V4.1 Flash served by Zen. It sits between
# DeepSeek and Qwen in ai_generate — only after DeepSeek failed; a
# Zen failure falls through to Qwen, then Mistral, then Groq, then
# OpenAI, then Gemini, then Kilo, then OpenRouter, then GLM.

async def _zen_post(path: str, headers=None, json=None) -> dict:
    """One POST to the OpenCode Zen API, with retries on rate limits
    and server errors. Same shape as _openrouter_post (two retries,
    after 5s then 15s; 500 joins 429/503). The client shape is
    identical (timeout 120s, trust_env False)."""
    url = ZEN_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning(
                    "Zen %s, retrying (attempt %d of 3)", status, attempt + 2
                )
                continue
            raise


def _zen_headers() -> dict:
    return {"Authorization": f"Bearer {ZEN_API_KEY}"}


async def zen_generate(prompt: str, system: str = None) -> str:
    """One Zen text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _zen_post(
        "/chat/completions",
        headers=_zen_headers(),
        json={"model": ZEN_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# -------------------------------------------------------------- Mistral --
# Mistral mirrors the OpenRouter provider exactly (same inputs,
# same outputs, same retry shape), with Mistral's base URL and its
# own key/model env vars. The default model "mistral-small-latest"
# is Mistral's small chat model. It sits between Qwen and Groq in
# ai_generate — only after Qwen failed; a Mistral failure falls
# through to Groq, then OpenAI, then Gemini, then Kilo, then
# OpenRouter, then GLM.

async def _mistral_post(path: str, headers=None, json=None) -> dict:
    """One POST to the Mistral API, with retries on rate limits
    and server errors. Same shape as _openrouter_post (two retries,
    after 5s then 15s; 500 joins 429/503). The client shape is
    identical (timeout 120s, trust_env False)."""
    url = MISTRAL_URL + path
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 500, 503) and attempt < 2:
                log.warning(
                    "Mistral %s, retrying (attempt %d of 3)", status, attempt + 2
                )
                continue
            raise


def _mistral_headers() -> dict:
    return {"Authorization": f"Bearer {MISTRAL_API_KEY}"}


async def mistral_generate(prompt: str, system: str = None) -> str:
    """One Mistral text call (OpenAI-compatible chat completions).
    Returns the reply text (may be empty)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = await _mistral_post(
        "/chat/completions",
        headers=_mistral_headers(),
        json={"model": MISTRAL_MODEL, "messages": messages},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _log_ai_failure(message: str, exc) -> None:
    """Log an AI-provider failure: message + HTTP status only.

    Never log the exception object or a traceback here — an httpx
    error's text carries the request URL, and the Gemini URL carries
    the API key (?key=...), which leaked into the Render logs (13 Nov
    2026). The status code is all the debugging signal there is.
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        log.warning("%s (HTTP %s)", message, status)
    else:
        log.warning("%s", message)


async def ai_generate(prompt: str, system: str = None) -> str:
    """Text from the AI: DeepSeek when DEEPSEEK_API_KEY is set, else
    Zen when ZEN_API_KEY is set (model deepseek-v4.1-flash-free —
    free tier, no card, owner approved 14 Nov 2026; a Zen failure
    falls through to Qwen), else Qwen when QWEN_API_KEY is set,
    else Mistral when MISTRAL_API_KEY is set (model
    mistral-small-latest — pay-as-you-go, owner approved 14 Nov
    2026: $0.10/$0.30 per 1M tokens, PAYG needs $10 prepaid credits
    first, no monthly minimum; a Mistral failure falls through to
    Groq), else Groq when GROQ_API_KEY is set, else ChatGPT when
    OPENAI_API_KEY is set, else Gemini, else Kilo (no key — free
    gateway, only after Gemini failed, so it never burns its per-IP
    hourly cap), else OpenRouter when OPENROUTER_API_KEY is set
    (free :free models — only after Kilo failed, so it never burns
    its daily cap), else GLM when GLM_API_KEY is set (free last
    resort — slow and rate-limited, so it only runs when every other
    provider failed).
    Every caller uses this, so the provider switch is one env var
    and the fallback is automatic. A provider that raises after its
    own retries falls through to the next one; only when every
    configured provider failed does the error reach the caller
    (extract_intent then answers from local_intent instead of going
    silent). The last provider's error is re-raised — never retried
    — so a total failure fails once, not twice."""
    last_exc = None
    if DEEPSEEK_API_KEY:
        try:
            return await deepseek_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("DeepSeek generate failed, trying next provider", exc)
            last_exc = exc
    if ZEN_API_KEY:
        try:
            return await zen_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("Zen generate failed, trying next provider", exc)
            last_exc = exc
    if QWEN_API_KEY:
        try:
            return await qwen_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("Qwen generate failed, trying next provider", exc)
            last_exc = exc
    if MISTRAL_API_KEY:
        try:
            return await mistral_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("Mistral generate failed, trying next provider", exc)
            last_exc = exc
    if GROQ_API_KEY:
        try:
            return await groq_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("Groq generate failed, trying next provider", exc)
            last_exc = exc
    if OPENAI_API_KEY:
        try:
            return await openai_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("OpenAI generate failed, trying next provider", exc)
            last_exc = exc
    if GEMINI_API_KEY:
        try:
            return await gemini_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("Gemini generate failed, trying next provider", exc)
            last_exc = exc
    try:
        return await kilo_generate(prompt, system=system)
    except Exception as exc:
        _log_ai_failure("Kilo generate failed, trying next provider", exc)
        last_exc = exc
    if OPENROUTER_API_KEY:
        try:
            return await openrouter_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("OpenRouter generate failed, trying next provider", exc)
            last_exc = exc
    if GLM_API_KEY:
        try:
            return await glm_generate(prompt, system=system)
        except Exception as exc:
            _log_ai_failure("GLM generate failed, trying next provider", exc)
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    # No provider configured at all: let Gemini raise so the caller
    # falls back to local rules instead of going silent.
    return await gemini_generate(prompt, system=system)


# ------------------------------------------- Amharic translate-bridge ---
# Amharic, Tigrinya and Oromo messages are translated to English by
# Gemini first, the whole flow runs in English, and prose replies
# are translated back to the user's language before sending (see
# reply_message). Owner, 13 Nov 2026: DeepSeek/Qwen/Groq have
# unproven Amharic, but Gemini is strong on it, so Gemini does the
# translating while the main AI does the thinking. Oromo and
# Tigrinya were added the same way on 14 Nov 2026. Links, numbers,
# service IDs, prices and service names are never translated — the
# prompts say so, and Confirm cards, buttons and post-acceptance
# summaries never pass through the bridge at all. If either
# translation call fails, the original text is used instead — the
# bot never goes silent and never drops an order over a translation
# failure.
#
# _BRIDGE_LANG is the language this turn's message was bridged from
# ("am", "ti" or "om"), or None when the message was English. It is
# reset at the start of every turn in handle_order_text: the old
# boolean flag was set on an Amharic turn and never cleared, and
# because PTB processes updates sequentially in one task
# (max_concurrent_updates=1, the default — build_application does
# not change it), it leaked into every later English turn and
# translated those replies to Amharic too (live bug, 14 Nov 2026:
# "I'm tired" and "I said do you speak English" both got Amharic
# replies). _BRIDGE_AMHARIC is kept as a legacy alias, synced by
# _set_bridge_lang, because the offline tests reset it between
# cases.
_BRIDGE_LANG = contextvars.ContextVar("paxyo_bridge_lang", default=None)
_BRIDGE_AMHARIC = contextvars.ContextVar("paxyo_bridge_amharic", default=False)

_BRIDGE_LANG_NAMES = {
    "am": "Amharic", "ti": "Tigrinya", "om": "Oromo (Afaan Oromo)",
}


def _set_bridge_lang(lang):
    """Record the language this turn was bridged from (or None)."""
    _BRIDGE_LANG.set(lang)
    _BRIDGE_AMHARIC.set(lang == "am")


def _bridge_to_english_prompt(lang: str) -> str:
    return (
        f"Translate this {_BRIDGE_LANG_NAMES[lang]} message to English. "
        "Keep links, numbers, service IDs and prices exactly as they "
        "are. Reply with only the translation."
    )


def _bridge_from_english_prompt(lang: str) -> str:
    return (
        f"Translate this reply to {_BRIDGE_LANG_NAMES[lang]}. Keep links, "
        "numbers, service IDs, prices and service names exactly as "
        "they are. Reply with only the translation."
    )


BRIDGE_TO_ENGLISH_PROMPT = _bridge_to_english_prompt("am")
BRIDGE_TO_AMHARIC_PROMPT = _bridge_from_english_prompt("am")


async def translate_to_english(text: str, source_lang: str = "am") -> str:
    """A non-English message -> English via Gemini. Returns "" on any
    failure (no key, 429, empty reply) — the caller then uses the
    original text instead."""
    if not GEMINI_API_KEY:
        return ""
    try:
        result = await gemini_generate(
            _bridge_to_english_prompt(source_lang) + "\n\n" + text
        )
    except Exception as exc:
        _log_ai_failure("bridge translate to English failed", exc)
        return ""
    return (result or "").strip()


async def translate_to_language(text: str, lang: str) -> str:
    """English -> the user's language via Gemini. Returns "" on any
    failure — the caller then sends the English reply as-is."""
    if not GEMINI_API_KEY:
        return ""
    try:
        result = await gemini_generate(
            _bridge_from_english_prompt(lang) + "\n\n" + text
        )
    except Exception as exc:
        _log_ai_failure("bridge translate from English failed", exc)
        return ""
    return (result or "").strip()


async def translate_to_amharic(text: str) -> str:
    """English -> Amharic via Gemini. Wrapper kept for callers that
    only know Amharic; translate_to_language is the general one."""
    return await translate_to_language(text, "am")


async def ai_transcribe(audio_bytes: bytes, language: str = None) -> str:
    """Voice transcription: Groq Whisper when GROQ_API_KEY is set,
    else Whisper when OPENAI_API_KEY is set, else Gemini. A provider
    that raises falls through to the next one. `language` is a
    Whisper language hint (\"am\", \"ti\", \"om\", \"en\") — None means
    auto-detect."""
    if GROQ_API_KEY:
        try:
            return await groq_transcribe(audio_bytes, language=language)
        except Exception as exc:
            _log_ai_failure("Groq transcribe failed, trying next provider", exc)
    if OPENAI_API_KEY:
        try:
            return await openai_transcribe(audio_bytes, language=language)
        except Exception as exc:
            _log_ai_failure("OpenAI transcribe failed, trying next provider", exc)
    return await gemini_transcribe(audio_bytes, language=language)


def _has_arabic_script(text: str) -> bool:
    """True when the text contains Arabic-script characters
    (U+0600–U+06FF). Amharic is Ge'ez script, Tigrinya is Ge'ez,
    Oromo is Latin — Arabic script in a transcription means the
    transcriber mis-detected the language, unless the user
    actually speaks Arabic."""
    return bool(re.search(r"[\u0600-\u06ff]", text or ""))


async def transcribe_voice_with_retry(audio, user_id: int, user_lang: str) -> str:
    """Transcribe a voice note, with one language-hinted retry
    when the first try comes back in Arabic script (owner, 14
    Nov 2026). ROOT CAUSE of the owner's report: Whisper
    auto-detects the language and its Amharic is weak, so short
    Amharic clips can be mis-detected as Arabic — both are
    Semitic languages — and the Arabic-script text then flows
    into the order flow, where detect_language has no Arabic
    branch and the AI mirrors the Arabic back. The retry hints
    the user's last detected language (or their Telegram
    language, or Amharic) and only then is the result trusted.
    Returns \"\" when both tries fail or stay Arabic, so the
    caller answers honestly instead of feeding Arabic to the
    order flow."""
    text = await ai_transcribe(audio)
    if not _has_arabic_script(text):
        return text
    if (user_lang or "").lower().startswith("ar"):
        return text
    hint = LAST_LANG.get(user_id)
    if hint not in ("am", "ti", "om", "en"):
        code = (user_lang or "").lower()
        hint = code[:2] if code[:2] in ("am", "ti", "om", "en") else "am"
    try:
        retry = await ai_transcribe(audio, language=hint)
    except Exception:
        return ""
    if _has_arabic_script(retry):
        return ""
    return retry


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
    "comments", "reactions",
)

# Emoji the bot reads (round 8, 14 Nov 2026): an emoji in a message
# carries meaning — 👍 IS the thumbs-up reaction, ❤️ the heart
# reaction, and so on. The classifier sees the emoji itself (it
# survives normalize_text), but the local helpers only read words,
# so the meaning is mapped here for local intent, kind detection
# and restatements. 👀 means views; 🙏 is thanks/prayer, not a
# reaction type, so it maps to a word but never to "reactions".
EMOJI_MEANINGS = {
    "👍": "thumbs-up",
    "❤️": "heart",
    "❤": "heart",
    "🔥": "fire",
    "😂": "laugh",
    "🤣": "laugh",
    "😆": "laugh",
    "😮": "wow",
    "😢": "sad",
    "💔": "broken-heart",
    "🙏": "pray",
    "👀": "views",
    "😍": "heart-eyes",
    "😊": "smile",
    "🥰": "love",
    "👏": "clap",
    "🎉": "party",
    "💯": "hundred",
    "😎": "cool",
    "🤔": "thinking",
    "😡": "angry",
    "👎": "thumbs-down",
}
# Emoji that pick a Telegram reaction type when the user orders one
# (round 8.1, 14 Nov 2026; extended 14 Nov 2026 — 👎 😡 😎 🤔 🎉 😍
# have dedicated single-emoji services; 😆 added 14 Nov 2026 for
# Facebook reactions, which have a dedicated 😆 service). 🙏 is
# deliberately NOT in this tuple: on its own it is thanks
# ("thank you 🙏" -> None, pinned by test), and only counts as a
# reaction in a reactions-order context — see reaction_emoji.
# The tuple is platform-general: the same emoji pick a Facebook
# reaction service when the order is for Facebook (owner,
# 14 Nov 2026 — the exact-emoji rule covers Facebook too).
REACTION_EMOJI = (
    "👍", "❤️", "❤", "🔥", "😂", "🤣", "😆", "😮", "😢",
    "👎", "😡", "😎", "🤔", "🎉", "😍",
)
# Emoji that are just chat (a laugh, a smile) — never an order.
_CHAT_EMOJI = ("😂", "🤣", "😄", "😊")


def emoji_meanings(text: str):
    """[(emoji, meaning)] for every known emoji in the text, in
    order. A variation selector is kept with its emoji (❤️ stays
    ❤️) and a skin tone is dropped (👍🏻 reads as 👍), so the
    returned emoji is the one the user sent."""
    s = text or ""
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        emoji = ch
        j = i + 1
        if j < len(s) and s[j] == "\ufe0f":
            emoji = ch + s[j]
            j += 1
        while j < len(s) and "\U0001f3fb" <= s[j] <= "\U0001f3ff":
            j += 1
        meaning = EMOJI_MEANINGS.get(ch)
        if meaning is not None and (not out or out[-1][0] != emoji):
            out.append((emoji, meaning))
        i = j
    return out


def reaction_emoji(text: str):
    """The reaction emoji in the text (👍 ❤️ 🔥 🙏 ...), or None.
    🙏 counts only when the message is about reactions ("add 10 🙏
    of tg reaction", "I want only 🙏 reaction"): on its own 🙏 is
    thanks, not a reaction type, so "thank you 🙏" still returns
    None."""
    found_pray = None
    for emoji, _meaning in emoji_meanings(text):
        if emoji in REACTION_EMOJI:
            return emoji
        if emoji == "🙏" and found_pray is None:
            found_pray = emoji
    if found_pray is not None:
        s = " ".join((text or "").strip().lower().split())
        if "reaction" in s or "telegram" in s or " tg " in f" {s} ":
            return found_pray
    return None


# Reaction emoji that may start a bare order ("10 🙏", "🙏 10",
# "10 👍"): REACTION_EMOJI plus 🙏, which is a reaction choice
# only in a reactions context — and a bare "10 🙏" IS that
# context (owner, 14 Nov 2026 — live retest: it got "I did not
# understand", and the bare link after it asked "Which
# platform?").
_BARE_REACTION_ORDER_EMOJI = REACTION_EMOJI + ("🙏",)


def bare_reaction_order(text: str):
    """(emoji, quantity) when the message is ONLY a reaction emoji
    with an optional quantity — "10 🙏", "🙏 10", "10 👍" — or a
    bare 🙏 on its own, or None. A bare emoji that is already in
    REACTION_EMOJI keeps the existing bare-emoji branch (a natural
    acknowledgement), so only 🙏 matches on its own here. The
    quantity is any whole number 1..1,000,000; the order flow's
    validate_quantity still rejects one outside the service's own
    min/max when the card is built. Skin tones are dropped, as in
    emoji_meanings."""
    s = " ".join((text or "").strip().split())
    if not s:
        return None
    s = re.sub(r"[\U0001f3fb-\U0001f3ff]", "", s)
    s = s.replace("\ufe0f", "")
    pattern = "|".join(
        re.escape(e.replace("\ufe0f", ""))
        for e in sorted(
            _BARE_REACTION_ORDER_EMOJI, key=len, reverse=True
        )
    )
    match = re.fullmatch(
        r"(?:(\d[\d,]*)\s*)?(" + pattern + r")(?:\s*(\d[\d,]*))?", s
    )
    if match is None:
        return None
    if match.group(1) is not None and match.group(3) is not None:
        return None  # a number on both sides is not a clean start
    stripped = match.group(2)
    emoji = next(
        (
            e for e in _BARE_REACTION_ORDER_EMOJI
            if e.replace("\ufe0f", "") == stripped
        ),
        stripped,
    )
    qty_text = match.group(1) or match.group(3)
    if qty_text is None:
        if emoji in REACTION_EMOJI:
            return None
        return (emoji, None)
    try:
        qty = int(qty_text.replace(",", ""))
    except ValueError:
        return None
    if not 1 <= qty <= 1000000:
        return None
    return (emoji, qty)


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
    metric = kind_from_text(s)
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
    elif "the usual" in s or "same as yesterday" in s or "same as last" in s or "as usual" in s:
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
    elif (
        "how" in words
        and ("link" in words or "public" in words or "username" in words)
        and any(p in s for p in (
            "how do i", "how to", "how can i", "how do you",
        ))
    ):
        # A how-to question (owner, 14 Nov 2026): how to get a
        # link, how to make an account public, how to find a
        # username. Answered freely by the AI — never deflected.
        intent["intent"] = "how_to"
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
    elif is_reseller_request(text):
        # Next batch, 14 Nov 2026: before the order fallback —
        # "I want to sell followers" names the followers metric,
        # so without this it would be misread as an order.
        intent["intent"] = "reseller"
    elif is_contact_request(text):
        intent["intent"] = "contact"
    elif is_paused_services_request(text):
        # Paused services, 14 Nov 2026: before the order fallback —
        # "I want CapCut Pro" has no platform/metric, but "I want
        # premium followers" must still fall through to order (the
        # guard already excludes metric words).
        intent["intent"] = "paused_services"
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


async def extract_intent(text: str, user_id: int = None,
                         services=None) -> dict:
    """Ask the AI (DeepSeek, then Zen, Qwen, Mistral, Groq, ChatGPT, Gemini,
    Kilo, OpenRouter, GLM — see ai_generate) to classify the message and extract the order intent.

    The prompt is built by build_classify_prompt: the message, the
    last 3 turns, and — when the message names a platform and a
    metric — the matching services only (see the prompt shrink).
    `services` is the catalogue (or None: no services section, as
    before); it is only ever a hint to the classifier — the
    deterministic code still picks from the full catalogue.

    The text is normalised first (typos/slang fixed, URLs kept
    verbatim), so "let me deposit 10 br by teleirr" still classifies
    as a deposit. Returns {"intent": ..., "platform": ...,
    "service_hint": ..., "service_id": ..., "link": ..., "quantity": ...,
    "interval_minutes": ..., "amount": ..., "method": ...,
    "phone": ..., "quantity_multiplier": ..., "orders": ...,
    "split": ...}. intent is one of order, recurring, schedules,
    stop_schedule, balance, orders, deposit, deposit_status, help,
    how_to_order, how_to, miniapp, social, greeting, paxyo_info,
    source_question, reseller, contact, paused_services, usual, goal, budget, batch,
    change_order, refill, split_payment, max_for_balance, discount,
    safety, refund_policy, geo_target, free_sample, price_pushback,
    content_help, support_issue, cancel, off_topic, unclear — or
    None when the model output had no usable JSON.
    """
    prompt = build_classify_prompt(text, services=services,
                                   user_id=user_id)
    try:
        reply = await ai_generate(prompt, system=SYSTEM_PROMPT)
    except Exception as exc:
        # The AI is unreachable (rate limit, outage). Answer from the
        # message itself instead of going silent — see local_intent.
        # Log status only: the exception text carries the request URL,
        # and the Gemini URL carries the API key (?key=...).
        _log_ai_failure("AI classify failed, using local fallback", exc)
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


async def answer_paxyo_question(text: str, lang: str, user_id: int = None) -> str:
    """Answer a question about Paxyo itself (paxyo_info intent).

    The AI answers from PAXYO_KNOWLEDGE only, in the user's language,
    in 1-3 short sentences. When the AI is down (or gives nothing),
    the local facts answer instead — the bot still knows who owns
    Paxyo, what it is, how to pay and where to find it. Falls back
    to a short canned line when neither has an answer. Never mentions
    the provider or costs.
    """
    system = (
        PAXYO_KNOWLEDGE
        + "\nAnswer the user's question using only these facts, in "
        + ("Amharic (Ethiopic fidels mixed with English) — " if lang == "am"
           else "English — ")
        + "1-3 short sentences. If the question is about how to do "
        "something needed to order (getting a link, making an "
        "account public, using Telegram, TikTok or Instagram), "
        "answer it from your own general knowledge in 1-3 short "
        "sentences. Only questions truly unrelated to Paxyo or "
        "ordering get a one-line steer back to ordering. "
        "Never say where Paxyo's services come from, and never talk "
        "about what Paxyo pays for them. Never quote a price; say "
        "prices are shown in ETB per 1000 before confirming. Never "
        "warn the user against buying followers, likes, views, "
        "members or reactions, and never call them fake — Paxyo sells "
        "these services. If the "
        "question is how long delivery takes, never say the time is "
        "only shown before confirming."
    )
    prompt = text
    if user_id is not None:
        history = chat_history_lines(user_id, max_exchanges=3)
        if history:
            prompt += (
                "\n\nRecent conversation with this user (most recent last):\n"
                + "\n".join(history)
            )
    try:
        reply = await ai_generate(prompt, system=system)
    except Exception as exc:
        _log_ai_failure("paxyo_info answer failed", exc)
        return paxyo_facts_answer(text, lang) or t("paxyo_info_fallback", lang)
    answer = strip_moralizing((reply or "").strip())
    if answer:
        return answer
    return paxyo_facts_answer(text, lang) or t("paxyo_info_fallback", lang)


def paxyo_facts_answer(text: str, lang: str):
    """Answer a Paxyo question from the local facts, without the AI.

    Used when the AI is down or gives nothing: the bot still knows
    who owns Paxyo, what it is, how to pay and where to find it.
    Returns None when the question matches no local fact (the caller
    then uses the generic fallback line). Only the public facts —
    never the supplier, never what Paxyo pays.
    """
    s = " ".join((text or "").strip().lower().split())
    if any(p in s for p in (
        "who owns", "who is the owner", "who runs", "who created",
        "who made", "who is william", "who is yohannes", "ባለቤት",
    )):
        return t("paxyo_owner", lang)
    if any(p in s for p in (
        "how do i add money", "how to add money", "how do i pay",
        "how to pay", "how can i pay", "how do you accept payment",
        "how do i deposit", "how to deposit", "how can i deposit",
        "add money", "top up", "recharge", "ገንዘብ ማስገባት",
    )):
        return t("paxyo_pay", lang)
    if any(p in s for p in (
        "where can i find", "website", "paxyo.et", "channel",
        "mini app", "where is paxyo", "follow paxyo", "social",
    )):
        return t("paxyo_find", lang)
    if any(p in s for p in (
        "what is paxyo", "about paxyo", "what does paxyo do",
        "tell me about paxyo", "ምንድን ነው",
    )):
        return t("paxyo_what", lang)
    return None


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

    Amharic translate-bridge: when this turn's message was bridged
    (see handle_order_text), prose replies are translated back to
    the user's language here before sending. Anything with buttons
    (Confirm cards, keyboards) is never translated, and a failed
    translation sends the English reply as-is. The English original
    is what goes into the conversation history, so the AI keeps
    reading English there.

    Returns the sent message (or None when the send produced none),
    so a caller that shows a Confirm card can remember the card's
    message id for later deletion (a replaced card is dropped, not
    left stacked in the chat).
    """
    out_text, out_lang = text, lang
    _target = _BRIDGE_LANG.get()
    if reply_markup is None and _target:
        if _target == "am":
            _translated = await translate_to_amharic(text)
        else:
            _translated = await translate_to_language(text, _target)
        if _translated:
            out_text, out_lang = _translated, _target
    if voice and reply_markup is None:
        ogg = await speak_reply(out_text, out_lang)
        if ogg:
            try:
                sent = await message.reply_voice(
                    voice=InputFile(io.BytesIO(ogg), filename="reply.ogg")
                )
                _record_bot_reply(text)
                return sent
            except Exception as exc:
                log.warning("reply_voice failed, falling back to text: %s", exc)
    sent = await message.reply_text(out_text, reply_markup=reply_markup)
    _record_bot_reply(text)
    return sent


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
# The language of each user's most recent detected message
# (\"am\", \"ti\", \"om\", \"en\"): the hint for the next voice-note
# transcription, so an Amharic voice note is not auto-detected as
# Arabic on the retry (owner, 14 Nov 2026). Set in
# handle_order_text; cleared with the rest of the per-user state
# in tests.
LAST_LANG = {}
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
# ------------------------------------------------------- round 5 ------
# Round-5 helpers (13 Nov 2026): short names, bare quantities,
# price questions, reply/quote context, order history, voice fixes,
# GIFs/stickers, humor, off-topic steering, offensive users,
# conversation memory, order-now, delivery times, terms, ban answers.

# --- conversation memory: last ~10 exchanges per user ---------------
# Persisted to a local JSON file (best effort) so it survives a bot
# restart. Render's free disk is ephemeral on redeploy, so this is
# not permanent storage — see README, "Conversation memory".
CHAT_HISTORY_FILE = os.environ.get("CHAT_HISTORY_FILE", "chat_history.json")
MAX_HISTORY_EXCHANGES = 10
MAX_HISTORY_USERS = 500
CHAT_HISTORY = {}
_CHAT_HISTORY_LOADED = False
_LAST_HISTORY_SAVE = 0.0
_CURRENT_USER_ID = contextvars.ContextVar("paxyo_current_user", default=None)
_LAST_USER_TEXT = contextvars.ContextVar("paxyo_last_user_text", default=None)


def load_chat_history() -> None:
    """Load saved conversation memory (best effort)."""
    global _CHAT_HISTORY_LOADED
    if _CHAT_HISTORY_LOADED:
        return
    _CHAT_HISTORY_LOADED = True
    try:
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    for key, exchanges in data.items():
        try:
            user_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(exchanges, list):
            CHAT_HISTORY[user_id] = [
                e for e in exchanges
                if isinstance(e, dict) and e.get("user") and e.get("bot")
            ][-MAX_HISTORY_EXCHANGES:]


def save_chat_history() -> None:
    """Persist conversation memory (best effort — never raises).
    Throttled to one write per 5 seconds: the in-memory copy is
    always current, so a crash loses at most a few seconds."""
    global _LAST_HISTORY_SAVE
    import time

    now = time.monotonic()
    if now - _LAST_HISTORY_SAVE < 5:
        return
    _LAST_HISTORY_SAVE = now
    try:
        data = {
            str(uid): exchanges[-MAX_HISTORY_EXCHANGES:]
            for uid, exchanges in list(CHAT_HISTORY.items())[-MAX_HISTORY_USERS:]
        }
        with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def record_exchange(user_id: int, user_text: str, bot_text: str) -> None:
    """Remember one user/bot exchange, capped at the last 10."""
    if not user_id or not (user_text or "").strip() or not (bot_text or "").strip():
        return
    load_chat_history()
    exchanges = CHAT_HISTORY.setdefault(int(user_id), [])
    exchanges.append({"user": user_text.strip()[:500], "bot": bot_text.strip()[:500]})
    del exchanges[:-MAX_HISTORY_EXCHANGES]
    if len(CHAT_HISTORY) > MAX_HISTORY_USERS:
        CHAT_HISTORY.pop(next(iter(CHAT_HISTORY)))
    save_chat_history()


def chat_history_lines(user_id: int, max_exchanges: int = 10):
    """'User: ... / Bot: ...' lines for the AI prompt, or []. Only
    the last `max_exchanges` turns (prompt shrink, 14 Nov 2026:
    the classifier does not need the whole chat — 3 turns is
    enough context and keeps the prompt small)."""
    load_chat_history()
    lines = []
    for e in CHAT_HISTORY.get(int(user_id), [])[-max_exchanges:]:
        lines.append(f"User: {e.get('user', '')}")
        lines.append(f"Bot: {e.get('bot', '')}")
    return lines


def history_summary_text(user_id: int, lang: str):
    """What this user talked about before, or None when there is
    nothing to remember."""
    load_chat_history()
    user_texts = [
        e.get("user", "") for e in CHAT_HISTORY.get(int(user_id), [])
        if e.get("user")
    ]
    if not user_texts:
        return None
    summary = "; ".join(user_texts[-3:])
    return t("history_summary", lang, summary=summary)


def _record_bot_reply(bot_text: str) -> None:
    """Record the bot's reply against the user message that caused
    this turn (set by handle_order_text). Only the first reply of a
    turn is recorded, so one turn is one exchange."""
    user_id = _CURRENT_USER_ID.get()
    if user_id is None:
        return
    user_text = _LAST_USER_TEXT.get()
    if not user_text:
        return
    _LAST_USER_TEXT.set(None)
    record_exchange(user_id, user_text, bot_text)


# --- off-topic steering: first two get a general answer + nudge -----
OFF_TOPIC_COUNT = {}  # telegram_id -> consecutive off-topic turns


# --- no fake-follower moralizing (owner, 14 Nov 2026) --------------
# Paxyo sells followers/likes/views, so the bot must NEVER lecture
# a user about "fake followers" or warn them off buying. The AI's
# free answers sometimes do exactly that ("avoid buying fake
# followers"), so the rule is in every free-answer prompt AND in a
# sanitizer that strips any such sentence if the AI still writes
# one. The ban answer keeps the owner's NO line (14 Nov 2026,
# platform-general — no platform bans or strikes over fake
# followers, likes or views) — it states the fact for the ban
# question specifically and is not a lecture.
_MORALIZING_RES = (
    re.compile(
        r"avoid\s+(buying\s+)?(fake\s+)?(followers|likes|views|members|reactions)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(don't|do not|never|shouldn't|should not)\s+buy\s+(fake\s+)?"
        r"(followers|likes|views|members|reactions)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bfake\s+(followers|likes|views|members|reactions)\b.{0,80}\b"
        r"(harm|hurt|risk|ban|damage|penal|danger|unsafe|bad for)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(beware|be careful|watch out)\b.{0,60}\bfake\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"buying\s+(fake\s+)?(followers|likes|views)\b.{0,60}\b"
        r"(against|violates|breaks|harm|risk|danger)",
        re.IGNORECASE,
    ),
)


def strip_moralizing(text: str) -> str:
    """Drop any sentence that lectures the user against buying
    followers/likes/views (owner, 14 Nov 2026). Returns the cleaned
    text, or "" when nothing is left. A sentence that merely says
    the followers are real ("these are not fake followers") has no
    warning words and survives."""
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [p for p in parts if not any(rx.search(p) for rx in _MORALIZING_RES)]
    return " ".join(kept).strip()


async def answer_general_question(text: str, lang: str):
    """A brief general-knowledge answer (1-2 short sentences) from
    the AI, or None when the AI is down. Never about Paxyo's supplier
    or costs — the system prompt says so, and the caller steers back
    to ordering right after. Never moralizes about fake followers
    (owner, 14 Nov 2026): the prompt forbids it and the reply is
    sanitized, so a warning the AI writes anyway never reaches the
    user."""
    system = (
        "Answer briefly (1-2 short sentences) from your own general "
        "knowledge, in "
        + {
            "am": "Amharic (Ethiopic fidels mixed with English)",
            "ti": "Tigrinya (Ge'ez script)",
            "om": "Oromo (Afaan Oromo, Latin script)",
        }.get(lang, "English")
        + ". Never mention where Paxyo's services come from, what "
        "Paxyo pays for them, or any supplier. Never quote a price. "
        "Never warn the user against buying followers, likes, views, "
        "members or reactions, and never call them fake — Paxyo sells "
        "these services."
    )
    try:
        reply = await ai_generate(text, system=system)
    except Exception as exc:
        _log_ai_failure("general answer failed", exc)
        return None
    return strip_moralizing((reply or "").strip()) or None


# --- offensive users: firm and blunt, never polite -------------------
_OFFENSIVE_RE = re.compile(
    r"\b(fuck\w*|shit\w*|bitch\w*|bastard\w*|asshole\w*|dickhead\w*|moron\w*|idiot\w*)\b"
    r"|shut up|stupid bot|dumb bot|hate you|useless bot",
    re.IGNORECASE,
)
OFFENSE_COUNT = {}  # telegram_id -> consecutive offensive messages


def is_offensive(text: str) -> bool:
    """True when the message insults or swears at the bot."""
    return bool(_OFFENSIVE_RE.search(normalize_text(text or "")))


# --- humor: a light line on happy paths ------------------------------
HUMOR_LINES = {
    "en": [
        "🎉 Order in — nice choice!",
        "Done! Your order is on its way. 🚀",
        "Nice — that's ordered! 🎉",
        "All set — enjoy! 🚀",
    ],
    "am": [
        "🎉 Order ገብቷል — ጥሩ ምርጫ!",
        "ተጠናቋል! Orderዎ በመንገድ ላይ ነው። 🚀",
        "ጥሩ ነው — ተዘዟል! 🎉",
        "ሁሉም ተዘጋጅቷል — ይደሰቱ! 🚀",
    ],
}
HUMOR_INDEX = {}


def humor_line(user_id: int, lang: str) -> str:
    """A rotating light line, so the same joke is not repeated
    every time."""
    lines = HUMOR_LINES.get(lang) or HUMOR_LINES["en"]
    idx = HUMOR_INDEX.get(user_id, 0)
    HUMOR_INDEX[user_id] = idx + 1
    return lines[idx % len(lines)]


# --- bare quantities, order-now, price/ban/public/terms/history ------
_BARE_QUANTITY_FILLERS = {"please", "pls", "just", "only", "thanks", "thank", "you"}


def bare_quantity(text: str):
    """A message that is essentially just a number ('1000 please',
    '200') as a quantity, or None. Quantities must be multiples of
    10, so a bare service ID (6139) never counts."""
    words = [
        w.strip(".,!?") for w in normalize_text(text or "").split()
    ]
    words = [w for w in words if w not in _BARE_QUANTITY_FILLERS]
    if len(words) == 1 and re.fullmatch(r"\d[\d,]*", words[0]):
        try:
            value = int(words[0].replace(",", ""))
        except ValueError:
            return None
        if 10 <= value <= 1000000 and value % 10 == 0:
            return value
    return None


_ORDER_NOW_PHRASES = (
    "order now", "order it now", "place it now", "place the order now",
    "just place it", "do it now", "order right now",
    "place it right now", "now please", "right now",
)


def is_order_now(text: str) -> bool:
    """True when the user explicitly says to order NOW (owner
    override, 13 Nov 2026): the order is placed at once, no Confirm
    card. A vague 'I want views' is never order-now."""
    s = " ".join((text or "").strip().lower().split())
    return any(p in s for p in _ORDER_NOW_PHRASES)


# Order verbs the local order guard recognises (round 7,
# 13 Nov 2026). Amharic እፈል- covers እፈልጋለሁ/እፈልግ/እፈልጋለች
# ("I want"); ትዕዛዝ/ይዘዝ is "order", ይግዝ is "buy". "please"
# is deliberately NOT here: "please, is this link safe?" is a
# question, not an order.
_ORDER_REQUEST_VERBS = (
    "want", "order", "buy", "get me", "give me", "need",
    "እፈል", "ትዕዛዝ", "ይዘዝ", "ይግዝ",
)
# Intent types the order guard may override: a message that pastes
# a link and names a metric with an order verb IS an order, even
# when the AI called it one of these. Anything more specific
# (usual, batch, recurring, deposit, ...) is left alone.
_ORDER_OVERRIDABLE = (
    "safety", "paxyo_info", "unclear", "off_topic", "goal",
    "content_help", "support_issue", "greeting", "help",
    "refund_policy", "geo_target", "free_sample", "price_pushback",
    "discount",
)


def is_order_request(text: str) -> bool:
    """True when the message itself is an order: it pastes a link (or
    an @handle) and names a metric or platform with an order verb
    ("I want TikTok followers for <link>"). Used to rescue orders
    the AI misclassified (round 7, 13 Nov 2026: that message came
    back as "safety", so the link-mismatch answer never fired in
    that turn and the followers draft leaked into the next one).
    Genuine questions are untouched: a price, ban, payment or
    public-account question is answered by its own check, and a
    message with no order verb ("is this link safe?") is not an
    order."""
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return False
    if (is_price_question(text) or is_ban_question(text)
            or is_pay_methods_question(text) or is_public_question(text)):
        return False
    links = extract_links(text)
    has_target = bool(links) or any(
        tok.startswith("@") and tok.lower() != "@paxyo_bot"
        for tok in s.split()
    )
    if not has_target:
        return False
    if kind_from_text(text) is None and not any(
        p in s.split() for p in _PLATFORMS
    ):
        return False
    return any(v in s for v in _ORDER_REQUEST_VERBS)


def _empty_intent(intent_type, **fields):
    out = {
        "intent": intent_type, "platform": None, "service_hint": None,
        "service_id": None, "link": None, "quantity": None,
        "interval_minutes": None, "amount": None, "method": None,
        "phone": None, "quantity_multiplier": None, "orders": None,
        "split": None,
    }
    out.update(fields)
    return out


def reply_or_bare_intent(text: str, quoted_text, user_id: int):
    """An intent from a bare-quantity answer or a reply/quote, or
    None. Runs before the classifier, so '1000 please' after 'How
    many?' and '1000' replied TO the bot's 'How many?' message both
    complete the order instead of being misread as a service search.
    A reply only counts when it answers the bot's quantity question;
    a plain message only counts while an order is waiting for its
    quantity. Never fires while a deposit amount or split links are
    awaited."""
    if user_id in DEPOSIT_DRAFT and not (PARTIAL.get(user_id) or {}).get("link"):
        return None
    if user_id in SPLIT_DRAFT:
        return None
    qty = bare_quantity(text)
    if qty is None:
        return None
    stored = PARTIAL.get(user_id) or {}
    if quoted_text is not None:
        q = " ".join(str(quoted_text).strip().lower().split())
        if ("how many" in q or "quantity" in q) and (
            stored.get("link") or stored.get("platform") or stored.get("service_hint")
        ):
            return _empty_intent("order", quantity=qty)
        return None
    if stored.get("quantity"):
        return None
    if stored.get("link") or stored.get("platform") or stored.get("service_hint"):
        return _empty_intent("order", quantity=qty)
    return None


# The link/quantity of the order a user just cancelled (round 6,
# 13 Nov 2026). The order flow drops exactly these values if the
# AI returns them from conversation history after the cancel — and
# only these values. The record clears as soon as the user gives a
# fresh link, or an order is placed (see complete_order).
CANCELLED_DRAFT = {}


def clear_order_state(user_id: int, cancelled=None):
    """Drop everything a cancelled order left behind (round 6,
    13 Nov 2026): the draft being built, any Confirm card still open
    for this user, the budget choice and any fastest-fallback token.
    A fresh order after a cancel starts from scratch — it must not
    auto-show the cancelled order's link and quantity. (The last
    PLACED order is not touched: LAST_ORDER and the server's order
    history still remember it, so "the usual" keeps working.)

    `cancelled` is the Confirm card that was cancelled (its link and
    quantity): it is remembered in CANCELLED_DRAFT so the order flow
    can drop exactly those values if the AI returns them from
    conversation history after the cancel."""
    PARTIAL.pop(user_id, None)
    BUDGET_OPTIONS.pop(user_id, None)
    for token in [
        t for t, fb in FASTEST_FALLBACK.items()
        if fb.get("user_id") == user_id
    ]:
        FASTEST_FALLBACK.pop(token, None)
    for cid in [
        c for c, p in PENDING.items() if p.get("user_id") == user_id
    ]:
        PENDING.pop(cid, None)
    if cancelled:
        _record = {
            k: cancelled.get(k)
            for k in ("link", "quantity")
            if cancelled.get(k) is not None
        }
        if _record:
            CANCELLED_DRAFT[user_id] = _record


_USUAL_PHRASES = (
    "the usual", "same as yesterday", "same as last", "as usual",
    "my usual",
)


def is_usual_request(text: str) -> bool:
    """True when the user wants their usual order again ('same like
    as usual please order 1k views', 'give me the usual'). The AI
    sometimes reads it as a plain order and the flow then asks for
    the link, even though the last order's link is known — so the
    phrasing is caught locally, before the classifier."""
    s = " ".join((text or "").strip().lower().split())
    return any(p in s for p in _USUAL_PHRASES)


def quantity_from_text(text: str):
    """First number in the message that is a valid quantity (a
    multiple of 10, 10..1,000,000), or None. The text is already
    normalised, so '1k' reads as 1000."""
    for m in re.finditer(r"\d[\d,]*", text or ""):
        try:
            value = int(m.group(0).replace(",", ""))
        except ValueError:
            continue
        if 10 <= value <= 1000000 and value % 10 == 0:
            return value
    return None


def quantity_before_metric(text: str):
    """Quantity written right before the metric it buys ("200 TikTok
    views", "200 የቲክቶክ እይታዎች"), or None. Only a number
    immediately before the metric counts, so a stray number
    elsewhere in the message ("my balance is 100") is never read as
    the quantity. (Round 7, 13 Nov 2026: "please order now 200
    TikTok views" asked "How many?" because the AI did not return
    the quantity.)"""
    s = text or ""
    am_words = "|".join(
        sorted(_AMHARIC_METRICS, key=len, reverse=True)
    )
    pattern = (
        r"(\d[\d,]*)\s+(?:[^\s]+\s+){0,2}?"
        r"(views?|followers?|likes?|comments?|subscribers?|members?|shares?"
        r"|reactions?"
        r"|" + am_words + r")\b"
    )
    for m in re.finditer(pattern, s, flags=re.IGNORECASE):
        try:
            value = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if 10 <= value <= 1000000 and value % 10 == 0:
            return value
    return None


# Pay phrasings only (round 6, 13 Nov 2026): "how do I add
# money?" / "how do I deposit?" are deposit-flow entries — the
# existing tests pin them to asking for the amount — so they are
# NOT methods questions and must not be swallowed by this guard.
_PAY_METHODS_PHRASES = (
    "how can i pay", "how do i pay", "how to pay",
    "how can i pay you",
    "how do you accept payment", "how do you take payment",
    "what payment methods", "which payment methods", "payment methods",
)


def is_pay_methods_question(text: str) -> bool:
    """True for a bare how-to-pay question ('how can I pay?'). A
    message that already carries an amount, a method or a phone is
    a deposit in progress, not a question — the deposit flow keeps
    it instead of answering with the methods list."""
    s = " ".join((text or "").strip().lower().split())
    if not any(p in s for p in _PAY_METHODS_PHRASES):
        return False
    if parse_money_amount(s) is not None or parse_deposit_amount(s) is not None:
        return False
    if normalize_method(text) is not None or normalize_phone(text) is not None:
        return False
    return True


_VIDEO_LINK_MARKERS = (
    "/video/", "vt.tiktok.com", "/p/", "/reel", "/shorts/",
    "watch", "youtu.be", "/clip/",
)
_PROFILE_METRICS = ("followers", "members", "subscribers")
_CONTENT_METRICS = ("views", "likes", "comments", "shares")


def link_content_kind(link: str):
    """'video' when the link points at a single post/video,
    'profile' when it points at an account/channel, None when it
    cannot be told (a short link with no recognisable shape)."""
    low = str(link or "").strip().lower()
    if not low:
        return None
    if any(m in low for m in _VIDEO_LINK_MARKERS):
        return "video"
    if "t.me/" in low:
        # t.me/name/123 is a post; t.me/name is a channel.
        tail = low.split("t.me/", 1)[1].strip("/")
        return "video" if "/" in tail and tail.rsplit("/", 1)[1].isdigit() else "profile"
    if any(d in low for d in (
        "tiktok.com", "instagram.com", "youtube.com", "youtu.be",
        "facebook.com", "fb.com", "x.com", "twitter.com",
    )):
        return "profile"
    if low.startswith("@"):
        return "profile"
    return None


def metric_content_kind(service_hint: str):
    """The kind of link a metric needs: 'profile' for followers /
    members / subscribers, 'video' for views / likes / comments /
    shares, None when the hint names no metric."""
    words = (service_hint or "").lower().split()
    if any(w in words for w in _PROFILE_METRICS):
        return "profile"
    if any(w in words for w in _CONTENT_METRICS):
        return "video"
    return None


def _same_link(a: str, b: str) -> bool:
    """Same link up to scheme, www, query string and a trailing
    slash — the AI sometimes normalises the link it returns."""
    def _norm(u):
        u = str(u or "").strip().lower()
        u = re.sub(r"^https?://", "", u)
        u = re.sub(r"^www\.", "", u)
        return u.split("?")[0].rstrip("/")
    return bool(a) and bool(b) and _norm(a) == _norm(b)


def _link_grounded_in_text(text: str, link) -> bool:
    """True when the link the intent carries is actually in this
    message (pasted just now), not pulled from an older turn."""
    if not link:
        return False
    for candidate in extract_links(text):
        if _same_link(candidate, link):
            return True
    # A handle target (@user) is grounded by an @-mention in the text.
    if str(link).startswith("@"):
        return any(tok.startswith("@") for tok in (text or "").split())
    return False


def _quantity_grounded_in_text(text: str, quantity) -> bool:
    """True when the quantity the intent carries is a number in this
    message (the text is already normalised, so '1k' reads as 1000)."""
    try:
        wanted = int(quantity)
    except (TypeError, ValueError):
        return False
    for m in re.finditer(r"\d[\d,]*", text or ""):
        try:
            if int(m.group(0).replace(",", "")) == wanted:
                return True
        except ValueError:
            continue
    return False


def is_price_question(text: str) -> bool:
    """True when the user asks the price of a service ('how much are
    tiktok views?', "what's the price of 1000 views?"). A budget
    ('how much views can 10 br get me') carries a currency amount
    and is not a price question; neither is a balance or a deposit
    question. A pasted link is not a price question only when the
    message also has an order verb ("I want 1000 views for
    <link>") — a link with a bare price question ("how much for
    1000 views on this <link>?") still is one. Shapes the owner
    hit live (14 Nov 2026): "what's the rate", "how much for
    1000" (no platform named), "how much is it", and Amharic
    (ዋጋ is price, ስንት is how much) when the translate bridge
    fails and the Ge'ez text reaches this detector unchanged."""
    s = " ".join(normalize_text(text or "").split())
    if extract_links(text) and any(
        v in s for v in _ORDER_REQUEST_VERBS
    ):
        return False
    if parse_money_amount(s) is not None:
        return False
    if "deposit" in s or "balance" in s:
        return False
    if "price" in s or "cost" in s:
        return True
    if any(w in s.split() for w in ("rate", "rates", "pricing", "charge", "charges")):
        return True
    if "ዋጋ" in s:
        return True
    if "ስንት" in s and (
        kind_from_text(text) is not None
        or any(p in s.split() for p in _PLATFORMS)
    ):
        return True
    if "how much" in s and (
        kind_from_text(s) is not None
        or any(p in s.split() for p in _PLATFORMS)
        or re.search(r"\d", s) is not None
        # Word-boundary match: "how much is it?" ends in "it?",
        # and a split() comparison ("it" != "it?") misses it.
        or re.search(r"\b(it|this|that|one|them)\b", s) is not None
    ):
        return True
    return False


def _service_price_line(service, quantity, lang: str) -> str:
    """The deterministic price line for one service, straight from
    the catalogue: "Thumbs up 👍: 5.46 ETB for 1,000 (5.46 ETB per
    1000)." when a quantity was asked for, else the per-1000 rate."""
    rate = float(service.get("rate_etb_per_1000", 0) or 0)
    name = short_service_name(service.get("name"))
    if quantity is not None:
        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            qty = None
        if qty:
            return t(
                "price_total", lang, service=name, quantity=f"{qty:,}",
                rate=format_money(rate),
                total=format_money(estimated_total_etb(rate, qty)),
            )
    return t(
        "price_per_1000", lang, service=name, rate=format_money(rate)
    )


async def _price_line(user_id: int, text: str, platform, hint, quantity,
                      lang: str, reaction_emoji=None, services=None):
    """The deterministic price line for an identified service, straight
    from the catalogue (rate x420 ETB): "Thumbs up 👍: 5.46 ETB for
    1,000 (5.46 ETB per 1000)." when a quantity was asked for, else
    the per-1000 rate. Returns (line, platform, hint) — line is None
    when no service can be named, and platform/hint are the values
    actually used, after falling back to the order in progress and
    then to the message itself. Short service names only, like
    everywhere else. The caller decides what None means:
    price_answer_text asks which service; the link-ask safety net
    just skips the line."""
    platform = (platform or "").strip().lower() or None
    if not platform and not hint:
        platform, hint = _conversation_context(user_id)
    if not platform and hint:
        # A price question that names a metric but no platform
        # ("how much are the views?") is about the order being
        # built, not the fastest views service on any platform —
        # take the platform from the pending order or the draft.
        _ctx_platform, _ctx_hint = _conversation_context(user_id)
        if _ctx_platform:
            platform = _ctx_platform
    if not platform and not hint:
        words = set(re.findall(r"[a-z]+", normalize_text(text).lower()))
        platform = next((p for p in _PLATFORMS if p in words), None)
        metric = kind_from_text(text)
        hint = " ".join(p for p in (platform, metric) if p) or None
    if not platform and not hint:
        return None, platform, hint
    if services is None:
        try:
            services = await paxyo.services()
        except Exception as exc:
            log.warning("price lookup failed: %s", exc)
            return None, platform, hint
    picks = pick_services(
        services, platform=platform, service_hint=hint, limit=100,
        reaction_emoji=reaction_emoji,
    )
    if not picks:
        return None, platform, hint
    return _service_price_line(picks[0], quantity, lang), platform, hint


async def price_answer_text(user_id: int, text: str, intent: dict, lang: str):
    """The price, straight from the catalogue: ETB per 1000, and the
    total when a quantity was asked for. Never asks for the link
    first. Always answers a price question with a price line, the cheapest price for the platform/metric, or
    the ask-which-service line — never None once the catalogue is
    fetched (owner, 14 Nov 2026: a price question that fell
    through to a free AI reply got no price at all, because the
    free-answer prompts forbid quoting prices). None only when the
    catalogue itself cannot be fetched, so the caller falls through
    to the classifier and retries — the flaky-lookup tests pin the
    fetch count, so this fetches exactly once per call."""
    platform = (intent.get("platform") or "").strip().lower() or None
    hint = intent.get("service_hint")
    quantity = intent.get("quantity")
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("price lookup failed: %s", exc)
        return None
    line, platform, hint = await _price_line(
        user_id, text, platform, hint, quantity, lang,
        reaction_emoji=reaction_emoji(text), services=services,
    )
    if line is None and (platform or hint):
        # No fastest pick for this platform/metric: offer the
        # cheapest price for it instead of silence.
        cheapest = cheapest_service(
            services, platform=platform, service_hint=hint
        )
        if cheapest is not None:
            line = _service_price_line(cheapest, quantity, lang)
    if line is not None:
        if quantity is not None:
            try:
                qty = int(quantity)
            except (TypeError, ValueError):
                qty = None
            if qty:
                _remember_price_question(user_id, platform, hint, qty, text)
        return line
    return t("price_ask_service", lang)


def _remember_price_question(user_id: int, platform, hint, qty, text):
    """Remember what a price question asked about, in the draft
    (round 8.1, 14 Nov 2026): "how much 1k" names the quantity
    for the order being built, so the next turn — and the "do you
    understand" restatement — must not ask "how many" again. Only
    when no Confirm card is pending and the draft has no link (a
    price question never hijacks an order already being built). A
    different metric replaces a link-less draft, the same as a new
    order does (round 7)."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        return
    stored = PARTIAL.get(user_id) or {}
    if stored.get("link"):
        return
    stored_metric = _primary_metric(kind_from_text(stored.get("service_hint") or ""))
    new_metric = _primary_metric(kind_from_text(hint or ""))
    if not stored or stored_metric is None or stored_metric == new_metric:
        merged = {k: v for k, v in stored.items() if v is not None}
        merged.update({
            "platform": platform, "service_hint": hint, "quantity": qty,
            "reaction_emoji": reaction_emoji(text) or stored.get("reaction_emoji"),
        })
        PARTIAL[user_id] = {k: v for k, v in merged.items() if v is not None}
    else:
        PARTIAL[user_id] = {
            "platform": platform, "service_hint": hint, "quantity": qty,
            "reaction_emoji": reaction_emoji(text),
        }


def is_ban_question(text: str) -> bool:
    """True when the user asks about bans / shadowbans.

    English is matched on Latin words — but the detector also
    runs on the RAW text when the translate bridge is down
    (Gemini's free tier is 20/day, so an Amharic question often
    reaches this check untranslated), so Ge'ez and Oromo ban
    words are matched too. Live bug, 14 Nov 2026: the Amharic
    question "ተከታዮችን በመግዛት አካውንቴ ሊታገድ ይችላል?" got a
    free AI answer saying "no one can guarantee zero risk"
    instead of the deterministic NO — the detector saw no Latin
    ban word. The Ge'ez ban verb is ታገደ: "ሊታገድ" (may be
    banned), "ታገደ" (was banned), "ይታገዳል" (is being banned),
    "ታግዷል" (has been banned), "ታግደዋል" (have been banned),
    "እገዳ" (a ban) — the same root in Tigrinya. The stems are
    matched exactly ("ታገ" alone would also catch ታገሠ,
    patience), so every real inflection is listed. Oromo:
    "cufamuu" (to be closed/shut), "dhoowwaa" (prohibition)."""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    if (
        words & {"ban", "banned", "banning", "shadowban", "shadowbanned"}
        or ("shadow" in words and "ban" in words)
    ):
        return True
    geez = re.findall(r"[\u1200-\u137c]+", text or "")
    if any(
        part in word
        for word in geez
        for part in (
            "ታገድ", "ታገደ", "ታገዳ", "ታግዷ", "ታግደ", "እገዳ",
        )
    ):
        return True
    if any(
        word == "ባን" for word in geez
    ):
        return True
    if any(
        word.startswith(prefix)
        for word in words
        for prefix in ("cufam", "dhooww")
    ):
        return True
    return False


def is_public_question(text: str) -> bool:
    """True when the user asks whether their account must be public."""
    s = " ".join((text or "").strip().lower().split())
    return ("public" in s or "private" in s) and (
        "account" in s or "profile" in s or "need" in s or "must" in s
        or "have to" in s
    )


def is_history_question(text: str) -> bool:
    """True when the user asks what they talked about before."""
    s = " ".join((text or "").strip().lower().split())
    return any(p in s for p in (
        "what did i ask", "what did i say", "what did we talk about",
        "what was my last", "do you remember", "what did i order before",
        "what did i ask about before", "what did i talk about",
    ))


_QUESTION_OPENERS = (
    "how", "what", "where", "when", "why", "who", "whom", "whose",
    "which", "can", "could", "should", "would", "do", "does", "did",
    "is", "are", "was", "were", "will", "have", "has",
)


def is_question(text: str) -> bool:
    """True when the message is shaped like a question: it ends
    with '?' or opens with a question word. A question always
    gets a free AI answer (owner, 14 Nov 2026) — it is never
    steered away unanswered, however many turns it takes."""
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return False
    if s.endswith("?"):
        return True
    return s.split(" ", 1)[0] in _QUESTION_OPENERS


def is_comment_likes_question(text: str) -> bool:
    """True when the user asks what the bot needs for likes on a
    comment (owner, 14 Nov 2026): the link of the video/post the
    comment is on, plus either the comment's own link or the
    username. An actual order (a link is pasted) is never a
    question — the order flow keeps it."""
    if extract_links(text):
        return False
    s = " ".join((text or "").strip().lower().split())
    if "comment" not in s or "like" not in s:
        return False
    return (
        "how" in s or "what" in s or "need" in s or "do i" in s
        or "?" in (text or "")
    )


def is_telegram_post_link_question(text: str) -> bool:
    """True when the user asks how to get the link of a Telegram
    post (owner, 14 Nov 2026): "how do I get the link of a
    Telegram post?", "how to copy a telegram post link". A
    deterministic Paxyo fact — the AI kept getting the steps
    wrong ("click the post and click copy link" skips the share
    step; "right-click" is useless on a phone), so the answer is
    a template, never a free reply. A comment-link question
    ("link of a comment") is not a post-link question, and a
    channel-link question ("link of my channel") is not one
    either."""
    s = " ".join((text or "").strip().lower().split())
    has_telegram = (
        "telegram" in s or "ቴሌግራም" in s or " tg " in f" {s} "
    )
    has_link = "link" in s or "ሊንክ" in s
    has_post = "post" in s or "ፖስት" in s
    has_how = "how" in s.split() or "እንዴት" in s or "እንደምን" in s
    return has_telegram and has_link and has_post and has_how


async def speed_answer_text(user_id: int, text: str, intent: dict, lang: str):
    """A REAL delivery-time answer for a speed question (owner,
    13 Nov 2026): the pending Confirm card's service first (round
    4), else the fastest service for the platform+metric in the
    message, else the no-time line with the order-now nudge. The
    vague 'shown before you confirm / varies by service' line is
    never used."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        answer = pending_confirm_answer(pending.get("service"), "speed", lang)
        if answer is not None:
            return answer
    platform = (intent.get("platform") or "").strip().lower() or None
    hint = intent.get("service_hint")
    if not platform and not hint:
        platform, hint = _conversation_context(user_id)
    if not platform and not hint:
        words = set(re.findall(r"[a-z]+", normalize_text(text).lower()))
        platform = next((p for p in _PLATFORMS if p in words), None)
        metric = kind_from_text(text)
        hint = " ".join(p for p in (platform, metric) if p) or None
    if not platform and not hint:
        return t("speed_unknown", lang)
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("speed lookup failed: %s", exc)
        return t("speed_unknown", lang)
    picks = pick_services(
        services, platform=platform, service_hint=hint, limit=100,
        reaction_emoji=reaction_emoji(text),
    )
    if not picks:
        return t("speed_unknown", lang)
    service = picks[0]
    avg = service.get("average_time")
    if parse_average_time(avg) is not None:
        return t(
            "speed_answer", lang,
            service=short_service_name(service.get("name")), avg=avg,
        )
    return t("speed_unknown", lang)


_ORDER_STATUS_ICONS = {
    "completed": "✅", "pending": "⏳", "in_progress": "⏳",
    "processing": "⏳", "cancelled": "❌", "canceled": "❌",
    "refunded": "❌", "failed": "❌",
}


async def orders_history_text(user_id: int, lang: str) -> str:
    """The user's LAST 5 orders only (owner, 14 Nov 2026 — the
    20-row monospace table was ugly and confusing on a phone):
    one line per order — ID, short service name, quantity, status
    with an icon, total in ETB. Newest first. No extra fields,
    no long text, no monospace block that wraps badly."""
    try:
        orders = await paxyo.recent_orders(user_id, limit=5)
    except Exception as exc:
        log.warning("orders history failed: %s", exc)
        return t("not_understood", lang)
    if not orders:
        # The API has nothing, but this session placed an order
        # (tracked in memory): show its status line.
        return await last_order_status_text(user_id, lang)
    lines = [t("orders_history_title", lang)]
    for o in orders[:5]:
        status = str(o.get("status") or "?").strip().lower()
        icon = _ORDER_STATUS_ICONS.get(status, "ℹ️")
        name = short_service_name(o.get("service_name") or "") or f"service {o.get('service_id')}"
        lines.append(
            f"#{o.get('id') or o.get('order_id') or '?'} {name} "
            f"×{int(o.get('quantity') or 0)} — {icon} {status} — "
            f"{format_money(o.get('charge', 0) or 0)} ETB"
        )
    return "\n".join(lines)


def terms_answer(text: str, lang: str):
    """An answer from Paxyo's Terms & Conditions (paxyo-terms.md),
    or None when the message is not a terms question. Never invents
    a term: an uncovered terms question says so and offers support."""
    s = " ".join((text or "").strip().lower().split())
    about_terms = "term" in s or "condition" in s
    if any(p in s for p in ("show me the terms", "full terms", "read the terms", "terms and conditions", "terms & conditions")):
        return t("terms_full", lang)
    if "refund" in s or "money back" in s or "get my money back" in s:
        return t("terms_refund", lang)
    if "cancel" in s and any(p in s for p in ("after", "start", "processing", "placed", "begun")):
        return t("terms_cancel", lang)
    if any(p in s for p in ("privacy", "my data", "personal data", "sell my data")):
        return t("terms_privacy", lang)
    if any(p in s for p in ("suspend", "suspended", "terminat")):
        return t("terms_suspension", lang)
    if "public" in s and "account" in s:
        return t("public_answer", lang)
    if about_terms:
        return t("terms_not_covered", lang)
    return None


async def place_order_now(message, user_id: int, merged: dict, lang: str,
                          named_service_id=None, last_service_id=None,
                          note: str = None, show_full_name: bool = False) -> bool:
    """Place a fully-specified order at once, no Confirm card
    (owner override, 13 Nov 2026 — explicit 'order now' only).
    Returns True when the user got an answer (placed, or a plain
    failure line); False when nothing could be placed yet, so the
    caller falls through to the normal Confirm card. An ambiguous
    metric is never guessed: False, and the normal flow asks."""
    try:
        services = await paxyo.services()
    except Exception as exc:
        log.warning("order-now services failed: %s", exc)
        return False
    service = None
    if named_service_id is not None:
        service, svc_error = resolve_named_service(services, named_service_id)
        if svc_error is not None:
            return False
    if service is None:
        picks = pick_services(
            services, platform=merged.get("platform"),
            service_hint=merged.get("service_hint"),
            reaction_emoji=merged.get("reaction_emoji"),
        )
        if not picks:
            return False
        if not merged.get("service_hint"):
            metrics = []
            for pick in picks:
                hay = (str(pick.get("name") or "") + " " + str(pick.get("category") or "")).lower()
                found = next((m for m in _METRICS if m in hay), None)
                if found and found not in metrics:
                    metrics.append(found)
            if len(metrics) > 1:
                return False
        service = picks[0]
    error = validate_quantity(merged.get("quantity"), service)
    if error:
        return False
    quantity = int(merged["quantity"])
    total = estimated_total_etb(float(service.get("rate_etb_per_1000", 0)), quantity)
    pending = {
        "user_id": user_id, "service": service, "link": merged["link"],
        "quantity": quantity, "total": total,
        "full_name": show_full_name,
    }
    PARTIAL.pop(user_id, None)
    # A complete order was placed: the cancelled draft is history now.
    CANCELLED_DRAFT.pop(user_id, None)
    await send_order_result(message, lang, pending, user_id)
    return True


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


_LINK_RECALL_PHRASES = (
    "link of the last order", "link of my last order",
    "link of the previous order", "link of the latest order",
    "link of my order", "link of that order",
    "send me the link of", "what was the link of",
    "what is the link of", "give me the link of",
    "link for the last order", "link from my last order",
)


def is_link_recall_question(text: str) -> bool:
    """A request for the LINK of a past order (owner, 14 Nov
    2026) — \"please send me the link of the last order about
    the Telegram reaction\" — as opposed to a request for the
    link of the order being built. The \"link of\" phrasing is
    what separates the two: the order flow says \"send the link\"
    with no \"of\"."""
    s = " ".join((text or "").strip().lower().split())
    if "link" not in s:
        return False
    return any(p in s for p in _LINK_RECALL_PHRASES)


def _match_recall_order(orders, text):
    """The most recent order matching what the user named: the
    platform and the kind, when either is named. No type named
    means the single most recent order. Returns None when
    nothing matches."""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    platform = next(
        (p for p in _PLATFORMS if p in words), None
    )
    metric = kind_from_text(text)
    for order in orders:
        o_platform, _hint = _platform_hint_of_service(
            {"name": order.get("service_name") or ""}
        )
        o_kind = kind_from_text(order.get("service_name") or "")
        if platform is not None and o_platform != platform:
            continue
        if metric is not None and o_kind != metric:
            continue
        return order
    return None


def _recall_desc(text):
    """The words describing the order the user asked about
    (\"Telegram reactions \", \"Instagram followers \", or \"\"
    when no type was named), for the recall reply."""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    platform = next(
        (p for p in _PLATFORMS if p in words), None
    )
    metric = kind_from_text(text)
    parts = []
    if platform:
        parts.append(_PLATFORM_DISPLAY.get(platform, platform.title()))
    if metric:
        parts.append(metric)
    return (" ".join(parts) + " ") if parts else ""


async def link_recall_text(user_id: int, text: str, lang: str):
    """The link of a past order (owner, 14 Nov 2026). The API's
    GET /orders list DOES return the link for each order, so the
    bot answers with the actual link of the most recent matching
    order. When no order matches, or the order has no link
    saved, it says so honestly — it never invents a link."""
    try:
        orders = await paxyo.recent_orders(user_id, limit=5)
    except Exception as exc:
        log.warning("link recall recent_orders failed: %s", exc)
        return t("not_understood", lang)
    if not orders:
        return t("link_recall_none", lang)
    desc = _recall_desc(text)
    order = _match_recall_order(orders, text)
    if order is None:
        return t("link_recall_no_match", lang, desc=desc)
    link = (order.get("link") or "").strip()
    if not link:
        return t("link_recall_no_link", lang)
    return t("link_recall_found", lang, desc=desc, link=link)


# ------------------------------------------------- edge-case helpers ----
# Messy real-world inputs (owner spec, 13 Nov 2026): the helpers the
# new intent handlers share. All of them are pure except the ones
# that read the in-memory order state.

def confirm_card_text(lang: str, service, quantity, total, link,
                      note: str = None, full_name: bool = False) -> str:
    """The Confirm card for one order: service, quantity, link and
    total, always in that order, with an optional one-line note on
    top (a quantity change, a doubled usual, a link warning). The
    service name is SHORT by default (owner, 13 Nov 2026); the full
    long name is shown only when the user entered a service ID
    (full_name=True). A public-account reminder is always on the
    card: a private account can't receive the order."""
    name = (
        clean_service_name(service.get("name"))
        if full_name
        else short_service_name(service.get("name"))
    )
    lines = [t("confirm_title", lang), ""]
    if note:
        lines.append(note)
        lines.append("")
    lines.extend([
        f"{name} (#{service.get('service')})",
        f"⏱ {service.get('average_time') or '—'}",
        f"💰 {format_money(service.get('rate_etb_per_1000', 0))} ETB / 1000",
        f"🔢 {quantity}",
        f"🧾 {format_money(total)} ETB (estimated)",
        f"🔗 {link}",
        "",
        t("public_reminder", lang),
    ])
    return "\n".join(lines)


def pending_note(user_id: int, lang: str) -> str:
    """One line telling the user where their order stands, or "".

    A Confirm card waiting for Confirm is named first; otherwise a
    half-built order (what the bot already has). Used after an
    interruption (a question mid-flow) so the user is never left
    wondering whether their order survived it. Only a draft with a
    LINK counts as an order being built (owner, 14 Nov 2026): a
    link-less draft left by a price question ("how much 1k" stores
    platform + quantity) is not an order, and naming it on an info
    answer is a stray confusing line."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        return t(
            "pending_reminder", lang,
            service=short_service_name(pending["service"].get("name")),
            quantity=pending["quantity"],
        )
    partial = PARTIAL.get(user_id) or {}
    if not partial.get("link"):
        return ""
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


def _platform_hint_of_service(service):
    """(platform, service_hint) for a service dict, from its name and
    category: the platform word and the kind phrase ("tiktok comment
    likes", "tiktok views"). Word-based, so "x" never matches "max"."""
    hay = (
        str(service.get("name") or "") + " "
        + str(service.get("category") or "")
    ).lower()
    words = re.findall(r"[a-z]+", hay)
    platform = next((p for p in _PLATFORMS if p in words), None)
    kind = kind_from_text(hay)
    hint = " ".join(p for p in (platform, kind) if p) or None
    return platform, hint


def _conversation_context(user_id: int):
    """(platform, service_hint) of the order the user is talking
    about — the pending Confirm card first, then the order being
    built. Used when a message ("something cheaper", "how much can
    10 br get me") names no platform of its own: the cheapest reply
    stays on the platform and metric already in the conversation
    instead of wandering to another platform's cheapest service
    (13 Nov 2026 — a TikTok views chat got Twitter Tweet
    Statistics). Returns (None, None) when there is no context."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        return _platform_hint_of_service(pending.get("service") or {})
    partial = PARTIAL.get(user_id) or {}
    platform = (partial.get("platform") or "").strip().lower() or None
    hint = partial.get("service_hint")
    if platform or hint:
        return platform, hint
    return None, None


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
    # Next batch (14 Nov 2026): the owner asks about drops as
    # "fade" / "go away" / "vanish" too — same question.
    "fade", "go away", "vanish",
)


def _canonical_metric(word: str):
    """Plural metric in _METRICS for a singular/plural word, or None.

    "comment" -> "comments", "like" -> "likes", "view" -> "views",
    "follower" -> "followers", "subscriber" -> "subscribers",
    "share" -> "shares", "member" -> "members". Already-plural words
    return themselves; anything else returns None.
    """
    w = (word or "").strip().lower()
    for m in _METRICS:
        if w == m or w == m[:-1]:
            return m
    return None


def _name_kinds(name: str):
    """Canonical kind words in a service name, as a set.

    Word-based, not substring: "preview" never counts as "views",
    and "comment" in "Tiktok Comment Likes" counts as "comments".
    """
    words = re.findall(r"[a-z]+", (name or "").lower())
    kinds = set()
    for w in words:
        metric = _canonical_metric(w)
        if metric is not None:
            kinds.add(metric)
    return kinds


def _hint_word_matches(word: str, hay: str) -> bool:
    """True when a hint word appears in a service name/category.

    Kind words match in singular or plural ("views" matches a
    service named "TikTok View", "comment" matches "Comments");
    other words must appear exactly as written.
    """
    if word in hay:
        return True
    if _canonical_metric(word) is not None:
        variant = word[:-1] if word.endswith("s") else word + "s"
        return variant in hay
    return False


# Amharic metric words (round 7, 13 Nov 2026): the bot reads
# Amharic orders, but kind_from_text only saw Latin words, so an
# Amharic views order inherited the previous turn's followers hint
# from the AI and got the wrong answer.
_AMHARIC_METRICS = {
    "እይታ": "views", "እይታዎች": "views",
    "ተከታይ": "followers", "ተከታዮች": "followers",
    "ላይክ": "likes", "ላይኮች": "likes",
    "አስተያየት": "comments", "አስተያየቶች": "comments",
    "ኮሜንት": "comments", "ኮሜንቶች": "comments",
    "ሰብስክራይበር": "subscribers", "ሰብስክራይበሮች": "subscribers",
    "ሼር": "shares", "አባል": "members", "አባላት": "members",
}


def kind_from_text(text: str):
    """The service kind the message asks for, or None.

    "comment likes" when the message asks for likes on a comment
    ("likes for my comment", "like my comment"); "comments" for a
    comments request ("comments on my video", "tiktok comment");
    otherwise the first metric word in message order ("views",
    "likes", "followers", ...). Singular and plural count the same,
    so "tiktok comment" and "tiktok comments" are the same kind.
    Amharic metric words count the same way ("እይታዎች" is views).
    """
    words = re.findall(r"[a-z]+", (text or "").lower())
    word_set = set(words)
    am_words = re.findall(r"[\u1200-\u137c]+", text or "")
    am_metrics = [
        _AMHARIC_METRICS[w] for w in am_words if w in _AMHARIC_METRICS
    ]
    if "comment" in word_set and ("like" in word_set or "likes" in word_set):
        return "comment likes"
    if "comments" in am_metrics and "likes" in am_metrics:
        return "comment likes"
    for w in words:
        metric = _canonical_metric(w)
        if metric is not None:
            return metric
    if am_metrics:
        return am_metrics[0]
    # An emoji can carry the metric on its own (round 8, 14 Nov
    # 2026): "👍" means the thumbs-up reaction, "👀" means views.
    # It is a fallback only — a word the user typed wins over it.
    if reaction_emoji(text) is not None:
        return "reactions"
    if "👀" in (text or ""):
        return "views"
    return None


_PLATFORM_DISPLAY = {
    "telegram": "Telegram", "instagram": "Instagram",
    "tiktok": "TikTok", "youtube": "YouTube",
    "facebook": "Facebook", "x": "X",
}


def ask_link_text(platform, service_hint, lang):
    """The link question for the order being built (owner, 14 Nov
    2026): specific to what is being ordered — followers get the
    profile link naming the platform, video views the video link,
    Telegram post interaction the Telegram post link, likes the
    post/video to like, comments the post/video to comment on,
    comment likes the existing two-thing question. The bare
    generic ask_link is used only when the order type is
    genuinely unknown."""
    metric = kind_from_text(service_hint or "")
    platform = (platform or "").strip().lower() or None
    disp = _PLATFORM_DISPLAY.get(
        platform or "", (platform or "").title()
    )
    if metric == "followers" and platform:
        return t("ask_link_profile", lang, platform=disp)
    if metric == "views":
        if platform == "telegram":
            return t("ask_link_post", lang, platform=disp)
        return t("ask_link_video", lang)
    if metric == "reactions":
        if platform:
            return t("ask_link_post", lang, platform=disp)
        return t("ask_link_post_generic", lang)
    if metric == "likes":
        return t("ask_link_like", lang)
    if metric == "comments":
        return t("ask_link_comment", lang)
    if metric == "comment likes":
        return t("comment_likes_need", lang)
    if metric == "members":
        return t("ask_link_group", lang)
    if metric == "subscribers":
        return t("ask_link_channel", lang)
    if metric == "shares":
        return t("ask_link_share", lang)
    return t("ask_link", lang)


# ------------------------------------------------- prompt shrink -------
# Prompt shrink (owner approved, 14 Nov 2026): every AI call used to
# send the whole SYSTEM_PROMPT (~2,460 tokens) plus up to 10 turns
# of history. The service catalogue was NEVER in the prompt — the
# bulk was the classifier instructions and the history — so the
# shrink is: a compact SYSTEM_PROMPT, the last 3 turns only, and a
# short list of matching services, but only when the message names
# both a platform and a metric. The full catalogue is never pasted
# into a prompt (7,176 services would be ~100k tokens); the
# deterministic code (pick_services, price) still works from the
# full catalogue, exactly as before.
PROMPT_SERVICES_LIMIT = 30

_PLATFORM_WORDS = {
    "instagram": "instagram", "insta": "instagram",
    "tiktok": "tiktok", "telegram": "telegram", "tg": "telegram",
    "youtube": "youtube", "yt": "youtube",
    "facebook": "facebook", "fb": "facebook",
    "twitter": "x",
}


def detect_platform_metric(text):
    """(platform, metric) the message asks for, deterministically —
    words and links only, never the AI. Platform from a platform
    word ("tiktok", "telegram", ...) or a link's domain; metric
    from kind_from_text (words, Amharic words, or a reaction emoji).
    Returns (None, None) when neither can be read — the caller then
    sends no services section and the deterministic code still
    works from the full catalogue."""
    norm = normalize_text(text or "")
    words = set(re.findall(r"[a-z]+", norm.lower()))
    platform = None
    for word, plat in _PLATFORM_WORDS.items():
        if word in words:
            platform = plat
            break
    if platform is None:
        for token in re.findall(r"https?://\S+|t\.me/\S+", norm):
            platform = platform_from_link(token)
            if platform:
                break
    if platform is None and "x.com" in norm.lower():
        platform = "x"
    metric = kind_from_text(norm)
    return platform, metric


def services_for_prompt(services, platform=None, metric=None,
                        limit=PROMPT_SERVICES_LIMIT, reaction_emoji=None):
    """Services to show the AI for this message: the matching ones
    only (same matching as pick_services — fastest first, inactive
    and blacklisted excluded, reactions limited to the emoji's
    single-post family). When platform or metric is unknown, returns
    the FULL catalogue unchanged: the caller must then NOT paste it
    into the prompt — it omits the section, and the deterministic
    code (pick_services, price) still works from the full catalogue,
    exactly as today."""
    if not platform or not metric:
        return list(services or [])
    hint = " ".join(p for p in (platform, metric) if p)
    return pick_services(
        services or [], platform=platform, service_hint=hint,
        limit=limit, reaction_emoji=reaction_emoji,
    )


def build_classify_prompt(text, services=None, user_id=None,
                          max_history=3):
    """The prompt extract_intent sends the AI: the message, the last
    few turns, and — only when the message names BOTH a platform and
    a metric — the matching services, at most 30, fastest first (id,
    short name, ETB per 1000, average time). When platform or metric
    cannot be read, there is no services section at all: the
    deterministic code still picks from the full catalogue, exactly
    as before. The full catalogue is never pasted into a prompt."""
    prompt = normalize_text(text)
    if user_id is not None:
        history = chat_history_lines(user_id, max_exchanges=max_history)
        if history:
            prompt += (
                "\n\nRecent conversation with this user (most recent last):\n"
                + "\n".join(history)
            )
    if services:
        platform, metric = detect_platform_metric(text)
        if platform and metric:
            shown = services_for_prompt(
                services, platform, metric,
                reaction_emoji=reaction_emoji(text),
            )
            if shown:
                lines = [
                    "Candidate services for this request "
                    "(id, name, ETB per 1000, average time):"
                ]
                for s in shown:
                    rate = s.get("rate_etb_per_1000")
                    try:
                        rate_text = format_money(rate)
                    except (TypeError, ValueError):
                        rate_text = "?"
                    avg = s.get("average_time") or "no time listed"
                    lines.append(
                        f"#{s.get('service')} "
                        f"{short_service_name(s.get('name'))} — "
                        f"{rate_text} ETB per 1000, {avg}"
                    )
                prompt += "\n\n" + "\n".join(lines)
    return prompt


def _primary_metric(kind: str):
    """The metric actually being bought in a kind string ("comment
    likes" -> "likes", "views" -> "views"), or None. Used to tell a
    new order (different metric) from a clarification of the same
    one ("likes for my comment" is still likes)."""
    if not kind:
        return None
    for w in reversed(str(kind).split()):
        metric = _canonical_metric(w)
        if metric is not None:
            return metric
    return None


def metric_from_text(text: str):
    """First metric kind in the message text, or None.

    The classifier sometimes drops the metric ("I want 1000 tiktok
    views" -> hint "tiktok" or none); the order flow reads the metric
    back from the user's own words instead of guessing. May return
    the two-word kind "comment likes" for likes on a comment.
    """
    return kind_from_text(text)


def pending_order_question(text: str, known_quantity=None):
    """'speed' / 'drop' / None: is this message a question about an
    order being built? A question carries no link and no
    quantity-like number, and is not a service choice ("use the
    fastest one"). A number that equals a quantity already known
    (the pending order's quantity, or the order being built) is a
    reference to that order, not new information, so it does not
    block the question: "how fast would those 1000 views arrive?"
    is a question about the 1000-view order."""
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
        if value == known_quantity:
            continue
        if 10 <= value <= 1000000 and value % 10 == 0:
            return None
    if any(p in s for p in _PENDING_DROP_PHRASES):
        return "drop"
    if any(p in s for p in _PENDING_SPEED_PHRASES):
        return "speed"
    return None


def pending_confirm_answer(service, question: str, lang: str):
    """Answer a question about an order awaiting Confirm, from the
    pending service itself. Returns the answer string, or None when
    there is no service to answer from. The order stays open — the
    caller does not cancel it. (13 Nov 2026: "how fast can you
    deliver it" after a Confirm card got the busy line, because the
    pending-question fix only covered a PARTIAL order waiting for a
    link.)"""
    if not service:
        return None
    name = short_service_name(service.get("name"))
    if question == "speed":
        avg = service.get("average_time")
        if parse_average_time(avg) is not None:
            return t("confirm_speed", lang, service=name, avg=avg)
        return t("confirm_speed_unknown", lang, service=name)
    if question == "drop":
        # Owner, 14 Nov 2026: Telegram reactions, Telegram views
        # and Facebook reactions never drop — say so instead of
        # the refill line. Any other service keeps the refill
        # answer below.
        kind = _service_never_drop_kind(service)
        if kind is not None:
            return t("never_drop", lang, service=kind)
    low = str(service.get("name") or "").lower()
    if "no refill" in low:
        refill = t("pending_no_refill", lang)
    elif "refill" in low:
        refill = t("pending_has_refill", lang)
    else:
        refill = t("pending_refill_unknown", lang)
    return t("confirm_drop", lang, service=name, refill=refill)


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
            f"🛑 {short_service_name(sched.get('service_name')) or sched.get('service_id')} "
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


# ------------------------------------------------- conversation (round 8) ---

# Round 8, 14 Nov 2026 — the bot talks like a normal AI mid-order.
# Live case: the user said "Do you understand what I said first"
# and the bot just repeated "Please send the link the order is for."
# A normal AI says what it understood first, then continues. These
# guards run BEFORE the order flow, so a question or a chatty
# message is never swallowed by the next order prompt. They never
# touch the draft or a pending Confirm card — the order survives
# the chat, and the next order message picks it up where it was.

_CONFIRM_UNDERSTANDING_PHRASES = (
    "do you understand", "did you understand", "do you get it",
    "did you get it", "did you get that", "do you know what i mean",
    "do you know what i want", "do you understand what i said",
    "do you understand me", "did you understand me",
    "what did i say", "what did i just say", "what did i tell you",
    "are you following", "are you listening", "did you hear me",
    "do you follow", "did you get what i said",
    # Amharic equivalents (fidels): "did you understand",
    # "what did I say".
    "ገባህ", "ገብቶሃል", "ተረድተሃል", "ተረድተሺ", "ምን አልኩ",
)

_CONVERSATION_QUESTION_PHRASES = (
    "what do you mean", "what did you mean", "what do u mean", "wdym",
    "why are you asking", "why do you ask", "why are you asking that",
    "why do you need", "why do you need that", "why are you asking me",
    "what are you asking", "what do you want to know",
    "ምን ማለት", "ለምን ጠየቅ", "እያዳመጥክ",
)

# Chatty messages that are not orders: laughter, thanks, feelings,
# small talk, opinions ("do you think ..."). Single words only
# count in a short message, so "great, send me the link" still
# goes to the order flow.
_FREE_CHAT_PHRASES = (
    "haha", "lol", "lmao", "hehe", "i'm tired", "i am tired",
    "i'm bored", "i am bored", "i'm happy", "i am happy",
    "i'm sad", "i am sad", "i feel", "how are you", "how r you",
    "what's up", "whats up", "good morning", "good afternoon",
    "good evening", "do you think", "what do you think",
    "thank you", "thank u",
)
_FREE_CHAT_WORDS = {
    "nice", "cool", "great", "awesome", "thanks", "thx", "wow", "lovely",
}

_PLATFORM_DISPLAY = {
    "tiktok": "TikTok", "instagram": "Instagram", "telegram": "Telegram",
    "youtube": "YouTube", "facebook": "Facebook", "x": "X",
}


def is_confirm_understanding(text: str) -> bool:
    """True when the user asks whether the bot understood what they
    said ("do you understand", "did you get that", "what did I
    say", "are you listening" — English and Amharic)."""
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return False
    return any(p in s for p in _CONFIRM_UNDERSTANDING_PHRASES)


def is_conversation_question(text: str, user_id=None) -> bool:
    """True when the user asks about the conversation itself mid-order
    ("what do you mean", "why are you asking that"). A bare "what?"
    or "huh?" counts only while an order is being built — otherwise
    it is just confusion with nothing to explain."""
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return False
    if any(p in s for p in _CONVERSATION_QUESTION_PHRASES):
        return True
    if s in ("what?", "what", "huh?", "huh", "??", "???", "what??", "huh??"):
        if user_id is None:
            return False
        _cid, pending = pending_for_user(user_id)
        return pending is not None or bool(PARTIAL.get(user_id))
    return False


def is_free_chat(text: str) -> bool:
    """True when the message is chat, not an order: a greeting, small
    talk, a comment, a feeling, an opinion, a joke. The caller must
    have already ruled out order details (link, quantity, service
    ID, deposit fields) — this only reads the chatty markers."""
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return False
    if any(p in s for p in _FREE_CHAT_PHRASES):
        return True
    if any(emoji in s for emoji in _CHAT_EMOJI):
        return True
    words = set(re.findall(r"[a-z]+", s))
    if words & _FREE_CHAT_WORDS and len(words) <= 4:
        return True
    return False


def _describe_hint(hint: str, platform: str, user_id: int, text=None) -> str:
    """Short plain description of an order being built, for
    restatements: "👍 reactions for your Telegram channel post",
    "TikTok views", "Instagram followers". The reaction emoji comes
    from the message itself, else from the user's recent messages."""
    h = (hint or "").strip().lower()
    p = (platform or "").strip().lower()
    if "reaction" in h:
        emoji = reaction_emoji(text) if text else None
        if emoji is None:
            load_chat_history()
            for entry in reversed(CHAT_HISTORY.get(int(user_id), [])[-5:]):
                emoji = reaction_emoji(entry.get("user", ""))
                if emoji is not None:
                    break
        label = f"{emoji} reactions" if emoji else "reactions"
        if p == "telegram" or "telegram" in h:
            return f"{label} for your Telegram channel post"
        if p:
            return f"{label} for your {p} post"
        return label
    if h:
        words = h.split()
        if words and words[0] in _PLATFORM_DISPLAY:
            words[0] = _PLATFORM_DISPLAY[words[0]]
            desc = " ".join(words)
        elif p and p not in h:
            desc = f"{_PLATFORM_DISPLAY.get(p, p.capitalize())} {h}"
        else:
            desc = h[:1].upper() + h[1:]
        return desc
    if p:
        return _PLATFORM_DISPLAY.get(p, p.capitalize())
    return ""


def _recent_quantity(user_id: int, kind):
    """The quantity the user gave for this metric in their last 3
    chat messages (round 8.1, 14 Nov 2026): "I want 👍 reaction
    for my telegram channel post how much 1k" names 1,000, so a
    later "do you understand what I said first" must restate the
    1,000 and never ask "how many" again. The metric must match —
    a quantity given for followers does not carry into a views
    order. A quantity in a message naming a different metric is
    ignored, and the search stops at the newest matching one."""
    load_chat_history()
    entries = CHAT_HISTORY.get(int(user_id), [])
    user_texts = [e.get("user", "") for e in entries if e.get("user")]
    wanted = _primary_metric(kind)
    for text in reversed(user_texts[-3:]):
        text_kind = kind_from_text(text)
        if wanted is not None and text_kind is not None:
            if _primary_metric(text_kind) != wanted:
                continue
        # The text is normalised first: quantity_from_text reads
        # "1k" only after normalisation expands it to 1000.
        qty = quantity_from_text(normalize_text(text))
        if qty:
            return qty
    return None


def _order_context_summary(user_id: int):
    """What the user is talking about: the pending Confirm card
    first, then the draft being built, then the last thing they
    asked about in chat history. Returns {"desc", "quantity",
    "link", "missing", "pending"} or None when there is nothing
    to restate."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        service = pending.get("service") or {}
        name = short_service_name(service.get("name")) or "your order"
        qty = pending.get("quantity")
        desc = f"{name}, {qty:,}" if qty else name
        return {
            "desc": desc, "quantity": qty, "link": pending.get("link"),
            "missing": [], "pending": True,
        }
    partial = PARTIAL.get(user_id) or {}
    hint = (partial.get("service_hint") or "").strip()
    platform = (partial.get("platform") or "").strip()
    if hint or platform:
        desc = _describe_hint(hint, platform, user_id)
        missing = []
        if not partial.get("link"):
            missing.append("link")
        if not partial.get("quantity"):
            missing.append("quantity")
        return {
            "desc": desc, "quantity": partial.get("quantity"),
            "link": partial.get("link"), "missing": missing,
            "pending": False,
        }
    load_chat_history()
    entries = CHAT_HISTORY.get(int(user_id), [])
    user_texts = [e.get("user", "") for e in entries if e.get("user")]
    for text in reversed(user_texts[-3:]):
        kind = kind_from_text(text)
        qty = quantity_from_text(normalize_text(text))
        words = set(re.findall(r"[a-z]+", (text or "").lower()))
        platform = next((p for p in _PLATFORMS if p in words), None)
        if kind or platform or qty:
            desc = _describe_hint(kind or "", platform or "", user_id, text)
            links = extract_links(text)
            # The quantity may live in an earlier message than the
            # one being restated (the price question named 1,000;
            # "do you understand" names none) — look back at the
            # same metric instead of asking "how many" again.
            if not qty:
                qty = _recent_quantity(user_id, kind)
            missing = []
            if not links:
                missing.append("link")
            if not qty:
                missing.append("quantity")
            return {
                "desc": desc, "quantity": qty,
                "link": links[0] if links else None,
                "missing": missing,
                "pending": False,
            }
    return None


def understanding_text(user_id: int, lang: str) -> str:
    """The restatement for "do you understand": what the bot
    understood from the conversation so far, and what is still
    missing. Never just the link prompt again."""
    summary = _order_context_summary(user_id)
    if summary is None:
        return t("understand_none", lang)
    if summary.get("pending"):
        return t("understand_pending", lang, desc=summary["desc"])
    desc = summary["desc"]
    qty = summary.get("quantity")
    if qty and f"{qty:,}" not in desc:
        desc = f"{desc}, {qty:,}"
    missing = summary.get("missing") or []
    if not missing:
        return t("understand_partial", lang, desc=desc, missing="")
    if missing == ["link"]:
        missing_text = t("missing_link", lang)
    elif missing == ["quantity"]:
        missing_text = t("missing_quantity", lang)
    else:
        missing_text = t("missing_link_quantity", lang)
    return t("understand_partial", lang, desc=desc, missing=missing_text)


def explain_asking_text(user_id: int, lang: str) -> str:
    """The answer for "what do you mean / why are you asking":
    what the bot needs and why, from the order being built. Falls
    back to quoting the bot's last message."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        service = pending.get("service") or {}
        name = short_service_name(service.get("name")) or "your order"
        qty = pending.get("quantity")
        desc = f"{name}, {qty:,}" if qty else name
        return t("mean_pending", lang, desc=desc)
    if DEPOSIT_DRAFT.get(user_id):
        return t("mean_deposit", lang)
    partial = PARTIAL.get(user_id) or {}
    if partial:
        desc = _describe_hint(
            partial.get("service_hint") or "",
            partial.get("platform") or "", user_id,
        ) or "your order"
        if not partial.get("link"):
            return t("mean_link", lang, desc=desc)
        if not partial.get("quantity"):
            return t("mean_quantity", lang, desc=desc)
    load_chat_history()
    for entry in reversed(CHAT_HISTORY.get(int(user_id), [])):
        last = entry.get("bot", "")
        if last:
            return t("mean_last", lang, last=last[:200])
    return t("understand_none", lang)


def _feeling_ack(text: str, lang: str) -> str:
    """The human part of a message, acknowledged FIRST (round 8.1,
    14 Nov 2026): "haha nice, I'm tired today but I need views"
    is laughter AND tiredness, and the bot must not ignore either
    and jump straight to tips. Laugh + tired together get the
    combined line; either one alone gets its own line; nothing
    felt returns ""."""
    s = " ".join((text or "").strip().lower().split())
    laugh = any(w in s for w in ("haha", "lol", "lmao", "hehe")) \
        or any(e in s for e in ("😂", "🤣"))
    tired = "tired" in s or "bored" in s
    if laugh and tired:
        return t("chat_laugh_tired", lang)
    if laugh:
        return t("chat_laugh", lang)
    if tired:
        return t("chat_tired", lang)
    return ""


def local_chat_reply(text: str, lang: str) -> str:
    """Warm acknowledgement when the AI is down: keyed by what the
    user said. Never a price, never an order prompt — the caller
    appends the soft continuation. The human part comes first
    (round 8.1, 14 Nov 2026): laugh and tiredness are
    acknowledged before anything else, so a tired user never gets
    only tips."""
    ack = _feeling_ack(text, lang)
    if ack:
        return ack
    s = " ".join((text or "").strip().lower().split())
    if "thank" in s or "thx" in s:
        return t("chat_thanks", lang)
    if "happy" in s or "feel good" in s:
        return t("chat_happy", lang)
    if any(p in s for p in (
        "how are you", "how r you", "what's up", "whats up",
        "good morning", "good afternoon", "good evening",
    )):
        return t("chat_greeting", lang)
    if "viral" in s:
        return t("chat_viral", lang)
    return t("chat_default", lang)


def chat_continue_note(user_id: int, lang: str) -> str:
    """The soft line that ends a free-chat reply: it points back to
    the order without interrogating ("send the link when you're
    ready"), or invites a first order when there is none."""
    _cid, pending = pending_for_user(user_id)
    if pending is not None:
        return t("chat_continue_confirm", lang)
    partial = PARTIAL.get(user_id) or {}
    if partial:
        if not partial.get("link"):
            return t("chat_continue_link", lang)
        if not partial.get("quantity"):
            return t("chat_continue_quantity", lang)
        return t("chat_continue_confirm", lang)
    return t("chat_continue_fresh", lang)


async def conversation_reply(update, text: str, lang: str, voice: bool = False) -> bool:
    """Answer a conversational message mid-order and return True
    when handled (the caller returns). Three kinds, in order:
    "do you understand" gets a restatement of the order; "what do
    you mean / why are you asking" gets an explanation; free chat
    (greetings, small talk, comments, feelings, opinions) gets a
    natural AI answer plus a soft steer back. Real questions and
    order details are never swallowed: ban, price, source, payment,
    usual, order-now, links, quantities, service IDs and deposit
    fields all fall through to their own handlers. The draft and
    any Confirm card stay untouched."""
    user = update.effective_user
    user_id = user.id
    s = " ".join((text or "").strip().lower().split())
    if not s:
        return False
    if (is_ban_question(text) or is_price_question(text)
            or is_source_question(text) or is_paid_phrase(text)
            or is_usual_request(text) or is_order_now(text)
            or extract_links(text) or extract_service_id(text) is not None
            or quantity_from_text(text) is not None
            or normalize_method(text) is not None
            or normalize_phone(text) is not None
            or parse_deposit_amount(text) is not None
            or parse_interval_minutes(text) is not None):
        return False
    if is_confirm_understanding(text):
        await reply_message(
            update.message, understanding_text(user_id, lang),
            lang, voice=voice,
        )
        OFF_TOPIC_COUNT.pop(user_id, None)
        return True
    if is_conversation_question(text, user_id):
        await reply_message(
            update.message, explain_asking_text(user_id, lang),
            lang, voice=voice,
        )
        OFF_TOPIC_COUNT.pop(user_id, None)
        return True
    if is_free_chat(text):
        _cid, _pending = pending_for_user(user_id)
        _partial = PARTIAL.get(user_id) or {}
        if _pending is None and not _partial:
            # Pure small talk with no order being built counts toward
            # the same 2-3 turn steering as off-topic (round 5).
            count = OFF_TOPIC_COUNT.get(user_id, 0) + 1
            OFF_TOPIC_COUNT[user_id] = count
            if count >= 3:
                await reply_message(
                    update.message,
                    with_pending_note(
                        user_id, lang, t("off_topic_steer", lang)
                    ),
                    lang, voice=voice,
                )
                return True
        general = await answer_general_question(text, lang)
        if general is None:
            general = local_chat_reply(text, lang)
        else:
            # The AI answered the content but never acknowledges
            # the human part (round 8.1, 14 Nov 2026: "haha nice,
            # I'm tired today" got only video tips) — the feeling
            # goes first, before the tips or the steering.
            ack = _feeling_ack(text, lang)
            if ack and ack not in general:
                general = ack + " " + general
        await reply_message(
            update.message,
            general + "\n" + chat_continue_note(user_id, lang),
            lang, voice=voice,
        )
        return True
    return False


# ------------------------------------------------------------- handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # A redelivered /start (same update id, seen 14 Nov 2026: the
    # greeting went out twice at 07:26) must not greet twice.
    if _update_seen(update):
        return
    user = update.effective_user
    lang = detect_language("", user.language_code)
    try:
        await paxyo.create_user(
            user.id, username=user.username, first_name=user.first_name
        )
    except Exception as exc:  # account creation must never block /start
        log.warning("create_user failed (continuing): %s", exc)
    await update.message.reply_text(t("greeting", lang))
    record_exchange(user.id, update.message.text or "/start", t("greeting", lang))


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
        name = short_service_name(sched.get("service_name")) or f"service {sched.get('service_id')}"
        lines.append(
            f"{i}. {name} ×{sched.get('quantity')} "
            f"every {format_interval(sched.get('interval_minutes'))}"
        )
    return "\n".join(lines)


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = lang_of("", user.language_code)
    text = await balance_text(user.id, lang)
    await update.message.reply_text(text)
    record_exchange(user.id, update.message.text or "/balance", text)


async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ALL of the user's orders as a table (owner, 13 Nov 2026)."""
    user = update.effective_user
    lang = lang_of("", user.language_code)
    text = await orders_history_text(user.id, lang)
    await update.message.reply_text(text)
    record_exchange(user.id, update.message.text or "/orders", text)


async def schedules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = lang_of("", user.language_code)
    text = await schedules_text(user.id, lang)
    await update.message.reply_text(text)
    record_exchange(user.id, update.message.text or "/schedules", text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = lang_of("", user.language_code)
    text = t("help", lang)
    await update.message.reply_text(text)
    record_exchange(user.id, update.message.text or "/help", text)


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
        "service": (
            clean_service_name(service.get("name"))
            if pending.get("full_name")
            else short_service_name(service.get("name"))
        ),
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
    summary = t(
        "order_summary",
        lang,
        service=result["service"],
        quantity=result["quantity"],
        link=result["link"],
        total=format_money(result["total"]),
        order_id=result["order_id"],
        status=result["status"],
    )
    await message.reply_text(summary + "\n" + humor_line(user_id, lang))
    _record_bot_reply(summary)


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


# The user wants to sell Paxyo's services themselves (next batch,
# 14 Nov 2026). This is NOT the source question: "are you a
# reseller?" asks about Paxyo and still deflects. The difference
# is the user wanting to sell — first-person want / can-I /
# become / how-do-I. A plain "do you sell followers?" (asking
# whether Paxyo sells) matches none of these.
_RESELLER_REQUEST_PATTERNS = (
    "want to resell", "wanna resell", "can i resell",
    "could i resell", "how do i resell", "how can i resell",
    "how to resell", "become a reseller", "be a reseller",
    "become reseller", "interested in reselling",
    "start reselling", "resell your", "resell paxyo",
    "want to sell", "wanna sell", "can i sell", "could i sell",
    "how do i sell your", "how can i sell your",
    "how to sell your", "sell your services", "sell paxyo",
)


def is_reseller_request(text: str) -> bool:
    """True when the user wants to sell Paxyo's services
    themselves — not when they ask whether Paxyo resells."""
    s = " ".join((normalize_text(text or "")).strip().lower().split())
    return any(p in s for p in _RESELLER_REQUEST_PATTERNS)


# The user wants a human — support, the owner, the admin (next
# batch, 14 Nov 2026). "Who owns / who is the owner" is in here
# too: the contact reply names William, so the owner question
# still gets its answer, plus how to reach him. A reported
# problem ("my payment failed, fix my account") matches none of
# these — that stays the support_issue redirect.
_CONTACT_REQUEST_PATTERNS = (
    "talk to a human", "talk to someone", "talk with a human",
    "speak to a human", "speak with a human", "speak to someone",
    "talk to a real person", "speak to a real person",
    "i need support", "need support", "i want support",
    "need help from support", "contact you", "contact william",
    "contact the owner", "contact admin", "contact support",
    "how do i contact", "how can i contact", "how to contact",
    "talk to william", "speak to william", "talk to the owner",
    "speak to the owner", "get in touch", "customer support",
    "who is the owner", "who owns paxyo", "who runs paxyo",
    "who is william", "who is yohannes", "who is the boss",
)


def is_contact_request(text: str) -> bool:
    """True when the user asks to reach a human — support, the
    owner or the admin — rather than reporting a problem."""
    s = " ".join((normalize_text(text or "")).strip().lower().split())
    return any(p in s for p in _CONTACT_REQUEST_PATTERNS)


# Premium subscriptions (CapCut Pro, Canva Pro, ...) and the SMS OTP
# verification service are PAUSED (owner, 14 Nov 2026). The guard
# matches the brand names and the OTP-service phrasing — but never a
# message that names a social-media metric: "premium followers",
# "Spotify followers" and "Telegram Premium members" are real orders
# (the catalogue has 293 "premium" services and Spotify
# followers/likes), and "Telegram Premium" on its own is a Bot Start
# service. CapCut/Canva/Netflix/OTP have no services in the
# catalogue, so the bare brand names are safe. The metric check is
# word-based on plurals only: "I would like CapCut Pro" must still
# match (the verb "like" is not the metric "likes").
_PAUSED_SERVICES_PATTERNS = (
    "capcut", "canva", "netflix",
    "spotify premium", "youtube premium",
    "premium subscription", "premium subscriptions",
    "cheap premium", "buy premium", "get premium", "want premium",
    "need premium", "sell premium", "do you sell premium",
    "do you have premium",
    "sms otp", "otp verification", "otp number", "otp code",
    "otp service", "sms verification",
    "buy otp", "need otp", "want otp", "get otp", "otp for",
    "otp to verify",
)
_PAUSED_METRIC_WORDS = (
    "followers", "likes", "views", "comments", "subscribers",
    "reactions", "members", "shares", "saves",
)


def is_paused_services_request(text: str) -> bool:
    """True when the user asks for a paused service — a premium
    subscription or SMS OTP verification. False for anything that
    names a social-media metric (that is an order) or Telegram
    Premium (a real Bot Start service)."""
    s = " ".join((normalize_text(text or "")).strip().lower().split())
    if "telegram premium" in s:
        return False
    words = set(re.findall(r"[a-z]+", s))
    if words & set(_PAUSED_METRIC_WORDS):
        return False
    return any(p in s for p in _PAUSED_SERVICES_PATTERNS)


# Which services never drop (owner, 14 Nov 2026): ONLY Telegram
# reactions, Telegram views and Facebook reactions. Every other
# service keeps the terms language — results not guaranteed
# permanent, drops may occur — and the bot must never claim
# never-drop for those. The claim is only ever given when the
# user ASKS about drops for one of the three; it is never
# volunteered unprompted.
_NEVER_DROP_KINDS = (
    ("telegram", "reactions", "Telegram reactions"),
    ("telegram", "views", "Telegram views"),
    ("facebook", "reactions", "Facebook reactions"),
)
_DROP_WORDS = (
    "drop", "disappear", "fade", "fall off", "go away", "vanish",
    "decrease", "go down",
)


def never_drop_kind(text: str, platform=None, service_hint=None):
    """The never-drop service kind the message asks about, or None.

    The message must ask about drops AND pin the service to one of
    the three covered kinds (platform + metric). A drop question
    about anything else — TikTok followers, Instagram likes,
    Telegram followers, a bare "do they drop?" with no platform —
    returns None, so the terms/refund answer stands.
    """
    s = " ".join((normalize_text(text or "")).strip().lower().split())
    if not any(p in s for p in _DROP_WORDS):
        return None
    plat = (platform or "").strip().lower() or None
    if plat is None:
        for p in _PLATFORMS:
            if re.search(rf"\b{re.escape(p)}\b", s):
                plat = p
                break
    hint = (service_hint or "").strip().lower()
    metric = kind_from_text(hint) if hint else None
    if metric is None:
        metric = kind_from_text(s)
    if metric is None or plat is None:
        return None
    for p, m, label in _NEVER_DROP_KINDS:
        if p == plat and m == metric:
            return label
    return None


def _service_never_drop_kind(service):
    """The never-drop kind of a service dict, or None.

    Same three kinds as never_drop_kind, read from the service's
    own category/name: "Telegram Reactions", "Telegram Post Views",
    "Facebook Reactions". A Bot Start service has no
    reactions/views metric in its name, so it never matches.
    """
    if not service:
        return None
    text = (
        str(service.get("category") or "")
        + " " + str(service.get("name") or "")
    ).lower()
    plat = None
    for p in ("telegram", "facebook"):
        if re.search(rf"\b{re.escape(p)}\b", text):
            plat = p
            break
    if plat is None:
        return None
    metric = kind_from_text(text)
    if metric is None:
        return None
    for p, m, label in _NEVER_DROP_KINDS:
        if p == plat and m == metric:
            return label
    return None


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
    name = short_service_name(sched.get("service_name")) or f"service {sched.get('service_id')}"
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
        await reply_message(
            update.message,
            ask_link_text(merged.get("platform"), merged.get("service_hint"), lang),
            lang, voice=voice,
        )
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
            reaction_emoji=reaction_emoji(text),
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
                service=short_service_name(service.get("name")),
                min=service.get("min"),
                max=service.get("max"),
            ),
            lang,
            voice=voice,
        )
        return
    # Complete plan: pick the service and show the summary with Confirm.
    RECURRING_DRAFT[user.id] = {k: v for k, v in merged.items() if v is not None}
    if error:
        await reply_message(
            update.message,
            t(
                "bad_quantity",
                lang,
                service=short_service_name(service.get("name")),
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
        f"{short_service_name(service.get('name'))}",
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
                         note: str = None, ask_metric: bool = True,
                         show_full_name: bool = False):
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
    # A complete order was built (and is about to be confirmed or
    # placed): the cancelled draft is history now.
    CANCELLED_DRAFT.pop(user_id, None)
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
            services, platform=merged.get("platform"), service_hint=merged.get("service_hint"),
            reaction_emoji=merged.get("reaction_emoji"),
        )
        if not picks:
            # A specific reaction emoji with no dedicated service:
            # say so honestly (owner, 14 Nov 2026) — never
            # silently sell the Positive mix.
            if merged.get("reaction_emoji") and "reaction" in (merged.get("service_hint") or "").lower():
                await reply_message(
                    message,
                    t("no_exact_reaction", lang, emoji=merged["reaction_emoji"]),
                    lang, voice=voice,
                )
                return False
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
                # One-tap "Use the fastest one" (round 7, 13 Nov
                # 2026): until now the button only appeared when a
                # service named by ID was refused, so in two live
                # retests it never appeared at all. It is offered
                # here too, so the user can skip the choice and take
                # the fastest service for the platform.
                _token = uuid.uuid4().hex[:12]
                FASTEST_FALLBACK[_token] = {
                    "user_id": user_id,
                    "merged": {
                        k: v for k, v in merged.items() if v is not None
                    },
                }
                await reply_message(
                    message,
                    t("ask_metric_choose", lang, metrics=", ".join(metrics)),
                    lang, voice=voice,
                    reply_markup=fastest_fallback_keyboard(_token, lang),
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
                service=short_service_name(service.get("name")),
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
    _pending_entry = {
        "user_id": user_id,
        "service": service,
        "link": merged["link"],
        "quantity": quantity,
        "total": total,
        "full_name": show_full_name,
    }
    PENDING[confirm_id] = _pending_entry
    # Confirm card: always text — a voice message cannot carry buttons.
    _sent = await reply_message(
        message,
        confirm_card_text(lang, service, quantity, total, merged["link"],
                          note=note, full_name=show_full_name),
        lang,
        reply_markup=confirm_keyboard(confirm_id),
    )
    _remember_card_message(_pending_entry, message, _sent)
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
    explicit = intent.get("quantity")
    try:
        explicit = int(explicit) if explicit is not None else None
    except (TypeError, ValueError):
        explicit = None
    if explicit is not None:
        # "same like as usual please order 1k views": the new
        # quantity in the same message wins over the last order's.
        wanted = explicit
    else:
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
    if not platform and not hint:
        # A budget question in the middle of an order ("how much
        # views can 10 br get me" after a TikTok views order) is
        # about that platform and metric — not about every service
        # Paxyo sells.
        platform, hint = _conversation_context(user.id)
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
        # State the quantity each option buys, not just the per-1000
        # price: "how much views can 10 br get me" is a question
        # about a number (13 Nov 2026 — the bot listed prices and
        # never said how many views). An option the budget cannot
        # buy at minimum is left out; when none is affordable, say
        # so with the cheapest minimum instead.
        shown = []
        shown_services = []
        for s in options:
            qty = qty_for_amount(
                budget, float(s.get("rate_etb_per_1000", 0) or 0)
            )
            if qty < int(s.get("min", 0) or 0):
                continue
            metric_word = (
                kind_from_text(hint or "")
                or kind_from_text(clean_service_name(s.get("name")) or "")
                or "service"
            )
            shown.append(
                f"{short_service_name(s.get('name'))} — "
                f"about {qty:,} {metric_word} "
                f"({format_money(s.get('rate_etb_per_1000', 0))} ETB per 1000)"
            )
            shown_services.append(s)
        if not shown:
            await reply_message(
                update.message,
                t(
                    "budget_too_small", lang, budget=format_money(budget),
                    minimum=int(cheapest.get("min", 0) or 0),
                    metric=metric,
                    name=short_service_name(cheapest.get("name")),
                    total=format_money(estimated_total_etb(
                        float(cheapest.get("rate_etb_per_1000", 0) or 0),
                        int(cheapest.get("min", 0) or 0),
                    )),
                ),
                lang, voice=voice,
            )
            return
        option_text = "; ".join(shown)
        # Remember what was shown, in order, so "first one" /
        # "second one" picks it instead of starting a new order.
        BUDGET_OPTIONS[user.id] = {
            "platform": platform, "service_hint": hint,
            "quantity": None, "options": shown_services,
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
            f"{short_service_name(s.get('name'))} — "
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
                name=short_service_name(cheapest.get("name")),
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
            name=short_service_name(cheapest.get("name")),
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
                f"{link} — {short_service_name(service.get('name'))}: "
                f"quantity must be between "
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
            f"{i}. {short_service_name(o['service'].get('name'))} "
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
        name = short_service_name(draft["service"].get("name"))
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
            f"{short_service_name(o['service'].get('name'))} ×{o['quantity']} → {o['link']}"
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
            f"{short_service_name(o['service'].get('name'))} ×{o['quantity']} → {o['link']}"
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


_CHANGE_PHRASES = (
    "instead", "make it", "change", "just get", "rather",
)


def _is_quantity_change(text, merged, pending):
    """True when a message with a new quantity is a change to the
    order awaiting Confirm, not a new order: it says so ("200
    instead", "make it 200"), or it names the same platform and kind
    as the pending service (a bare "200" while a Confirm card is up
    means "200 instead"). A different platform or kind is a new
    order and still asks for its link."""
    s = " ".join((text or "").strip().lower().split())
    if any(p in s for p in _CHANGE_PHRASES):
        return True
    service = pending.get("service") or {}
    hay = (
        str(service.get("name") or "") + " "
        + str(service.get("category") or "")
    ).lower()
    platform = (merged.get("platform") or "").strip().lower()
    if platform:
        words = re.findall(r"[a-z]+", hay)
        if platform not in words:
            return False
    kind = kind_from_text(text)
    if kind is not None:
        kind_words = {
            _canonical_metric(w) for w in kind.split()
        } - {None}
        if kind_words != _name_kinds(service.get("name")):
            return False
    return True


def _remember_card_message(pending, user_message, sent):
    """Remember which Telegram message carries a Confirm card, on
    the PENDING entry itself: the chat id from the user's message
    and the message id from the sent card. A later replacement
    (a reaction correction, a quantity change) deletes that message
    instead of leaving a stale card stacked in the chat. Missing
    ids are simply not stored — deletion is best effort."""
    if not isinstance(pending, dict):
        return
    chat_id = getattr(user_message, "chat_id", None)
    message_id = getattr(sent, "message_id", None)
    if chat_id is not None:
        pending["chat_id"] = chat_id
    if message_id is not None:
        pending["message_id"] = message_id


async def drop_pending_card(update, pending):
    """Delete the Confirm card message of a pending order, best
    effort. Called when the card is replaced (a reaction
    correction) so its buttons cannot place the old service. The
    PENDING entry is popped by the caller either way; a failed
    delete (message too old, no rights, no stored id) is logged,
    never fatal — the old buttons are dead once the entry is
    gone."""
    message_id = (pending or {}).get("message_id")
    chat_id = (pending or {}).get("chat_id")
    if not message_id or not chat_id:
        return
    try:
        bot = update.message.get_bot()
    except Exception:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        log.warning("dropping old card failed: %s", exc)


async def try_reaction_correction(update, text, lang, voice=False):
    """A different reaction emoji for the order already awaiting
    Confirm ("I want only 🙏 reaction") re-picks the service for
    that emoji and shows a NEW card — never the old card unchanged
    (owner, 14 Nov 2026: a 🙏 correction re-showed the Positive mix
    card). The link and quantity come from the pending order, and
    the old card is dropped so its buttons cannot place the old
    service. Returns True when a correction was handled. Only when
    the pending service is a reactions service and the new emoji
    differs from it. The message's OWN fields decide: a link or a
    quantity in the message is a new order, not a correction — the
    merged draft still carries the old link and quantity (PARTIAL
    survives the card), so merged must not be consulted here."""
    user = update.effective_user
    _cid, _pending = pending_for_user(user.id)
    if _pending is None:
        return False
    _pending_name = str(_pending["service"].get("name") or "")
    if "reaction" not in _pending_name.lower():
        return False
    _own = local_intent(text)
    if _own.get("link") or _own.get("quantity"):
        return False
    _new_emoji = reaction_emoji(text)
    _old_emoji = reaction_emoji(_pending_name)
    if (
        _new_emoji is None
        or _old_emoji is None
        or _new_emoji == _old_emoji
    ):
        return False
    try:
        _services = await paxyo.services()
    except Exception as exc:
        log.warning("correction services failed: %s", exc)
        _services = []
    # The correction re-picks on the PENDING order's platform:
    # a Facebook ❤️ correction must re-pick a Facebook service,
    # not a Telegram one (owner, 14 Nov 2026 — the exact-emoji
    # rule covers Facebook reactions too).
    _platform, _hint = _platform_hint_of_service(_pending["service"])
    if not _hint or "reaction" not in _hint:
        _hint = f"{_platform} reactions" if _platform else "reactions"
    _picks = pick_services(
        _services, platform=_platform,
        service_hint=_hint,
        reaction_emoji=_new_emoji,
    ) if _services else []
    if not _picks:
        await reply_message(
            update.message,
            t("no_exact_reaction", lang, emoji=_new_emoji),
            lang, voice=voice,
        )
        return True
    _service = _picks[0]
    _new_qty = int(_pending["quantity"])
    _error = validate_quantity(_new_qty, _service)
    if _error:
        await reply_message(
            update.message,
            t(
                "bad_quantity", lang,
                service=short_service_name(_service.get("name")),
                min=_service.get("min"), max=_service.get("max"),
            ),
            lang, voice=voice,
        )
        return True
    _new_total = estimated_total_etb(
        float(_service.get("rate_etb_per_1000", 0)), _new_qty
    )
    _new_id = uuid.uuid4().hex[:12]
    PENDING.pop(_cid, None)
    _new_pending = {
        "user_id": user.id, "service": _service,
        "link": _pending["link"], "quantity": _new_qty,
        "total": _new_total,
        "full_name": _pending.get("full_name", False),
    }
    PENDING[_new_id] = _new_pending
    # The old card goes first, so the chat never shows two live
    # cards for one order (live bug, 14 Nov 2026: both Pray cards
    # stayed stacked, each with its own Confirm/Cancel).
    await drop_pending_card(update, _pending)
    _sent = await reply_message(
        update.message,
        confirm_card_text(
            lang, _service, _new_qty, _new_total, _pending["link"],
            note=t("change_note", lang, quantity=_new_qty),
            full_name=_pending.get("full_name", False),
        ),
        lang,
        reply_markup=confirm_keyboard(_new_id),
    )
    _remember_card_message(_new_pending, update.message, _sent)
    return True


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
    if new_qty is not None and not _quantity_grounded_in_text(text, new_qty):
        # The classifier carries the pending order's quantity
        # forward from conversation history (live bug, 14 Nov
        # 2026: "I want only ❤️ reaction" arrived as a
        # change_order with quantity=10, and the quantity path
        # re-issued the same Pray card instead of the emoji
        # correction running). A quantity the user did not type
        # in this message is not a quantity change — drop it, so
        # the number extraction below and the correction check
        # see only what this message actually said.
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
        # No number: maybe a different reaction emoji for the
        # pending order ("I want only 🙏 reaction") — that re-picks
        # the service instead of failing with "not understood".
        if await try_reaction_correction(update, text, lang, voice=voice):
            return
        await reply_message(update.message, t("not_understood", lang), lang, voice=voice)
        return
    confirm_id, pending = pending_for_user(user.id)
    if pending is not None:
        service = pending["service"]
        error = validate_quantity(new_qty, service)
        if error:
            await reply_message(
                update.message,
                t(
                    "bad_quantity", lang,
                    service=short_service_name(service.get("name")),
                    min=service.get("min"), max=service.get("max"),
                ),
                lang, voice=voice,
            )
            return
        pending["quantity"] = new_qty
        pending["total"] = estimated_total_etb(
            float(service.get("rate_etb_per_1000", 0)), new_qty
        )
        _sent = await reply_message(
            update.message,
            confirm_card_text(
                lang, service, new_qty, pending["total"], pending["link"],
                note=t("change_note", lang, quantity=new_qty),
                full_name=pending.get("full_name", False),
            ),
            lang,
            reply_markup=confirm_keyboard(confirm_id),
        )
        _remember_card_message(pending, update.message, _sent)
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
            await reply_message(
                update.message,
                ask_link_text(merged.get("platform"), merged.get("service_hint"), lang),
                lang, voice=voice,
            )
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
                service=short_service_name(service_name)
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
    metric = hint or short_service_name(service.get("name"))
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
    if not platform and not hint:
        # "Something cheaper" in the middle of an order names no
        # platform of its own: stay on the platform and metric
        # already in the conversation.
        platform, hint = _conversation_context(user.id)
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
    metric = hint or short_service_name(service.get("name"))
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
                service=short_service_name(service.get("name")),
                price=price,
            ),
        ),
        lang, voice=voice,
    )


async def handle_order_text(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            text: str, voice: bool = False, intent: dict = None,
                            quoted_text: str = None):
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
      how_to_order, how_to, miniapp, social, help, greeting,
      paxyo_info, source_question, reseller, contact, paused_services, usual, goal,
      budget, batch, change_order, refill, split_payment,
      max_for_balance, discount, safety, refund_policy, geo_target,
      free_sample, price_pushback, content_help, support_issue,
      cancel, off_topic, unclear).
      Conversational intents are answered before the order flow, so the bot talks like
      customer support instead of only understanding orders;
      a real question always gets a free AI answer (owner,
      14 Nov 2026) — only non-question chit-chat is steered back
      to ordering, from the third turn.
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
    - Orders work in Amharic, Tigrinya, Oromo and English, by text.
      (Voice messages are still transcribed when sent, but the bot
      does not claim to take orders by voice — owner, 13 Nov 2026.)
      The reply is always in the language of the user's current
      message (owner, 14 Nov 2026): English in -> English out,
      Amharic in -> Amharic out, and the same for Tigrinya and
      Oromo — never the previous turn's language.
    - A user replying TO one of the bot's messages (a quote) is read
      in that context: "1000" replied to "How many?" is the quantity;
      "yes" replied to a Confirm card confirms it. See
      reply_or_bare_intent, checked before the classifier.
    """
    user = update.effective_user
    # Tolerate typos and slang before anything else: the classifier,
    # the acceptance check and the follow-up parsers all see the
    # cleaned text. URLs are kept verbatim (case-sensitive links).
    text = normalize_text(text)
    # Reply in the language of THIS message (owner, 14 Nov 2026):
    # the bridge flag is reset every turn, so a bridged turn can
    # never leak into the next one.
    _set_bridge_lang(None)
    _detected = detect_language(text, user.language_code)
    lang = _detected
    # Translate-bridge (owner, 13 Nov 2026; Oromo and Tigrinya
    # added 14 Nov 2026): a message in Amharic, Tigrinya or Oromo
    # is translated to English by Gemini first, so the whole flow
    # below runs in English and the main AI never has to guess the
    # language. Prose replies are translated back before sending
    # (see reply_message). Only non-English text triggers it —
    # English never touches the bridge. If translation fails or
    # comes back unchanged, the original text is used and the local
    # handling applies untouched.
    if _detected in ("am", "ti", "om"):
        _english = await translate_to_english(text, source_lang=_detected)
        if _english and _english.strip() != text.strip():
            text = _english
            lang = "en"
            _set_bridge_lang(_detected)
    # Conversation memory: remember who is speaking and what they
    # said, so the bot's first reply of this turn is recorded.
    # The detected language is also remembered per user: the next
    # voice note's transcription retry hints it (owner, 14 Nov
    # 2026 — an Amharic voice note must not be auto-detected as
    # Arabic on the retry).
    _CURRENT_USER_ID.set(user.id)
    _LAST_USER_TEXT.set(text)
    LAST_LANG[user.id] = _detected

    # Arabic-script text (owner, 14 Nov 2026): the bot has no
    # Arabic templates and must never mirror Arabic back. It can
    # only arrive from a mis-transcribed voice note (Whisper
    # auto-detect confuses Amharic with Arabic) or a typed message
    # in a language the bot does not speak. Answer honestly
    # instead of feeding it to the classifier or the AI.
    if _has_arabic_script(text):
        await reply_message(
            update.message, t("not_understood_language", lang),
            lang, voice=voice,
        )
        return

    # Offensive users (owner, 13 Nov 2026): push back firmly and
    # bluntly — never polite, never apologetic. A second insult in
    # the same exchange refuses to continue; a third goes silent.
    # The bot itself never uses slurs back. Any non-offensive
    # message resets the count.
    if is_offensive(text):
        count = OFFENSE_COUNT.get(user.id, 0) + 1
        OFFENSE_COUNT[user.id] = count
        if count >= 3:
            return
        if count >= 2:
            await reply_message(update.message, t("offensive_refusal", lang), lang, voice=voice)
            return
        await reply_message(update.message, t("offensive_pushback", lang), lang, voice=voice)
        return
    OFFENSE_COUNT.pop(user.id, None)

    # "please order now" with a Confirm card pending (owner override,
    # 13 Nov 2026): place the pending order at once, no second card.
    if is_order_now(text):
        _cid, _pending = pending_for_user(user.id)
        if _pending is not None:
            PENDING.pop(_cid, None)
            await send_order_result(update.message, lang, _pending, user.id)
            return

    # The user wants to sell Paxyo's services themselves, or to
    # reach William (next batch, 14 Nov 2026): answer at once,
    # without calling Gemini, and before free-chat handling — a
    # short "I need support" must not become a generic chat reply.
    # The reseller check runs before the source-question guard
    # below: "resell" is a source-question word, but "I want to
    # resell" is the user asking to sell, not asking about Paxyo's
    # supplier. Both answers are one short line with the contact,
    # so asking again just repeats it.
    if intent is None and is_reseller_request(text):
        await reply_message(
            update.message, t("reseller_contact", lang), lang, voice=voice
        )
        return
    if intent is None and is_contact_request(text):
        await reply_message(
            update.message, t("contact_owner", lang), lang, voice=voice
        )
        return

    # Premium subscriptions and SMS OTP verification are paused
    # (owner, 14 Nov 2026): answer at once, without calling Gemini,
    # and before free-chat handling — "do you sell CapCut Pro" must
    # not become a generic chat reply or an order. One short line,
    # no date, no price, never a social-media service instead.
    if intent is None and is_paused_services_request(text):
        await reply_message(
            update.message, t("paused_services", lang), lang, voice=voice
        )
        return

    # A bare quantity + reaction emoji ("10 🙏", "🙏 10") or a bare
    # 🙏 starts a Telegram reactions order (owner, 14 Nov 2026 —
    # live retest: "10 🙏" alone got "I did not understand", and
    # the bare link after it asked "Which platform?"). The draft
    # carries platform Telegram + the emoji, so the link the user
    # sends next completes the order instead of asking for the
    # platform. Skipped while a Confirm card is pending: there the
    # normal flow handles the emoji as a correction and the number
    # as a quantity change.
    _reaction_start = bare_reaction_order(text)
    if _reaction_start is not None:
        _cid, _pending = pending_for_user(user.id)
        if _pending is None:
            _emoji, _qty = _reaction_start
            _draft = {
                "platform": "telegram",
                "service_hint": "telegram reactions",
                "reaction_emoji": _emoji,
            }
            if _qty is not None:
                _draft["quantity"] = _qty
            PARTIAL[user.id] = _draft
            await reply_message(
                update.message,
                ask_link_text("telegram", "telegram reactions", lang),
                lang, voice=voice,
            )
            return

    # A bare non-reaction emoji is a media reaction (owner, 14
    # Nov 2026): it is answered from the user's situation — a
    # delayed order, a completed order, a pending Confirm card,
    # or nothing at all — never with the same canned line twice,
    # and it never touches the draft or the Confirm card.
    # Reaction emoji take the reactions path below instead.
    _media_emoji = _bare_non_reaction_emoji(text)
    if _media_emoji is not None:
        if await media_reply_for_text(update, _media_emoji, lang, voice=voice):
            return

    # A conversational message mid-order (round 8, 14 Nov 2026):
    # "do you understand", "what do you mean", free chat — answer
    # like a normal AI first, then continue the order. Never
    # swallowed by the link prompt. The draft and any Confirm card
    # stay untouched.
    if await conversation_reply(update, text, lang, voice=voice):
        return

    # A bare reaction emoji (round 8.1, 14 Nov 2026): "👍" is a
    # reply, not a new order — it is the reaction the user wants.
    # Only a message that IS just the emoji takes this branch: a
    # full order message that merely contains one ("I want 👍
    # reactions for … 1000") goes through the order flow as usual.
    # In a reactions order context (a reactions draft is being
    # built, or a reactions Confirm card is pending) it is
    # acknowledged as that choice first, then the link is asked
    # for, and it is stored in the draft so the picker matches
    # the family. With no order context at all it gets a natural
    # reply, never the stock link request on its own — and the
    # draft is still started (service_hint "reactions"), so the
    # link the user sends next completes a reactions order. A bare
    # emoji while a NON-reactions order is being built is just an
    # acknowledgement — it falls through to the normal flow, it
    # never hijacks that order into reactions. (It runs before
    # reply_or_bare_intent so the emoji is never misread as a
    # service search.)
    emoji = reaction_emoji(text)
    _bare_emoji = (
        emoji is not None
        and (text or "").strip().replace("\ufe0f", "")
        == emoji.replace("\ufe0f", "")
    )
    if _bare_emoji:
        _cid, _pending = pending_for_user(user.id)
        _stored = PARTIAL.get(user.id) or {}
        _is_reactions_pending = _pending is not None and "reaction" in (
            short_service_name((_pending.get("service") or {}).get("name"))
            + " "
            + str((_pending.get("service") or {}).get("category") or "")
        ).lower()
        _is_reactions_draft = "reaction" in (
            _stored.get("service_hint") or ""
        ).lower()
        if _is_reactions_pending or _is_reactions_draft:
            if _is_reactions_draft:
                _stored["reaction_emoji"] = emoji
                PARTIAL[user.id] = {
                    k: v for k, v in _stored.items() if v is not None
                }
            await reply_message(
                update.message,
                t("emoji_ack_order", lang, emoji=emoji),
                lang, voice=voice,
            )
            return
        if _pending is None and not _stored:
            PARTIAL[user.id] = {
                "service_hint": "reactions", "reaction_emoji": emoji,
            }
            await reply_message(
                update.message,
                t(
                    "emoji_ack_fresh", lang, emoji=emoji,
                    meaning=EMOJI_MEANINGS.get(emoji, ""),
                ),
                lang, voice=voice,
            )
            return

    # Catch-all for a bare emoji the reactions path did not claim
    # (owner, 14 Nov 2026 — "he also misunderstood the emoji"): a
    # bare 👀, 💔, 🤗 ... is a reaction, not a failed order, and a
    # bare reaction emoji while a Confirm card is pending is an
    # acknowledgement, not a new order. Both get a sensible
    # emoji-aware reply from the user's situation, like a GIF —
    # never "I did not understand". A bare reaction emoji while a
    # NON-reactions draft is being built keeps the old behaviour
    # (the flow below re-asks for the missing piece), so this
    # only fires for an emoji the reactions path does not claim,
    # or while a card is pending. The draft and the card are never
    # touched.
    if _is_bare_emoji(text):
        _cid, _pending = pending_for_user(user.id)
        if emoji is None or _pending is not None:
            _first = emoji_meanings(text)
            await media_reply_for_text(
                update, _first[0][0] if _first else None, lang,
                voice=voice,
            )
            return

    # Bare-quantity answers and replies to the bot's questions are
    # read before the classifier, so "1000 please" after "How many?"
    # (or "1000" replied TO that message) completes the order
    # instead of being misread as a service search.
    if intent is None:
        intent = reply_or_bare_intent(text, quoted_text, user.id)

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
                    service=short_service_name(rec_draft["service"].get("name")),
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

    # "Same as usual" (round 6, 13 Nov 2026): the AI sometimes
    # reads it as a plain order and the flow then asks for the link,
    # even though the last order's link is known. Catch the phrasing
    # locally, before the classifier, and route it to the usual
    # handler with the quantity from the message. (An injected
    # intent — a photo — is never overridden.)
    if intent is None and is_usual_request(text):
        _words = set(re.findall(r"[a-z]+", text.lower()))
        intent = _empty_intent(
            "usual",
            quantity=quantity_from_text(text),
            quantity_multiplier=(
                2 if "double" in _words
                else 3 if "triple" in _words else None
            ),
        )
    # Price questions are answered from local detection only, BEFORE
    # the AI classifier (live bug, 14 Nov 2026: the price arrived
    # 68 seconds late because the classifier and the bridge ran
    # first, and the queue of earlier updates delayed it further).
    # local_intent reads the platform, metric and quantity straight
    # from the message, and the price comes from the catalogue —
    # the AI is never in the path. When this fast path cannot name
    # a service (price is None), the flow continues to the
    # classifier and the post-classification price branch below,
    # which may resolve it from the AI's intent instead.
    if intent is None and is_price_question(text):
        _local = local_intent(text)
        price = await price_answer_text(user.id, text, _local, lang)
        if price is not None:
            await reply_message(update.message, price, lang, voice=voice)
            return
    # How to get a Telegram post link: a deterministic answer,
    # before the classifier (owner, 14 Nov 2026 — the AI kept
    # getting the steps wrong, and the free answer was
    # desktop-flavoured). Never a free AI reply for this one.
    if intent is None and is_telegram_post_link_question(text):
        await reply_message(
            update.message, t("telegram_post_link", lang), lang,
            voice=voice,
        )
        return
    # `intent` is injected by the photo handler (a picture's link is
    # already classified by Gemini vision, so a second text
    # classification of the bare link would be wasted and could
    # misread it). Otherwise the text is classified here — with the
    # catalogue as a hint when it is available (cached 10 minutes;
    # a fetch failure just means no services section, as before).
    if intent is None:
        try:
            _services = await paxyo.services() if paxyo is not None else None
        except Exception:
            _services = None
        intent = await extract_intent(
            text, user_id=user.id, services=_services
        )
    intent_type = (intent.get("intent") or "unclear").strip().lower()
    # Off-topic steering counts consecutive off-topic turns; any
    # Paxyo topic resets it.
    if intent_type not in ("off_topic", "unclear"):
        OFF_TOPIC_COUNT.pop(user.id, None)

    # A message that pastes a link and names a metric with an order
    # verb IS an order, even when the AI called it something else
    # (round 7, 13 Nov 2026: "I want TikTok followers for <video
    # link>" came back as "safety", so the link-mismatch answer
    # never fired in that turn and the followers draft leaked into
    # the next one). Missing fields are filled from the message
    # itself, so the order flow sees the link and the metric.
    if intent_type in _ORDER_OVERRIDABLE and is_order_request(text):
        _local = local_intent(text)
        for _k in (
            "platform", "service_hint", "link", "quantity", "service_id",
        ):
            if intent.get(_k) is None and _local.get(_k) is not None:
                intent[_k] = _local[_k]
        intent["intent"] = "order"
        intent_type = "order"

    # A question about an order awaiting Confirm ("how fast would
    # those 1000 views actually arrive?") is answered from the
    # pending service whatever the classifier called it — paxyo_info,
    # unclear, anything. The round-3 fix only ran inside the order
    # flow, so a paxyo_info classification answered it with the
    # generic line instead of the real "about 1 minute". A number
    # that equals the pending quantity is a reference to that order,
    # not new information.
    if intent_type in ("paxyo_info", "unclear", "order", "off_topic"):
        _cid, _pending = pending_for_user(user.id)
        if _pending is not None:
            _question = pending_order_question(
                text, _pending.get("quantity")
            )
            if _question is not None:
                _answer = pending_confirm_answer(
                    _pending.get("service"), _question, lang
                )
                if _answer is not None:
                    await reply_message(
                        update.message, _answer, lang, voice=voice
                    )
                    return

    # --- round 5: direct answers that must not fall through to the
    # --- order flow or the generic AI line ---
    # The price question is answered by the deterministic detector,
    # never by the AI's classification (live bug, 14 Nov 2026: the
    # same "I want 👍 reaction ... how much 1k" got its price from
    # Groq and lost it from DeepSeek, because the old intent-type
    # gate let the classifier decide whether a price question got
    # its price at all).
    if is_price_question(text):
        price = await price_answer_text(user.id, text, intent, lang)
        if price is not None:
            await reply_message(update.message, price, lang, voice=voice)
            return
    if is_ban_question(text):
        await reply_message(update.message, with_pending_note(user.id, lang, t("ban_no", lang)), lang, voice=voice)
        return
    # The link of a past order (owner, 14 Nov 2026): answer with
    # the ACTUAL link from history — never the history list, never
    # an invented link. Runs before the history-table handler
    # below, so "send me the link of the last order" does not get
    # the table instead.
    if is_link_recall_question(text):
        recall = await link_recall_text(user.id, text, lang)
        await reply_message(update.message, recall, lang, voice=voice)
        return
    _never_drop = never_drop_kind(
        text, intent.get("platform"), intent.get("service_hint")
    )
    if _never_drop is not None:
        # Owner, 14 Nov 2026: Telegram reactions, Telegram views
        # and Facebook reactions never drop. Only when the user
        # asks about drops for one of those three — every other
        # drop question falls through to the terms/refund answer.
        # Runs before terms_answer, so a covered question never
        # gets the generic "drops may occur" line.
        await reply_message(
            update.message,
            with_pending_note(
                user.id, lang, t("never_drop", lang, service=_never_drop)
            ),
            lang, voice=voice,
        )
        return
    if is_pay_methods_question(text):
        # "How can I pay?" (round 6, 13 Nov 2026): list the methods
        # FIRST — the deposit flow jumps straight to "How much do you
        # want to deposit?" and the user never sees them.
        await reply_message(update.message, with_pending_note(user.id, lang, t("paxyo_pay", lang)), lang, voice=voice)
        return
    if is_public_question(text):
        await reply_message(update.message, with_pending_note(user.id, lang, t("public_answer", lang)), lang, voice=voice)
        return
    if is_comment_likes_question(text):
        # Owner, 14 Nov 2026: for likes on a comment the bot needs
        # the video/post link plus either the comment's own link or
        # the username. A deterministic Paxyo fact — the AI must
        # never invent a different requirement.
        await reply_message(update.message, with_pending_note(user.id, lang, t("comment_likes_need", lang)), lang, voice=voice)
        return
    if is_telegram_post_link_question(text):
        # Deterministic Telegram post-link steps (owner, 14 Nov
        # 2026): the AI kept getting them wrong. Runs here too so
        # a classifier that already ran (photo intent) cannot send
        # the question to a free AI reply.
        await reply_message(update.message, t("telegram_post_link", lang), lang, voice=voice)
        return
    _terms = terms_answer(text, lang)
    if _terms is not None:
        await reply_message(update.message, with_pending_note(user.id, lang, _terms), lang, voice=voice)
        return
    if is_history_question(text):
        summary = history_summary_text(user.id, lang)
        await reply_message(
            update.message,
            summary if summary is not None else t("history_none", lang),
            lang, voice=voice,
        )
        return
    if intent_type in ("paxyo_info", "unclear") and pending_order_question(text) == "speed":
        answer = await speed_answer_text(user.id, text, intent, lang)
        if answer is not None:
            await reply_message(update.message, answer, lang, voice=voice)
            return
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
                await reply_message(
                    update.message,
                    ask_link_text(merged.get("platform"), merged.get("service_hint"), lang),
                    lang, voice=voice,
                )
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
                        f"🛑 {short_service_name(sched.get('service_name')) or sched.get('service_id')} "
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
            clear_order_state(user.id, cancelled=pending)
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
        clear_order_state(user.id)
        RECURRING_DRAFT.pop(user.id, None)
        DEPOSIT_DRAFT.pop(user.id, None)
        SPLIT_DRAFT.pop(user.id, None)
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
        # service's average time; a plain history question gets the
        # full table (owner, 13 Nov 2026).
        if is_wait_question(text):
            await handle_order_wait(update, text, lang, voice=voice)
            return
        await reply_message(
            update.message, await orders_history_text(user.id, lang),
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
                        service=short_service_name(slow.get("name")),
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
    if intent_type == "reseller":
        # The user wants to sell Paxyo's services themselves:
        # send them to William. One short line, repeated as-is
        # if they ask again.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("reseller_contact", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "contact":
        # The user wants a human: William at t.me/paxyo.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("contact_owner", lang)),
            lang, voice=voice,
        )
        return
    if intent_type == "paused_services":
        # Premium subscriptions and SMS OTP verification are paused
        # (owner, 14 Nov 2026): one short line, repeated as-is if
        # they ask again. No date, no price, never a social-media
        # service offered instead.
        await reply_message(
            update.message,
            with_pending_note(user.id, lang, t("paused_services", lang)),
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
            update.message, await answer_paxyo_question(text, lang, user_id=user.id),
            lang, voice=voice,
        )
        return
    if intent_type == "how_to":
        # A how-to question gets a free AI answer, like DeepSeek
        # would give (owner, 14 Nov 2026). No steer-back line: it
        # is about ordering, not off-topic chat. The AI is up here
        # (the classifier ran), so a None answer only means an
        # empty reply — the short Paxyo line is the fallback.
        general = await answer_general_question(text, lang)
        await reply_message(
            update.message,
            general if general is not None else t("paxyo_info_fallback", lang),
            lang, voice=voice,
        )
        return
    if intent_type == "off_topic":
        # Off-topic steering (owner, 13 Nov 2026; widened 14 Nov
        # 2026): a real QUESTION always gets a free AI answer plus
        # one short steer-back line — never the canned deflection,
        # however many turns it takes. Only non-question chit-chat
        # is capped: the first two turns get a general answer plus
        # a nudge, the third (and beyond) steers back.
        if is_question(text):
            general = await answer_general_question(text, lang)
            if general is not None:
                await reply_message(
                    update.message,
                    general + "\n" + t("off_topic_nudge", lang),
                    lang, voice=voice,
                )
                return
            # AI down: fall through to the cap logic below, which
            # ends in the one-line deflection.
        count = OFF_TOPIC_COUNT.get(user.id, 0) + 1
        OFF_TOPIC_COUNT[user.id] = count
        if count >= 3:
            await reply_message(update.message, t("off_topic_steer", lang), lang, voice=voice)
            return
        general = await answer_general_question(text, lang)
        if general is None:
            await reply_message(update.message, t("off_topic", lang), lang, voice=voice)
            return
        await reply_message(
            update.message, general + "\n" + t("off_topic_nudge", lang),
            lang, voice=voice,
        )
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
    for key in ("platform", "service_hint", "link", "quantity", "service_id",
                "named_by_id", "reaction_emoji"):
        value = intent.get(key)
        merged[key] = value if value is not None else stored.get(key)

    # A new order with a different metric REPLACES the old draft,
    # never merges with it (round 7, 13 Nov 2026: a followers draft
    # survived into the next turn, so a views order got the followers
    # answer, and a remembered 200-view draft auto-showed a Confirm
    # card). The metric is read from the message's own words first
    # (Amharic included), then from the AI's hint. A clarification
    # of the same metric ("likes for my comment" is still likes)
    # does not reset.
    metric_changed = False
    # A bare emoji carries no words (round 8.1, 14 Nov 2026): its
    # emoji-only kind ("👍" -> "reactions") must not wipe a draft
    # being built for another metric, or rewrite that draft's
    # kind. The emoji fallback in kind_from_text only counts when
    # the message also has words naming a kind — or when the AI's
    # hint names one.
    _text_has_words = any(ch.isalpha() for ch in (text or ""))
    _new_kind = (kind_from_text(text) if _text_has_words else None) or kind_from_text(
        intent.get("service_hint") or ""
    )
    _stored_kind = kind_from_text(stored.get("service_hint") or "")
    _new_metric = _primary_metric(_new_kind)
    _stored_metric = _primary_metric(_stored_kind)
    if (
        _new_metric is not None
        and _stored_metric is not None
        and _new_metric != _stored_metric
    ):
        stored = {}
        metric_changed = True
        for key in ("platform", "service_hint", "link", "quantity",
                    "service_id", "named_by_id", "reaction_emoji"):
            merged[key] = intent.get(key)

    # A bare number right before the metric ("200 TikTok views") is
    # the quantity even when the AI did not return one (round 7:
    # "please order now 200 TikTok views" asked "How many?"
    # instead of placing the order).
    if merged.get("quantity") is None:
        merged["quantity"] = quantity_before_metric(text)

    # Metric-from-text safety net (13 Nov 2026): the classifier
    # sometimes returns an order intent with no service_hint (or only
    # the platform word), and then complete_order picks the fastest
    # service of the whole platform — a views order got Tiktok Comment
    # Likes. When the message itself names a metric, use it. A hint
    # that already carries a metric word is never overridden. merged
    # is stored into PARTIAL at the ask-link/ask-quantity steps, so a
    # derived hint survives a later bare-link message.
    hint_words = set(
        (merged.get("service_hint") or "").strip().lower().split()
    )
    if not (hint_words & set(_METRICS)):
        metric = metric_from_text(text)
        if metric:
            platform = (merged.get("platform") or "").strip().lower()
            merged["service_hint"] = (
                f"{platform} {metric}" if platform else metric
            )

    # "Likes for my comment" is a different kind from "likes for my
    # video": the classifier often returns just "tiktok likes" for a
    # comment-likes request, and the fastest pick would then be a
    # video-likes service. When the message itself names a kind the
    # hint does not carry, the message wins — the hint is rewritten
    # to the kind the user actually asked for. A bare emoji names
    # no kind in words (round 8.1), so it never rewrites the hint.
    kind = kind_from_text(text) if _text_has_words else None
    if kind is not None:
        kind_words = {
            _canonical_metric(w) for w in kind.split()
        } - {None}
        hint_kind_words = {
            _canonical_metric(w)
            for w in (merged.get("service_hint") or "").split()
        } - {None}
        if kind_words != hint_kind_words:
            platform = (merged.get("platform") or "").strip().lower()
            merged["service_hint"] = (
                f"{platform} {kind}" if platform else kind
            )

    # The reaction emoji being ordered rides in the draft (round
    # 8.1, 14 Nov 2026): the service picker matches the exact
    # family (👍 -> thumbs up / like) instead of guessing. It comes
    # from this message first, else from the stored draft, and is
    # dropped when the order stops being about reactions.
    if "reaction" in (merged.get("service_hint") or "").lower():
        merged["reaction_emoji"] = (
            reaction_emoji(text) or stored.get("reaction_emoji")
        )
    else:
        merged["reaction_emoji"] = None

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
    link_from_last = False
    if (not merged.get("link") and mentions_that_link(text)) or same_service:
        last = await resolve_last_order(user.id)
        if last:
            if not merged.get("link") and mentions_that_link(text):
                merged["link"] = last.get("link")
                link_from_last = True
                last_service_id = last.get("service_id")
            if same_service and named_service_id is None:
                last_service_id = last.get("service_id")
                if last_service_id is not None:
                    named_service_id = last_service_id
                    merged["service_id"] = named_service_id

    # The full long service name is shown only when the user entered
    # a service ID (owner, 13 Nov 2026) — in this message, or in an
    # earlier turn of this order (remembered in PARTIAL). A service
    # from "same service as last time" is not an entered ID.
    named_by_id = bool(
        extract_service_id(text) is not None
        or intent.get("service_id") is not None
        or merged.get("named_by_id")
    )
    if named_by_id:
        merged["named_by_id"] = True

    # The link the user just pasted always wins (round 6,
    # 13 Nov 2026): the AI sometimes drops it, and then the flow
    # asks for the link again even though the user sent it — the
    # ask-link loop. A bare @handle message is a link too.
    text_links = extract_links(text)
    if text_links:
        merged["link"] = text_links[0]
    elif not merged.get("link"):
        handle = next(
            (tok for tok in (text or "").split() if tok.startswith("@")),
            None,
        )
        if handle is not None and handle.lower() != "@paxyo_bot":
            merged["link"] = handle
    # Cancelled-order guard (round 6): right after a cancel, the
    # AI sometimes returns the cancelled order's link/quantity from
    # conversation history even though the user typed nothing of the
    # sort — and the flow then auto-shows the cancelled Confirm
    # card. Only the exact cancelled values are dropped, and only
    # while the user has not typed them in this message (a link or
    # quantity the user just pasted is a deliberate fresh choice and
    # is kept). Values from the stored draft or from "that link" are
    # never touched. The record clears only when an order is placed
    # (see complete_order / place_order_now): a fresh link in a turn
    # that never becomes an order must not clear it (round 7), or
    # the AI can resurrect the cancelled link from history on the
    # next turn.
    cancelled_draft = CANCELLED_DRAFT.get(user.id) or {}
    if cancelled_draft:
        if (merged.get("link")
                and merged["link"] == cancelled_draft.get("link")
                and not _link_grounded_in_text(text, merged["link"])
                and not link_from_last):
            merged["link"] = stored.get("link")
        if (merged.get("quantity") is not None
                and merged["quantity"] == cancelled_draft.get("quantity")
                and not _quantity_grounded_in_text(
                    text, merged["quantity"])):
            merged["quantity"] = stored.get("quantity")
    # A metric change starts a fresh order: a link or quantity the
    # AI carried over from the old order's history is dropped unless
    # the user typed it in this message (round 7, 13 Nov 2026: after
    # a followers draft, "I want TikTok views" auto-showed a Confirm
    # card for the remembered link and quantity). A reply to the
    # bot's question is explicit context, not history, so it is
    # never dropped. "That link" is resolved after this and can
    # still bring the last order's link back.
    if metric_changed and quoted_text is None:
        if merged.get("link") and not _link_grounded_in_text(
            text, merged.get("link")
        ):
            merged["link"] = None
        if (merged.get("quantity") is not None
                and not _quantity_grounded_in_text(
                    text, merged.get("quantity"))):
            merged["quantity"] = None
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
    # A link for the wrong kind of thing (round 6, 13 Nov 2026): a
    # profile link for views/likes, or a video link for followers.
    # Say so in one plain line and ask for the right link — never
    # loop "Please send the link" with no explanation. The bad link
    # is dropped from the draft so it cannot loop. TikTok links only:
    # TikTok URL shapes are unambiguous (vt.tiktok.com and /video/
    # are a video; tiktok.com/@user is a profile), while other
    # platforms' links serve several metrics and the provider
    # confirms the order on the Confirm card.
    if (merged.get("link") and merged.get("service_hint")
            and platform_from_link(merged["link"]) == "tiktok"):
        _need = metric_content_kind(merged["service_hint"])
        _have = link_content_kind(merged["link"])
        if _need is not None and _have is not None and _need != _have:
            _metric = kind_from_text(merged["service_hint"]) or "services"
            _dropped = dict(merged)
            _dropped.pop("link", None)
            PARTIAL[user.id] = {
                k: v for k, v in _dropped.items() if v is not None
            }
            _key = (
                "link_kind_video_for_profile"
                if _need == "profile"
                else "link_kind_profile_for_video"
            )
            await reply_message(
                update.message, t(_key, lang, metric=_metric),
                lang, voice=voice,
            )
            return

    # A question about an order awaiting Confirm ("how fast can you
    # deliver it?") is answered from the pending service — the order
    # stays open and the Confirm card stays up. The PARTIAL branch
    # below already answers questions about an order being built;
    # this one covers the Confirm card. Placed before the "nothing
    # to work with" check, or the question would fall through to
    # the busy line while the AI is down.
    if not merged.get("link") and not merged.get("quantity"):
        _cid, _pending = pending_for_user(user.id)
        if _pending is not None:
            question = pending_order_question(
                text, _pending.get("quantity")
            )
            if question is not None:
                answer = pending_confirm_answer(
                    _pending.get("service"), question, lang
                )
                if answer is not None:
                    await reply_message(
                        update.message, answer, lang, voice=voice
                    )
                    return

    # A new quantity for the order already awaiting Confirm ("could I
    # get 200 views instead?") updates that card — the link and the
    # service are already known, so the bot never asks for the link
    # again (13 Nov 2026 — it did ask, and the user had to paste the
    # link a second time). A different platform or kind is a new
    # order, not a change, and still asks for its link. The quantity
    # must be typed in THIS message (live bug, 14 Nov 2026: the AI
    # carried the pending quantity forward from history, so an emoji
    # switch arrived with quantity=10 and re-issued the same card
    # here instead of reaching the correction below).
    if not merged.get("link") and merged.get("quantity"):
        _cid, _pending = pending_for_user(user.id)
        if (
            _pending is not None
            and _is_quantity_change(text, merged, _pending)
            and _quantity_grounded_in_text(text, merged["quantity"])
        ):
            service = _pending["service"]
            new_qty = int(merged["quantity"])
            error = validate_quantity(new_qty, service)
            if error:
                await reply_message(
                    update.message,
                    t(
                        "bad_quantity", lang,
                        service=short_service_name(service.get("name")),
                        min=service.get("min"), max=service.get("max"),
                    ),
                    lang, voice=voice,
                )
                return
            _pending["quantity"] = new_qty
            _pending["total"] = estimated_total_etb(
                float(service.get("rate_etb_per_1000", 0)), new_qty
            )
            _sent = await reply_message(
                update.message,
                confirm_card_text(
                    lang, service, new_qty, _pending["total"],
                    _pending["link"],
                    note=t("change_note", lang, quantity=new_qty),
                    full_name=_pending.get("full_name", False),
                ),
                lang,
                reply_markup=confirm_keyboard(_cid),
            )
            _remember_card_message(_pending, update.message, _sent)
            return

    # A different reaction emoji for the order already awaiting
    # Confirm ("I want only 🙏 reaction") re-picks the service for
    # that emoji and shows a NEW card — never the old card
    # unchanged (owner, 14 Nov 2026: a 🙏 correction re-showed the
    # Positive mix card). See try_reaction_correction.
    if await try_reaction_correction(update, text, lang, voice=voice):
        return

    # Nothing to work with at all: not understood. (A bare number or a
    # bare link with no context still counts as something: it is stored
    # and the bot asks for the next missing piece below.)
    if is_order_now(text) and intent_type != "order" and not merged.get("platform") and not merged.get("service_hint") and not merged.get("link"):
        await reply_message(update.message, t("ask_platform", lang), lang, voice=voice)
        return
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
        question = pending_order_question(text, stored.get("quantity"))
        if question is not None:
            try:
                services = await paxyo.services()
            except Exception as exc:
                log.warning("pending-question services failed: %s", exc)
                services = []
            picks = pick_services(
                services, platform=stored.get("platform"),
                service_hint=stored.get("service_hint"),
                reaction_emoji=stored.get("reaction_emoji"),
            ) if services else []
            if picks:
                service = picks[0]
                name = short_service_name(service.get("name"))
                if question == "speed":
                    avg = service.get("average_time")
                    if parse_average_time(avg) is not None:
                        answer = t("pending_speed", lang, service=name, avg=avg)
                    else:
                        answer = t("pending_speed_unknown", lang, service=name)
                else:
                    # Owner, 14 Nov 2026: Telegram reactions,
                    # Telegram views and Facebook reactions never
                    # drop — say so instead of the refill line.
                    kind = _service_never_drop_kind(service)
                    if kind is not None:
                        answer = t("never_drop", lang, service=kind)
                    else:
                        low = str(service.get("name") or "").lower()
                        if "no refill" in low:
                            refill = t("pending_no_refill", lang)
                        elif "refill" in low:
                            refill = t("pending_has_refill", lang)
                        else:
                            refill = t("pending_refill_unknown", lang)
                        answer = t(
                            "pending_drop", lang, service=name, refill=refill
                        )
                await reply_message(update.message, answer, lang, voice=voice)
                return
    if not merged.get("link"):
        PARTIAL[user.id] = {k: v for k, v in merged.items() if v is not None}
        # The emoji was the reaction choice (round 8.1, 14 Nov
        # 2026): acknowledge it first, then ask for the link —
        # never the stock link line on its own.
        _emoji = merged.get("reaction_emoji")
        if _emoji and "reaction" in (merged.get("service_hint") or "").lower():
            _reply = t("emoji_ack_order", lang, emoji=_emoji)
        else:
            _reply = ask_link_text(
                merged.get("platform"), merged.get("service_hint"), lang
            )
        # A price question that reached this far (the direct price
        # answer above found no service, or the catalogue hiccuped)
        # still gets its price in the very reply that asks for the
        # link — the price is deterministic code, never left to the
        # AI's wording (live bug, 14 Nov 2026: DeepSeek's reply
        # asked for the link with no price at all). The line is
        # only prepended when a service can actually be named, so
        # it can never duplicate a price already in the reply —
        # neither template above carries one.
        if is_price_question(text):
            _line, _p, _h = await _price_line(
                user.id, text, merged.get("platform"),
                merged.get("service_hint"), merged.get("quantity"),
                lang, reaction_emoji=merged.get("reaction_emoji"),
            )
            if _line is not None:
                _reply = _line + "\n" + _reply
        await reply_message(update.message, _reply, lang, voice=voice)
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
    # The full long service name is shown only when the user
    # entered a service ID (owner, 13 Nov 2026) — tracked above,
    # across turns of this order.
    show_full_name = bool(merged.get("named_by_id"))
    # Explicit "order now" (owner override, 13 Nov 2026): a fully
    # specified order is placed at once, no Confirm card. If it
    # cannot be placed (ambiguous metric, missing detail), fall
    # through to the normal Confirm card below.
    if is_order_now(text) and merged.get("link") and merged.get("quantity"):
        placed = await place_order_now(
            update.message, user.id, merged, lang,
            named_service_id=named_service_id,
            last_service_id=last_service_id,
            note="\n".join(notes) if notes else None,
            show_full_name=show_full_name,
        )
        if placed:
            return
    await complete_order(
        update.message, user.id, merged, lang, voice=voice,
        named_service_id=named_service_id,
        last_service_id=last_service_id,
        note="\n".join(notes) if notes else None,
        show_full_name=show_full_name,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Text in -> text out, always. The bot never answers a text
    # message with a voice message (handle_order_text gets voice=False).
    if _update_seen(update):
        return
    # A reply/quote (owner, 13 Nov 2026): when the user replies to
    # one of the bot's own messages, the quoted text is passed on so
    # the reply is read in that context ("1000" to "How many?" is
    # the quantity). Replies to anyone else's message are ignored.
    quoted = getattr(update.message, "reply_to_message", None)
    quoted_text = None
    if quoted is not None:
        sender = getattr(quoted, "from_user", None)
        if sender is None or getattr(sender, "is_bot", False):
            quoted_text = getattr(quoted, "text", None) or None
    await handle_order_text(
        update, context, update.message.text or "", quoted_text=quoted_text
    )


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A voice message (owner, 13 Nov 2026): download it, transcribe
    it with Groq Whisper, SHOW the transcription ("You said: ...")
    so the user can see what the bot heard, then handle the
    transcribed text exactly like the same typed message. The old
    handler lumped download and transcription into one try block,
    so a download failure looked like a transcription failure and
    an exception inside handle_order_text could go silent — both
    are separate now, and the flow is wrapped so it can never go
    silent. Replies are text: the bot does not claim to take orders
    by voice (owner, 13 Nov 2026), so voice=False."""
    if _update_seen(update):
        return
    user = update.effective_user
    lang = lang_of("", user.language_code)
    try:
        voice_file = await update.message.voice.get_file()
        audio = bytes(await voice_file.download_as_bytearray())
    except Exception as exc:
        _log_ai_failure("voice download failed", exc)
        await update.message.reply_text(t("voice_download_failed", lang))
        return
    try:
        text = await transcribe_voice_with_retry(
            audio, user.id, user.language_code
        )
    except Exception as exc:
        _log_ai_failure("voice transcription failed", exc)
        await update.message.reply_text(t("transcribe_failed", lang))
        return
    if not text:
        await update.message.reply_text(t("transcribe_failed", lang))
        return
    await update.message.reply_text(
        t("voice_heard", lang, text=text.strip())
    )
    try:
        await handle_order_text(update, context, text, voice=False)
    except Exception as exc:
        log.exception("voice order flow failed: %s", exc)
        await update.message.reply_text(t("not_understood", lang))


async def on_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A video note (round face message) carries no transcription:
    one plain line, never silence."""
    if _update_seen(update):
        return
    lang = lang_of("", update.effective_user.language_code)
    await update.message.reply_text(t("voice_video_note", lang))


# ------------------------------------------- context-aware media ----
# Media replies (owner, 14 Nov 2026): the bot responds like a
# person to emoji, GIFs, stickers and photos — differently each
# time, understanding the situation from context and memory. A
# media reaction is a reply, not a reset: it never loses a
# half-built order or a pending Confirm card, and it never
# invents an order that does not exist.
#
# Mood comes from the emoji (a bare emoji, or a sticker's emoji);
# a GIF carries no emoji, so its mood comes from the situation
# instead — a GIF while an order is delayed gets the delay reply,
# a GIF while an order is on track gets a warm reply, never an
# apology for a delay that has not happened (owner, 14 Nov 2026).
# The situation comes from the real order state: the most recent
# placed order's status and average time, a pending Confirm card,
# a half-built draft, or nothing at all.
_MEDIA_MOODS = {
    "😤": "frustrated", "😡": "frustrated", "🤬": "frustrated",
    "😩": "frustrated", "😠": "frustrated", "😖": "frustrated",
    "😫": "frustrated", "😭": "frustrated", "😢": "frustrated",
    "🎉": "happy", "🥳": "happy", "😍": "happy", "❤️": "happy",
    "😄": "happy", "😁": "happy", "😀": "happy", "😃": "happy",
    "🙂": "happy", "😊": "happy", "👍": "happy", "👏": "happy",
    "😂": "happy", "🤣": "happy",
    "🙏": "thanks",
    # A wave is a greeting, not thanks (owner, 14 Nov 2026 — a 👋
    # sticker got "You're welcome!"): 👋, 🙋 and ✋ all greet.
    "👋": "greeting", "🙋": "greeting", "✋": "greeting",
}


def media_mood(emoji):
    """The mood of one emoji (\"frustrated\" / \"happy\" /
    \"thanks\" / \"greeting\"), or None when it carries no mood."""
    return _MEDIA_MOODS.get(emoji)


def _bare_non_reaction_emoji(text):
    """The emoji when the message IS just one non-reaction emoji
    (\"😤\", \"🎉\", \"👋\"), else None. Reaction emoji (👍 ❤️ 🔥
    🙏 😍 ...) take the reactions path instead, so they never
    reach this branch."""
    s = (text or "").strip()
    if not s or reaction_emoji(s) is not None:
        return None
    for emoji in _MEDIA_MOODS:
        if s.replace("\ufe0f", "") == emoji.replace("\ufe0f", ""):
            return emoji
    return None


def _is_bare_emoji(text: str) -> bool:
    """True when the message is only emoji — one emoji, or a short
    run of them (\"😂😂\"). Variation selectors, skin tones,
    joiners and keycap marks are stripped first; letters, digits
    and punctuation all fail, so a word or a link never counts.
    Used by the catch-all in handle_order_text: a bare emoji the
    reactions path does not claim (👀, 💔, 🤗, ...) must never
    fall through to \"I did not understand\" (owner, 14 Nov 2026
    — \"he also misunderstood the emoji\")."""
    s = (text or "").strip()
    if not s:
        return False
    s = re.sub(r"[\ufe0f\u200d\U0001f3fb-\U0001f3ff\u20e3]", "", s)
    if not s:
        return False
    return all(
        "\U0001f000" <= ch <= "\U0001faff"
        or "\u2600" <= ch <= "\u27bf"
        or "\u2190" <= ch <= "\u21ff"
        or "\u2300" <= ch <= "\u23ff"
        or "\u2b00" <= ch <= "\u2bff"
        for ch in s
    )


# The reply variants, per mood x situation, English + Amharic.
# {order_id}, {service}, {status}, {total} come from the real
# order state; {time} is \", usually about <average time>\" when
# the average time is known, else empty — the bot never says
# \"soon\" and never invents a time. Variants rotate per user, so
# the same user never gets the same canned line twice in a row.
_MEDIA_REPLIES = {
    "frustrated_delayed": {
        "en": [
            "I'm really sorry it's taking so long — your order #{order_id} ({service}) is still {status}{time}.",
            "I hear you — that wait is frustrating. Your order #{order_id} is still {status}{time}.",
            "Sorry about the delay — your order #{order_id} ({service}) is still {status}{time}. It hasn't been forgotten.",
        ],
        "am": [
            "ይቅርታ — በጣም ዘግይቷል። orderዎ #{order_id} ({service}) አሁንም {status} ላይ ነው{time}።",
            "ገብቶኛል — መጠበቁ አስቸጋሪ ነው። orderዎ #{order_id} አሁንም {status} ላይ ነው{time}።",
            "ስለ መዘግየቱ ይቅርታ — orderዎ #{order_id} ({service}) አሁንም {status} ላይ ነው{time}።",
        ],
    },
    "frustrated_failed": {
        "en": [
            "That's not OK — your last order ({service}) didn't go through. Want me to place it again?",
            "I'm sorry about that — your last order ({service}) failed. I can place it again for you, just say the word.",
        ],
        "am": [
            "ይህ ትክክል አይደለም — የመጨረሻው orderዎ ({service}) አልተሳካም። እንደገና ልጀምር?",
            "ይቅርታ — የመጨረሻው orderዎ ({service}) አልተሳካም። ከፈለጉ እንደገና እጀምራለሁ።",
        ],
    },
    "frustrated_awaiting_confirm": {
        "en": [
            "I hear you — your order ({service}, {total} ETB) is ready and waiting for your Confirm. Tap Confirm and I'll place it right away.",
            "Sorry for the wait — your order ({service}, {total} ETB) is built, it just needs your Confirm to go.",
        ],
        "am": [
            "ገብቶኛል — orderዎ ({service}, {total} ETB) ዝግጁ ነው፣ Confirm ብቻ ነው የሚጠብቀው። Confirm ይጫኑና አስቀምጣለሁ።",
            "ስለ መጠበቁ ይቅርታ — orderዎ ({service}, {total} ETB) ተዘጋጅቷል፣ Confirm ብቻ ነው የሚቀረው።",
        ],
    },
    "frustrated_draft": {
        "en": [
            "I hear you — your order isn't finished yet. Send the link and I'll place it right away.",
            "Sorry about that — we're still building your order. Send the link and I'll get it going.",
        ],
        "am": [
            "ገብቶኛል — orderዎ ገና አልተጠናቀቀም። Link ይላኩልኝና አስቀምጣለሁ።",
            "ይቅርታ — orderዎን ገና እየገነባን ነው። Link ይላኩልኝና እጀምራለሁ።",
        ],
    },
    "frustrated_none": {
        "en": [
            "I hear you — that sounds frustrating. I don't see an order from you right now — tell me what happened and I'll sort it out.",
            "Sorry you're dealing with that. I don't have an order from you at the moment — what were you trying to order?",
        ],
        "am": [
            "ገብቶኛል — አስቸጋሪ ነው። አሁን ምንም order አላየሁም — ምን እንደተፈጠረ ንገሩኝ።",
            "ይቅርታ — አሁን ምንም order አልያዝኩም — ምን ማዘዝ ይፈልጋሉ?",
        ],
    },
    "happy_completed": {
        "en": [
            "🎉 It worked — your order #{order_id} ({service}) is done! Enjoy!",
            "Yes! Your order #{order_id} is complete — {service} delivered. 🎉",
            "There it is — order #{order_id} ({service}) finished! 🎉",
        ],
        "am": [
            "🎉 ተሳክቷል — orderዎ #{order_id} ({service}) ተጠናቋል! ይደሰቱ!",
            "አዎ! orderዎ #{order_id} ተጠናቋል — {service} ተደርሷል። 🎉",
            "እነሆ — orderዎ #{order_id} ({service}) ተጠናቋል! 🎉",
        ],
    },
    "happy_other": {
        "en": [
            "😄 Glad to hear it! What would you like to order next?",
            "Haha, love that! Tell me what you need next.",
        ],
        "am": [
            "😄 ደስ ብሎኛል! ቀጥሎ ምን ማዘዝ ይፈልጋሉ?",
            "😄 በጣም ጥሩ ነው! ቀጥሎ ምን ይፈልጋሉ?",
        ],
    },
    "thanks": {
        "en": [
            "You're welcome! 😊 Anything else you need?",
            "Anytime! 😊 Just tell me what you'd like to order.",
        ],
        "am": [
            "እንኳን ደህና መጡ! 😊 ሌላ ምን ይፈልጋሉ?",
            "በደስታ! 😊 ምን ማዘዝ ይፈልጋሉ?",
        ],
    },
    # A wave is a greeting, not thanks (owner, 14 Nov 2026 — a 👋
    # sticker got "You're welcome!"): 👋, 🙋 and ✋ all greet.
    "greeting": {
        "en": [
            "Hello! 👋 Great to see you — what would you like to order?",
            "Hi there! 👋 Tell me what you need and I'll get it going.",
        ],
        "am": [
            "ሰላም! 👋 ደስ ብሎኛል — ምን ማዘዝ ይፈልጋሉ?",
            "ሰላም! 👋 ምን እንደሚፈልጉ ንገሩኝ።",
        ],
    },
    # Frustrated, but the order is on track (owner, 14 Nov 2026):
    # acknowledge the feeling and reassure with the real status —
    # never apologise for a delay that has not happened.
    "frustrated_on_track": {
        "en": [
            "I hear you — your order #{order_id} ({service}) is still {status}{time}, right on track. Hang in there.",
            "I get it — waiting is hard. Your order #{order_id} is still {status}{time}, on track.",
        ],
        "am": [
            "ገብቶኛል — orderዎ #{order_id} ({service}) አሁንም {status} ላይ ነው{time}፣ በተገቢው መንገድ እየሄደ ነው።",
            "ገብቶኛል — መጠበቁ አስቸጋሪ ነው። orderዎ #{order_id} አሁንም {status} ላይ ነው{time}፣ እየሄደ ነው።",
        ],
    },
    "neutral_on_track": {
        "en": [
            "Your order #{order_id} ({service}) is still {status}{time} — right on track.",
            "Still going — order #{order_id} is {status}{time}, on track.",
        ],
        "am": [
            "orderዎ #{order_id} ({service}) አሁንም {status} ላይ ነው{time} — በተገቢው መንገድ እየሄደ ነው።",
            "ገና በመሄድ ላይ ነው — orderዎ #{order_id} {status} ላይ ነው{time}።",
        ],
    },
    "neutral_delayed": {
        "en": [
            "Your order #{order_id} ({service}) is still {status}{time}. I'll keep an eye on it.",
            "Still going — order #{order_id} is {status}{time}.",
        ],
        "am": [
            "orderዎ #{order_id} ({service}) አሁንም {status} ላይ ነው{time}። እከታተላለሁ።",
            "ገና በመሄድ ላይ ነው — orderዎ #{order_id} {status} ላይ ነው{time}።",
        ],
    },
    "neutral_completed": {
        "en": [
            "🎉 Your order #{order_id} ({service}) is complete!",
            "Good news — order #{order_id} ({service}) finished! 🎉",
        ],
        "am": [
            "🎉 orderዎ #{order_id} ({service}) ተጠናቋል!",
            "ጥሩ ዜና — orderዎ #{order_id} ({service}) ተጠናቋል! 🎉",
        ],
    },
    "neutral_awaiting_confirm": {
        "en": [
            "Your order ({service}, {total} ETB) is still waiting for Confirm — tap it when you're ready.",
            "Just a reminder — your order ({service}) is built and waiting for your Confirm.",
        ],
        "am": [
            "orderዎ ({service}, {total} ETB) Confirm እየጠበቀ ነው — ሲዘጋጁ ይጫኑት።",
            "ማስታወሻ — orderዎ ({service}) ተዘጋጅቶ Confirm እየጠበቀ ነው።",
        ],
    },
    "neutral_none": {
        "en": [
            "😄 Nice one! What would you like to order?",
            "😄 Haha, good one! What would you like to order?",
        ],
        "am": [
            "😄 ጥሩ ነው! ምን ማዘዝ ይፈልጋሉ?",
            "😄 አዝናኝ ነው! ምን ማዘዝ ይፈልጋሉ?",
        ],
    },
}

# (user_id, reply group) -> how many times that group was used:
# the rotation counter, so the same user never gets the same
# canned line twice in a row. Cleared with the per-user state in
# tests.
MEDIA_REPLY_COUNT = {}


def media_reply_text(user_id: int, mood, ctx: dict, lang: str) -> str:
    """The reply for a media reaction: mood x situation, rotating
    the variants per user. `ctx` is media_order_context's dict."""
    situation = ctx.get("situation") or "none"
    if mood == "frustrated":
        group = f"frustrated_{situation}"
    elif mood == "happy":
        group = (
            "happy_completed" if situation == "completed"
            else "happy_other"
        )
    elif mood == "thanks":
        group = "thanks"
    elif mood == "greeting":
        group = "greeting"
    else:
        group = {
            "delayed": "neutral_delayed",
            "completed": "neutral_completed",
            "failed": "frustrated_failed",
            "awaiting_confirm": "neutral_awaiting_confirm",
            "on_track": "neutral_on_track",
        }.get(situation, "neutral_none")
    variants = _MEDIA_REPLIES.get(group, _MEDIA_REPLIES["neutral_none"])
    texts = variants.get(lang) or variants["en"]
    key = (user_id, group)
    idx = MEDIA_REPLY_COUNT.get(key, 0)
    MEDIA_REPLY_COUNT[key] = idx + 1
    template = texts[idx % len(texts)]
    avg = ctx.get("avg")
    if lang == "am":
        time = (
            f"፣ አብዛኛውን ጊዜ {avg} ያህል ይወስዳል" if avg else ""
        )
    else:
        time = f", usually about {avg}" if avg else ""
    total = ctx.get("total")
    total = format_money(total) if isinstance(total, (int, float)) else ""
    return template.format(
        order_id=ctx.get("order_id") or "",
        service=ctx.get("service") or "",
        status=ctx.get("status") or "",
        total=total,
        time=time,
    )


def _parse_created_at(value):
    """An ISO-8601 created_at string -> aware datetime, or None
    when the value is missing or unparseable."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _order_is_delayed(order, avg_minutes):
    """True when an in-progress order is past its average time.
    Unknown created_at or unknown average time -> True: the old
    behaviour assumed the user was waiting, and a delay apology
    is the safe reply when the bot genuinely cannot tell."""
    if avg_minutes is None:
        return True
    created = _parse_created_at(order.get("created_at"))
    if created is None:
        return True
    elapsed = (datetime.now(timezone.utc) - created).total_seconds() / 60
    return elapsed > avg_minutes


async def media_order_context(user_id: int) -> dict:
    """The order situation a media reply is grounded in: the most
    recent placed order's real status and average time (same data
    as the \"why hasn't it started\" answer), a pending Confirm
    card, a half-built draft, or nothing at all. Never invents an
    order — \"none\" means no order is claimed. An in-progress
    order is \"delayed\" only when its elapsed time is past its
    average time (owner, 14 Nov 2026 — a GIF while order #1837
    was merely in progress got a delay apology); otherwise it is
    \"on_track\"."""
    try:
        last = await resolve_last_order(user_id)
    except Exception as exc:
        log.warning("media order context failed: %s", exc)
        last = None
    if last:
        status = str(last.get("status") or "").strip().lower()
        service_id = last.get("service_id")
        service_name = last.get("service_name")
        avg = None
        if service_id is not None:
            try:
                services = await paxyo.services()
                found = find_service_by_id(services, service_id)
                if found is not None:
                    avg = found.get("average_time")
                    service_name = found.get("name")
            except Exception as exc:
                log.warning("media order context services failed: %s", exc)
        if status in ("completed", "complete"):
            situation = "completed"
        elif status in (
            "pending", "in_progress", "in progress",
            "processing", "partial",
        ):
            situation = (
                "delayed"
                if _order_is_delayed(last, parse_average_time(avg))
                else "on_track"
            )
        elif status in ("failed", "cancelled", "canceled", "refunded"):
            situation = "failed"
        else:
            situation = "none"
        return {
            "situation": situation,
            "order_id": last.get("id") or last.get("order_id"),
            "status": status,
            "service": (
                short_service_name(service_name)
                or f"service {service_id}"
            ),
            "avg": avg, "total": last.get("charge"),
        }
    _cid, _pending = pending_for_user(user_id)
    if _pending is not None:
        service = _pending.get("service") or {}
        return {
            "situation": "awaiting_confirm",
            "service": short_service_name(service.get("name")) or "your order",
            "total": _pending.get("total"),
            "order_id": None, "status": None, "avg": None,
        }
    if PARTIAL.get(user_id):
        return {
            "situation": "draft", "service": None,
            "order_id": None, "status": None, "avg": None,
        }
    return {
        "situation": "none", "service": None,
        "order_id": None, "status": None, "avg": None,
    }


async def media_reply(update, emoji, lang: str, voice: bool = False) -> str:
    """Answer one media reaction (GIF, sticker, bare emoji) from
    the user's situation, and return the text sent. Reads order
    state only — it never clears a draft or a Confirm card.
    The mood comes from the emoji when there is one; a GIF
    carries no emoji, so the situation sets the mood — a GIF
    while an order is delayed or failed is frustration, a GIF
    after a completed order is celebration, and a GIF while an
    order is on track is celebration too, never an apology for a
    delay that has not happened (owner, 14 Nov 2026). Photos are
    NOT routed here: they are read by Gemini vision
    (route_photo_result) and keep working as before."""
    user = update.effective_user
    mood = media_mood(emoji)
    ctx = await media_order_context(user.id)
    if mood is None:
        situation = ctx.get("situation")
        if situation in ("delayed", "failed"):
            mood = "frustrated"
        elif situation in ("completed", "on_track"):
            mood = "happy"
    text = media_reply_text(user.id, mood, ctx, lang)
    if voice:
        await reply_message(update.message, text, lang, voice=voice)
    else:
        await update.message.reply_text(text)
    return text


async def media_reply_for_text(update, emoji, lang: str, voice: bool = False) -> bool:
    """A bare non-reaction emoji in handle_order_text: answer it
    from the user's situation. Always True when called — the
    caller returns."""
    await media_reply(update, emoji, lang, voice=voice)
    return True


async def on_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A GIF (owner, 13 Nov 2026): never silent, never
    'I did not understand'. A caption is the user's message and is
    handled normally; otherwise the reply depends on the user's
    situation (owner, 14 Nov 2026) — a delayed order gets empathy
    and the real status, a completed order gets a celebration, no
    order gets a varied friendly steer back to ordering."""
    if _update_seen(update):
        return
    caption = (update.message.caption or "").strip()
    if caption:
        await handle_order_text(update, context, caption)
        return
    user = update.effective_user
    lang = LAST_LANG.get(user.id) or lang_of("", user.language_code)
    await media_reply(update, None, lang)


async def on_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A sticker (owner, 13 Nov 2026): same as a GIF — a caption is
    the user's message; otherwise the reply depends on the
    sticker's emoji and the user's situation, like a GIF."""
    if _update_seen(update):
        return
    caption = (update.message.caption or "").strip()
    if caption:
        await handle_order_text(update, context, caption)
        return
    user = update.effective_user
    lang = LAST_LANG.get(user.id) or lang_of("", user.language_code)
    sticker = getattr(update.message, "sticker", None)
    emoji = getattr(sticker, "emoji", None) if sticker else None
    await media_reply(update, emoji, lang)


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
        _log_ai_failure("ai_vision failed", exc)
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
        # The stored order (PARTIAL) may still know the metric the
        # failed message dropped ("tiktok views"): use it, so the
        # fallback picks the fastest VIEWS service, never the
        # globally fastest service for the platform.
        stored = PARTIAL.get(user.id) or {}
        if not merged.get("service_hint") and stored.get("service_hint"):
            merged["service_hint"] = stored["service_hint"]
        if not merged.get("platform") and stored.get("platform"):
            merged["platform"] = stored["platform"]
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
        name = short_service_name(sched.get("service_name")) or f"service {sched.get('service_id')}"
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
            # Cancelling clears the stored order state (round 6,
            # 13 Nov 2026): a fresh order after this starts from
            # scratch instead of auto-showing the cancelled card.
            clear_order_state(user.id, cancelled=pending)
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
        summary = t(
            "order_summary",
            lang,
            service=result["service"],
            quantity=result["quantity"],
            link=result["link"],
            total=format_money(result["total"]),
            order_id=result["order_id"],
            status=result["status"],
        )
        await query.edit_message_text(summary + "\n" + humor_line(user.id, lang))
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
                service=short_service_name(rec_draft["service"].get("name")),
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
    name = short_service_name(service.get("name"))
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
    app.add_handler(MessageHandler(filters.VIDEO_NOTE, on_video_note))
    app.add_handler(MessageHandler(filters.ANIMATION, on_animation))
    app.add_handler(MessageHandler(filters.Sticker.ALL, on_sticker))
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
