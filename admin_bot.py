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
  * FIRST-USE PASSWORD GATE (William, 15 Nov 11:38 EAT — a Telegram
    bot cannot be made private/hidden, so this is the second lock):
    env ADMIN_BOT_PASSWORD. When set, an allowlisted user must enter
    the password once per process run before ANY command, question,
    broadcast or setting change is answered; until unlocked, every
    message gets one short line (the password prompt for commands,
    a short refusal for a wrong attempt) and no admin content leaks.
    Wrong password: short refusal, no hint. 5 wrong attempts in an
    hour locks that user out for an hour. The password itself is
    never logged, echoed or stored anywhere except the env var. A
    redeploy/restart clears the unlock — the password is entered
    again. When ADMIN_BOT_PASSWORD is unset/empty the gate is OFF
    and behaviour is exactly the allowlist-only behaviour. Non-
    allowlisted users get the existing refusal and never reach the
    password prompt.
  * EVERY change (broadcast, setting, refund, promo code, balance
    adjustment) needs an
    explicit Confirm step — a Confirm tap or a typed "yes" while a
    preview is pending. Nothing sends, writes, refunds or adjusts
    a balance on a single message.
  * Refunds go through the Confirm-gated admin-refund endpoint
    (POST /admin/orders/{id}/refund, HMAC confirm token minted only
    after Confirm): once, never twice, never for a completed order,
    and only to the user's Paxyo balance — never cash. Balance
    adjustments go through the same pattern (POST
    /admin/users/{id}/balance/adjust, HMAC confirm token minted
    only after Confirm, never below zero). Promo codes are created
    the same way: preview, Confirm, then POST /promo-codes. No
    other money movement happens here.
  * Never reveal provider names, buying costs, secrets, or the words
    "SMM panel". Only Paxyo selling prices exist, and this bot does
    not quote prices at all.
  * Reply language: English only.

UNDERSTANDING — deterministic parsing FIRST (regex/patterns for the
stats questions (incl. net profit), broadcast commands, ticker
changes, refund commands, promo-code creation, one order's status,
and plain-language report commands that run the matching /command
handler), AI only for
free-form questions. Common admin typos are normalised before
matching, so "how much profite did we make" still routes. The AI
never triggers a broadcast, a setting write, a refund or a
promo-code creation: those go through the
deterministic Confirm flow only. The AI
is minimal — DeepSeek first if DEEPSEEK_API_KEY is set, then
Gemini (same keys the order bot already uses), each call with a
5-second budget and fast failover (an HTTP error is never
retried, a transport failure gets one quick retry); with no key
set, free-form gets a short "I didn't understand — try
..." reply, never silence. No Groq: the user bot already uses
Groq, and the admin bot must not share its free-tier quota.

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
  ADMIN_BOT_PASSWORD (optional) — first-use password; when set, an
    allowlisted user must enter it once per process run before any
    command is answered (unset/empty = gate off, allowlist only)
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
import time
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
# Fast-failover budgets (17 Nov 2026, order bot): a free-form
# question must not hang for a minute the way two 30s calls did.
# NO Groq here (18 Nov 2026): the user bot already uses Groq, and
# the admin bot must not share its free-tier quota — DeepSeek
# first, then Gemini, each with the same fast-failover shape as
# bot.py: 5s per attempt, HTTP errors never retried, one quick
# retry only on a transport failure.
AI_POST_TIMEOUT_SECONDS = 5.0
AI_TRANSIENT_RETRY_DELAY_SECONDS = 0.5
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

# First-use password gate (William, 15 Nov 11:38 EAT). No default,
# no hardcoded fallback: unset/empty means the gate is OFF.
ADMIN_BOT_PASSWORD = os.environ.get("ADMIN_BOT_PASSWORD", "") or ""


def is_admin_user(user_id: int) -> bool:
    """True when this Telegram user may use the admin bot."""
    try:
        return int(user_id) in ADMIN_TELEGRAM_IDS
    except (TypeError, ValueError):
        return False


REFUSAL = "Sorry — this bot is only for the Paxyo owner."

# ------------------------------------------------------ password gate ---

PASSWORD_PROMPT = (
    "This bot is locked — please send the password to continue."
)
PASSWORD_WRONG = "Wrong password."
PASSWORD_LOCKED_OUT = "Too many wrong passwords — try again later."
PASSWORD_UNLOCKED = "Unlocked. What would you like to do?"

PASSWORD_MAX_WRONG = 5
PASSWORD_WINDOW_SECONDS = 3600

# In-memory password-gate state (per process run): ids that entered
# the correct password, and per-user monotonic timestamps of wrong
# attempts (pruned to the last hour). A redeploy/restart clears
# both — the password must be entered again. The password itself
# is never stored here, only the fact that a user unlocked.
# Tests clear both sets in setUp/tearDown.
UNLOCKED_USERS = set()
_WRONG_PASSWORD_ATTEMPTS = {}


def _password_gate_on() -> bool:
    """True when a password is configured: the gate is on."""
    return bool(ADMIN_BOT_PASSWORD)


def is_unlocked(user_id: int) -> bool:
    """True when this user may use the bot right now: the gate is
    off, or they entered the correct password in this process run."""
    if not _password_gate_on():
        return True
    try:
        return int(user_id) in UNLOCKED_USERS
    except (TypeError, ValueError):
        return False


def _prune_wrong_attempts(user_id: int, now: float):
    """Wrong-attempt timestamps inside the last hour for this user
    (older ones are forgotten)."""
    attempts = _WRONG_PASSWORD_ATTEMPTS.get(int(user_id)) or []
    attempts = [t for t in attempts
                if now - t < PASSWORD_WINDOW_SECONDS]
    if attempts:
        _WRONG_PASSWORD_ATTEMPTS[int(user_id)] = attempts
    else:
        _WRONG_PASSWORD_ATTEMPTS.pop(int(user_id), None)
    return attempts


def _password_locked_out(user_id: int, now: float = None) -> bool:
    """True when this user made 5 wrong attempts in the last hour."""
    if now is None:
        now = time.monotonic()
    return len(_prune_wrong_attempts(user_id, now)) >= PASSWORD_MAX_WRONG


def try_password(user_id: int, text: str, now: float = None) -> str:
    """Check one password attempt. Returns "ok" (unlocked),
    "wrong" (recorded) or "locked" (5 wrong in the last hour).
    The password itself is never logged, echoed or returned.
    compare_digest keeps the check time from leaking the password.
    Only call when the gate is on."""
    if now is None:
        now = time.monotonic()
    if _password_locked_out(user_id, now):
        return "locked"
    if hmac.compare_digest(text or "", ADMIN_BOT_PASSWORD):
        UNLOCKED_USERS.add(int(user_id))
        _WRONG_PASSWORD_ATTEMPTS.pop(int(user_id), None)
        return "ok"
    attempts = _prune_wrong_attempts(user_id, now)
    attempts.append(now)
    _WRONG_PASSWORD_ATTEMPTS[int(user_id)] = attempts
    return "wrong"


