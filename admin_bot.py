#!/usr/bin/env python3
"""Paxyo admin chat bot — a BRAND-NEW bot, NOT @paxadmin_bot.

William (15 Nov 2026, 07:12 EAT) decided this is a new bot: @paxadmin_bot
is Abel's / already taken, so this bot gets its own token (created later
in BotFather) and reads it from env ADMIN_BOT_TOKEN — never hardcoded,
never in git. The code works with whichever token is eventually set.

What it does, for William only (English only, like the admin panel):
  1. LIVE QUESTIONS — "how much did we make today?", "how many users
     in the last 7 days?", orders / deposits / top service. Numbers come
     from GET /admin/stats on paxyo.et (the same endpoint the daily
     digest uses); until that endpoint is live, the bot says honestly
     that it is not connected yet and never invents a number.
  2. TARGETED BROADCASTS FROM CHAT — "send this to users who never
     deposited: <message>". The bot counts the matching users via
     GET /broadcasts/audience, shows the count + the exact message,
     William taps Confirm, and only then the bot sends (sequentially,
     via this bot's own token) and reports delivered / failed counts.
  3. SETTINGS CHANGES FROM CHAT — "change ticker display to ...".
     The bot shows exactly what will change, William taps Confirm,
     and only then it writes the setting via POST /admin/settings.
     Ticker first; the endpoint is generic by key, other settings
     follow the same call.
  4. REFUNDS FROM CHAT — "refund order #1841". The bot looks the
     order up (GET /orders/{id}), shows id / service / quantity /
     total / status / owner, William taps Confirm, and only then it
     mints an HMAC confirm token and calls POST
     /admin/orders/{id}/refund. The full total goes back to the
     user's Paxyo balance (never cash), once, never twice, never
     for a completed order.
  5. PROMO-CODE CREATION FROM CHAT — "create promo code PAXYO20
     20%". The bot shows the code + percent (+ expiry / max uses
     when given), William taps Confirm, and only then it calls
     POST /promo-codes.
  6. WIN-BACK MESSAGES — /winbacks. Users with no order in 14+
     days: the bot shows the COUNT first, William taps Confirm,
     and only then it sends one personal message each (their usual
     service named, never an order placed, never a Confirm card
     to the user), then records the sends so nobody is messaged
     twice in 30 days.
  7. MORNING MONEY REPORT — /morning, on demand, plus one
     automatic send a day at 8am EAT on a proper schedule (the
     loop sleeps until the next 08:00 EAT): yesterday's revenue,
     net profit, new users, top service, deposits count, all from
     GET /admin/stats?day=yesterday. Exact 8am delivery needs the
     always-on server (Oracle move); on free Render the process
     sleeps and the report goes out on the next wake after 8am
     instead. The once-a-day marker lives on the server
     (POST /admin/morning-sent) so a restart after 8am cannot
     double-send; an in-memory marker is only the fallback when
     that endpoint is not live yet.

SAFETY (never break):
  * ONLY William can use it. Allowlist from env ADMIN_TELEGRAM_IDS
    (same pattern as bot.py's is_admin_user); EMPTY by default means
    the bot refuses EVERYONE until William's Telegram id is set.
  * EVERY change (broadcast, setting, refund, promo code) needs an
    explicit Confirm step — a Confirm tap or a typed "yes" while a
    preview is pending. Nothing sends, writes or refunds on a single
    message.
  * Refunds go through the Confirm-gated admin-refund endpoint
    (POST /admin/orders/{id}/refund, HMAC confirm token minted only
    after Confirm): once, never twice, never for a completed order,
    and only to the user's Paxyo balance — never cash, never a
    balance touched directly. Promo codes are created the same way:
    preview, Confirm, then POST /promo-codes. No other money
    movement happens here.
  * Never reveal provider names, buying costs, secrets, or the words
    "SMM panel". Only Paxyo selling prices exist, and this bot does
    not quote prices at all.
  * Reply language: English only.

UNDERSTANDING — deterministic parsing FIRST (regex/patterns for the
stats questions, broadcast commands, ticker changes, refund
commands and promo-code creation), AI only for
free-form questions. The AI never triggers a broadcast, a setting
write, a refund or a promo-code creation: those go through the
deterministic Confirm flow only. The AI
is minimal — DeepSeek if DEEPSEEK_API_KEY is set, else Gemini if
GEMINI_API_KEY is set (same keys the order bot already uses); with
neither key set, free-form gets a short "I didn't understand — try
..." reply, never silence.

TECHNICAL — polling, not webhook (simplest on Render free, and no
webhook conflict with @paxorder_bot since this is a different bot /
token). python-telegram-bot, same library as bot.py; no new
dependency (requirements.txt is unchanged). A tiny health-check HTTP
server answers GET / with "ok" on $PORT so a Render free web service
stays up while polling. No Render service is created by this file.

Env vars (values NEVER recorded — only names):
  ADMIN_BOT_TOKEN   (required) — this bot's Telegram token, from BotFather
  BOT_API_SECRET    (required) — same secret as the order bot
  PAXYO_API_BASE    (default https://paxyo.et/api/bot)
  ADMIN_TELEGRAM_IDS (comma-separated; empty = refuses everyone)
  DEEPSEEK_API_KEY  (optional) — free-form answers only
  DEEPSEEK_MODEL    (default deepseek-chat)
  GEMINI_API_KEY    (optional) — free-form answers only, after DeepSeek
  GEMINI_MODEL      (default gemini-3.5-flash)
  SEND_DELAY_SECONDS (default 0.05) — pause between broadcast sends
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

log = logging.getLogger("admin_bot")

ADMIN_BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN", "") or ""
BOT_API_SECRET = os.environ.get("BOT_API_SECRET", "") or ""
PAXYO_API_BASE = os.environ.get("PAXYO_API_BASE", "https://paxyo.et/api/bot").rstrip("/")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "") or ""
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/v1"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or ""
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
SEND_DELAY_SECONDS = float(os.environ.get("SEND_DELAY_SECONDS", "0.05") or 0.05)

# Ethiopia is UTC+3 all year (no daylight saving).
EAT_TZ = timezone(timedelta(hours=3))

# In-memory fallback for the morning-report once-a-day marker:
# dates (YYYY-MM-DD, EAT) the report was already sent on, in this
# process. The server-side marker (POST /admin/morning-sent) is
# the authority; this set only covers the case where that endpoint
# is not live yet. Tests clear it in setUp/tearDown.
MORNING_SENT_DATES = set()

# The settings key for the ticker text. TO VERIFY on the server before
# go-live: check what key the site / mini app actually reads for the
# ticker (see S3 in server/api-admin-settings.php). If it is a
# different key, change this constant — the endpoint is generic and
# needs no change.
TICKER_SETTING_KEY = "ticker_text"

# Segments the audience endpoint understands (see
# server/api-admin-broadcasts.php — that file is the authority).
SEGMENTS = ("all", "never_deposited", "deposited", "service")

# ------------------------------------------------------------------ admin ---

def _admin_ids_from_env():
    """Telegram user ids allowed to use this bot, from the
    ADMIN_TELEGRAM_IDS env var (comma-separated). Empty by default:
    nobody may use it until William's id is configured."""
    raw = os.environ.get("ADMIN_TELEGRAM_IDS", "") or ""
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


ADMIN_TELEGRAM_IDS = _admin_ids_from_env()


def is_admin_user(user_id: int) -> bool:
    """True when this Telegram user may use the admin bot."""
    try:
        return int(user_id) in ADMIN_TELEGRAM_IDS
    except (TypeError, ValueError):
        return False