async def _check_password_gate(update, text, try_as_password: bool) -> bool:
    """The password gate for one incoming message. Returns True
    when the handler may proceed. Gate off, or user already
    unlocked: always True. Otherwise:
      * a command (try_as_password False) -> the prompt line, False.
      * a text message -> treated as a password attempt: correct
        unlocks ("Unlocked..."), wrong -> short refusal, 5 wrong
        in an hour -> locked-out refusal. All False — the message
        was the password, not a command, so nothing else runs.
    An empty text message is not an attempt: it gets the prompt.
    Never logs or echoes the password."""
    user = update.effective_user
    if not _password_gate_on() or is_unlocked(user.id):
        return True
    if not try_as_password or not (text or "").strip():
        await update.message.reply_text(PASSWORD_PROMPT)
        return False
    result = try_password(user.id, text)
    if result == "ok":
        await update.message.reply_text(PASSWORD_UNLOCKED)
    elif result == "locked":
        await update.message.reply_text(PASSWORD_LOCKED_OUT)
    else:
        await update.message.reply_text(PASSWORD_WRONG)
    return False

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

    async def get_user_balance(self, telegram_id):
        """GET /admin/users/{id}/balance -> {telegram_id, username,
        first_name, balance}. A 404 with a "User not found" body
        means the user does not exist -> {"user_not_found": True}.
        Any other 404 means the endpoint is not live yet -> None
        (same 404-tolerance as the other admin reads). Other errors
        raise. (The contract is server/api-admin-user-balance.php.)
        Users are identified by Telegram id only: the auth table
        has no phone column (phone lives only in deposit records),
        so a phone number cannot look a user up."""
        path = f"/admin/users/{int(telegram_id)}/balance"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                if "user not found" in _error_message(exc).lower():
                    return {"user_not_found": True}
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def adjust_user_balance(self, telegram_id, delta_etb,
                                  admin_telegram_id, confirm_token):
        """POST /admin/users/{id}/balance/adjust {delta_etb,
        admin_telegram_id, confirm_token} -> {ok, telegram_id,
        old_balance, new_balance, delta_etb}. Errors raise — the
        caller maps 404/403/409 to the plain messages in
        server/api-admin-user-balance.php. (The contract is that
        file; the HMAC token is minted by mint_admin_balance_token,
        only after William taps Confirm.)"""
        return await self._send(
            build_api_request(
                "POST",
                f"/admin/users/{int(telegram_id)}/balance/adjust",
                {
                    "delta_etb": float(delta_etb),
                    "admin_telegram_id": int(admin_telegram_id),
                    "confirm_token": confirm_token,
                },
            )
        )

    async def lookup_user_by_username(self, username):
        """GET /admin/users/lookup?username={name} -> {telegram_id,
        username, first_name, balance}. A 404 with a "User not
        found" body means no Paxyo user has that username ->
        {"user_not_found": True}. Any other 404 means the endpoint
        is not live yet -> None (same 404-tolerance as the other
        admin reads). Other errors raise. (The contract is
        server/api-admin-user-lookup.php.) The username is matched
        exactly against auth.username, a leading @ stripped first."""
        path = f"/admin/users/lookup?username={username}"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                if "user not found" in _error_message(exc).lower():
                    return {"user_not_found": True}
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def get_user_deposits(self, telegram_id):
        """GET /admin/users/{id}/deposits -> {telegram_id,
        deposits: [{id, amount, method, status, created_at}]}, at
        most 3, newest first. A 404 with a "User not found" body
        means the user does not exist -> {"user_not_found": True}.
        Any other 404 means the endpoint is not live yet -> None.
        Other errors raise. (The contract is
        server/api-admin-user-deposits.php.) The method comes from
        the deposit's chapa_response record, so it can be null
        when it was never recorded — never a guessed method."""
        path = f"/admin/users/{int(telegram_id)}/deposits"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                if "user not found" in _error_message(exc).lower():
                    return {"user_not_found": True}
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def get_user_ban(self, telegram_id):
        """GET /admin/users/{id}/ban -> {telegram_id, username,
        banned}. A 404 with a "User not found" body means the user
        does not exist -> {"user_not_found": True}. Any other 404
        means the endpoint is not live yet -> None. Other errors
        raise. (The contract is server/api-admin-user-ban.php.)"""
        path = f"/admin/users/{int(telegram_id)}/ban"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                if "user not found" in _error_message(exc).lower():
                    return {"user_not_found": True}
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def set_user_ban(self, telegram_id, action,
                           admin_telegram_id, confirm_token):
        """POST /admin/users/{id}/ban {action ("ban"|"unban"),
        admin_telegram_id, confirm_token} -> {ok, telegram_id,
        banned}. Errors raise — the caller maps 404/403 to the
        plain messages in server/api-admin-user-ban.php. (The
        contract is that file; the HMAC token is minted by
        mint_admin_ban_token, only after William taps Confirm.)"""
        return await self._send(
            build_api_request(
                "POST",
                f"/admin/users/{int(telegram_id)}/ban",
                {
                    "action": action,
                    "admin_telegram_id": int(admin_telegram_id),
                    "confirm_token": confirm_token,
                },
            )
        )

    async def list_price_overrides(self):
        """GET /admin/service-price-overrides -> {overrides:
        [{provider, service_id, combined_id, price_etb,
        updated_at}]}. 404 -> None (endpoint not live yet). Other
        errors raise. (The contract is
        server/api-admin-service-price.php.)"""
        path = "/admin/service-price-overrides"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def set_price_override(self, provider, service_id, price_etb,
                                 admin_telegram_id, confirm_token):
        """POST /admin/service-price/set {provider, service_id,
        price_etb, admin_telegram_id, confirm_token} -> {ok,
        provider, service_id, combined_id, price_etb}. Errors
        raise — the caller maps 404/403/400 to the plain messages
        in server/api-admin-service-price.php. (The contract is
        that file; the HMAC token is minted by
        mint_admin_price_token, only after William taps Confirm.)"""
        return await self._send(
            build_api_request(
                "POST",
                "/admin/service-price/set",
                {
                    "provider": provider,
                    "service_id": int(service_id),
                    "price_etb": float(price_etb),
                    "admin_telegram_id": int(admin_telegram_id),
                    "confirm_token": confirm_token,
                },
            )
        )

    async def clear_price_override(self, provider, service_id,
                                   admin_telegram_id, confirm_token):
        """POST /admin/service-price/clear {provider, service_id,
        admin_telegram_id, confirm_token} -> {ok, provider,
        service_id, combined_id, cleared}. Errors raise — the
        caller maps 404/403 to the plain messages in
        server/api-admin-service-price.php. (The contract is that
        file; the HMAC token is minted by mint_admin_price_token
        with no price, only after William taps Confirm.)"""
        return await self._send(
            build_api_request(
                "POST",
                "/admin/service-price/clear",
                {
                    "provider": provider,
                    "service_id": int(service_id),
                    "admin_telegram_id": int(admin_telegram_id),
                    "confirm_token": confirm_token,
                },
            )
        )

    async def create_promo_code(self, code, percent=None, expires_at=None,
                                max_uses=None, fixed_etb=None):
        """POST /promo-codes {code, percent?|fixed_etb?, expires_at?,
        max_uses?} -> {ok, code, percent, fixed_etb, active,
        expires_at, max_uses}. Either a percent (1–100) or a fixed
        ETB bonus — never both, never neither (the client-side
        validator enforces it before any Confirm). 404 -> None
        (endpoint not live yet). Any other error raises (409 = the
        code already exists)."""
        body = {"code": code}
        if percent is not None:
            body["percent"] = int(percent)
        if fixed_etb is not None:
            body["fixed_etb"] = float(fixed_etb)
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

    async def disputes(self):
        """GET /disputes — the open disputes (15, 15 Nov 2026):
        {disputes: [{id, order_id, telegram_id, username, message,
        created_at}], ...}, newest first, max 50. 404 -> None
        (endpoint not live yet)."""
        try:
            data = await self._send(build_api_request("GET", "/disputes"))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /disputes returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def close_dispute(self, dispute_id):
        """POST /disputes/{id}/close -> {ok, id, status}. 404 ->
        None (endpoint not live yet, or the dispute is already
        closed). Any other error raises."""
        try:
            data = await self._send(
                build_api_request("POST", f"/disputes/{dispute_id}/close")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning(
                    "POST /disputes/%s/close returned 404 (endpoint not live yet)",
                    dispute_id,
                )
                return None
            raise
        return data if isinstance(data, dict) else None

    async def profitable(self):
        """GET /admin/profitable — the services earning the most
        (16, 15 Nov 2026): {services: [{service_id, service_name,
        orders, quantity, revenue_etb, profit_etb}], ...}, top 10
        by profit. 404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request("GET", "/admin/profitable")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /admin/profitable returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def deposits_by_method(self):
        """GET /admin/deposits-by-method — completed deposits
        broken down by method (18, 15 Nov 2026): {methods:
        [{method, count_7d, amount_7d, count_all, amount_all}],
        ...} for Telebirr, CBE, M-Pesa and CBE Birr. 404 -> None
        (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request("GET", "/admin/deposits-by-method")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /admin/deposits-by-method returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def satisfaction(self):
        """GET /satisfaction — the 👍/👎 feedback score (20, 15 Nov
        2026): {total, positive, negative, percent_positive}.
        404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request("GET", "/satisfaction")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /satisfaction returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def weekly_stats(self):
        """GET /admin/weekly — this week vs last week (27, 15 Nov
        2026): {this_week: {users, orders, completed, revenue_etb,
        net_profit_etb, deposits_count, deposits_etb, from, to},
        last_week: {...}, changes: {users_pct, orders_pct,
        revenue_pct, profit_pct}}. Weeks are EAT Monday–Sunday.
        404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request("GET", "/admin/weekly")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /admin/weekly returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def weekly_sent(self, monday_str: str):
        """GET /admin/weekly-sent?date=YYYY-MM-DD (the Monday) ->
        {date, sent}. 404 -> None (endpoint not live yet — the
        caller falls back to the in-memory marker)."""
        path = f"/admin/weekly-sent?date={monday_str}"
        try:
            data = await self._send(build_api_request("GET", path))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET %s returned 404 (endpoint not live yet)", path)
                return None
            raise
        return data if isinstance(data, dict) else None

    async def mark_weekly_sent(self, monday_str: str):
        """POST /admin/weekly-sent {date} -> {ok, date, sent}.
        404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request(
                    "POST", "/admin/weekly-sent", {"date": monday_str}
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("POST /admin/weekly-sent returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def promo_codes(self):
        """GET /promo-codes — every promo code (25, 15 Nov 2026):
        {codes: [{code, percent, fixed_etb, active, expires_at,
        max_uses, used}]}. 404 -> None (endpoint not live yet)."""
        try:
            data = await self._send(
                build_api_request("GET", "/promo-codes")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("GET /promo-codes returned 404 (endpoint not live yet)")
                return None
            raise
        return data if isinstance(data, dict) else None

    async def promo_off(self, code):
        """POST /promo-codes/{code}/off -> {ok, code, active}.
        404 -> None (endpoint not live yet, or the code does not
        exist). Any other error raises."""
        try:
            data = await self._send(
                build_api_request("POST", f"/promo-codes/{code}/off")
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning(
                    "POST /promo-codes/%s/off returned 404 (endpoint not live yet)",
                    code,
                )
                return None
            raise
        return data if isinstance(data, dict) else None


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
#   {"kind": "promo", "code": ..., "percent": <int|None>,
#    "fixed_etb": <float|None>, "expires_at": <"YYYY-MM-DD 23:59:59"|None>,
#    "max_uses": <int|None>}
# A dispute-close entry (Confirm-gated, like every other change):
#   {"kind": "dispute_close", "dispute_id": ...,
#    "order_id": <int|None>, "message": <str|None>}
# A win-back entry (audience frozen at preview time — the count
# shown is the count messaged):
#   {"kind": "winback",
#    "users": [{"telegram_id": ..., "usual_service": ...,
#               "usual_quantity": ...}, ...]}
# A balance-adjustment entry (current balance read at preview
# time; the HMAC token is minted only when the Confirm runs, and
# the server re-checks the never-below-zero guard atomically):
#   {"kind": "balance_adjust", "telegram_id": ...,
#    "delta_etb": <float, +add / -remove>,
#    "current_balance": <float>, "new_balance": <float>,
#    "user_label": "@name (id)"}
PENDING = {}

CONFIRM_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Confirm", callback_data="admin_confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel"),
    ]
])

_YES_WORDS = {"yes", "confirm", "send it", "do it", "ok", "okay"}
_NO_WORDS = {"no", "cancel", "don't send", "dont send", "stop"}

# Typo tolerance for the deterministic parsers (07-admin-english,
# 15 Nov 2026 — same idea as the order bot's TYPO_MAP, but only
# the admin words). The keys are the typo'd forms William actually
# types; the values are what the parsers match on. Applied to the
# lowercased detection copy inside each parser — never to a value
# the bot shows back (ticker text, broadcast message), which keeps
# the user's own words.
_ADMIN_TYPO_MAP = {
    "profite": "profit", "revenu": "revenue",
    "deposite": "deposit", "deposites": "deposits",
    "broadcst": "broadcast", "refuned": "refund",
    "prom": "promo", "disput": "dispute",
    "satisfacion": "satisfaction", "wekly": "weekly",
    "mornig": "morning", "usrs": "users", "ordrs": "orders",
    "servise": "service", "tickr": "ticker",
    "winbak": "winback", "loyalti": "loyalty",
    "fruad": "fraud", "reprot": "report",
    "balence": "balance", "mesage": "message",
    "chnage": "change", "mony": "money", "mad": "made",
    "tody": "today", "ernd": "earned",
    "custmers": "customers", "nevr": "never",
}


def _normalize_admin_text(s: str) -> str:
    """Fix the common admin typos in a lowercased string, one
    whole word at a time. Input is expected lowercased already."""
    if not s:
        return s
    for bad, good in _ADMIN_TYPO_MAP.items():
        s = re.sub(r"\b" + bad + r"\b", good, s)
    return s


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
    {"kind": revenue|profit|users|orders|deposits|top_service|summary,
     "days": N, "yesterday": bool} or None when the message is not
    a stats question. "Yesterday" is recognised but NOT supported
    by the endpoint (windows end today) — the answer says so."""
    s = _normalize_admin_text(re.sub(r"\s+", " ", (text or "").lower()).strip())
    if not s:
        return None
    # Questions the stats endpoint cannot answer (07-admin-english,
    # 15 Nov 2026): pending / big / threshold deposits, per-user
    # deposit counts, and anything about the provider. They fall
    # through to the AI, which says so honestly, instead of the
    # bot answering with the wrong figure (e.g. total deposits
    # for "how many users never deposited").
    if (
        "pending" in s
        or "big deposit" in s
        or "provider" in s
        or ("users" in s and "deposit" in s)
        or re.search(r"over\s+\d+", s)
    ):
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
    # Net profit (07-admin-english, 15 Nov 2026): "how much profit",
    # "what is our net profit". Checked BEFORE revenue — "how much
    # profit did we make" would match revenue's "how much"+"make".
    # The word-boundary check keeps "profitable" out: "most
    # profitable services" is a services question, not a profit
    # figure. The shape guard keeps "top 10 by profit" out too —
    # that is the profitable-services list, handled by the plain
    # -language report router.
    if re.search(r"\bprofit\b", s) and (
        "how much" in s or "what" in s or "net profit" in s
        or s.startswith("profit") or "show" in s
    ):
        return {"kind": "profit", "days": days, "yesterday": yesterday}
    if (
        ("how much" in s and ("made" in s or "make" in s or "earn" in s))
        or ("earn" in s and ("we" in s or "did" in s))
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
    low = _normalize_admin_text(s.lower())
    if "send" not in low and "broadcast" not in low \
            and "message" not in low and "tell" not in low:
        return None
    head, message = _split_broadcast_message(s)
    head_low = _normalize_admin_text(head.lower())
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
    text, or None when the message is not a ticker change. The
    keyword match is typo-tolerant (chnage, tickr/ticke) and
    "announcement" means the ticker too (07-admin-english, 15 Nov
    2026); the VALUE is always taken from the user's own words,
    never from a normalised copy."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    m = re.search(
        r"(?:change|chnage|set|update)\s+(?:the\s+)?(?:tick\w*|announcement)"
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
    m = re.search(
        r"\brefund\s+(?:order\s+)?#?(\d+)\b",
        _normalize_admin_text(s.lower()), re.IGNORECASE,
    )
    if not m:
        return None
    try:
        order_id = int(m.group(1))
    except ValueError:
        return None
    if order_id <= 0:
        return None
    return {"order_id": order_id}


def _balance_user_id(text: str):
    """The Telegram id in a balance command: 5+ digits standing
    on their own (\"balance of 779060335\", \"add 500 ETB to
    779060335\"). A phone number cannot identify a user — the auth
    table has no phone column — so only a Telegram id counts, and
    anything shorter than 5 digits is refused as too short to be
    one. Returns the int id, or None."""
    m = re.search(r"(?<!\d)(\d{5,15})(?!\d)", text or "")
    if not m:
        return None
    try:
        user_id = int(m.group(1))
    except ValueError:
        return None
    return user_id if user_id > 0 else None


def _user_target_from_text(text: str):
    """The user named in an admin command: a Telegram id (5-15
    digits standing on their own) or a @username, as {"telegram_id":
    N} or {"username": "name"} — or None when the text names no
    user at all. A bare username without the @ is only read after
    "of" / "for" / "to" / "from" / "user" ("balance of william",
    "add 500 ETB to william"), never as a bare word elsewhere, so
    a command word can never be mistaken for a name. Reserved
    words (balance, deposit, order, service, price, history, ban,
    unban, user) never count as a username. The username keeps
    its typed spelling; the server matches it exactly against
    auth.username (a leading @ is stripped there)."""
    s = (text or "").strip()
    if not s:
        return None
    # @username first: the @ is unambiguous.
    m = re.search(r"@([A-Za-z][A-Za-z0-9_]{4,31})\b", s)
    if m:
        return {"username": m.group(1)}
    # A Telegram id: 5+ digits standing on their own.
    user_id = _balance_user_id(s)
    if user_id is not None:
        return {"telegram_id": user_id}
    # A bare username after of / for / to / from / user / ban /
    # unban / deposit / deposits / history ("balance of william",
    # "add 500 ETB to william", "ban william", "show deposits
    # william"). A word scan, not a regex finditer: in "deposit
    # history william" the word "history" is both the word after
    # "deposit" (reserved, skipped) and the keyword before
    # "william" — a finditer would consume it once and miss the
    # second reading.
    keywords = {
        "of", "for", "to", "from", "user", "ban", "unban",
        "deposit", "deposits", "history",
    }
    reserved = {
        "balance", "deposit", "deposits", "order", "service",
        "price", "history", "ban", "unban", "user",
    }
    tokens = s.split()
    for i, tok in enumerate(tokens):
        if tok.lower().strip(".,?!") not in keywords:
            continue
        if i + 1 >= len(tokens):
            continue
        name = tokens[i + 1].strip(".,?!@")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", name):
            continue
        if name.lower() not in reserved:
            return {"username": name}
    return None


async def _resolve_user_target(target):
    """Resolve a parsed user target ({"telegram_id": N} or
    {"username": "name"}) to a user record {telegram_id, username,
    first_name, balance}. Returns (record, None) on success, or
    (None, error_text) when the user does not exist or the lookup
    endpoint is not live yet. The error text names the target the
    way William typed it (id or @username). A Telegram id is
    looked up by the balance endpoint; a username by the lookup
    endpoint — both return the same record shape, so every caller
    below works the same for either target."""
    if "telegram_id" in target:
        tg_id = target["telegram_id"]
        try:
            record = await admin_api.get_user_balance(tg_id)
        except Exception as exc:
            log.warning("get_user_balance failed: %s", exc)
            return None, (
                f"Could not look up user {tg_id}. Please try again."
            )
        if record is None:
            return None, (
                "The balance lookup is not connected yet. "
                f"I couldn't look up user {tg_id}."
            )
        if record.get("user_not_found"):
            return None, f"There is no Paxyo user with Telegram id {tg_id}."
        return record, None
    name = target["username"]
    try:
        record = await admin_api.lookup_user_by_username(name)
    except Exception as exc:
        log.warning("lookup_user_by_username failed: %s", exc)
        return None, (
            f"Could not look up user @{name}. Please try again."
        )
    if record is None:
        return None, (
            "The user lookup is not connected yet. "
            f"I couldn't look up user @{name}."
        )
    if record.get("user_not_found"):
        return None, f"There is no Paxyo user with username @{name}."
    return record, None


def parse_balance_check_command(text: str):
    """Deterministic balance-check parser. "balance of 779060335",
    "what is the balance of 779060335", "show balance 779060335",
    "user balance 779060335" -> {"telegram_id": 779060335}. A
    @username works the same way ("balance of @william" ->
    {"username": "william"}); a bare username after "of" does too
    ("balance of william"). None when there is no user target, or
    when the message is about a balance adjustment ("add ... to
    ...", "remove ... from ...") or the provider balance
    ("provider balance") — those are not a user lookup. A bare
    "what is my balance?" is a question for the AI, not a command."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    if "balance" not in low:
        return None
    if "provider" in low:
        return None
    # An adjustment wording with an amount is an update, never a
    # check ("add 500 ETB to ..." parses as an adjustment below).
    # A bare action word without an amount ("take a look at the
    # balance of ...") is still a check.
    if parse_balance_adjust_command(s) is not None:
        return None
    if not re.search(r"\bbalance\b", low):
        return None
    return _user_target_from_text(low)


def parse_balance_adjust_command(text: str):
    """Deterministic balance-adjustment parser. "add 500 ETB to
    779060335", "give 250 to 779060335", "remove 200 ETB from
    779060335", "deduct 100 birr from 779060335" ->
    {"telegram_id": 779060335, "delta_etb": +500.0 / -200.0}.
    The amount is the number next to the action word (with an
    optional ETB/birr unit); the user is the Telegram id at the
    end. None when there is no action word, no amount, or no user
    id. A zero or negative amount is returned as-is and refused
    by the handler with a plain message — it is never silently
    re-read as a different command."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    m = re.search(
        r"\b(add|give|credit|top\s*up)\b\s*(\d+(?:\.\d+)?)\s*(?:etb|birr)?\b"
        r"|\b(remove|deduct|take|subtract|debit)\b\s*(\d+(?:\.\d+)?)\s*(?:etb|birr)?\b",
        low,
    )
    if not m:
        return None
    if m.group(1) is not None:
        sign = 1.0
        amount_text = m.group(2)
    else:
        sign = -1.0
        amount_text = m.group(4)
    try:
        amount = float(amount_text)
    except (TypeError, ValueError):
        return None
    # The user is the Telegram id or @username AFTER the amount
    # (the "to 779060335" / "from @william" at the end); never the
    # amount itself.
    rest = low[m.end():]
    target = _user_target_from_text(rest)
    if target is None:
        return None
    return {**target, "delta_etb": sign * amount}


def parse_deposit_history_command(text: str):
    """Deterministic deposit-history parser. "deposit history of
    779060335", "last deposits @william", "show deposits william",
    "deposits of 779060335" -> {"telegram_id": ...} or
    {"username": ...}. None when there is no user target, or when
    the message is the deposits-by-method report ("deposits by
    method") or a deposit itself (no "history"/"last"/"show"/"of"
    wording). A bare "show me the deposits" is a question for the
    AI, not a command."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    if "deposit" not in low:
        return None
    if "by method" in low:
        return None
    if not re.search(
        r"\b(?:history|last)\b.*\bdeposits?\b|\bdeposits?\s+of\b"
        r"|\bshow\b.*\bdeposits?\b|\bdeposit\s+history\b",
        low,
    ):
        return None
    return _user_target_from_text(low)


def parse_ban_command(text: str):
    """Deterministic ban parser. "ban 779060335", "ban user
    @william", "ban william" -> {"telegram_id": ...} or
    {"username": ...} with "action": "ban". None when there is no
    user target, or when the message is an unban ("unban ..." is
    the unban command, parsed separately). A bare "ban him" with
    no user is a question for the AI, not a command."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    if not re.search(r"(?<!un)\bban\b", low):
        return None
    if re.search(r"\bunban\b", low):
        return None
    target = _user_target_from_text(low)
    if target is None:
        return None
    return {**target, "action": "ban"}


def parse_unban_command(text: str):
    """Deterministic unban parser. "unban 779060335", "unban user
    @william", "unban william" -> {"telegram_id": ...} or
    {"username": ...} with "action": "unban". None when there is
    no user target."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    if not re.search(r"\bunban\b", low):
        return None
    target = _user_target_from_text(low)
    if target is None:
        return None
    return {**target, "action": "unban"}


def _price_service_target(text: str):
    """The (provider, service_id) named in a price command:
    "gop service 6139" / "smm service 6139" -> ("gop"/"smm",
    6139); "service 6139" / a bare "6139" after "price" ->
    (None, 6139) — the provider is resolved from the catalogue by
    the handler. None when there is no service id at all."""
    low = _normalize_admin_text((text or "").lower())
    m = re.search(
        r"\b(gop|smm)\s+service\s+(\d+)\b|\bservice\s+(\d+)\b",
        low,
    )
    if m:
        if m.group(1) is not None:
            return (m.group(1), int(m.group(2)))
        return (None, int(m.group(3)))
    m = re.search(r"\bprice\b.*?(\d+)\b", low)
    if m:
        return (None, int(m.group(1)))
    return None


def parse_price_set_command(text: str):
    """Deterministic price-set parser. "set price of service 6139
    to 50 ETB", "edit price 6139 50", "change price of gop service
    6139 to 50 ETB" -> {"provider": "gop"|"smm"|None,
    "service_id": 6139, "price_etb": 50.0}. The provider word is
    optional — without it the handler resolves it from the
    catalogue. None when there is no service id or no amount. A
    zero or negative amount is returned as-is and refused by the
    handler with a plain message — it is never silently re-read
    as a different command."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    if not re.search(r"\b(?:set|edit|change|update)\b.*\bprice\b", low):
        return None
    target = _price_service_target(low)
    if target is None:
        return None
    provider, service_id = target
    # The amount is the number next to "to" / after the service id
    # ("to 50 ETB", "6139 50"), with an optional ETB/birr unit.
    # The minus is part of the number: "to -10 ETB" parses as -10
    # and is refused by the handler, never silently read as +10.
    m = re.search(
        r"\bto\s+(-?\d+(?:\.\d+)?)\s*(?:etb|birr)?\b", low
    )
    if m is None:
        m = re.search(
            r"\bservice\s+\d+\s+(-?\d+(?:\.\d+)?)\s*(?:etb|birr)?\b",
            low,
        )
    if m is None:
        m = re.search(
            r"\bprice\b.*?(-?\d+(?:\.\d+)?)\s*(?:etb|birr)\b", low
        )
    if m is None:
        # A bare trailing number ("edit price 6139 50"): the last
        # number is the amount, unless it is the service id itself
        # ("set price 6139" names no amount at all).
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*$", low)
        if m is not None and float(m.group(1)) == service_id:
            m = None
    if m is None:
        return None
    try:
        price = float(m.group(1))
    except (TypeError, ValueError):
        return None
    return {
        "provider": provider,
        "service_id": service_id,
        "price_etb": price,
    }


def parse_price_clear_command(text: str):
    """Deterministic price-clear parser. "clear price of service
    6139", "remove price override 6139", "reset price of smm
    service 6139" -> {"provider": "gop"|"smm"|None,
    "service_id": 6139}. None when there is no service id, or
    when the message is a price SET ("set ... to 50 ETB" parses
    as a set, never as a clear)."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    if not re.search(
        r"\b(?:clear|remove|reset|delete)\b.*\bprice\b", low
    ):
        return None
    if parse_price_set_command(s) is not None:
        return None
    target = _price_service_target(low)
    if target is None:
        return None
    provider, service_id = target
    return {"provider": provider, "service_id": service_id}


def parse_price_show_command(text: str):
    """Deterministic price-show parser. "show price of service
    6139", "price of service 6139", "what is the price of service
    6139" -> {"provider": "gop"|"smm"|None, "service_id": 6139}.
    None when there is no service id, or when the message is a
    price SET or CLEAR — those parse as a set or a clear, never
    as a show."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return None
    low = _normalize_admin_text(s.lower())
    if "price" not in low or "service" not in low:
        return None
    if parse_price_set_command(s) is not None:
        return None
    if parse_price_clear_command(s) is not None:
        return None
    target = _price_service_target(low)
    if target is None:
        return None
    provider, service_id = target
    return {"provider": provider, "service_id": service_id}


def _balance_user_label(record: dict) -> str:
    """\"@username (779060335)\" or \"user 779060335\" for a balance
    reply, from a GET /admin/users/{id}/balance record."""
    name = str(record.get("username") or "").strip()
    first = str(record.get("first_name") or "").strip()
    label = name or first
    tg_id = record.get("telegram_id")
    if label:
        return f"{label} ({tg_id})"
    return f"user {tg_id}"


def _balance_preview(pending: dict) -> str:
    """The Confirm preview for a balance adjustment: who, what,
    current balance, new balance. Nothing here moves money — the
    adjustment runs only on Confirm."""
    action = "Add" if pending["delta_etb"] > 0 else "Remove"
    return (
        f"{action} {format_money(abs(pending['delta_etb']))} ETB "
        f"{'to' if pending['delta_etb'] > 0 else 'from'} "
        f"{pending['user_label']}?\n\n"
        f"Current balance: {format_money(pending['current_balance'])} ETB\n"
        f"New balance: {format_money(pending['new_balance'])} ETB\n\n"
        "Tap Confirm to adjust the balance, or Cancel."
    )


def _balance_error_text(pending: dict, exc) -> str:
    """Plain balance-adjustment failure message: the server's 409
    / 403 / 404 text shown as-is, anything else a short generic
    line. A 404 here means the endpoint is not live yet (the user
    was looked up before the preview, so the user exists)."""
    status = exc.response.status_code if exc.response is not None else None
    msg = _error_message(exc)
    if status == 404:
        return (
            "The balance endpoint is not connected yet — "
            "nothing was changed."
        )
    if status == 403:
        return msg or "You are not allowed to adjust this balance."
    if status == 409:
        return msg or (
            "That adjustment was refused — nothing was changed."
        )
    if msg:
        return f"Could not adjust the balance — {msg}"
    return "Could not adjust the balance — please try again."


def format_deposit_history(record: dict, deposits) -> str:
    """The last-3 deposit list for a user: one line per deposit —
    amount, method, date, status. A deposit with no recorded
    method says so plainly, never a guessed method. No deposits
    at all says so plainly too."""
    label = _balance_user_label(record)
    deposits = list(deposits or [])
    if not deposits:
        return f"No deposits yet for {label}."
    lines = [f"Last {len(deposits)} deposit{'s' if len(deposits) != 1 else ''} for {label}:"]
    for d in deposits:
        amount = d.get("amount")
        amount_text = format_money(amount) if amount is not None else "?"
        method = str(d.get("method") or "").strip() or "method not recorded"
        created = str(d.get("created_at") or "")[:16]
        status = str(d.get("status") or "").strip() or "?"
        lines.append(f"{amount_text} ETB, {method}, {created}, {status}")
    return "\n".join(lines)


def _ban_preview(pending: dict) -> str:
    """The Confirm preview for a ban / unban: who, what, current
    state. Nothing here bans anyone — the ban runs only on
    Confirm."""
    action = "Ban" if pending["action"] == "ban" else "Unban"
    state = "banned" if pending["currently_banned"] else "not banned"
    return (
        f"{action} {pending['user_label']}?\n\n"
        f"Currently: {state}.\n\n"
        "Tap Confirm to go ahead, or Cancel."
    )


def _ban_error_text(pending: dict, exc) -> str:
    """Plain ban/unban failure message: the server's 403 / 404
    text shown as-is, anything else a short generic line. A 404
    here means the endpoint is not live yet (the user was looked
    up before the preview, so the user exists)."""
    status = exc.response.status_code if exc.response is not None else None
    msg = _error_message(exc)
    if status == 404:
        return (
            "The ban endpoint is not connected yet. "
            "Nothing was changed."
        )
    if status == 403:
        return msg or "You are not allowed to ban this user."
    if msg:
        verb = "ban" if pending["action"] == "ban" else "unban"
        return f"Could not {verb} the user. {msg}"
    verb = "ban" if pending["action"] == "ban" else "unban"
    return f"Could not {verb} the user. Please try again."


def _price_label(provider: str, service_id: int) -> str:
    """\"gop:6139\" — the combined id, the only id that never
    collides between the two providers."""
    return f"{provider}:{int(service_id)}"


def _price_set_preview(pending: dict) -> str:
    """The Confirm preview for a price set: which service, current
    price, new price. Nothing here changes a price — the override
    is written only on Confirm."""
    current = pending.get("current_price")
    current_text = (
        f"{format_money(current)} ETB per 1000"
        if current is not None
        else "not in the live list"
    )
    if pending.get("current_override") is not None:
        current_text += " (override)"
    return (
        f"Set the price of service {pending['combined_id']} to "
        f"{format_money(pending['price_etb'])} ETB per 1000?\n\n"
        f"Current price: {current_text}\n\n"
        "Tap Confirm to set the price, or Cancel."
    )


def _price_clear_preview(pending: dict) -> str:
    """The Confirm preview for clearing a price override: which
    service, the override being cleared, the price it falls back
    to. Nothing here changes a price — the override is cleared
    only on Confirm."""
    current = pending.get("current_price")
    current_text = (
        f"{format_money(current)} ETB per 1000"
        if current is not None
        else "not in the live list"
    )
    return (
        f"Clear the price override for service "
        f"{pending['combined_id']}?\n\n"
        f"Override now: {format_money(pending['current_override'])} ETB per 1000\n"
        f"Normal price: {current_text}\n\n"
        "Tap Confirm to clear it, or Cancel."
    )


def _price_error_text(pending: dict, exc) -> str:
    """Plain price-set/clear failure message: the server's 400 /
    403 / 404 text shown as-is, anything else a short generic
    line. A 404 here means the endpoint is not live yet."""
    status = exc.response.status_code if exc.response is not None else None
    msg = _error_message(exc)
    if status == 404:
        return (
            "The price endpoint is not connected yet. "
            "Nothing was changed."
        )
    if status == 403:
        return msg or "You are not allowed to change this price."
    if status == 400:
        return msg or "That price was refused. Nothing was changed."
    if msg:
        return f"Could not change the price. {msg}"
    return "Could not change the price. Please try again."


async def _resolve_price_provider(parsed: dict):
    """Resolve the provider for a price command: the parsed
    provider word wins; otherwise an override for exactly one
    provider settles it, otherwise the live catalogue (GOP only)
    — an id in it is GOP. Anything else is unresolved and the
    handler asks William to say "gop" or "smm".
    Returns (provider-or-None, catalogue_price-or-None,
    override_price-or-None, error_text-or-None). The catalogue
    price is the live list's price for a GOP service, None
    otherwise (the admin bot cannot see SMM catalogue prices —
    the live list is GOP only — so an SMM service with no
    override has no known current price)."""
    provider = parsed.get("provider")
    service_id = parsed["service_id"]
    # Overrides for this service id, by provider: at most one row
    # per provider, so this also settles an ambiguous id when only
    # one side has an override.
    overrides = {}
    try:
        data = await admin_api.list_price_overrides()
    except Exception as exc:
        log.warning("list_price_overrides failed: %s", exc)
        data = None
    if isinstance(data, dict):
        for row in data.get("overrides") or []:
            if not isinstance(row, dict):
                continue
            try:
                if int(row.get("service_id")) != service_id:
                    continue
            except (TypeError, ValueError):
                continue
            overrides[str(row.get("provider") or "")] = row
    if provider is None:
        if len(overrides) == 1:
            provider = next(iter(overrides))
        else:
            try:
                services = await admin_api.services()
            except Exception as exc:
                log.warning("services lookup failed: %s", exc)
                services = []
            found = False
            catalogue_price = None
            for svc in services or []:
                if not isinstance(svc, dict):
                    continue
                try:
                    sid = int(svc.get("service", svc.get("id")))
                except (TypeError, ValueError):
                    continue
                if sid == service_id:
                    found = True
                    try:
                        catalogue_price = float(
                            svc.get("rate_etb_per_1000", svc.get("price", 0))
                        )
                    except (TypeError, ValueError):
                        catalogue_price = None
                    break
            if not found:
                return (
                    None, None, None,
                    f"I don't see service {service_id} in the live list. "
                    "If it is an SMM service, say \"smm service "
                    f"{service_id}\". Or give me the right service id.",
                )
            provider = "gop"
            override_price = None
            row = overrides.get("gop")
            if row is not None:
                try:
                    override_price = float(row.get("price_etb"))
                except (TypeError, ValueError):
                    override_price = None
            return provider, catalogue_price, override_price, None
    # A provider is settled: the override for it (if any) and,
    # for GOP, the catalogue price.
    override_price = None
    row = overrides.get(provider)
    if row is not None:
        try:
            override_price = float(row.get("price_etb"))
        except (TypeError, ValueError):
            override_price = None
    catalogue_price = None
    if provider == "gop":
        try:
            services = await admin_api.services()
        except Exception as exc:
            log.warning("services lookup failed: %s", exc)
            services = []
        for svc in services or []:
            if not isinstance(svc, dict):
                continue
            try:
                sid = int(svc.get("service", svc.get("id")))
            except (TypeError, ValueError):
                continue
            if sid == service_id:
                try:
                    catalogue_price = float(
                        svc.get("rate_etb_per_1000", svc.get("price", 0))
                    )
                except (TypeError, ValueError):
                    catalogue_price = None
                break
    return provider, catalogue_price, override_price, None


def parse_promo_create_command(text: str):
    """Deterministic promo-code creation parser. "create promo code
    PAXYO20 20%", "new promo code WELCOME10 10 percent" ->
    {"code": "PAXYO20", "percent": 20, "fixed_etb": None,
     "expires_at": "2026-12-31 23:59:59"|None, "max_uses": 100|None}.
    A fixed ETB bonus instead of a percent (25, 15 Nov 2026):
    "create promo code FLAT100 100 ETB" -> {"fixed_etb": 100,
    "percent": None}. Optional "expires 2026-12-31" and "max 100
    uses" are parsed when present. The code is uppercased here
    (the server normalises the same way). percent / fixed_etb are
    None when neither was given — the handler then asks for one,
    plainly. The code keeps its raw shape for validate_promo_create,
    which refuses bad ones before any Confirm."""
    s = _normalize_admin_text(
        re.sub(r"\s+", " ", (text or "").strip()).lower()
    )
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
    fixed_etb = None
    # A fixed amount: "100 ETB" / "100 birr" — not "100 uses"
    # (max uses is parsed separately below).
    fm = re.search(r"(\d+(?:\.\d+)?)\s*(?:ETB|birr)\b", rest, re.IGNORECASE)
    if fm:
        try:
            fixed_etb = float(fm.group(1))
        except ValueError:
            fixed_etb = None
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
        "fixed_etb": fixed_etb,
        "expires_at": expires_at,
        "max_uses": max_uses,
    }


def parse_promo_list_command(text: str):
    """"/promo list" / "list promo codes" / "show promo codes" /
    "show me the promo codes" / "list all promo codes" ->
    True, else None. (25, 15 Nov 2026; "me"/"all" added with
    07-admin-english, 15 Nov 2026.)"""
    s = _normalize_admin_text(
        re.sub(r"\s+", " ", (text or "").strip().lower())
    )
    if re.fullmatch(r"/promo\s+list", s) or re.fullmatch(
        r"(?:list|show|all)\s+(?:all\s+)?(?:me\s+)?(?:the\s+)?promo\s+codes?", s
    ):
        return True
    return None


def parse_promo_off_command(text: str):
    """"/promo off CODE" / "turn off promo code CODE" / "disable
    promo code CODE" -> {"code": "CODE"}, else None.
    (25, 15 Nov 2026.)"""
    s = _normalize_admin_text(
        re.sub(r"\s+", " ", (text or "").strip()).lower()
    )
    m = re.search(
        r"(?:/promo\s+off|turn\s+off|disable|deactivate)\s+(?:promo\s+code\s+)?([A-Za-z0-9]+)",
        s,
        re.IGNORECASE,
    )
    if not m:
        return None
    return {"code": m.group(1).strip().upper()}


# ------------------------------------------------- capability questions ---
# 19 Nov 2026 — William asked "Can we add promo code" and the AI
# answered that promo codes "can't be created from chat" and live in
# a "Promotions section" of the admin panel. Both were wrong: promo
# codes ARE created in chat ("create promo code PAXYO20 20%"), and
# there is no Promotions section. The exact commands already match
# above; a bare question about a capability fell through to the AI,
# which guessed. So questions are answered deterministically here,
# before the AI fallback, for every command family: the answer says
# plainly whether it can be done in chat and gives the exact wording
# to send. Nothing here runs a change — it is guidance only.
_CAPABILITY_ANSWERS = (
    # Promo codes — created in chat, never in a panel.
    (
        r"\bpromo\b",
        "Yes — you can create promo codes right here in chat. Send "
        "\"create promo code PAXYO20 20% expires 2026-12-31\" (or a "
        "fixed amount, like \"100 ETB\", and optional \"max 100 uses\"). "
        "I will show a preview and the code is created only after you "
        "tap Confirm. \"list promo codes\" shows every code, and "
        "\"turn off promo code PAXYO20\" switches one off.",
    ),
    # One user's balance, and changing it.
    (
        r"\bbalance\b",
        "Yes — ask me for one user's balance, like \"What is the "
        "balance of 779060335?\" or \"What is the balance of "
        "@username?\" To change a balance, send \"Add 500 ETB to "
        "779060335\" — I will show a preview first and it only happens "
        "after you tap Confirm.",
    ),
    # Deposit history.
    (
        r"\bdeposit history\b|\bdeposits\b",
        "Yes — send \"Deposit history of 779060335\" (or @username) and "
        "I will show the last 3 deposits.",
    ),
    # Looking a user up by @username.
    (
        r"\blook\s*up\b|\blookup\b|\bfind (?:a |the )?user\b",
        "Yes — I can look a user up by @username when you ask for "
        "their balance, deposit history or ban, for example \"What is "
        "the balance of @username?\"",
    ),
    # Ban / unban.
    (
        r"\bban\b|\bunban\b|\bblock (?:a |the )?user\b",
        "Yes — send \"Ban @username\" or \"Ban 779060335\" (\"Unban "
        "779060335\" to lift it). I will show a preview and it only "
        "happens after you tap Confirm.",
    ),
    # The price multiplier lives in Settings on the admin panel —
    # checked before the service-price entry below, so "change the
    # price multiplier" is never read as a service price.
    (
        r"\bmultiplier\b",
        "The price multiplier is changed in Settings on the admin "
        "panel — I can't change it here. I can change one service's "
        "price in chat, though: \"Set price of service 6139 to 50 "
        "ETB\".",
    ),
    # Service prices.
    (
        r"\bprice\b",
        "Yes — send \"Set price of service 6139 to 50 ETB\" to change "
        "one (preview, then Confirm), \"Show price of service 6139\" to "
        "see it, or \"Clear price of service 6139\" to remove an "
        "override.",
    ),
    # Refunds.
    (
        r"\brefund\b",
        "Yes — send \"Refund order #1841\" and I will show the order "
        "first; the refund only happens after you tap Confirm.",
    ),
    # One order's status.
    (
        r"\border\b.*\bstatus\b|\bstatus\b.*\border\b",
        "Yes — send \"What is the status of order #1841?\"",
    ),
    # Broadcasts.
    (
        r"\bbroadcast\b|\bmessage (?:the )?users\b|\bsend\b.*\busers\b",
        "Yes — send \"Send this to users who never deposited: <your "
        "message>\" and I will show how many users it would reach "
        "before you Confirm.",
    ),
    # Ticker.
    (
        r"\bticker\b",
        "Yes — send \"Change ticker to <new text>\" and I will show a "
        "preview first.",
    ),
    # Disputes.
    (
        r"\bdispute\b",
        "Yes — \"/disputes\" lists the open ones, and \"Close dispute "
        "#3\" closes one (preview, then Confirm).",
    ),
    # Win-backs.
    (
        r"\bwin-?back\b|\bwent quiet\b|\bquiet users\b",
        "Yes — send /winbacks and I will show how many users went "
        "quiet, then message each one after you Confirm.",
    ),
    # Reports.
    (
        r"\bmorning report\b|\bmorning\b",
        "Yes — send /morning for yesterday's money report.",
    ),
    (
        r"\bweekly report\b|\bweekly\b",
        "Yes — send /weekly for this week's report.",
    ),
    (
        r"\bmost profitable\b|\bprofitable services\b",
        "Yes — send /profitable or \"Show me the most profitable "
        "services\".",
    ),
    (
        r"\bsatisfaction\b",
        "Yes — send /satisfaction for the satisfaction report.",
    ),
    (
        r"\bdeposits by method\b",
        "Yes — send /deposits_by_method for deposits by method.",
    ),
    # Money / stats.
    (
        r"\bprofit\b|\brevenue\b|\bearn\b|"
        r"\bhow much\b.*\b(made|money)\b",
        "Yes — ask me straight, like \"How much did we make today?\" "
        "or \"How many users in the last 7 days?\"",
    ),
    # Things that live in the admin panel — an honest no.
    (
        r"\bloyalty\b",
        "That one lives in the admin panel — I can't list loyalty "
        "bonuses here.",
    ),
    (
        r"\bfraud\b",
        "That one lives in the admin panel — I can't list fraud flags "
        "here.",
    ),
    (
        r"\bresellers?\b",
        "That one lives in the admin panel — I can't list resellers "
        "here.",
    ),
    (
        r"\bconfused\b",
        "That one lives in the admin panel — I can't list confused "
        "chats here.",
    ),
    (
        r"\blist (?:the )?orders\b|\blist (?:the )?users\b",
        "That lives in the admin panel — I can't list orders or users "
        "here. I can look up one order (\"What is the status of order "
        "#1841?\") or one user's balance.",
    ),
    (
        r"\bcancel\b.*\border\b",
        "I can't cancel an order from chat — send \"Refund order "
        "#1841\" instead and I will show the order first.",
    ),
)