REFUSAL = "Sorry — this bot is only for the Paxyo owner."

# ------------------------------------------------------------- API client ---

def build_api_request(method: str, path: str, json_body=None) -> httpx.Request:
    """Build (never send) an authenticated Paxyo API request."""
    return httpx.Request(
        method,
        PAXYO_API_BASE + path,
        headers={"X-Bot-Secret": BOT_API_SECRET},
        json=json_body,
    )


class AdminPaxyoClient:
    """Async client for the Paxyo Bot API, admin endpoints only.

    admin_stats / broadcast_audience / set_setting are all
    404-tolerant the same way bot.py's client is: a 404 means the
    server endpoint is not live yet, so the caller answers honestly
    that it is not connected yet. Any other error raises."""

    def __init__(self):
        # trust_env=False: ignore any proxy env vars so the client
        # talks directly to paxyo.et (Render services have direct egress).
        self._client = httpx.AsyncClient(timeout=30.0, trust_env=False)

    async def _send(self, request: httpx.Request):
        response = await self._client.send(request)
        response.raise_for_status()
        return response.json()

    async def admin_stats(self, days: int = 1, day: str = None):
        """GET /admin/stats[?days=N | ?day=yesterday] — the digest
        numbers. `days` is the last N calendar days in EAT, today
        included (1 = today). `day="yesterday"` asks for yesterday's
        EAT calendar day only (the ?days=N windows always end
        today, so yesterday alone needs this parameter). 404 ->
        None (endpoint not live yet)."""
        path = "/admin/stats"
        if day == "yesterday":
            path = "/admin/stats?day=yesterday"
        elif days and int(days) > 1:
            path = f"/admin/stats?days={int(days)}"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def winback_audience(self, days: int = 14):
        """GET /winbacks/audience?days=N — users with >=1 order
        whose most recent order is more than N days ago, excluding
        users messaged in the last 30 days and users with a draft
        in progress. -> {days, count,
        users: [{telegram_id, usual_service, usual_quantity}]}.
        404 -> None (endpoint not live yet)."""
        path = f"/winbacks/audience?days={int(days)}"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def record_winbacks(self, telegram_ids):
        """POST /winbacks/record {telegram_ids: [...]} -> {ok,
        recorded}. Idempotent on the server (a re-record only
        refreshes sent_at). 404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request(
                    "POST",
                    "/winbacks/record",
                    {"telegram_ids": [int(t) for t in telegram_ids]},
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("POST /winbacks/record returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def morning_sent(self, date_str: str):
        """GET /admin/morning-sent?date=YYYY-MM-DD -> {date, sent}.
        404 -> None (endpoint not live yet — the caller falls back
        to the in-memory marker)."""
        path = f"/admin/morning-sent?date={date_str}"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def mark_morning_sent(self, date_str: str):
        """POST /admin/morning-sent {date} -> {ok, date, sent}.
        404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request(
                    "POST", "/admin/morning-sent", {"date": date_str}
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("POST /admin/morning-sent returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def broadcast_audience(self, segment: str, service_id=None):
        """GET /broadcasts/audience?segment=&service_id= — the
        audience contract (see server/api-admin-broadcasts.php):
        {segment, service_id, count, telegram_ids} with DISTINCT
        telegram_ids. 404 -> None (endpoint not live yet)."""
        path = f"/broadcasts/audience?segment={segment}"
        if service_id is not None:
            path += f"&service_id={int(service_id)}"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def set_setting(self, key: str, value: str):
        """POST /admin/settings {key, value} -> {ok, key, value}.
        404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request("POST", "/admin/settings", {"key": key, "value": value})
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("POST /admin/settings returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def get_order(self, order_id):
        """GET /orders/{id} — one order, for the refund preview. The
        record carries the owner's telegram id, which the refund
        POST needs, plus service / quantity / total / status.
        404 -> None (endpoint not live yet). Any other error raises."""
        try:
            data = await self._send(
                build_api_request("GET", f"/orders/{order_id}")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning(
                    "GET /orders/%s returned 404 (endpoint not live yet)",
                    order_id,
                )
                return None
            raise
        return _order_record(data)

    async def admin_refund_order(self, order_id, telegram_id,
                                 admin_telegram_id, confirm_token):
        """POST /admin/orders/{id}/refund {telegram_id (order owner),
        admin_telegram_id, confirm_token} -> the cancel-refund reply
        {ok, order_id, refunded_etb, provider_status, duplicate}.
        Errors raise — the caller maps 404/403/409/502 to the plain
        messages in server/api-admin-refund.php. (The contract is
        that file; the HMAC token is minted by
        mint_admin_refund_token, only after William taps Confirm.)"""
        return await self._send(
            build_api_request(
                "POST",
                f"/admin/orders/{order_id}/refund",
                {
                    "telegram_id": int(telegram_id),
                    "admin_telegram_id": int(admin_telegram_id),
                    "confirm_token": confirm_token,
                },
            )
        )

    async def create_promo_code(self, code, percent, expires_at=None,
                                max_uses=None):
        """POST /promo-codes {code, percent, expires_at?, max_uses?}
        -> {ok, code, percent, active, expires_at, max_uses}.
        404 -> None (endpoint not live yet). Any other error raises
        (409 = the code already exists)."""
        body = {"code": code, "percent": int(percent)}
        if expires_at is not None:
            body["expires_at"] = expires_at
        if max_uses is not None:
            body["max_uses"] = int(max_uses)
        try:
            data = await self._send(
                build_api_request("POST", "/promo-codes", body)
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("POST /promo-codes returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def services(self):
        """GET /services — the catalogue, only used to resolve a
        service NAME to its id for a service broadcast ("who bought
        TikTok views"). 404 -> [] (a name then needs an id)."""
        try:
            data = await self._send(build_api_request("GET", "/services"))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /services returned 404 (endpoint not live yet)")
                return []
            raise
        raw = data.get("services", data) if isinstance(data, dict) else data
        return raw if isinstance(raw, list) else []


# The live client, set in main(). Tests patch this object.
admin_api = None

# ------------------------------------------------------------ pending state ---

# One pending Confirm per admin user id. A broadcast entry:
#   {"kind": "broadcast", "segment": ..., "service_id": ...,
#    "service_label": "users who never deposited",
#    "message": <text or None while we are still asking for it>,
#    "telegram_ids": [...]}  (telegram_ids frozen at preview time —
#    the count shown is the count sent)
# A setting entry:
#   {"kind": "setting", "key": ..., "value": ...}
# A refund entry (preview already shown; the HMAC token is minted
# only when the Confirm runs, never before):
#   {"kind": "refund", "order_id": ..., "telegram_id": <order owner>}
# A promo-code entry:
#   {"kind": "promo", "code": ..., "percent": ...,
#    "expires_at": <"YYYY-MM-DD 23:59:59"|None>,
#    "max_uses": <int|None>}
# A win-back entry (audience frozen at preview time — the count
# shown is the count messaged):
#   {"kind": "winback",
#    "users": [{"telegram_id": ..., "usual_service": ...,
#               "usual_quantity": ...}, ...]}
PENDING = {}

CONFIRM_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Confirm", callback_data="admin_confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel"),
    ]
])

_YES_WORDS = {"yes", "confirm", "send it", "do it", "ok", "okay"}
_NO_WORDS = {"no", "cancel", "don't send", "dont send", "stop"}


def _is_confirm(text: str) -> bool:
    return (text or "").strip().lower() in _YES_WORDS