def parse_capability_question(text: str):
    """A natural question about what the bot can do — "can we add a
    promo code", "how do I check a balance", "can I ban a user" —
    -> the guidance answer, or None. Only question/ask forms match
    (can/could we|I|you, how do/can I|we, is it possible to, I want
    to, I'd like to): an actual command ("create promo code PAXYO20
    20%", "ban @william") is handled by its own parser above and
    never reaches here, and a general "what can you do" goes to the
    help/AI route, not here. (19 Nov 2026.)"""
    s = _normalize_admin_text(
        re.sub(r"\s+", " ", (text or "").strip().lower())
    )
    if not s:
        return None
    # A general "what can you do" is not a question about one
    # capability — it goes to the help/AI route, as before.
    if re.search(
        r"what can (you|this bot) do|what are your commands|"
        r"list your commands|show commands|show me what you can do",
        s,
    ):
        return None
    if not re.search(
        r"\b(?:can|could)\s+(?:we|i|you)\b"
        r"|\bhow\s+do\s+(?:i|we)\b"
        r"|\bhow\s+can\s+(?:i|we|you)\b"
        r"|\bis\s+it\s+possible\s+to\b"
        r"|\bi\s+want\s+to\b"
        r"|\bi'?d\s+like\s+to\b"
        r"|\bi\s+would\s+like\s+to\b",
        s,
    ):
        return None
    for pattern, answer in _CAPABILITY_ANSWERS:
        if re.search(pattern, s):
            return answer
    return None


def parse_dispute_close_command(text: str):
    """"/disputes close 3" / "close dispute #3" / "close dispute 3"
    / "resolve dispute #3" -> {"dispute_id": 3}, else None.
    (15, 15 Nov 2026; "resolve" added with 07-admin-english.)"""
    s = _normalize_admin_text(
        re.sub(r"\s+", " ", (text or "").strip()).lower()
    )
    m = re.search(
        r"(?:close|resolve)\s+dispute\s+#?(\d+)", s, re.IGNORECASE
    )
    if not m:
        return None
    try:
        return {"dispute_id": int(m.group(1))}
    except ValueError:
        return None


def parse_order_status_command(text: str):
    """One order's status in plain words (07-admin-english,
    15 Nov 2026): "what is the status of order #1841",
    "check order #1841", "order 1841 status", "where is order
    #1841", "is order #1841 done" -> {"order_id": 1841}. None
    when there is no order id, or when the message is a refund
    or a cancel — those are different flows, and a refund must
    never be read as a status check."""
    s = _normalize_admin_text(
        re.sub(r"\s+", " ", (text or "").strip()).lower()
    )
    if not s or "refund" in s or "cancel" in s:
        return None
    if not (
        "status" in s or "check" in s or "where is" in s
        or "done" in s or "finished" in s or "what happened" in s
    ):
        return None
    m = re.search(r"\border\s+#?(\d+)\b", s)
    if not m:
        return None
    try:
        order_id = int(m.group(1))
    except ValueError:
        return None
    if order_id <= 0:
        return None
    return {"order_id": order_id}


def parse_admin_report_command(text: str):
    """Plain-language routes to the existing /command reports
    (07-admin-english, 15 Nov 2026 — same precedent as the
    plain-language promo list/off and dispute-close steps in
    on_text). Returns one of "profitable" | "satisfaction" |
    "weekly" | "deposits_by_method" | "disputes" | "morning" |
    "winbacks" | "help", or None. Keyword checks only — the
    caller runs the matching /command handler, so the behaviour
    is exactly the command's behaviour."""
    s = _normalize_admin_text(
        re.sub(r"\s+", " ", (text or "").strip()).lower()
    )
    if not s:
        return None
    if (
        "went quiet" in s
        or "gone quiet" in s
        or "quiet users" in s
        or "win back" in s
        or "winback" in s
        or "hasn't ordered" in s
        or "has not ordered" in s
        or "stopped ordering" in s
        or "no orders in" in s
    ):
        return "winbacks"
    if "dispute" in s and (
        "open" in s or "any" in s or "show" in s or "list" in s
        or "how many" in s or "are there" in s
    ):
        return "disputes"
    if (
        "morning report" in s
        or "morning money" in s
        or "yesterday's numbers" in s
        or "yesterday's money" in s
        or "yesterday's report" in s
    ):
        return "morning"
    if (
        "weekly report" in s
        or "weekly growth" in s
        or "weekly summary" in s
        or "week's report" in s
        or "week's numbers" in s
        or "week report" in s
        or "vs last week" in s
        or "this week vs" in s
    ):
        return "weekly"
    if (
        "satisfaction" in s
        or "feedback score" in s
        or "feedback" in s
        or "rating" in s
        or "rate us" in s
        or "reviews" in s
        or "thumbs" in s
        or "how satisfied" in s
        or "what do users think" in s
        or "what do users say" in s
        or "happy" in s
    ):
        return "satisfaction"
    if (
        "most profitable" in s
        or "profitable services" in s
        or "top 10 by profit" in s
        or "make the most" in s
        or "earn the most" in s
        or "best earning" in s
    ):
        return "profitable"
    if (
        "deposits by method" in s
        or "deposits by payment method" in s
        or "deposit breakdown" in s
        or "which payment method" in s
        or "payment method brings" in s
        or "came in by" in s
        or "came by" in s
        or "by telebirr" in s
        or "by cbe" in s
        or "by m-pesa" in s
        or "by mpesa" in s
    ):
        return "deposits_by_method"
    if (
        s.strip() in ("help", "help please")
        or "what can you do" in s
        or "what can this bot do" in s
        or "what you can do" in s
        or "your commands" in s
        or "show commands" in s
        or "list your commands" in s
    ):
        return "help"
    return None


def validate_promo_create(parsed: dict):
    """Client-side promo-code validation, before any Confirm.
    Returns a plain refusal, or None when the code + bonus are
    usable. Code: letters + digits only, 4–20 chars. Bonus:
    EITHER a percent (1–100) OR a fixed ETB amount (>= 1) —
    never both, never neither. Expiry must be a real date, not in
    the past. Max uses must be at least 1."""
    code = (parsed.get("code") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
        return (
            "That code won't work — use 4–20 letters and digits, "
            "for example PAXYO20."
        )
    percent = parsed.get("percent")
    fixed_etb = parsed.get("fixed_etb")
    if percent is not None and fixed_etb is not None:
        return (
            "Pick one bonus for the code — a percent (for example "
            f"\"create promo code {code} 10%\") or a fixed amount "
            f"(for example \"create promo code {code} 100 ETB\"), "
            "not both."
        )
    if percent is None and fixed_etb is None:
        return (
            "Tell me the bonus too — a percent, for example "
            f"\"create promo code {code} 10%\", or a fixed amount, "
            f"for example \"create promo code {code} 100 ETB\"."
        )
    if percent is not None and (percent < 1 or percent > 100):
        return "The percent must be between 1 and 100."
    if fixed_etb is not None and fixed_etb < 1:
        return "The fixed amount must be at least 1 ETB."
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


def mint_admin_balance_token(telegram_id, delta_etb, admin_telegram_id,
                             secret=None):
    """HMAC-SHA256 confirm token for POST
    /admin/users/{id}/balance/adjust, keyed by BOT_API_SECRET over
    "admin-user-balance:{telegram_id}:{delta:.2f}:{admin_telegram_id}"
    (the exact string server/api-admin-user-balance.php verifies).
    The amount is part of the token, so a token minted for +500 ETB
    cannot adjust by any other amount. Minted ONLY after William
    taps Confirm. Returns 64 hex chars. The secret comes from the
    Render env, never hardcoded, never logged. The delta is
    formatted with exactly two decimals on both sides — Python
    f"{delta:.2f}" here, PHP number_format(..., 2) there — so the
    two HMACs agree."""
    key = secret if secret is not None else BOT_API_SECRET
    msg = (
        f"admin-user-balance:{int(telegram_id)}:{float(delta_etb):.2f}"
        f":{int(admin_telegram_id)}"
    )
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def mint_admin_ban_token(telegram_id, action, admin_telegram_id,
                         secret=None):
    """HMAC-SHA256 confirm token for POST
    /admin/users/{id}/ban, keyed by BOT_API_SECRET over
    "admin-user-ban:{telegram_id}:{action}:{admin_telegram_id}"
    (the exact string server/api-admin-user-ban.php verifies).
    The action ("ban" / "unban") is part of the token, so a token
    minted for a ban cannot unban. Minted ONLY after William taps
    Confirm. Returns 64 hex chars. The secret comes from the
    Render env, never hardcoded, never logged."""
    key = secret if secret is not None else BOT_API_SECRET
    msg = (
        f"admin-user-ban:{int(telegram_id)}:{action}"
        f":{int(admin_telegram_id)}"
    )
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def mint_admin_price_token(provider, service_id, admin_telegram_id,
                           price_etb=None, secret=None):
    """HMAC-SHA256 confirm token for POST /admin/service-price/set
    (price given) or /admin/service-price/clear (price None),
    keyed by BOT_API_SECRET over
    "admin-service-price:set:{provider}:{service_id}:{price:.2f}:{admin_telegram_id}"
    or
    "admin-service-price:clear:{provider}:{service_id}:{admin_telegram_id}"
    (the exact strings server/api-admin-service-price.php
    verifies). The provider, id and price are part of the token,
    so a token minted for one service or price cannot change
    another. Minted ONLY after William taps Confirm. Returns 64
    hex chars. The secret comes from the Render env, never
    hardcoded, never logged. The price is formatted with exactly
    two decimals on both sides — Python f"{price:.2f}" here, PHP
    number_format(..., 2) there — so the two HMACs agree."""
    key = secret if secret is not None else BOT_API_SECRET
    if price_etb is None:
        msg = (
            f"admin-service-price:clear:{provider}:{int(service_id)}"
            f":{int(admin_telegram_id)}"
        )
    else:
        msg = (
            f"admin-service-price:set:{provider}:{int(service_id)}"
            f":{float(price_etb):.2f}:{int(admin_telegram_id)}"
        )
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
    "creating only happen after the owner taps Confirm. "
    "Examples of what you can do in chat: \"How much did we make "
    "today?\" (live stats), \"Show me the most profitable services\", "
    "\"Who went quiet?\", \"Morning report\", \"Refund order #1841\" "
    "(preview, then Confirm), \"What is the balance of 779060335?\" "
    "(one user's balance), \"Add 500 ETB to 779060335\" (preview, "
    "then Confirm), \"Deposit history of 779060335\" (the last 3 "
    "deposits), \"Ban @william\" (preview, then Confirm), \"Set "
    "price of service 6139 to 50 ETB\" (preview, then Confirm). "
    "You can also create promo codes in chat: 'Create promo code "
    "PAXYO20 20% expires 2026-12-31' (preview, then Confirm), "
    "'list promo codes', 'turn off promo code PAXYO20', 'What is "
    "the balance of @username?' (a username is looked up first), "
    "'Unban 779060335', 'Show price of service 6139', 'Clear "
    "price of service 6139'. "
    "Things you cannot do in chat: list orders or users, list "
    "resellers, list loyalty bonuses, list fraud flags, or list "
    "confused chats — those live in the admin panel; say so honestly "
    "and never invent a figure. You can look up ONE order by its "
    "number. You cannot cancel an order from chat — offer the refund "
    "flow instead. The ticker and service prices can be changed in "
    "chat (service prices are overrides, preview then Confirm); the "
    "price multiplier is changed in Settings on the admin panel. You "
    "can quote a service's current price when asked (\"Show price "
    "of service 6139\"). "
    "To count users who never deposited, offer a broadcast — the "
    "broadcast preview shows the count. If William asks whether "
    "something can be done in chat, answer only from this list, "
    "never invent an admin-panel section or a feature that is not "
    "listed here. Promo codes are created in chat, never in the "
    "admin panel, there is no Promotions section."
)


async def _deepseek_post(payload: dict) -> dict:
    """One POST to the DeepSeek API, with fast failover (18 Nov 2026,
    same shape as the order bot's _deepseek_post): an HTTP error
    raises at once, never retried; only a transport failure gets
    one quick retry after 0.5s. 5s per attempt, never 30s."""
    url = DEEPSEEK_URL + "/chat/completions"
    for attempt in (0, 1):
        try:
            async with httpx.AsyncClient(timeout=AI_POST_TIMEOUT_SECONDS, trust_env=False) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError:
            raise
        except httpx.TransportError as exc:
            if attempt == 0:
                log.warning(
                    "Admin AI DeepSeek transport error (%s), retrying once",
                    type(exc).__name__,
                )
                await asyncio.sleep(AI_TRANSIENT_RETRY_DELAY_SECONDS)
                continue
            raise


async def _gemini_post(payload: dict) -> dict:
    """One POST to the Gemini API, with fast failover (18 Nov 2026,
    same shape as the order bot's _gemini_post): an HTTP error
    raises at once, never retried; only a transport failure gets
    one quick retry after 0.5s. 5s per attempt, never 30s. Only the
    exception TYPE is ever logged, never its text — httpx error
    text carries the request URL, and the Gemini URL carries the
    API key."""
    url = GEMINI_URL.format(model=GEMINI_MODEL)
    for attempt in (0, 1):
        try:
            async with httpx.AsyncClient(timeout=AI_POST_TIMEOUT_SECONDS, trust_env=False) as client:
                resp = await client.post(
                    url, params={"key": GEMINI_API_KEY}, json=payload
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError:
            raise
        except httpx.TransportError as exc:
            if attempt == 0:
                log.warning(
                    "Admin AI Gemini transport error (%s), retrying once",
                    type(exc).__name__,
                )
                await asyncio.sleep(AI_TRANSIENT_RETRY_DELAY_SECONDS)
                continue
            raise


def _chat_reply_text(data: dict) -> str:
    """Reply text from an OpenAI-compatible chat-completions body
    (DeepSeek), or "" when the shape is wrong."""
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _gemini_reply_text(data: dict) -> str:
    """Reply text from a Gemini generateContent body, or "" when
    the shape is wrong."""
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


async def ai_reply(text: str):
    """One minimal AI reply for a free-form question. DeepSeek first
    (DEEPSEEK_API_KEY), then Gemini (GEMINI_API_KEY) — the same keys
    the order bot already uses, but NOT Groq (18 Nov 2026: the user
    bot already uses Groq, and the admin bot must not share its
    free-tier quota). Fast failover (18 Nov 2026): 5s per attempt,
    HTTP errors never retried, one quick retry only on a transport
    failure — so a question can no longer hang for up to 60s.
    Returns the reply text, or None when no key is configured or
    every provider failed. The AI is NEVER called for broadcasts
    or setting changes, and its output never triggers an action."""
    if DEEPSEEK_API_KEY:
        try:
            data = await _deepseek_post(
                {
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": ADMIN_AI_SYSTEM},
                        {"role": "user", "content": text},
                    ],
                }
            )
            out = _chat_reply_text(data)
            if out.strip():
                return out.strip()
        except Exception as exc:  # fall through to Gemini
            log.warning(
                "Admin AI DeepSeek failed (%s)", type(exc).__name__
            )
    if GEMINI_API_KEY:
        try:
            data = await _gemini_post(
                {"contents": [{"parts": [{"text": ADMIN_AI_SYSTEM + "\n\n" + text}]}]}
            )
            out = _gemini_reply_text(data)
            if out.strip():
                return out.strip()
        except Exception as exc:
            log.warning(
                "Admin AI Gemini failed (%s)", type(exc).__name__
            )
    return None