def _is_cancel(text: str) -> bool:
    return (text or "").strip().lower() in _NO_WORDS


def format_money(value) -> str:
    return f"{float(value):,.2f}"


# ------------------------------------------------------- deterministic parse ---

def parse_days(text: str) -> int:
    """How many days a stats question covers. Default 1 (today)."""
    s = (text or "").lower()
    m = re.search(r"last\s+(\d+)\s+days?", s)
    if m:
        try:
            return max(1, min(90, int(m.group(1))))
        except ValueError:
            return 1
    if "last week" in s or "this week" in s:
        return 7
    if "last month" in s or "this month" in s:
        return 30
    return 1


def parse_stats_question(text: str):
    """Deterministic stats-question parser. Returns
    {"kind": revenue|users|orders|deposits|top_service|summary,
     "days": N, "yesterday": bool} or None when the message is not
    a stats question. "Yesterday" is recognised but NOT supported
    by the endpoint (windows end today) — the answer says so."""
    s = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not s:
        return None
    yesterday = "yesterday" in s
    days = parse_days(s)
    if (
        "digest" in s
        or "daily summary" in s
        or "how are we doing" in s
        or "today's numbers" in s
        or "todays numbers" in s
        or "sales report" in s
        or s in ("report", "summary", "how is business", "how is business?")
    ):
        return {"kind": "summary", "days": days, "yesterday": yesterday}
    if "deposit" in s and (
        "how many" in s or "how much" in s or "total" in s or "today" in s
        or "last" in s or "this week" in s or "this month" in s
    ):
        return {"kind": "deposits", "days": days, "yesterday": yesterday}
    if (
        "top service" in s
        or "best selling" in s
        or "best-selling" in s
        or "most ordered" in s
        or "most popular" in s
        or "top seller" in s
    ):
        return {"kind": "top_service", "days": days, "yesterday": yesterday}
    if "how many users" in s or "new users" in s or "how many new" in s:
        return {"kind": "users", "days": days, "yesterday": yesterday}
    if "how many orders" in s:
        return {"kind": "orders", "days": days, "yesterday": yesterday}
    if (
        ("how much" in s and ("made" in s or "make" in s or "earn" in s))
        or "revenue" in s
        or "earnings" in s
        or "how much money" in s
    ):
        return {"kind": "revenue", "days": days, "yesterday": yesterday}
    return None


def _split_broadcast_message(text: str):
    """Split a broadcast command into (head, message). The message
    comes after a colon ("...: Hello!"), after "saying ..." or after
    "that says ...". Returns (text, None) when no message is inline."""
    s = (text or "").strip()
    m = re.search(r"\bsaying\s+(.+)$", s, re.IGNORECASE)
    if m:
        return s[: m.start()].strip(), m.group(1).strip()
    m = re.search(r"\bthat says\s+(.+)$", s, re.IGNORECASE)
    if m:
        return s[: m.start()].strip(), m.group(1).strip()
    if ":" in s:
        head, message = s.split(":", 1)
        message = message.strip().strip("\"'")
        if message:
            return head.strip(), message
    return s, None


def parse_broadcast_command(text: str):
    """Deterministic broadcast-command parser. Returns
    {"segment": ..., "service_id": int|None,
     "service_name": str|None, "service_label": ...,
     "message": str|None} or None when the message is not a
    broadcast command. `message` is None when the user did not put
    the message in the same text — the bot then asks for it."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = s.lower()
    if "send" not in low and "broadcast" not in low:
        return None
    head, message = _split_broadcast_message(s)
    head_low = head.lower()
    segment = None
    service_id = None
    service_name = None
    service_label = None
    # Service first: it carries the most specific words.
    m = re.search(
        r"(?:bought|ordered)\s+(?:service\s+#?(\d+)|#(\d+))", head_low
    )
    if m:
        segment = "service"
        service_id = int(m.group(1) or m.group(2))
        service_label = f"users who bought service {service_id}"
    else:
        m = re.search(r"(?:bought|ordered)\s+(.+)$", head_low)
        if m and ("user" in head_low or "customer" in head_low or "who" in head_low):
            name = m.group(1).strip()
            # A trailing "users"/"customers" word is not the name.
            name = re.sub(r"\s+(users|customers)$", "", name).strip()
            if name:
                segment = "service"
                service_name = name
                service_label = f"users who bought {name}"
    if segment is None:
        if re.search(
            r"never\s+(deposited|made a deposit|paid)|"
            r"(haven't|have never|never)\s+deposited|"
            r"no\s+deposit(\s+yet)?|"
            r"who\s+never\s+deposited",
            head_low,
        ):
            segment = "never_deposited"
            service_label = "users who never deposited"
        elif re.search(
            r"(have\s+)?deposited\s+(before|already)|who\s+deposited|"
            r"users\s+who\s+deposited",
            head_low,
        ):
            segment = "deposited"
            service_label = "users who deposited before"
        elif re.search(r"\ball users\b|\beveryone\b|\beverybody\b|\ball\b", head_low):
            segment = "all"
            service_label = "all users"
    if segment is None:
        return None
    return {
        "segment": segment,
        "service_id": service_id,
        "service_name": service_name,
        "service_label": service_label,
        "message": message,
    }


def resolve_service_id(name: str, services):
    """Resolve a service NAME to its provider id from the catalogue.
    Exact name match first, then a unique substring match. Returns
    the id, or None when there is no match or more than one."""
    if not name or not services:
        return None
    want = name.strip().lower()
    exact = []
    partial = []
    for svc in services or []:
        if not isinstance(svc, dict):
            continue
        svc_name = str(svc.get("name") or "").strip()
        if not svc_name:
            continue
        try:
            svc_id = int(svc.get("service", svc.get("id")))
        except (TypeError, ValueError):
            continue
        if svc_name.lower() == want:
            exact.append(svc_id)
        elif want in svc_name.lower():
            partial.append(svc_id)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    if len(partial) == 1:
        return partial[0]
    return None


def parse_ticker_change(text: str):
    """Deterministic ticker-change parser. Returns the new ticker
    text, or None when the message is not a ticker change."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    m = re.search(
        r"(?:change|set|update)\s+(?:the\s+)?ticker"
        r"(?:\s+(?:display|text))?\s+to\s+(.+)$",
        s,
        re.IGNORECASE,
    )
    if not m:
        return None
    value = m.group(1).strip().strip("\"'")
    return value or None