FALLBACK_REPLY = (
    "I didn't understand — try one of these:\n"
    "• \"How much did we make today?\"\n"
    "• \"How many users in the last 7 days?\"\n"
    "• \"Send this to users who never deposited: <message>\"\n"
    "• \"Change ticker to <new text>\"\n"
    "• \"Refund order #1841\"\n"
    "• \"What is the balance of 779060335?\"\n"
    "• \"Add 500 ETB to 779060335\"\n"
    "• \"Deposit history of 779060335\"\n"
    "• \"Ban @william\" / \"Unban 779060335\"\n"
    "• \"Set price of service 6139 to 50 ETB\"\n"
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
    if kind == "profit":
        if "net_profit_etb" not in stats:
            return (
                "The net profit figure is not available yet — the "
                "stats endpoint does not report it."
            )
        return (
            f"{label}: net profit "
            f"{format_money(stats.get('net_profit_etb') or 0)} ETB."
        )
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
    ]
    if "net_profit_etb" in stats:
        lines.append(
            f"Net profit: {format_money(stats.get('net_profit_etb') or 0)} ETB"
        )
    lines += [
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


def format_morning_report(stats, satisfaction=None) -> str:
    """Yesterday's money report from a /admin/stats record fetched
    with day="yesterday". All five figures come from the record;
    a missing figure says so, never invented. The window is
    labelled from the response's own `from`/`date` fields, so the
    label is honest whatever window the server actually returned:
    "Yesterday (2026-11-14)" when the server sent day=yesterday,
    otherwise the same Today / Last N days label as answer_stats.
    A satisfaction record (20, 15 Nov 2026), when given, adds the
    👍/👎 score line; when it is None the line is left out (the
    morning send fetches it separately and only adds it when the
    endpoint answers)."""
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
    if satisfaction is not None:
        lines.append(format_satisfaction_line(satisfaction))
    return "\n".join(lines)


def format_satisfaction_line(data) -> str:
    """One satisfaction line from a /satisfaction record (20):
    "Satisfaction: 85% positive (17 of 20)". A record with no
    ratings yet says so, never a 0% that would read as all-bad."""
    data = data or {}
    total = int(data.get("total") or 0)
    if total <= 0:
        return "Satisfaction: no feedback yet."
    positive = int(data.get("positive") or 0)
    percent = data.get("percent_positive")
    if percent is None:
        percent = round(100 * positive / total)
    return (
        f"Satisfaction: {int(percent)}% positive "
        f"({positive} of {total})"
    )


def format_disputes(data) -> str:
    """The open disputes (15, 15 Nov 2026): one line each — id,
    order, user, their words (truncated). No open disputes says
    so; a missing endpoint says so."""
    if data is None:
        return (
            "The disputes list is not connected yet — the endpoint "
            "is not live on the server."
        )
    disputes = data.get("disputes") or []
    if not disputes:
        return "No open disputes."
    lines = [f"Open disputes ({len(disputes)}):"]
    for d in disputes:
        who = d.get("username") or d.get("telegram_id") or "?"
        order = d.get("order_id")
        order_part = f"order #{order}" if order is not None else "no order"
        message = str(d.get("message") or "")[:120]
        lines.append(
            f"#{d.get('id')} — {order_part} — {who}: {message}"
        )
    lines.append("Close one with: close dispute #<id>")
    return "\n".join(lines)


def format_profitable(data) -> str:
    """The most profitable services (16, 15 Nov 2026): top 10 by
    profit (revenue minus provider cost at the 200 ETB per USD
    buy rate). Profit and revenue come from the server, never
    computed here."""
    if data is None:
        return (
            "The profitable list is not connected yet — the "
            "endpoint is not live on the server."
        )
    services = data.get("services") or []
    if not services:
        return "No orders yet, so there is nothing profitable to rank."
    lines = ["Most profitable services:"]
    for i, s in enumerate(services[:10], 1):
        name = s.get("service_name") or f"service {s.get('service_id')}"
        lines.append(
            f"{i}. {name} — "
            f"{format_money(s.get('revenue_etb') or 0)} ETB revenue, "
            f"{format_money(s.get('profit_etb') or 0)} ETB profit "
            f"({int(s.get('orders') or 0)} orders)"
        )
    return "\n".join(lines)


def format_deposits_by_method(data) -> str:
    """Deposits broken down by method (18, 15 Nov 2026): last 7
    days + all time, one line per method. Only completed deposits
    count (the server counts those)."""
    if data is None:
        return (
            "The deposit-method report is not connected yet — the "
            "endpoint is not live on the server."
        )
    methods = data.get("methods") or []
    if not methods:
        return "No completed deposits yet."
    lines = ["Deposits by method (completed):"]
    for m in methods:
        lines.append(
            f"{m.get('method') or '?'} — last 7 days: "
            f"{int(m.get('count_7d') or 0)} "
            f"({format_money(m.get('amount_7d') or 0)} ETB); "
            f"all time: {int(m.get('count_all') or 0)} "
            f"({format_money(m.get('amount_all') or 0)} ETB)"
        )
    return "\n".join(lines)


def _pct_change(this_value, last_value):
    """Percent change from last week to this week, or None when
    there is no last-week figure to compare against."""
    try:
        this_value = float(this_value)
        last_value = float(last_value)
    except (TypeError, ValueError):
        return None
    if last_value == 0:
        return None
    return round(100 * (this_value - last_value) / last_value)


def format_weekly_report(data) -> str:
    """The weekly growth report (27, 15 Nov 2026): this week vs
    last week (EAT Monday–Sunday), with the % change where a
    last-week figure exists. All figures come from the server."""
    if data is None:
        return (
            "The weekly report is not connected yet — the endpoint "
            "is not live on the server."
        )
    this_week = data.get("this_week") or {}
    last_week = data.get("last_week") or {}
    changes = data.get("changes") or {}

    def change_line(label, key, money=False):
        this_value = this_week.get(key)
        last_value = last_week.get(key)
        pct = changes.get(key + "_pct")
        if pct is None:
            pct = _pct_change(this_value, last_value)
        if money:
            this_text = format_money(this_value or 0)
            last_text = format_money(last_value or 0)
        else:
            this_text = str(int(this_value or 0))
            last_text = str(int(last_value or 0))
        line = f"{label}: {this_text} (last week: {last_text}"
        if pct is None:
            line += ")"
        else:
            sign = "+" if pct >= 0 else ""
            line += f", {sign}{pct}%)"
        return line

    window = this_week.get("from") and this_week.get("to")
    lines = [
        (
            f"Weekly growth ({this_week.get('from')} to "
            f"{this_week.get('to')}):"
        )
        if window
        else "Weekly growth:",
        change_line("New users", "users"),
        change_line("Orders", "orders"),
        change_line("Revenue", "revenue_etb", money=True),
        change_line("Net profit", "net_profit_etb", money=True),
    ]
    if "deposits_count" in this_week:
        lines.append(
            change_line("Deposits", "deposits_count")
            + f" ({format_money(this_week.get('deposits_etb') or 0)} ETB)"
        )
    return "\n".join(lines)


def format_promo_codes(data) -> str:
    """Every promo code (25, 15 Nov 2026): code, bonus, active or
    off, expiry, uses. Inactive codes are shown too, marked off —
    William can see what he turned off."""
    if data is None:
        return (
            "The promo-code list is not connected yet — the "
            "endpoint is not live on the server."
        )
    codes = data.get("codes") or []
    if not codes:
        return "No promo codes yet."
    lines = [f"Promo codes ({len(codes)}):"]
    for c in codes:
        if c.get("percent") is not None:
            bonus = f"{c['percent']}%"
        elif c.get("fixed_etb") is not None:
            bonus = f"{format_money(c.get('fixed_etb'))} ETB"
        else:
            bonus = "?"
        state = "active" if c.get("active") else "off"
        parts = [f"{c.get('code')} — {bonus} — {state}"]
        if c.get("expires_at"):
            parts.append(f"expires {str(c['expires_at'])[:10]}")
        if c.get("max_uses") is not None:
            used = c.get("used") or 0
            parts.append(f"uses {used}/{c['max_uses']}")
        lines.append(" ".join(parts))
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


def _order_status_text(order: dict, order_id: int) -> str:
    """One order's status, read-only (07-admin-english, 15 Nov
    2026): id, service, quantity, total, status. No preview, no
    Confirm — nothing changes here."""
    total = _order_total(order)
    quantity = order.get("quantity")
    return "\n".join([
        f"Order #{order_id}:",
        f"Service: {_order_service_label(order)}"
        + (f" ×{quantity}" if quantity is not None else ""),
        f"Total: {format_money(total)} ETB"
        if total is not None
        else "Total: ?",
        f"Status: {order.get('status') or '?'}",
    ])


def _promo_preview(pending: dict) -> str:
    lines = [
        "Create this promo code?",
        f"Code: {pending['code']}",
    ]
    if pending.get("percent") is not None:
        lines.append(f"Bonus: {pending['percent']}% on a deposit")
    elif pending.get("fixed_etb") is not None:
        lines.append(
            f"Bonus: {format_money(pending['fixed_etb'])} ETB on a deposit"
        )
    if pending.get("expires_at"):
        lines.append(f"Expires: {str(pending['expires_at'])[:10]}")
    if pending.get("max_uses") is not None:
        lines.append(f"Max uses: {pending['max_uses']}")
    lines += ["", "Tap Confirm to create it, or Cancel."]
    return "\n".join(lines)


def _dispute_preview(pending: dict) -> str:
    """Close-dispute preview (15): the dispute id + order + the
    user's words, shown BEFORE anything closes."""
    lines = [
        "Close this dispute?",
        f"Dispute: #{pending['dispute_id']}",
    ]
    if pending.get("order_id") is not None:
        lines.append(f"Order: #{pending['order_id']}")
    if pending.get("message"):
        lines.append(f"Message: {str(pending['message'])[:120]}")
    lines += ["", "Tap Confirm to close it, or Cancel."]
    return "\n".join(lines)


async def _execute_pending(user_id: int, context) -> str:
    """Run a confirmed pending change (broadcast send, setting
    write, order refund, promo-code creation, or dispute close)
    and return the one-line outcome. Clears the pending entry
    first, so a double tap cannot run it twice."""
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
                percent=pending.get("percent"),
                expires_at=pending.get("expires_at"),
                max_uses=pending.get("max_uses"),
                fixed_etb=pending.get("fixed_etb"),
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
        if pending.get("percent") is not None:
            bonus = f"{pending['percent']}% bonus on a deposit"
        else:
            bonus = (
                f"{format_money(pending.get('fixed_etb'))} ETB bonus "
                "on a deposit"
            )
        lines = [
            f"✅ Promo code {pending['code']} created — {bonus}."
        ]
        if result.get("expires_at"):
            lines.append(f"Expires: {str(result['expires_at'])[:10]}")
        if result.get("max_uses") is not None:
            lines.append(f"Max uses: {result['max_uses']}")
        return "\n".join(lines)
    if pending["kind"] == "dispute_close":
        # Close the dispute (15): the server marks it closed; an
        # already-closed dispute 404s and says so honestly.
        try:
            result = await admin_api.close_dispute(pending["dispute_id"])
        except httpx.HTTPStatusError as exc:
            log.warning("close_dispute failed: %s", exc)
            return "Could not close the dispute — please try again."
        except Exception as exc:
            log.warning("close_dispute failed: %s", exc)
            return "Could not close the dispute — please try again."
        if result is None:
            return (
                "The disputes endpoint is not connected yet — "
                "nothing was closed."
            )
        return f"✅ Dispute #{pending['dispute_id']} closed."
    if pending["kind"] == "promo_off":
        # Turn a promo code off (25): the server deactivates it;
        # an unknown code 404s and says so honestly.
        try:
            result = await admin_api.promo_off(pending["code"])
        except httpx.HTTPStatusError as exc:
            log.warning("promo_off failed: %s", exc)
            return "Could not turn off the promo code — please try again."
        except Exception as exc:
            log.warning("promo_off failed: %s", exc)
            return "Could not turn off the promo code — please try again."
        if result is None:
            return (
                "The promo-code endpoint is not connected yet — "
                "nothing was turned off."
            )
        return f"✅ Promo code {pending['code']} is now off."
    if pending["kind"] == "balance_adjust":
        # The token is minted HERE, only after Confirm — never on
        # the preview, never on a single message. The amount is
        # part of the token, so it cannot be swapped afterwards.
        token = mint_admin_balance_token(
            pending["telegram_id"], pending["delta_etb"], user_id
        )
        try:
            result = await admin_api.adjust_user_balance(
                pending["telegram_id"], pending["delta_etb"], user_id, token
            )
        except httpx.HTTPStatusError as exc:
            return _balance_error_text(pending, exc)
        except Exception as exc:
            log.warning("adjust_user_balance failed: %s", exc)
            return "Could not adjust the balance — please try again."
        if not isinstance(result, dict):
            return "Could not adjust the balance — please try again."
        new_balance = result.get("new_balance")
        new_text = (
            format_money(new_balance) if new_balance is not None else "?"
        )
        action = "Added" if pending["delta_etb"] > 0 else "Removed"
        direction = "to" if pending["delta_etb"] > 0 else "from"
        return (
            f"✅ {action} {format_money(abs(pending['delta_etb']))} ETB "
            f"{direction} {pending['user_label']}. "
            f"New balance: {new_text} ETB."
        )
    if pending["kind"] in ("ban", "unban"):
        # The token is minted HERE, only after Confirm — never on
        # the preview, never on a single message. The action is
        # part of the token, so it cannot be swapped afterwards.
        token = mint_admin_ban_token(
            pending["telegram_id"], pending["action"], user_id
        )
        try:
            result = await admin_api.set_user_ban(
                pending["telegram_id"], pending["action"], user_id, token
            )
        except httpx.HTTPStatusError as exc:
            return _ban_error_text(pending, exc)
        except Exception as exc:
            log.warning("set_user_ban failed: %s", exc)
            verb = "ban" if pending["action"] == "ban" else "unban"
            return f"Could not {verb} the user. Please try again."
        if not isinstance(result, dict):
            verb = "ban" if pending["action"] == "ban" else "unban"
            return f"Could not {verb} the user. Please try again."
        verb = "banned" if pending["action"] == "ban" else "unbanned"
        return f"✅ {pending['user_label']} is now {verb}."
    if pending["kind"] == "price_set":
        # The token is minted HERE, only after Confirm — never on
        # the preview, never on a single message. The provider, id
        # and price are part of the token, so none of them can be
        # swapped afterwards.
        token = mint_admin_price_token(
            pending["provider"], pending["service_id"], user_id,
            pending["price_etb"],
        )
        try:
            result = await admin_api.set_price_override(
                pending["provider"], pending["service_id"],
                pending["price_etb"], user_id, token,
            )
        except httpx.HTTPStatusError as exc:
            return _price_error_text(pending, exc)
        except Exception as exc:
            log.warning("set_price_override failed: %s", exc)
            return "Could not change the price. Please try again."
        if not isinstance(result, dict):
            return "Could not change the price. Please try again."
        return (
            f"✅ Price of service {pending['combined_id']} set to "
            f"{format_money(pending['price_etb'])} ETB per 1000. "
            "The customer bot picks it up within 10 minutes."
        )
    if pending["kind"] == "price_clear":
        # The token is minted HERE, only after Confirm — never on
        # the preview, never on a single message.
        token = mint_admin_price_token(
            pending["provider"], pending["service_id"], user_id,
        )
        try:
            result = await admin_api.clear_price_override(
                pending["provider"], pending["service_id"], user_id, token,
            )
        except httpx.HTTPStatusError as exc:
            return _price_error_text(pending, exc)
        except Exception as exc:
            log.warning("clear_price_override failed: %s", exc)
            return "Could not change the price. Please try again."
        if not isinstance(result, dict):
            return "Could not change the price. Please try again."
        return (
            f"✅ Price override cleared for service "
            f"{pending['combined_id']}. It now uses the normal price."
        )
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
    # Satisfaction (20, 15 Nov 2026): the morning report carries
    # the 👍/👎 score line when the endpoint answers; when it does
    # not (404, not live yet) the line is simply left out — the
    # money figures still go out.
    try:
        satisfaction = await admin_api.satisfaction()
    except Exception as exc:
        log.warning("morning satisfaction failed: %s", exc)
        satisfaction = None
    text = format_morning_report(stats, satisfaction)
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


# ------------------------------------------------------- weekly report (27) ---

# In-memory fallback for the weekly sent marker (the Monday's date),
# used only while the server endpoint 404s — same shape as
# MORNING_SENT_DATES.
WEEKLY_SENT_MONDAYS = set()


def _monday_of_week(now: datetime) -> date:
    """The Monday (EAT date) of the week `now` falls in."""
    return (now.date() - timedelta(days=now.weekday()))


def should_send_weekly(now: datetime, sent_this_week: bool) -> bool:
    """Pure once-a-week gate (27): send only on a Monday at/after
    08:00 EAT, and only when this week's Monday has not been sent
    yet. `now` is an EAT datetime."""
    if sent_this_week:
        return False
    return now.weekday() == 0 and now.hour >= 8


async def send_weekly_report_once(app, now=None) -> bool:
    """One weekly-report attempt: this week vs last week, to every
    ADMIN_TELEGRAM_IDS id, at most once per week (keyed on the
    Monday's date). Mirrors send_morning_report_once: the sent
    marker is checked AND written server-side (GET/POST
    /admin/weekly-sent) so a restart after 8am Monday cannot
    double-send; when that endpoint 404s (not live yet) the
    in-memory WEEKLY_SENT_MONDAYS set is the fallback. Nothing is
    sent before Monday 8am EAT, nothing is sent when the week is
    already marked, and nothing is marked when the weekly endpoint
    is not connected yet (so the next wake retries instead of
    losing the week). Returns True when the report was sent."""
    now = now or datetime.now(EAT_TZ)
    monday = _monday_of_week(now).isoformat()
    server_marker = None
    try:
        server_marker = await admin_api.weekly_sent(monday)
    except Exception as exc:
        log.warning("weekly_sent check failed: %s", exc)
    if server_marker is None:
        log.warning(
            "Weekly-sent endpoint not connected yet — using the "
            "in-memory marker only for %s.",
            monday,
        )
        sent_this_week = monday in WEEKLY_SENT_MONDAYS
    else:
        sent_this_week = bool(server_marker.get("sent"))
    if not should_send_weekly(now, sent_this_week):
        return False
    try:
        data = await admin_api.weekly_stats()
    except Exception as exc:
        log.warning("weekly_stats failed: %s", exc)
        return False
    if data is None:
        log.warning("Weekly report not connected yet — weekly endpoint 404.")
        return False
    text = format_weekly_report(data)
    for admin_id in sorted(ADMIN_TELEGRAM_IDS):
        try:
            await app.bot.send_message(chat_id=admin_id, text=text)
        except Exception as exc:
            log.warning("Weekly report send to %s failed: %s", admin_id, exc)
    WEEKLY_SENT_MONDAYS.add(monday)
    try:
        await admin_api.mark_weekly_sent(monday)
    except Exception as exc:
        log.warning("mark_weekly_sent failed: %s", exc)
    return True


def _seconds_until_next_monday_8am_eat(now=None) -> float:
    """Seconds from `now` (EAT) until the next Monday 08:00 EAT.
    Pure helper so the schedule is testable: on a Monday before
    8am it is today 08:00, otherwise the coming Monday 08:00."""
    now = now or datetime.now(EAT_TZ)
    days_ahead = (0 - now.weekday()) % 7
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    target += timedelta(days=days_ahead)
    if target <= now:
        target += timedelta(days=7)
    return (target - now).total_seconds()


async def weekly_report_loop(app):
    """Background loop: sleep until the next Monday 08:00 EAT,
    send the weekly report once, then sleep until the next
    Monday's 08:00. Same shape as the morning loop (a proper
    schedule, not a poll)."""
    while True:
        await asyncio.sleep(_seconds_until_next_monday_8am_eat())
        try:
            await send_weekly_report_once(app)
        except Exception as exc:
            log.warning("Weekly report loop failed: %s", exc)


async def _post_init(app):
    """Application post_init hook: start the morning-report loop.
    Polling has no job queue, so the loop is an asyncio task."""
    asyncio.create_task(morning_report_loop(app))
    asyncio.create_task(weekly_report_loop(app))


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
    "• User balance — \"What is the balance of 779060335?\" (I look "
    "it up by Telegram id or @username)\n"
    "• Adjust a balance — \"Add 500 ETB to 779060335\" or \"Remove "
    "200 ETB from 779060335\" (I show the current and new balance, "
    "you confirm first, never below zero)\n"
    "• Deposit history: \"Deposit history of 779060335\" (the last "
    "3 deposits: amount, method, date, status)\n"
    "• Ban a user: \"Ban @william\" or \"Unban 779060335\" (you "
    "confirm first; a banned user cannot order or deposit)\n"
    "• Service price: \"Set price of service 6139 to 50 ETB\" or "
    "\"Show price of service 6139\" (you confirm first for a set; "
    "\"Clear price of service 6139\" removes an override)\n"
    "• Create a promo code — \"Create promo code PAXYO20 20%\" "
    "(you confirm first; a fixed amount works too — "
    "\"Create promo code FLAT100 100 ETB\")\n"
    "• Win back quiet users — /winbacks (I show the count first, "
    "you confirm, then each gets one personal message)\n"
    "• Morning money report — /morning (yesterday's revenue, net "
    "profit, new users, top service, deposits; also sent "
    "automatically once a day at 8am)\n"
    "• Disputes — /disputes (open problems from users; close one "
    "with \"close dispute #<id>\", you confirm first)\n"
    "• Most profitable services — /profitable (top 10 by profit)\n"
    "• Deposits by method — /deposits_by_method (Telebirr, CBE, "
    "M-Pesa, CBE Birr; last 7 days + all time)\n"
    "• Satisfaction — /satisfaction (the 👍/👎 feedback score; "
    "also in the morning report)\n"
    "• Weekly growth — /weekly (this week vs last week; also sent "
    "automatically once a week, Monday 8am)\n"
    "• Promo codes — /promo list (every code) and /promo off CODE "
    "(turn a code off, you confirm first)\n\n"
    "Refunds go through the Confirm-gated admin-refund endpoint, "
    "once, never twice, never for completed orders."
)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
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
    if not await _check_password_gate(update, None, try_as_password=False):
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
    if not await _check_password_gate(update, None, try_as_password=False):
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
    try:
        satisfaction = await admin_api.satisfaction()
    except Exception as exc:
        log.warning("morning satisfaction failed: %s", exc)
        satisfaction = None
    await update.message.reply_text(
        format_morning_report(stats, satisfaction)
    )