def parse_refund_command(text: str):
    """Deterministic refund-command parser. "refund order #1841",
    "refund 1841", "refund order 1841", "refund #1841" ->
    {"order_id": 1841}. None when there is no order id — a bare
    "can I get a refund?" is a question for the AI, not a command."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    m = re.search(r"\brefund\s+(?:order\s+)?#?(\d+)\b", s, re.IGNORECASE)
    if not m:
        return None
    try:
        order_id = int(m.group(1))
    except ValueError:
        return None
    if order_id <= 0:
        return None
    return {"order_id": order_id}


def parse_promo_create_command(text: str):
    """Deterministic promo-code creation parser. "create promo code
    PAXYO20 20%", "new promo code WELCOME10 10 percent" ->
    {"code": "PAXYO20", "percent": 20,
     "expires_at": "2026-12-31 23:59:59"|None, "max_uses": 100|None}.
    Optional "expires 2026-12-31" and "max 100 uses" are parsed
    when present. The code is uppercased here (the server
    normalises the same way). percent is None when no percent was
    given — the handler then asks for it, plainly. The code keeps
    its raw shape for validate_promo_create, which refuses bad
    ones before any Confirm."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    m = re.search(
        r"(?:create|make|new)\s+(?:a\s+)?(?:new\s+)?promo\s+code\s+(\S+)",
        s,
        re.IGNORECASE,
    )
    if not m:
        return None
    code = m.group(1).strip().strip("\"'.,").upper()
    rest = s[m.end():]
    percent = None
    # No \b after the unit: "%" is not a word char, so "20% " has
    # no word boundary after the "%" and \b would never match it.
    pm = re.search(r"(\d+)\s*(?:%|percent|pct)", rest, re.IGNORECASE)
    if pm:
        try:
            percent = int(pm.group(1))
        except ValueError:
            percent = None
    expires_at = None
    em = re.search(
        r"expir(?:y|es)?\s+(\d{4}-\d{2}-\d{2})", rest, re.IGNORECASE
    )
    if em:
        expires_at = em.group(1) + " 23:59:59"
    max_uses = None
    um = re.search(r"max\s+(?:uses\s+)?(\d+)", rest, re.IGNORECASE)
    if not um:
        um = re.search(r"(\d+)\s+uses\b", rest, re.IGNORECASE)
    if um:
        try:
            max_uses = int(um.group(1))
        except ValueError:
            max_uses = None
    return {
        "code": code,
        "percent": percent,
        "expires_at": expires_at,
        "max_uses": max_uses,
    }