async def disputes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /disputes — the open disputes (15, 15 Nov 2026), newest
    first. Close one with "close dispute #<id>" (Confirm first)."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
        return
    try:
        data = await admin_api.disputes()
    except Exception as exc:
        log.warning("disputes failed: %s", exc)
        await update.message.reply_text(
            "Could not load the disputes — please try again."
        )
        return
    await update.message.reply_text(format_disputes(data))


async def profitable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /profitable — the services earning the most (16, 15 Nov
    2026), top 10 by profit."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
        return
    try:
        data = await admin_api.profitable()
    except Exception as exc:
        log.warning("profitable failed: %s", exc)
        await update.message.reply_text(
            "Could not load the profitable services — please try again."
        )
        return
    await update.message.reply_text(format_profitable(data))


async def deposits_by_method_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /deposits_by_method — completed deposits broken down by
    method (18, 15 Nov 2026), last 7 days + all time."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
        return
    try:
        data = await admin_api.deposits_by_method()
    except Exception as exc:
        log.warning("deposits_by_method failed: %s", exc)
        await update.message.reply_text(
            "Could not load the deposit-method report — please try again."
        )
        return
    await update.message.reply_text(format_deposits_by_method(data))


async def satisfaction_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /satisfaction — the 👍/👎 feedback score (20, 15 Nov 2026):
    % positive out of all feedback so far."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
        return
    try:
        data = await admin_api.satisfaction()
    except Exception as exc:
        log.warning("satisfaction failed: %s", exc)
        await update.message.reply_text(
            "Could not load the satisfaction score — please try again."
        )
        return
    if data is None:
        await update.message.reply_text(
            "The satisfaction score is not connected yet — the "
            "endpoint is not live on the server."
        )
        return
    await update.message.reply_text(format_satisfaction_line(data))


async def weekly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /weekly — this week vs last week (27, 15 Nov 2026), on
    demand. Also sent automatically once a week, Monday 8am."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
        return
    try:
        data = await admin_api.weekly_stats()
    except Exception as exc:
        log.warning("weekly_stats failed: %s", exc)
        await update.message.reply_text(
            "Could not load the weekly report — please try again."
        )
        return
    await update.message.reply_text(format_weekly_report(data))


async def promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /promo list — every promo code (25, 15 Nov 2026).
    /promo off CODE — turn a code off (Confirm first).
    Bare /promo explains the two."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
        return
    args = (context.args or [])
    if not args:
        await update.message.reply_text(
            "Promo codes:\n"
            "• /promo list — every code, active and off\n"
            "• /promo off CODE — turn a code off (you confirm first)\n"
            "• Create one with: create promo code CODE 10% "
            "(or 100 ETB for a fixed amount)"
        )
        return
    sub = (args[0] or "").strip().lower()
    if sub == "list":
        try:
            data = await admin_api.promo_codes()
        except Exception as exc:
            log.warning("promo_codes failed: %s", exc)
            await update.message.reply_text(
                "Could not load the promo codes — please try again."
            )
            return
        await update.message.reply_text(format_promo_codes(data))
        return
    if sub == "off":
        if len(args) < 2:
            await update.message.reply_text(
                "Which code? For example: /promo off PAXYO20"
            )
            return
        code = args[1].strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
            await update.message.reply_text(
                "That code doesn't look right — use 4–20 letters "
                "and digits, for example PAXYO20."
            )
            return
        PENDING[user.id] = {"kind": "promo_off", "code": code}
        await update.message.reply_text(
            f"Turn off promo code {code}?\n\n"
            "Tap Confirm to turn it off, or Cancel.",
            reply_markup=CONFIRM_KEYBOARD,
        )
        return
    await update.message.reply_text(
        "Promo codes:\n"
        "• /promo list — every code, active and off\n"
        "• /promo off CODE — turn a code off (you confirm first)"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text(REFUSAL)
        return
    if not await _check_password_gate(update, None, try_as_password=False):
        return
    await update.message.reply_text(
        CAPABILITIES
        + "\n\nBroadcasts can go to: users who never deposited, "
        "users who deposited before, users who bought a service "
        "(\"users who bought service 6139\"), or all users.\n\n"
        "/winbacks messages users with no order in 14+ days "
        "(count first, you confirm). /morning shows yesterday's "
        "money report — it is also sent automatically once a day "
        "at 8am. /weekly shows this week vs last week — it is also "
        "sent automatically once a week, Monday 8am. /disputes "
        "lists open problems from users. /profitable, "
        "/deposits_by_method and /satisfaction show the most "
        "profitable services, deposits by payment method, and the "
        "feedback score."
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
    if not await _check_password_gate(update, text, try_as_password=True):
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

    # 1a. One user's last deposits in plain language (19 Nov 2026)
    # — "deposit history of 779060335", "last deposits @william".
    # Read-only lookup, last 3 only, no preview, no Confirm. The
    # AI is never called for this.
    deposit_history = parse_deposit_history_command(text)
    if deposit_history is not None:
        record, error_text = await _resolve_user_target(deposit_history)
        if record is None:
            await update.message.reply_text(error_text)
            return
        try:
            data = await admin_api.get_user_deposits(record["telegram_id"])
        except Exception as exc:
            log.warning("get_user_deposits failed: %s", exc)
            await update.message.reply_text(
                "Could not load the deposits. Please try again."
            )
            return
        if data is None:
            await update.message.reply_text(
                "The deposit history is not connected yet. "
                "I couldn't look up the deposits."
            )
            return
        if data.get("user_not_found"):
            await update.message.reply_text(
                f"There is no Paxyo user with Telegram id "
                f"{record['telegram_id']}."
            )
            return
        await update.message.reply_text(
            format_deposit_history(record, data.get("deposits") or [])
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
    #    Bad codes / bonuses are refused here, before any Confirm.
    promo = parse_promo_create_command(text)
    if promo is not None:
        problem = validate_promo_create(promo)
        if problem is not None:
            await update.message.reply_text(problem)
            return
        PENDING[user.id] = {
            "kind": "promo",
            "code": promo["code"],
            "percent": promo.get("percent"),
            "fixed_etb": promo.get("fixed_etb"),
            "expires_at": promo.get("expires_at"),
            "max_uses": promo.get("max_uses"),
        }
        await update.message.reply_text(
            _promo_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5a. Promo-code list / off in plain language (25) — "list
    # promo codes", "turn off promo code PAXYO20". The off path is
    # Confirm-gated like every other change; the list is a read.
    if parse_promo_list_command(text) is not None:
        try:
            data = await admin_api.promo_codes()
        except Exception as exc:
            log.warning("promo_codes failed: %s", exc)
            await update.message.reply_text(
                "Could not load the promo codes — please try again."
            )
            return
        await update.message.reply_text(format_promo_codes(data))
        return
    promo_off = parse_promo_off_command(text)
    if promo_off is not None:
        code = promo_off["code"]
        if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
            await update.message.reply_text(
                "That code doesn't look right — use 4–20 letters "
                "and digits, for example PAXYO20."
            )
            return
        PENDING[user.id] = {"kind": "promo_off", "code": code}
        await update.message.reply_text(
            f"Turn off promo code {code}?\n\n"
            "Tap Confirm to turn it off, or Cancel.",
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5b. Close a dispute in plain language (15) — "close dispute
    # #3". Confirm-gated like every other change; the preview
    # shows the dispute's own words (looked up first, so a wrong
    # id says so instead of confirming blind).
    dispute_close = parse_dispute_close_command(text)
    if dispute_close is not None:
        dispute_id = dispute_close["dispute_id"]
        try:
            data = await admin_api.disputes()
        except Exception as exc:
            log.warning("disputes failed: %s", exc)
            await update.message.reply_text(
                "Could not load the disputes — please try again."
            )
            return
        found = None
        if data is not None:
            for d in data.get("disputes") or []:
                try:
                    if int(d.get("id")) == dispute_id:
                        found = d
                        break
                except (TypeError, ValueError):
                    continue
        if found is None:
            await update.message.reply_text(
                f"There is no open dispute #{dispute_id}."
            )
            return
        PENDING[user.id] = {
            "kind": "dispute_close",
            "dispute_id": dispute_id,
            "order_id": found.get("order_id"),
            "message": found.get("message"),
        }
        await update.message.reply_text(
            _dispute_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5c. One order's status in plain language (07-admin-english,
    # 15 Nov 2026) — "what is the status of order #1841". Read-only
    # lookup, no preview, no Confirm. After the refund step on
    # purpose: "refund order #1841" must never be read as a status
    # check (the parser refuses refund/cancel wordings).
    order_status = parse_order_status_command(text)
    if order_status is not None:
        order_id = order_status["order_id"]
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
        await update.message.reply_text(
            _order_status_text(order, order_id)
        )
        return

    # 5d. Plain-language report commands (07-admin-english,
    # 15 Nov 2026) — "show me the most profitable services",
    # "who went quiet", "morning report". Each runs the matching
    # /command handler with the same update, so the behaviour is
    # exactly the command's behaviour (same fetch, same honest
    # "not connected yet" when the endpoint is not live).
    report = parse_admin_report_command(text)
    if report is not None:
        handler = {
            "profitable": profitable_cmd,
            "satisfaction": satisfaction_cmd,
            "weekly": weekly_cmd,
            "deposits_by_method": deposits_by_method_cmd,
            "disputes": disputes_cmd,
            "morning": morning_cmd,
            "winbacks": winbacks_cmd,
            "help": help_cmd,
        }[report]
        await handler(update, context)
        return

    # 5e. One user's balance in plain language (18 Nov 2026) —
    # "what is the balance of 779060335". Read-only lookup, no
    # preview, no Confirm. Users are named by Telegram id or
    # @username (19 Nov 2026): the name is resolved first, then
    # the lookup runs against the Telegram id.
    balance_check = parse_balance_check_command(text)
    if balance_check is not None:
        record, error_text = await _resolve_user_target(balance_check)
        if record is None:
            await update.message.reply_text(error_text)
            return
        balance = record.get("balance")
        balance_text = (
            format_money(balance) if balance is not None else "?"
        )
        await update.message.reply_text(
            f"{_balance_user_label(record)} — balance: "
            f"{balance_text} ETB."
        )
        return

    # 5f. Balance adjustment in plain language (18 Nov 2026) —
    # "add 500 ETB to 779060335", "remove 200 ETB from 779060335".
    # Confirm-gated like every other money move: the preview shows
    # the user, the amount, the current balance and the new balance;
    # the HMAC token is minted only when the Confirm runs. A change
    # that would leave the balance below zero is refused here,
    # before any Confirm. The AI is never called for this.
    balance_adjust = parse_balance_adjust_command(text)
    if balance_adjust is not None:
        delta = balance_adjust["delta_etb"]
        if delta == 0:
            await update.message.reply_text(
                "The amount has to be more than 0 ETB."
            )
            return
        record, error_text = await _resolve_user_target(balance_adjust)
        if record is None:
            await update.message.reply_text(error_text)
            return
        tg_id = record["telegram_id"]
        current = record.get("balance")
        if current is None:
            await update.message.reply_text(
                f"I couldn't read the balance for user {tg_id} — "
                "please try again."
            )
            return
        try:
            current = float(current)
        except (TypeError, ValueError):
            await update.message.reply_text(
                f"I couldn't read the balance for user {tg_id} — "
                "please try again."
            )
            return
        new_balance = current + float(delta)
        if new_balance < 0:
            await update.message.reply_text(
                "That would leave the balance below zero — "
                f"user {tg_id} has {format_money(current)} ETB. "
                "Nothing was changed."
            )
            return
        PENDING[user.id] = {
            "kind": "balance_adjust",
            "telegram_id": tg_id,
            "delta_etb": float(delta),
            "current_balance": current,
            "new_balance": new_balance,
            "user_label": _balance_user_label(record),
        }
        await update.message.reply_text(
            _balance_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5h. Ban / unban in plain language (19 Nov 2026) — "ban
    # 779060335", "ban @william", "unban 779060335". Confirm-gated
    # like every other change: the preview shows the user and the
    # current ban state; the HMAC token is minted only when the
    # Confirm runs. A user already in the wanted state is told so
    # plainly and nothing is previewed. The AI is never called.
    ban_cmd = parse_ban_command(text)
    unban_cmd = None
    if ban_cmd is None:
        unban_cmd = parse_unban_command(text)
    ban_target = ban_cmd if ban_cmd is not None else unban_cmd
    if ban_target is not None:
        action = ban_target["action"]
        record, error_text = await _resolve_user_target(ban_target)
        if record is None:
            await update.message.reply_text(error_text)
            return
        tg_id = record["telegram_id"]
        try:
            ban_data = await admin_api.get_user_ban(tg_id)
        except Exception as exc:
            log.warning("get_user_ban failed: %s", exc)
            await update.message.reply_text(
                "Could not check the ban state. Please try again."
            )
            return
        if ban_data is None:
            await update.message.reply_text(
                "The ban endpoint is not connected yet. "
                "Nothing was changed."
            )
            return
        if ban_data.get("user_not_found"):
            await update.message.reply_text(
                f"There is no Paxyo user with Telegram id {tg_id}."
            )
            return
        currently_banned = bool(ban_data.get("banned"))
        user_label = _balance_user_label(record)
        if action == "ban" and currently_banned:
            await update.message.reply_text(
                f"{user_label} is already banned."
            )
            return
        if action == "unban" and not currently_banned:
            await update.message.reply_text(
                f"{user_label} is not banned."
            )
            return
        PENDING[user.id] = {
            "kind": action,
            "action": action,
            "telegram_id": tg_id,
            "user_label": user_label,
            "currently_banned": currently_banned,
        }
        await update.message.reply_text(
            _ban_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5i. Set a service price in plain language (19 Nov 2026) —
    # "set price of service 6139 to 50 ETB". Confirm-gated: the
    # preview shows the service, the current price and the new
    # price; the HMAC token is minted only when the Confirm runs.
    # A zero or negative price is refused here, before any
    # Confirm. The AI is never called.
    price_set = parse_price_set_command(text)
    if price_set is not None:
        price = price_set["price_etb"]
        if price <= 0:
            await update.message.reply_text(
                "The price has to be more than 0 ETB."
            )
            return
        provider, catalogue_price, override_price, error_text = (
            await _resolve_price_provider(price_set)
        )
        if error_text is not None:
            await update.message.reply_text(error_text)
            return
        current_price = (
            override_price
            if override_price is not None
            else catalogue_price
        )
        PENDING[user.id] = {
            "kind": "price_set",
            "provider": provider,
            "service_id": price_set["service_id"],
            "combined_id": _price_label(provider, price_set["service_id"]),
            "price_etb": float(price),
            "current_price": current_price,
            "current_override": override_price,
        }
        await update.message.reply_text(
            _price_set_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5j. Clear a service price override in plain language
    # (19 Nov 2026) — "clear price of service 6139".
    # Confirm-gated like a set. Clearing a service that has no
    # override is refused plainly — it already uses the normal
    # price. The AI is never called.
    price_clear = parse_price_clear_command(text)
    if price_clear is not None:
        provider, catalogue_price, override_price, error_text = (
            await _resolve_price_provider(price_clear)
        )
        if error_text is not None:
            await update.message.reply_text(error_text)
            return
        if override_price is None:
            await update.message.reply_text(
                f"Service {_price_label(provider, price_clear['service_id'])} "
                "has no price override. It already uses the normal price."
            )
            return
        PENDING[user.id] = {
            "kind": "price_clear",
            "provider": provider,
            "service_id": price_clear["service_id"],
            "combined_id": _price_label(provider, price_clear["service_id"]),
            "current_price": catalogue_price,
            "current_override": override_price,
        }
        await update.message.reply_text(
            _price_clear_preview(PENDING[user.id]),
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    # 5k. Show a service price in plain language (19 Nov 2026) —
    # "show price of service 6139". Read-only, no preview, no
    # Confirm. The effective price is the override when one is
    # set, else the catalogue price when the admin bot can see it
    # (GOP only — the live list has no SMM prices, so an SMM
    # service with no override has no known price here). The AI
    # is never called.
    price_show = parse_price_show_command(text)
    if price_show is not None:
        provider, catalogue_price, override_price, error_text = (
            await _resolve_price_provider(price_show)
        )
        if error_text is not None:
            await update.message.reply_text(error_text)
            return
        combined = _price_label(provider, price_show["service_id"])
        if override_price is not None:
            await update.message.reply_text(
                f"Service {combined}: "
                f"{format_money(override_price)} ETB per 1000 (override)."
            )
            return
        if catalogue_price is not None:
            await update.message.reply_text(
                f"Service {combined}: "
                f"{format_money(catalogue_price)} ETB per 1000 (normal price)."
            )
            return
        await update.message.reply_text(
            f"Service {combined} has no price override, and I can't "
            "see its normal price from here (the live list is GOP "
            "only). Set a price to fix it."
        )
        return

    # 5l. Natural questions about what the bot can do (19 Nov 2026) —
    # "can we add a promo code", "how do I check a balance". The exact
    # commands already matched above; this only answers the bare
    # question with the exact wording to use, so a natural question
    # never reaches the AI, which once invented a "Promotions
    # section" in the admin panel. Guidance only — no preview, no
    # Confirm, no API call, no AI call.
    capability = parse_capability_question(text)
    if capability is not None:
        await update.message.reply_text(capability)
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
    if _password_gate_on() and not is_unlocked(user.id):
        # A locked user can never have created a pending preview
        # (every handler is gated), so a tap here is refused and
        # nothing executes.
        await query.edit_message_text(PASSWORD_PROMPT)
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
    app.add_handler(CommandHandler("disputes", disputes_cmd))
    app.add_handler(CommandHandler("profitable", profitable_cmd))
    app.add_handler(CommandHandler("deposits_by_method", deposits_by_method_cmd))
    app.add_handler(CommandHandler("satisfaction", satisfaction_cmd))
    app.add_handler(CommandHandler("weekly", weekly_cmd))
    app.add_handler(CommandHandler("promo", promo_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))
    return app


def _ensure_event_loop():
    """Python 3.14 removed the implicit event loop: run_polling() calls
    asyncio.get_event_loop() and crashes with RuntimeError when the main
    thread has none (atlas-desk-bot first deploy, Render, 15 Nov 2026).
    Create + set one if missing."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


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
    _ensure_event_loop()
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