def validate_promo_create(parsed: dict):
    """Client-side promo-code validation, before any Confirm.
    Returns a plain refusal, or None when the code + percent are
    usable. Code: letters + digits only, 4–20 chars. Percent:
    1–100. Expiry must be a real date, not in the past. Max uses
    must be at least 1."""
    code = (parsed.get("code") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
        return (
            "That code won't work — use 4–20 letters and digits, "
            "for example PAXYO20."
        )
    percent = parsed.get("percent")
    if percent is None:
        return (
            "Tell me the percent too — for example "
            f"\"create promo code {code} 10%\"."
        )
    if percent < 1 or percent > 100:
        return "The percent must be between 1 and 100."
    expires_at = parsed.get("expires_at")
    if expires_at:
        try:
            exp_date = datetime.strptime(
                expires_at, "%Y-%m-%d %H:%M:%S"
            ).date()
        except ValueError:
            return (
                "That expiry date doesn't look right — use YYYY-MM-DD, "
                "for example 2026-12-31."
            )
        if exp_date < date.today():
            return "That expiry date is in the past."
    max_uses = parsed.get("max_uses")
    if max_uses is not None and max_uses < 1:
        return "Max uses must be at least 1."
    return None


def mint_admin_refund_token(order_id, admin_telegram_id, secret=None):
    """HMAC-SHA256 confirm token for POST /admin/orders/{id}/refund,
    keyed by BOT_API_SECRET over
    "admin-refund:{order_id}:{admin_telegram_id}" (the exact string
    server/api-admin-refund.php verifies). Minted ONLY after
    William taps Confirm. Returns 64 hex chars. The secret comes
    from the Render env, never hardcoded, never logged."""
    key = secret if secret is not None else BOT_API_SECRET
    msg = f"admin-refund:{int(order_id)}:{int(admin_telegram_id)}"
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _order_record(data):
    """One order record from a GET /orders/{id} reply: flat, or
    nested under "order" (the order bot reads both shapes)."""
    if not isinstance(data, dict):
        return None
    inner = data.get("order")
    if isinstance(inner, dict):
        return inner
    return data


def _order_owner(order: dict):
    """The order owner's telegram id (telegram_id, user_id or tg_id
    — the orders table has been called all three), or None."""
    for key in ("telegram_id", "user_id", "tg_id"):
        try:
            owner = int(order.get(key))
        except (TypeError, ValueError):
            continue
        if owner > 0:
            return owner
    return None


def _order_total(order: dict):
    """The order total in ETB (total, total_etb, price or amount),
    or None when the record carries none."""
    for key in ("total", "total_etb", "price", "amount"):
        try:
            return float(order.get(key))
        except (TypeError, ValueError):
            continue
    return None


def _order_service_label(order: dict) -> str:
    """Service name for the refund preview, or "service <id>"."""
    name = str(order.get("service_name") or order.get("name") or "").strip()
    if name:
        return name
    service_id = order.get("service_id") or order.get("service")
    if service_id is not None:
        return f"service {service_id}"
    return "service ?"


def _error_message(exc) -> str:
    """Plain error text from an HTTP error response ("error" or
    "message"), or "" when the response carries none."""
    try:
        resp = exc.response
        if resp is None:
            return ""
        data = resp.json()
        if isinstance(data, dict):
            return str(data.get("error") or data.get("message") or "")
    except Exception:
        return ""
    return ""


def _refund_error_text(order_id: int, exc) -> str:
    """Plain refund-failure message from the server's reply, per
    server/api-admin-refund.php: 404 order not found, 403 bad
    token, 409 already-completed vs provider-refused, 502 provider
    unconfirmed. A 404 whose body is NOT "Order not found." means
    the endpoint itself is not live yet — nothing was refunded
    either way."""
    status = exc.response.status_code if exc.response is not None else None
    msg = _error_message(exc)
    if status == 404:
        if msg == "Order not found.":
            return "Order not found."
        return (
            "The refund endpoint is not connected yet — "
            "nothing was refunded."
        )
    if status == 403:
        if "Confirm token" in msg:
            return "Confirm token is not valid."
        return msg or "You are not allowed to refund this order."
    if status in (409, 502):
        if "already completed" in msg.lower():
            return (
                f"Order #{order_id} is already completed and "
                "cannot be refunded."
            )
        if msg:
            return f"No refund was made — {msg}"
        return (
            "No refund was made — the provider did not confirm "
            "the cancellation."
        )
    return "Could not refund the order — please try again."


def _promo_error_text(pending: dict, exc) -> str:
    """Plain promo-creation failure message: the server's 409
    duplicate text shown as-is, 400 likewise, anything else a
    short generic line."""
    status = exc.response.status_code if exc.response is not None else None
    msg = _error_message(exc)
    if status == 409:
        return msg or (
            f"Promo code {pending['code']} already exists — "
            "nothing was created."
        )
    if status == 400:
        return msg or "That promo code could not be created."
    return "Could not create the promo code — please try again."


# -------------------------------------------------------------- AI fallback ---

ADMIN_AI_SYSTEM = (
    "You are the Paxyo admin assistant, talking to William, the owner "
    "of Paxyo. Answer briefly in English. You can answer general "
    "questions about Paxyo and the business. Never reveal provider "
    "names, buying costs, secrets, or the words 'SMM panel'. Never "
    "claim you sent a message, changed a setting, refunded an order "
    "or created a promo code — sending, changing, refunding and "
    "creating only happen after the owner taps Confirm."
)


async def ai_reply(text: str):
    """One minimal AI reply for a free-form question. DeepSeek first
    (DEEPSEEK_API_KEY), then Gemini (GEMINI_API_KEY) — the same keys
    the order bot already uses. Returns the reply text, or None when
    no key is configured or every provider failed. The AI is NEVER
    called for broadcasts or setting changes, and its output never
    triggers an action."""
    if DEEPSEEK_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                resp = await client.post(
                    DEEPSEEK_URL + "/chat/completions",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                    json={
                        "model": DEEPSEEK_MODEL,
                        "messages": [
                            {"role": "system", "content": ADMIN_AI_SYSTEM},
                            {"role": "user", "content": text},
                        ],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            out = data["choices"][0]["message"]["content"] or ""
            if out.strip():
                return out.strip()
        except Exception as exc:  # fall through to Gemini
            log.warning("Admin AI DeepSeek failed: %s", exc)
    if GEMINI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                resp = await client.post(
                    GEMINI_URL.format(model=GEMINI_MODEL),
                    params={"key": GEMINI_API_KEY},
                    json={"contents": [{"parts": [{"text": ADMIN_AI_SYSTEM + "\n\n" + text}]}]},
                )
                resp.raise_for_status()
                data = resp.json()
            out = (
                data["candidates"][0]["content"]["parts"][0]["text"] or ""
            )
            if out.strip():
                return out.strip()
        except Exception as exc:
            log.warning("Admin AI Gemini failed: %s", exc)
    return None


FALLBACK_REPLY = (
    "I didn't understand — try one of these:\n"
    "• \"How much did we make today?\"\n"
    "• \"How many users in the last 7 days?\"\n"
    "• \"Send this to users who never deposited: <message>\"\n"
    "• \"Change ticker to <new text>\"\n"
    "• \"Refund order #1841\"\n"
    "• \"Create promo code PAXYO20 20%\"\n"
    "• /winbacks — message users who went quiet\n"
    "• /morning — yesterday's money report"
)

# ------------------------------------------------------------ stats answers ---

def _stats_window_label(stats, days: int) -> str:
    """'Today (2026-11-15)' or 'Last 7 days (2026-11-09 to 2026-11-15)'."""
    date = str((stats or {}).get("date") or "today")
    if days and int(days) > 1:
        start = str((stats or {}).get("from") or "")
        if start:
            return f"Last {int(days)} days ({start} to {date})"
        return f"Last {int(days)} days (to {date})"
    return f"Today ({date})"


def answer_stats(stats, question: dict) -> str:
    """Short plain answer from a /admin/stats record. Never invents
    a figure: a missing deposits figure says so, and no top service
    says so."""
    kind = question["kind"]
    days = int(question.get("days") or 1)
    if question.get("yesterday"):
        return (
            "I can only show today and the last 7 or 30 days — "
            "yesterday on its own is not available yet. "
            "Try \"How much did we make today?\" or "
            "\"How many users in the last 7 days?\""
        )
    stats = stats or {}
    label = _stats_window_label(stats, days)
    orders = int(stats.get("orders") or 0)
    completed = int(stats.get("completed") or 0)
    revenue = float(stats.get("revenue_etb") or 0)
    new_users = int(stats.get("new_users") or 0)
    if kind == "revenue":
        return f"{label}: revenue {format_money(revenue)} ETB."
    if kind == "users":
        return f"{label}: {new_users} new users."
    if kind == "orders":
        return f"{label}: {orders} orders ({completed} completed)."
    if kind == "deposits":
        if "deposits_count" not in stats or "deposits_etb" not in stats:
            return (
                "The deposits figure is not available yet — the stats "
                "endpoint does not report it."
            )
        count = int(stats.get("deposits_count") or 0)
        total = float(stats.get("deposits_etb") or 0)
        return f"{label}: {count} deposits, {format_money(total)} ETB."
    if kind == "top_service":
        top = stats.get("top_service")
        if not top:
            return f"{label}: no orders yet, so there is no top service."
        return (
            f"{label}: top service is {top} "
            f"×{int(stats.get('top_quantity') or 0)}."
        )
    # summary: every figure, one line each.
    lines = [
        f"{label}:",
        f"Revenue: {format_money(revenue)} ETB",
        f"Orders: {orders} ({completed} completed)",
        f"New users: {new_users}",
    ]
    if "deposits_count" in stats and "deposits_etb" in stats:
        lines.append(
            f"Deposits: {int(stats.get('deposits_count') or 0)} "
            f"({format_money(stats.get('deposits_etb') or 0)} ETB)"
        )
    top = stats.get("top_service")
    if top:
        lines.append(
            f"Top service: {top} ×{int(stats.get('top_quantity') or 0)}"
        )
    return "\n".join(lines)


def format_morning_report(stats) -> str:
    """Yesterday's money report from a /admin/stats record fetched
    with day="yesterday". All five figures come from the record;
    a missing figure says so, never invented. The window is
    labelled from the response's own `from`/`date` fields, so the
    label is honest whatever window the server actually returned:
    "Yesterday (2026-11-14)" when the server sent day=yesterday,
    otherwise the same Today / Last N days label as answer_stats."""
    stats = stats or {}
    if stats.get("day") == "yesterday":
        when = str(stats.get("from") or stats.get("date") or "yesterday")
        label = f"Yesterday ({when})"
    else:
        label = _stats_window_label(stats, int(stats.get("days") or 1))
    revenue = float(stats.get("revenue_etb") or 0)
    new_users = int(stats.get("new_users") or 0)
    lines = [
        f"{label}:",
        f"Revenue: {format_money(revenue)} ETB",
    ]
    if "net_profit_etb" in stats:
        lines.append(f"Net profit: {format_money(stats.get('net_profit_etb') or 0)} ETB")
    else:
        lines.append("Net profit: not available yet.")
    lines.append(f"New users: {new_users}")
    top = stats.get("top_service")
    if top:
        lines.append(
            f"Top service: {top} ×{int(stats.get('top_quantity') or 0)}"
        )
    else:
        lines.append("Top service: none yet.")
    if "deposits_count" in stats:
        deposits_line = f"Deposits: {int(stats.get('deposits_count') or 0)}"
        if "deposits_etb" in stats:
            deposits_line += (
                f" ({format_money(stats.get('deposits_etb') or 0)} ETB)"
            )
        lines.append(deposits_line)
    else:
        lines.append("Deposits: not available yet.")
    return "\n".join(lines)


# --------------------------------------------------------- broadcast sending ---

async def send_broadcast(bot, telegram_ids, message: str):
    """Send `message` to each id in `telegram_ids`, sequentially,
    one at a time, with a short pause between sends (Telegram rate
    limits). Ids are deduped first — a user is messaged at most
    once even if the audience list ever carried a duplicate.
    Returns (delivered, failed). Never raises: one failed send
    must not stop the rest."""
    ids = []
    seen = set()
    for raw in telegram_ids or []:
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            continue
        if tid <= 0 or tid in seen:
            continue
        seen.add(tid)
        ids.append(tid)
    delivered = 0
    failed = 0
    for i, tid in enumerate(ids):
        try:
            await bot.send_message(chat_id=tid, text=message)
            delivered += 1
        except Exception as exc:
            log.warning("Broadcast send to %s failed: %s", tid, exc)
            failed += 1
        if i < len(ids) - 1 and SEND_DELAY_SECONDS > 0:
            await asyncio.sleep(SEND_DELAY_SECONDS)
    return delivered, failed


def winback_message(user: dict) -> str:
    """One win-back message for one user, personalised with their
    usual service when the server knew it. Plain text only — it
    never places an order and never shows the user a Confirm card;
    the user just replies in chat if they want to order again."""
    service = str((user or {}).get("usual_service") or "").strip()
    if service:
        return (
            "We miss you at Paxyo! You usually order "
            f"{service} — want to order again? Just reply here."
        )
    return "We miss you at Paxyo! Want to order again? Just reply here."


async def send_winbacks(bot, users):
    """Send one personalised win-back message to each user in
    `users` ([{telegram_id, usual_service, usual_quantity}]),
    sequentially, one at a time, with a short pause between sends.
    Ids are deduped first — a user is messaged at most once even
    if the audience list ever carried a duplicate. Returns
    (delivered, failed, delivered_ids). Never raises: one failed
    send must not stop the rest, and a failed send is never
    recorded as sent."""
    seen = set()
    queue = []
    for user in users or []:
        if not isinstance(user, dict):
            continue
        try:
            tid = int(user.get("telegram_id"))
        except (TypeError, ValueError):
            continue
        if tid <= 0 or tid in seen:
            continue
        seen.add(tid)
        queue.append((tid, user))
    delivered = 0
    failed = 0
    delivered_ids = []
    for i, (tid, user) in enumerate(queue):
        try:
            await bot.send_message(chat_id=tid, text=winback_message(user))
            delivered += 1
            delivered_ids.append(tid)
        except Exception as exc:
            log.warning("Win-back send to %s failed: %s", tid, exc)
            failed += 1
        if i < len(queue) - 1 and SEND_DELAY_SECONDS > 0:
            await asyncio.sleep(SEND_DELAY_SECONDS)
    return delivered, failed, delivered_ids


def _winback_preview(pending: dict) -> str:
    return (
        "Win-back preview:\n"
        f"{len(pending['users'])} users have gone quiet "
        "(no order in 14+ days).\n"
        "Each gets one personal message naming the service they "
        "usually order — no order is placed for them.\n\n"
        "Tap Confirm to send them, or Cancel."
    )


def _broadcast_preview(pending: dict) -> str:
    return (
        "Broadcast preview:\n"
        f"To: {pending['service_label']} ({len(pending['telegram_ids'])} users)\n"
        "Message:\n"
        f"{pending['message']}\n\n"
        "Tap Confirm to send it, or Cancel."
    )


def _setting_preview(pending: dict) -> str:
    return (
        "Change this setting?\n"
        f"Ticker display: {pending['value']}\n\n"
        "Tap Confirm to save it, or Cancel."
    )


def _refund_preview(order: dict, order_id: int) -> str:
    """Refund preview: id, service, quantity, total, status, owner.
    Shown BEFORE any token is minted — nothing refunds here."""
    total = _order_total(order)
    quantity = order.get("quantity")
    lines = [
        "Refund this order?",
        f"Order: #{order_id}",
        f"Service: {_order_service_label(order)}"
        + (f" ×{quantity}" if quantity is not None else ""),
        f"Total: {format_money(total)} ETB"
        if total is not None
        else "Total: ?",
        f"Status: {order.get('status') or '?'}",
        f"User: {_order_owner(order)}",
        "",
        "The full total goes back to the user's Paxyo balance "
        "(not cash).",
        "Tap Confirm to refund it, or Cancel.",
    ]
    return "\n".join(lines)


def _promo_preview(pending: dict) -> str:
    lines = [
        "Create this promo code?",
        f"Code: {pending['code']}",
        f"Bonus: {pending['percent']}% on a deposit",
    ]
    if pending.get("expires_at"):
        lines.append(f"Expires: {str(pending['expires_at'])[:10]}")
    if pending.get("max_uses") is not None:
        lines.append(f"Max uses: {pending['max_uses']}")
    lines += ["", "Tap Confirm to create it, or Cancel."]
    return "\n".join(lines)


async def _execute_pending(user_id: int, context) -> str:
    """Run a confirmed pending change (broadcast send, setting
    write, order refund, or promo-code creation) and return the
    one-line outcome. Clears the pending entry first, so a double
    tap cannot run it twice."""
    pending = PENDING.pop(user_id, None)
    if pending is None:
        return "Nothing to confirm."
    if pending["kind"] == "broadcast":
        delivered, failed = await send_broadcast(
            context.bot, pending["telegram_ids"], pending["message"]
        )
        if failed:
            return (
                f"Sent to {delivered} users. "
                f"{failed} failed to deliver."
            )
        return f"Sent to {delivered} users."
    if pending["kind"] == "winback":
        delivered, failed, delivered_ids = await send_winbacks(
            context.bot, pending["users"]
        )
        # Record only the users who actually got the message, so
        # a failed send is not treated as sent. Best-effort: if
        # the record endpoint is not live yet (or fails), the
        # sends still happened and the report still stands.
        if delivered_ids:
            try:
                await admin_api.record_winbacks(delivered_ids)
            except Exception as exc:
                log.warning("record_winbacks failed: %s", exc)
        if failed:
            return (
                f"Sent to {delivered} users. "
                f"{failed} failed to deliver."
            )
        return f"Sent to {delivered} users."
    if pending["kind"] == "refund":
        # The token is minted HERE, only after Confirm — never on
        # the preview, never on a single message.
        token = mint_admin_refund_token(pending["order_id"], user_id)
        try:
            result = await admin_api.admin_refund_order(
                pending["order_id"], pending["telegram_id"], user_id, token
            )
        except httpx.HTTPStatusError as exc:
            return _refund_error_text(pending["order_id"], exc)
        except Exception as exc:
            log.warning("admin_refund_order failed: %s", exc)
            return "Could not refund the order — please try again."
        if not isinstance(result, dict):
            return "Could not refund the order — please try again."
        refunded = result.get("refunded_etb")
        refunded_text = (
            format_money(refunded) if refunded is not None else "?"
        )
        if result.get("duplicate"):
            return (
                f"Already refunded — {refunded_text} ETB "
                f"for order #{pending['order_id']}. "
                "No second refund was made."
            )
        return (
            f"✅ Refunded {refunded_text} ETB "
            f"to user {pending['telegram_id']} "
            f"for order #{pending['order_id']} "
            "(Paxyo balance, not cash). "
            f"Provider: {result.get('provider_status') or '?'}."
        )
    if pending["kind"] == "promo":
        try:
            result = await admin_api.create_promo_code(
                pending["code"],
                pending["percent"],
                expires_at=pending.get("expires_at"),
                max_uses=pending.get("max_uses"),
            )
        except httpx.HTTPStatusError as exc:
            return _promo_error_text(pending, exc)
        except Exception as exc:
            log.warning("create_promo_code failed: %s", exc)
            return "Could not create the promo code — please try again."
        if result is None:
            return (
                "The promo-code endpoint is not connected yet — "
                "nothing was created."
            )
        lines = [
            f"✅ Promo code {pending['code']} created — "
            f"{pending['percent']}% bonus on a deposit."
        ]
        if result.get("expires_at"):
            lines.append(f"Expires: {str(result['expires_at'])[:10]}")
        if result.get("max_uses") is not None:
            lines.append(f"Max uses: {result['max_uses']}")
        return "\n".join(lines)
    # setting
    try:
        result = await admin_api.set_setting(pending["key"], pending["value"])
    except Exception as exc:
        log.warning("set_setting failed: %s", exc)
        return "Could not save the setting — please try again."
    if result is None:
        return (
            "The settings endpoint is not connected yet — "
            "nothing was changed."
        )
    return f"Saved. Ticker display is now: {pending['value']}"


async def _resolve_audience_and_preview(user_id: int, parsed: dict):
    """Resolve the audience for a parsed broadcast command and, when
    there is someone to send to, store the pending preview and return
    its text. Returns (text, keyboard-or-None, stored-bool)."""
    try:
        audience = await admin_api.broadcast_audience(
            parsed["segment"], parsed["service_id"]
        )
    except Exception as exc:
        log.warning("broadcast_audience failed: %s", exc)
        return ("Could not count the audience — please try again.", None, False)
    if audience is None:
        return (
            "The broadcast list is not connected yet — the audience "
            "endpoint is not live on the server, so I cannot count "
            "who would get it.",
            None,
            False,
        )
    ids = audience.get("telegram_ids") or []
    if not ids or int(audience.get("count") or 0) == 0:
        return (
            f"Nobody matches — no {parsed['service_label']}. "
            "Nothing to send.",
            None,
            False,
        )
    pending = {
        "kind": "broadcast",
        "segment": parsed["segment"],
        "service_id": parsed["service_id"],
        "service_label": parsed["service_label"],
        "message": parsed["message"],
        "telegram_ids": list(ids),
    }
    PENDING[user_id] = pending
    return (_broadcast_preview(pending), CONFIRM_KEYBOARD, True)


# ------------------------------------------------------ morning report ---

def should_send_morning(now: datetime, sent_today: bool) -> bool:
    """Pure once-a-day gate: send only at/after 08:00 EAT, and only
    when today has not been sent yet. `now` is an EAT datetime."""
    if sent_today:
        return False
    return now.hour >= 8


async def send_morning_report_once(app, now=None) -> bool:
    """One morning-report attempt: send yesterday's money report to
    every ADMIN_TELEGRAM_IDS id, at most once per EAT calendar day.
    Returns True when the report was sent. The sent marker is
    checked AND written server-side (GET/POST /admin/morning-sent)
    so a restart after 8am cannot double-send; when that endpoint
    404s (not live yet) the in-memory MORNING_SENT_DATES set is
    the fallback and a warning is logged. Nothing is sent before
    8am EAT, nothing is sent when the day is already marked, and
    nothing is marked when the stats endpoint is not connected
    yet (so the next wake retries instead of losing the day)."""
    now = now or datetime.now(EAT_TZ)
    today = now.date().isoformat()
    server_marker = None
    try:
        server_marker = await admin_api.morning_sent(today)
    except Exception as exc:
        log.warning("morning_sent check failed: %s", exc)
    if server_marker is None:
        log.warning(
            "Morning-sent endpoint not connected yet — using the "
            "in-memory marker only for %s.",
            today,
        )
        sent_today = today in MORNING_SENT_DATES
    else:
        sent_today = bool(server_marker.get("sent"))
    if not should_send_morning(now, sent_today):
        return False
    try:
        stats = await admin_api.admin_stats(day="yesterday")
    except Exception as exc:
        log.warning("morning admin_stats failed: %s", exc)
        return False
    if stats is None:
        log.warning("Morning report not connected yet — stats endpoint 404.")
        return False
    text = format_morning_report(stats)
    for admin_id in sorted(ADMIN_TELEGRAM_IDS):
        try:
            await app.bot.send_message(chat_id=admin_id, text=text)
        except Exception as exc:
            log.warning("Morning report send to %s failed: %s", admin_id, exc)
    MORNING_SENT_DATES.add(today)
    try:
        await admin_api.mark_morning_sent(today)
    except Exception as exc:
        log.warning("mark_morning_sent failed: %s", exc)
    return True


def _seconds_until_next_8am_eat(now=None) -> float:
    """Seconds from `now` (EAT) until the next 08:00 EAT. Pure helper
    so the schedule is testable: before 8am it is today 08:00,
    at/after 8am it is tomorrow 08:00."""
    now = now or datetime.now(EAT_TZ)
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def morning_report_loop(app):
    """Background loop: sleep until the next 08:00 EAT, send the
    morning report once, then sleep until the next day's 08:00.
    A proper schedule, not a poll — on the always-on server
    (Oracle move) the report goes out at 08:00 sharp. On free
    Render the process sleeps, so the sleep finishes on the next
    wake after 08:00 and the report goes out then instead; the
    once-a-day gate in send_morning_report_once still prevents
    a double-send."""
    while True:
        await asyncio.sleep(_seconds_until_next_8am_eat())
        try:
            await send_morning_report_once(app)
        except Exception as exc:
            log.warning("Morning report loop failed: %s", exc)


async def _post_init(app):
    """Application post_init hook: start the morning-report loop.
    Polling has no job queue, so the loop is an asyncio task."""
    asyncio.create_task(morning_report_loop(app))


# ---------------------------------------------------------------- handlers ---

CAPABILITIES = (
    "Hello, William. I am the Paxyo admin bot.\n\n"
    "I can:\n"
    "• Answer live questions — \"How much did we make today?\" or "
    "\"How many users in the last 7 days?\"\n"
    "• Send a broadcast — \"Send this to users who never deposited: "
    "<message>\" (I show the count first, you confirm)\n"
    "• Change the ticker — \"Change ticker to <new text>\" "
    "(you confirm first)\n"
    "• Refund an order — \"Refund order #1841\" (I show the order, "
    "you confirm, the full total goes back to the user's Paxyo "
    "balance, never cash)\n"
    "• Create a promo code — \"Create promo code PAXYO20 20%\" "
    "(you confirm first)\n"
    "• Win back quiet users — /winbacks (I show the count first, "
    "you confirm, then each gets one personal message)\n"
    "• Morning money report — /morning (yesterday's revenue, net "
    "profit, new users, top service, deposits; also sent "
    "automatically once a day at 8am)\n\n"
    "Refunds go through the Confirm-gated admin-refund endpoint, "
    "once, never twice, never for completed orders."
)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    await update.message.reply_text(CAPABILITIES)


async def winbacks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /winbacks — count the quiet users (no order in 14+ days),
    show the count, and only send after William taps Confirm.
    Nothing is sent from this handler itself."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    try:
        audience = await admin_api.winback_audience()
    except Exception as exc:
        log.warning("winback_audience failed: %s", exc)
        await update.message.reply_text(
            "Could not count the quiet users — please try again."
        )
        return
    if audience is None:
        await update.message.reply_text(
            "The win-back list is not connected yet — the audience "
            "endpoint is not live on the server, so I cannot count "
            "who went quiet."
        )
        return
    users = audience.get("users") or []
    if not users or int(audience.get("count") or 0) == 0:
        await update.message.reply_text("No users have gone quiet.")
        return
    PENDING[user.id] = {"kind": "winback", "users": list(users)}
    await update.message.reply_text(
        _winback_preview(PENDING[user.id]),
        reply_markup=CONFIRM_KEYBOARD,
    )


async def morning_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /morning — yesterday's money report, on demand. All
    figures come from GET /admin/stats?day=yesterday; a 404 means
    the endpoint is not live yet and the bot says so honestly."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    try:
        stats = await admin_api.admin_stats(day="yesterday")
    except Exception as exc:
        log.warning("morning admin_stats failed: %s", exc)
        await update.message.reply_text(
            "Could not load yesterday's numbers — please try again."
        )
        return
    if stats is None:
        await update.message.reply_text(
            "The live numbers are not connected yet — the stats "
            "endpoint is not live on the server."
        )
        return
    await update.message.reply_text(format_morning_report(stats))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    await update.message.reply_text(
        CAPABILITIES
        + "\n\nBroadcasts can go to: users who never deposited, "
        "users who deposited before, users who bought a service "
        "(\"users who bought service 6139\"), or all users.\n\n"
        "/winbacks messages users with no order in 14+ days "
        "(count first, you confirm). /morning shows yesterday's "
        "money report — it is also sent automatically once a day "
        "at 8am."
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The whole admin conversation: admin gate, pending Confirm,
    deterministic stats / broadcast / ticker / refund / promo
    parsing, then the AI for free-form questions (or the short
    fallback when no AI key is configured). The AI is never called
    for a broadcast, a setting change, a refund or a promo-code
    creation. Broadcasts and tickers are parsed BEFORE refunds and
    promo codes, so a broadcast message (or ticker text) that
    happens to mention "refund order #N" or "create promo code"
    is read as the broadcast / ticker it is, not as a command."""
    user = update.effective_user
    text = (update.message.text or "").strip()
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not text:
        await update.message.reply_text(FALLBACK_REPLY)
        return

    pending = PENDING.get(user.id)
    if pending is not None:
        # A broadcast whose message we are still asking for: any
        # text (other than Cancel) IS the message.
        if pending["kind"] == "broadcast" and pending.get("message") is None:
            if _is_cancel(text):
                PENDING.pop(user.id, None)
                await update.message.reply_text("Cancelled.")
                return
            pending["message"] = text
            preview, keyboard, _stored = await _resolve_audience_and_preview(
                user.id,
                {
                    "segment": pending["segment"],
                    "service_id": pending["service_id"],
                    "service_label": pending["service_label"],
                    "message": text,
                },
            )
            if keyboard is None:
                PENDING.pop(user.id, None)
            await update.message.reply_text(preview, reply_markup=keyboard)
            return
        # A preview is waiting for Confirm / Cancel.
        if _is_confirm(text):
            outcome = await _execute_pending(user.id, context)
            await update.message.reply_text(outcome)
            return
        if _is_cancel(text):
            PENDING.pop(user.id, None)
            await update.message.reply_text("Cancelled.")
            return
        await update.message.reply_text(
            "You have a change waiting — tap Confirm to go ahead, "
            "or Cancel to drop it."
        )
        return

    # 1. Live questions — deterministic, numbers from /admin/stats.
    question = parse_stats_question(text)
    if question is not None:
        try:
            stats = await admin_api.admin_stats(days=question["days"])
        except Exception as exc:
            log.warning("admin_stats failed: %s", exc)
            stats = None
        if stats is None:
            await update.message.reply_text(
                "The live numbers are not connected yet — the stats "
                "endpoint is not live on the server."
            )
            return
        await update.message.reply_text(answer_stats(stats, question))
        return

    # 2. Targeted broadcasts — deterministic, Confirm required.
    parsed = parse_broadcast_command(text)
    if parsed is not None:
        if parsed["segment"] == "service" and parsed["service_id"] is None:
            # A service NAME, not an id: resolve it, or ask for the id.
            try:
                services = await admin_api.services()
            except Exception as exc:
                log.warning("services lookup failed: %s", exc)
                services = []
            resolved = resolve_service_id(parsed["service_name"], services)
            if resolved is None:
                await update.message.reply_text(
                    "I could not find one service for "
                    f"\"{parsed['service_name']}\" — please give me "
                    "the service ID, for example \"send this to users "
                    "who bought service 6139: <message>\"."
                )
                return
            parsed["service_id"] = resolved
            parsed["service_label"] = (
                f"users who bought service {resolved}"
            )
        if parsed["message"] is None:
            PENDING[user.id] = {
                "kind": "broadcast",
                "segment": parsed["segment"],
                "service_id": parsed["service_id"],
                "service_label": parsed["service_label"],
                "message": None,
                "telegram_ids": [],
            }
            await update.message.reply_text(
                "What should the message say? Send it as your next message."
            )
            return
        preview, keyboard, _stored = await _resolve_audience_and_preview(
            user.id, parsed
        )
        await update.message.reply_text(preview, reply_markup=keyboard)
        return

    # 3. Settings changes — deterministic, Confirm required.
    ticker = parse_ticker_change(text)
    if ticker is not None:
        PENDING[user.id] = {
            "kind": "setting",
            "key": TICKER_SETTING_KEY,
            "value": ticker,
        }
        await update.message.reply_text(
            _setting_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 4. Refunds — deterministic, Confirm required, never twice,
    #    never for a completed order. The preview shows the order;
    #    the HMAC token is minted only when the Confirm runs.
    refund = parse_refund_command(text)
    if refund is not None:
        order_id = refund["order_id"]
        try:
            order = await admin_api.get_order(order_id)
        except Exception as exc:
            log.warning("get_order failed: %s", exc)
            await update.message.reply_text(
                f"Could not look up order #{order_id} — please try again."
            )
            return
        if order is None:
            await update.message.reply_text(
                "The order lookup is not connected yet — "
                f"I couldn't look up order #{order_id}."
            )
            return
        if str(order.get("status") or "").strip().lower() == "completed":
            await update.message.reply_text(
                f"Order #{order_id} is already completed and "
                "cannot be refunded."
            )
            return
        owner = _order_owner(order)
        if owner is None:
            await update.message.reply_text(
                f"Order #{order_id} has no owner on file, so I "
                "can't refund it."
            )
            return
        PENDING[user.id] = {
            "kind": "refund",
            "order_id": order_id,
            "telegram_id": owner,
        }
        await update.message.reply_text(
            _refund_preview(order, order_id),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5. Promo-code creation — deterministic, Confirm required.
    #    Bad codes / percents are refused here, before any Confirm.
    promo = parse_promo_create_command(text)
    if promo is not None:
        problem = validate_promo_create(promo)
        if problem is not None:
            await update.message.reply_text(problem)
            return
        PENDING[user.id] = {
            "kind": "promo",
            "code": promo["code"],
            "percent": promo["percent"],
            "expires_at": promo.get("expires_at"),
            "max_uses": promo.get("max_uses"),
        }
        await update.message.reply_text(
            _promo_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 6. Free-form — AI when a key is configured, else the short reply.
    #    The AI can never trigger a broadcast, a setting write, a
    #    refund or a promo-code creation.
    reply = await ai_reply(text)
    await update.message.reply_text(reply if reply else FALLBACK_REPLY)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm / Cancel taps. Admin-only; a double tap cannot run a
    change twice (the pending entry is cleared before executing)."""
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    if not is_admin_user(user.id):
        await query.edit_message_text(REFUSAL)
        return
    if query.data == "admin_confirm":
        outcome = await _execute_pending(user.id, context)
        await query.edit_message_text(outcome)
        return
    if query.data == "admin_cancel":
        PENDING.pop(user.id, None)
        await query.edit_message_text("Cancelled.")
        return
    await query.edit_message_text("Nothing to do.")


# ------------------------------------------------------------- health server ---

class _HealthHandler(BaseHTTPRequestHandler):
    """GET / -> 200 'ok', so a Render free web service stays up
    while the bot polls. Nothing else is served."""

    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # keep the logs quiet
        pass


def start_health_server(port: int):
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def build_application():
    app = (
        ApplicationBuilder()
        .token(ADMIN_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("winbacks", winbacks_cmd))
    app.add_handler(CommandHandler("morning", morning_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))
    return app


def main():
    missing = [
        name
        for name, value in [
            ("ADMIN_BOT_TOKEN", ADMIN_BOT_TOKEN),
            ("BOT_API_SECRET", BOT_API_SECRET),
        ]
        if not value
    ]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        raise SystemExit(1)
    if not DEEPSEEK_API_KEY and not GEMINI_API_KEY:
        log.warning(
            "No AI key set (DEEPSEEK_API_KEY / GEMINI_API_KEY): free-form "
            "questions get the short fallback reply."
        )

    global admin_api
    admin_api = AdminPaxyoClient()
    app = build_application()

    # Render sets $PORT; the health server answers it so the free
    # web service stays up while the bot polls Telegram.
    port = int(os.environ.get("PORT", "8080") or 8080)
    start_health_server(port)
    log.info(
        "Paxyo admin bot starting (polling, health on :%s, AI %s)",
        port,
        "DeepSeek" if DEEPSEEK_API_KEY else ("Gemini" if GEMINI_API_KEY else "none"),
    )
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
