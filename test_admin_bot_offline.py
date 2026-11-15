#!/usr/bin/env python3
"""Offline self-test for the Paxyo admin chat bot (admin_bot.py).

Checks the allowlist (empty refuses everyone), the live-question
parsing and answers (numbers from a seeded stats record; 404 ->
"not connected yet", never an invented number), the targeted
broadcast flow (count shown, Confirm required, send only after
Confirm, duplicates collapsed, delivered/failed counts), the
ticker change (preview shown, no write before Confirm, write after
Confirm), service-name resolution, the refund flow (preview shows
the order, completed orders refused before Confirm, HMAC token
minted only on Confirm, exact server messages for success /
duplicate / 409 / 502 / 404 / 403, double-Confirm runs once), the
promo-code creation flow (preview, Confirm posts the right body,
bad codes / percents refused before Confirm, 409 duplicate shown
plainly), and the free-form AI fallback (no key -> short reply;
the AI is never called for a broadcast, a setting change, a refund
or a promo-code creation). No network calls, no Telegram
connection, no real messages sent.
"""

import asyncio
import hashlib
import hmac
import os
import sys
import unittest
from unittest import mock

import httpx

# The test imports admin_bot.py, which needs python-telegram-bot
# installed. Env vars are faked here so import-time config reads
# succeed; no secret is real and none is sent anywhere.
os.environ.setdefault("ADMIN_BOT_TOKEN", "test-admin-token")
os.environ.setdefault("BOT_API_SECRET", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import admin_bot  # noqa: E402


ADMIN_ID = 111
OTHER_ID = 222

STATS = {
    "date": "2026-11-15",
    "from": "2026-11-15",
    "days": 1,
    "orders": 12,
    "completed": 9,
    "revenue_etb": 486.20,
    "new_users": 3,
    "top_service": "TikTok Video Views",
    "top_quantity": 5400,
    "deposits_count": 4,
    "deposits_etb": 1250.00,
}

STATS_7D = {
    "date": "2026-11-15",
    "from": "2026-11-09",
    "days": 7,
    "orders": 80,
    "completed": 61,
    "revenue_etb": 3120.50,
    "new_users": 21,
    "top_service": "TikTok Video Views",
    "top_quantity": 31200,
    "deposits_count": 19,
    "deposits_etb": 9400.00,
}

SERVICES = [
    {"service": 6139, "name": "Telegram Post Views | Fast"},
    {"service": 1665, "name": "TikTok Video Views | Fast"},
    {"service": 1666, "name": "TikTok Video Views | Slow"},
    {"service": 1001, "name": "Instagram Followers | Fast"},
]

ORDER = {
    "id": 1841,
    "service_name": "TikTok Video Views",
    "service_id": 1665,
    "quantity": 1000,
    "total": 10.00,
    "status": "pending",
    "telegram_id": 779060335,
}

ORDER_COMPLETED = dict(ORDER, status="completed")


def _status_error(status, body=None):
    """An httpx.HTTPStatusError with a JSON error body, the way the
    real client raises it (mirrors test_bot_offline.py)."""
    req = httpx.Request(
        "POST", "https://paxyo.et/api/bot/admin/orders/1841/refund"
    )
    resp = httpx.Response(status, json=body or {}, request=req)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


def _expected_refund_token(order_id=1841, admin_id=ADMIN_ID):
    """The HMAC token the bot must mint, computed independently
    here from the test secret the module was imported with."""
    return hmac.new(
        admin_bot.BOT_API_SECRET.encode(),
        f"admin-refund:{order_id}:{admin_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


class FakeMessage:
    """Stand-in for a telegram.Message, recording what was sent."""

    def __init__(self, text=""):
        self.text = text
        self.text_sent = []
        self.markups = []
        self.chat_id = 1

    async def reply_text(self, text, reply_markup=None):
        self.text_sent.append(text)
        self.markups.append(reply_markup)
        return None


class FakeUser:
    def __init__(self, user_id=ADMIN_ID, language_code="en"):
        self.id = user_id
        self.language_code = language_code
        self.username = "william"
        self.first_name = "William"


class FakeUpdate:
    def __init__(self, message, user=None):
        self.message = message
        self.effective_user = user or FakeUser()
        self.callback_query = None


class FakeBot:
    """Stand-in for telegram.Bot as seen from a handler context:
    records broadcast sends, and fails for chosen ids."""

    def __init__(self, fail_ids=None):
        self.sent = []
        self._fail_ids = set(fail_ids or [])

    async def send_message(self, chat_id, text):
        if chat_id in self._fail_ids:
            raise RuntimeError("send failed (test)")
        self.sent.append((chat_id, text))


class FakeContext:
    def __init__(self, bot=None):
        self.bot = bot or FakeBot()


class FakeCallbackQuery:
    def __init__(self, data, message=None):
        self.data = data
        self.message = message or FakeMessage()
        self.answered = False
        self.edited = []

    async def answer(self):
        self.answered = True

    async def edit_message_text(self, text, reply_markup=None):
        self.edited.append(text)


class FakeCallbackUpdate:
    def __init__(self, query, user=None):
        self.callback_query = query
        self.effective_user = user or FakeUser()
        self.message = None


class FakeAdminPaxyo:
    """Stand-in for AdminPaxyoClient with a seeded stats record,
    seeded audiences, a record of every setting write, seeded
    orders for the refund preview, and a record of every refund
    and promo-code call. refund_error=<status> / promo_error=
    <status> raise the HTTP error the real client raises, with
    refund_error_body / promo_error_body as the JSON error body."""

    def __init__(self, stats=None, stats_none=False, stats_by_days=None,
                 audience=None, audience_none=False, services=None,
                 orders=None, order_none=False, order_error=False,
                 refund_result=None, refund_error=None,
                 refund_error_body=None,
                 promo_result=None, promo_error=None,
                 promo_error_body=None):
        self._stats = stats
        self._stats_none = stats_none
        self._stats_by_days = dict(stats_by_days or {})
        self.stats_days_seen = []
        self._audience = dict(audience or {})
        self._audience_none = audience_none
        self._services = list(services) if services is not None else SERVICES
        self.settings_written = []
        self._orders = {int(k): v for k, v in dict(orders or {}).items()}
        self._order_none = order_none
        self._order_error = order_error
        self.order_lookups = []
        self.refund_calls = []
        self._refund_result = refund_result
        self._refund_error = refund_error
        self._refund_error_body = refund_error_body
        self.promo_calls = []
        self._promo_result = promo_result
        self._promo_error = promo_error
        self._promo_error_body = promo_error_body

    async def admin_stats(self, days=1):
        self.stats_days_seen.append(days)
        if self._stats_none:
            return None
        if days in self._stats_by_days:
            return self._stats_by_days[days]
        return self._stats

    async def broadcast_audience(self, segment, service_id=None):
        if self._audience_none:
            return None
        record = self._audience.get((segment, service_id))
        if record is None:
            record = self._audience.get((segment, None))
        if record is None:
            return {"segment": segment, "service_id": service_id,
                    "count": 0, "telegram_ids": []}
        return record

    async def set_setting(self, key, value):
        self.settings_written.append((key, value))
        return {"ok": True, "key": key, "value": value}

    async def services(self):
        return self._services

    async def get_order(self, order_id):
        self.order_lookups.append(order_id)
        if self._order_error:
            raise RuntimeError("order lookup failed (test)")
        if self._order_none:
            return None
        return self._orders.get(int(order_id))

    async def admin_refund_order(self, order_id, telegram_id,
                                 admin_telegram_id, confirm_token):
        self.refund_calls.append({
            "order_id": order_id,
            "telegram_id": telegram_id,
            "admin_telegram_id": admin_telegram_id,
            "confirm_token": confirm_token,
        })
        if self._refund_error is not None:
            raise _status_error(self._refund_error, self._refund_error_body)
        if self._refund_result is not None:
            return self._refund_result
        return {
            "ok": True,
            "order_id": order_id,
            "refunded_etb": 10.00,
            "provider_status": "canceled",
            "duplicate": False,
        }

    async def create_promo_code(self, code, percent, expires_at=None,
                                max_uses=None):
        self.promo_calls.append({
            "code": code,
            "percent": percent,
            "expires_at": expires_at,
            "max_uses": max_uses,
        })
        if self._promo_error is not None:
            # Mirrors the real client: 404 -> None (endpoint not
            # live yet), any other error raises.
            if self._promo_error == 404:
                return None
            raise _status_error(self._promo_error, self._promo_error_body)
        if self._promo_result is not None:
            return self._promo_result
        return {
            "ok": True,
            "code": code,
            "percent": percent,
            "active": True,
            "expires_at": expires_at,
            "max_uses": max_uses,
        }


class AdminBotBase(unittest.IsolatedAsyncioTestCase):
    """Base: allowlist = {ADMIN_ID} only, pending state cleared."""

    def setUp(self):
        admin_bot.PENDING.clear()
        self._ids_patch = mock.patch.object(
            admin_bot, "ADMIN_TELEGRAM_IDS", {ADMIN_ID}
        )
        self._ids_patch.start()
        self.addCleanup(self._ids_patch.stop)

    def _patch_api(self, fake):
        patcher = mock.patch.object(admin_bot, "admin_api", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    async def _text(self, text, user_id=ADMIN_ID, fake=None, bot=None):
        if fake is not None:
            self._patch_api(fake)
        message = FakeMessage(text)
        update = FakeUpdate(message, FakeUser(user_id))
        await admin_bot.on_text(update, FakeContext(bot))
        return message

    async def _callback(self, data, user_id=ADMIN_ID, bot=None):
        query = FakeCallbackQuery(data)
        update = FakeCallbackUpdate(query, FakeUser(user_id))
        await admin_bot.on_callback(update, FakeContext(bot))
        return query


class TestAllowlist(AdminBotBase):
    def test_empty_allowlist_refuses_everyone(self):
        with mock.patch.object(admin_bot, "ADMIN_TELEGRAM_IDS", set()):
            self.assertFalse(admin_bot.is_admin_user(ADMIN_ID))
            self.assertFalse(admin_bot.is_admin_user(OTHER_ID))

    def test_admin_allowed_non_admin_refused(self):
        self.assertTrue(admin_bot.is_admin_user(ADMIN_ID))
        self.assertFalse(admin_bot.is_admin_user(OTHER_ID))

    async def test_non_admin_start_refused(self):
        message = FakeMessage("/start")
        update = FakeUpdate(message, FakeUser(OTHER_ID))
        await admin_bot.start_cmd(update, FakeContext())
        self.assertEqual(message.text_sent, [admin_bot.REFUSAL])

    async def test_admin_start_shows_capabilities(self):
        message = FakeMessage("/start")
        update = FakeUpdate(message, FakeUser(ADMIN_ID))
        await admin_bot.start_cmd(update, FakeContext())
        self.assertEqual(len(message.text_sent), 1)
        self.assertIn("How much did we make today", message.text_sent[0])

    async def test_non_admin_text_refused(self):
        message = await self._text(
            "How much did we make today?", user_id=OTHER_ID,
            fake=FakeAdminPaxyo(stats=STATS),
        )
        self.assertEqual(message.text_sent, [admin_bot.REFUSAL])

    async def test_non_admin_callback_refused(self):
        query = await self._callback("admin_confirm", user_id=OTHER_ID)
        self.assertEqual(query.edited, [admin_bot.REFUSAL])

    async def test_non_admin_cannot_change_anything(self):
        fake = FakeAdminPaxyo(stats=STATS)
        message = await self._text(
            "Change ticker to hello", user_id=OTHER_ID, fake=fake
        )
        self.assertEqual(message.text_sent, [admin_bot.REFUSAL])
        self.assertEqual(fake.settings_written, [])


class TestStatsParsing(unittest.TestCase):
    def test_revenue_today(self):
        self.assertEqual(
            admin_bot.parse_stats_question("How much did we make today?"),
            {"kind": "revenue", "days": 1, "yesterday": False},
        )

    def test_revenue_wording_variants(self):
        for text in ("What is our revenue today?", "How much money did we make?"):
            self.assertEqual(
                admin_bot.parse_stats_question(text)["kind"], "revenue"
            )

    def test_users_last_7_days(self):
        self.assertEqual(
            admin_bot.parse_stats_question("How many users in the last 7 days?"),
            {"kind": "users", "days": 7, "yesterday": False},
        )

    def test_users_last_30_days(self):
        self.assertEqual(
            admin_bot.parse_stats_question("How many new users in the last 30 days?")["days"],
            30,
        )

    def test_this_week_is_7_days(self):
        self.assertEqual(
            admin_bot.parse_stats_question("How many users this week?")["days"], 7
        )

    def test_this_month_is_30_days(self):
        self.assertEqual(
            admin_bot.parse_stats_question("How much did we make this month?")["days"],
            30,
        )

    def test_orders_today(self):
        self.assertEqual(
            admin_bot.parse_stats_question("How many orders did we get today?")["kind"],
            "orders",
        )

    def test_deposits(self):
        self.assertEqual(
            admin_bot.parse_stats_question("How many deposits did we get today?")["kind"],
            "deposits",
        )

    def test_top_service(self):
        self.assertEqual(
            admin_bot.parse_stats_question("What is our top service today?")["kind"],
            "top_service",
        )

    def test_summary(self):
        self.assertEqual(
            admin_bot.parse_stats_question("/digest")["kind"], "summary"
        )
        self.assertEqual(
            admin_bot.parse_stats_question("How are we doing?")["kind"], "summary"
        )

    def test_yesterday_flagged(self):
        parsed = admin_bot.parse_stats_question("How much did we make yesterday?")
        self.assertEqual(parsed["kind"], "revenue")
        self.assertTrue(parsed["yesterday"])

    def test_not_a_stats_question(self):
        for text in ("Hello", "Send this to all users: hi", "Change ticker to hi"):
            self.assertIsNone(admin_bot.parse_stats_question(text))


class TestStatsAnswers(AdminBotBase):
    async def test_revenue_today(self):
        fake = FakeAdminPaxyo(stats=STATS)
        message = await self._text("How much did we make today?", fake=fake)
        self.assertEqual(message.text_sent, ["Today (2026-11-15): revenue 486.20 ETB."])
        self.assertEqual(fake.stats_days_seen, [1])

    async def test_users_last_7_days_passes_days(self):
        fake = FakeAdminPaxyo(stats_by_days={7: STATS_7D})
        message = await self._text("How many users in the last 7 days?", fake=fake)
        self.assertEqual(
            message.text_sent,
            ["Last 7 days (2026-11-09 to 2026-11-15): 21 new users."],
        )
        self.assertEqual(fake.stats_days_seen, [7])

    async def test_orders_today(self):
        message = await self._text(
            "How many orders did we get today?",
            fake=FakeAdminPaxyo(stats=STATS),
        )
        self.assertEqual(
            message.text_sent, ["Today (2026-11-15): 12 orders (9 completed)."]
        )

    async def test_deposits_today(self):
        message = await self._text(
            "How many deposits did we get today?",
            fake=FakeAdminPaxyo(stats=STATS),
        )
        self.assertEqual(
            message.text_sent, ["Today (2026-11-15): 4 deposits, 1,250.00 ETB."]
        )

    async def test_deposits_missing_keys_is_honest(self):
        record = {k: v for k, v in STATS.items()
                  if k not in ("deposits_count", "deposits_etb")}
        message = await self._text(
            "How many deposits did we get today?",
            fake=FakeAdminPaxyo(stats=record),
        )
        self.assertIn("not available yet", message.text_sent[0])
        self.assertNotIn("1,250", message.text_sent[0])

    async def test_top_service(self):
        message = await self._text(
            "What is our top service today?",
            fake=FakeAdminPaxyo(stats=STATS),
        )
        self.assertEqual(
            message.text_sent,
            ["Today (2026-11-15): top service is TikTok Video Views ×5400."],
        )

    async def test_top_service_none_is_honest(self):
        record = dict(STATS, top_service=None, top_quantity=0)
        message = await self._text(
            "What is our top service today?",
            fake=FakeAdminPaxyo(stats=record),
        )
        self.assertIn("no orders yet", message.text_sent[0])

    async def test_summary_shows_every_figure(self):
        message = await self._text(
            "How are we doing?", fake=FakeAdminPaxyo(stats=STATS)
        )
        text = message.text_sent[0]
        self.assertIn("Revenue: 486.20 ETB", text)
        self.assertIn("Orders: 12 (9 completed)", text)
        self.assertIn("New users: 3", text)
        self.assertIn("Deposits: 4 (1,250.00 ETB)", text)
        self.assertIn("Top service: TikTok Video Views ×5400", text)

    async def test_stats_404_is_not_connected_yet(self):
        message = await self._text(
            "How much did we make today?",
            fake=FakeAdminPaxyo(stats_none=True),
        )
        self.assertIn("not connected yet", message.text_sent[0])
        self.assertNotIn("486", message.text_sent[0])

    async def test_yesterday_is_not_available(self):
        message = await self._text(
            "How much did we make yesterday?",
            fake=FakeAdminPaxyo(stats=STATS),
        )
        self.assertIn("yesterday on its own is not available yet", message.text_sent[0])


class TestBroadcastParsing(unittest.TestCase):
    def test_never_deposited_with_inline_message(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to users who never deposited: Hello from Paxyo!"
        )
        self.assertEqual(parsed["segment"], "never_deposited")
        self.assertEqual(parsed["message"], "Hello from Paxyo!")
        self.assertEqual(parsed["service_label"], "users who never deposited")

    def test_deposited_before(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to users who deposited before: Thank you!"
        )
        self.assertEqual(parsed["segment"], "deposited")
        self.assertEqual(parsed["message"], "Thank you!")

    def test_all_users(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to all users: Big news today"
        )
        self.assertEqual(parsed["segment"], "all")
        self.assertEqual(parsed["message"], "Big news today")

    def test_service_by_id(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to users who bought service 6139: New views deal"
        )
        self.assertEqual(parsed["segment"], "service")
        self.assertEqual(parsed["service_id"], 6139)
        self.assertEqual(parsed["message"], "New views deal")

    def test_service_by_hash_id(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to users who bought #6139: New views deal"
        )
        self.assertEqual(parsed["service_id"], 6139)

    def test_service_by_name(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to users who bought TikTok Video Views: New deal"
        )
        self.assertEqual(parsed["segment"], "service")
        self.assertIsNone(parsed["service_id"])
        self.assertEqual(parsed["service_name"], "tiktok video views")

    def test_no_inline_message(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to users who never deposited"
        )
        self.assertEqual(parsed["segment"], "never_deposited")
        self.assertIsNone(parsed["message"])

    def test_saying_message(self):
        parsed = admin_bot.parse_broadcast_command(
            "Send this to all users saying Hello everyone"
        )
        self.assertEqual(parsed["segment"], "all")
        self.assertEqual(parsed["message"], "Hello everyone")

    def test_not_a_broadcast(self):
        for text in (
            "How much did we make today?",
            "Hello",
            "Send me the link of my last order",
        ):
            self.assertIsNone(admin_bot.parse_broadcast_command(text))

    def test_send_with_no_segment(self):
        self.assertIsNone(
            admin_bot.parse_broadcast_command("Send this to someone: hi")
        )


class TestBroadcastFlow(AdminBotBase):
    def _audience_fake(self, ids):
        return FakeAdminPaxyo(
            stats=STATS,
            audience={
                ("never_deposited", None): {
                    "segment": "never_deposited", "service_id": None,
                    "count": len(ids), "telegram_ids": list(ids),
                },
                ("all", None): {
                    "segment": "all", "service_id": None,
                    "count": len(ids), "telegram_ids": list(ids),
                },
                ("service", 6139): {
                    "segment": "service", "service_id": 6139,
                    "count": len(ids), "telegram_ids": list(ids),
                },
            },
        )

    async def test_preview_shows_count_and_exact_message(self):
        fake = self._audience_fake([1, 2, 3])
        self._patch_api(fake)
        message = await self._text(
            "Send this to users who never deposited: Hello from Paxyo!"
        )
        self.assertEqual(len(message.text_sent), 1)
        preview = message.text_sent[0]
        self.assertIn("users who never deposited (3 users)", preview)
        self.assertIn("Hello from Paxyo!", preview)
        self.assertIn("Confirm", preview)
        self.assertIsNotNone(message.markups[0])

    async def test_nothing_sends_before_confirm(self):
        fake = self._audience_fake([1, 2, 3])
        bot = FakeBot()
        self._patch_api(fake)
        await self._text(
            "Send this to users who never deposited: Hello!",
            bot=bot,
        )
        self.assertEqual(bot.sent, [])

    async def test_confirm_tap_sends_to_each_id_once(self):
        fake = self._audience_fake([1, 2, 3])
        bot = FakeBot()
        self._patch_api(fake)
        await self._text(
            "Send this to users who never deposited: Hello!", bot=bot
        )
        query = await self._callback("admin_confirm", bot=bot)
        self.assertEqual(
            bot.sent, [(1, "Hello!"), (2, "Hello!"), (3, "Hello!")]
        )
        self.assertEqual(query.edited, ["Sent to 3 users."])

    async def test_duplicate_ids_collapsed(self):
        fake = self._audience_fake([1, 1, 2, 2, 3])
        bot = FakeBot()
        self._patch_api(fake)
        await self._text(
            "Send this to users who never deposited: Hello!", bot=bot
        )
        query = await self._callback("admin_confirm", bot=bot)
        self.assertEqual(
            bot.sent, [(1, "Hello!"), (2, "Hello!"), (3, "Hello!")]
        )
        self.assertEqual(query.edited, ["Sent to 3 users."])

    async def test_failed_send_counted_and_reported(self):
        fake = self._audience_fake([1, 2, 3])
        bot = FakeBot(fail_ids={2})
        self._patch_api(fake)
        await self._text(
            "Send this to users who never deposited: Hello!", bot=bot
        )
        query = await self._callback("admin_confirm", bot=bot)
        self.assertEqual(bot.sent, [(1, "Hello!"), (3, "Hello!")])
        self.assertEqual(query.edited, ["Sent to 2 users. 1 failed to deliver."])

    async def test_cancel_tap_sends_nothing(self):
        fake = self._audience_fake([1, 2, 3])
        bot = FakeBot()
        self._patch_api(fake)
        await self._text(
            "Send this to users who never deposited: Hello!", bot=bot
        )
        query = await self._callback("admin_cancel", bot=bot)
        self.assertEqual(bot.sent, [])
        self.assertEqual(query.edited, ["Cancelled."])

    async def test_typed_yes_confirms(self):
        fake = self._audience_fake([1, 2])
        bot = FakeBot()
        self._patch_api(fake)
        await self._text(
            "Send this to users who never deposited: Hello!", bot=bot
        )
        message = await self._text("yes", bot=bot)
        self.assertEqual(bot.sent, [(1, "Hello!"), (2, "Hello!")])
        self.assertEqual(message.text_sent, ["Sent to 2 users."])

    async def test_audience_404_sends_nothing(self):
        fake = FakeAdminPaxyo(stats=STATS, audience_none=True)
        bot = FakeBot()
        self._patch_api(fake)
        message = await self._text(
            "Send this to users who never deposited: Hello!", bot=bot
        )
        self.assertIn("not connected yet", message.text_sent[0])
        self.assertEqual(bot.sent, [])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)

    async def test_zero_audience_sends_nothing(self):
        fake = self._audience_fake([])
        bot = FakeBot()
        self._patch_api(fake)
        message = await self._text(
            "Send this to users who never deposited: Hello!", bot=bot
        )
        self.assertIn("Nobody matches", message.text_sent[0])
        self.assertEqual(bot.sent, [])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)

    async def test_message_asked_when_missing_then_preview(self):
        fake = self._audience_fake([1, 2])
        self._patch_api(fake)
        first = await self._text("Send this to users who never deposited")
        self.assertIn("What should the message say", first.text_sent[0])
        second = await self._text("Hello from Paxyo!")
        self.assertIn("users who never deposited (2 users)", second.text_sent[0])
        self.assertIn("Hello from Paxyo!", second.text_sent[0])

    async def test_service_segment_audience(self):
        fake = self._audience_fake([7, 8])
        bot = FakeBot()
        self._patch_api(fake)
        await self._text(
            "Send this to users who bought service 6139: Deal!", bot=bot
        )
        query = await self._callback("admin_confirm", bot=bot)
        self.assertEqual(bot.sent, [(7, "Deal!"), (8, "Deal!")])
        self.assertEqual(query.edited, ["Sent to 2 users."])


class TestTickerFlow(AdminBotBase):
    def test_parse_ticker_change(self):
        self.assertEqual(
            admin_bot.parse_ticker_change("Change ticker display to 20% off today"),
            "20% off today",
        )
        self.assertEqual(
            admin_bot.parse_ticker_change("set ticker to Hello"),
            "Hello",
        )
        self.assertEqual(
            admin_bot.parse_ticker_change("Update the ticker text to Sale!"),
            "Sale!",
        )
        self.assertIsNone(admin_bot.parse_ticker_change("Hello"))

    async def test_preview_shows_exact_change(self):
        message = await self._text(
            "Change ticker display to 20% off today",
            fake=FakeAdminPaxyo(stats=STATS),
        )
        self.assertEqual(len(message.text_sent), 1)
        self.assertIn("Ticker display: 20% off today", message.text_sent[0])
        self.assertIn("Confirm", message.text_sent[0])
        self.assertIsNotNone(message.markups[0])

    async def test_no_write_before_confirm(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._text("Change ticker to 20% off today", fake=fake)
        self.assertEqual(fake.settings_written, [])

    async def test_confirm_tap_writes(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        await self._text("Change ticker to 20% off today")
        query = await self._callback("admin_confirm")
        self.assertEqual(fake.settings_written, [("ticker_text", "20% off today")])
        self.assertEqual(
            query.edited, ["Saved. Ticker display is now: 20% off today"]
        )

    async def test_typed_yes_writes(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        await self._text("Change ticker to Sale!")
        message = await self._text("yes")
        self.assertEqual(fake.settings_written, [("ticker_text", "Sale!")])
        self.assertEqual(
            message.text_sent, ["Saved. Ticker display is now: Sale!"]
        )

    async def test_cancel_writes_nothing(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        await self._text("Change ticker to Sale!")
        query = await self._callback("admin_cancel")
        self.assertEqual(fake.settings_written, [])
        self.assertEqual(query.edited, ["Cancelled."])

    async def test_settings_404_writes_nothing_and_says_so(self):
        class FailingSettings(FakeAdminPaxyo):
            async def set_setting(self, key, value):
                return None

        fake = FailingSettings(stats=STATS)
        self._patch_api(fake)
        await self._text("Change ticker to Sale!")
        query = await self._callback("admin_confirm")
        self.assertEqual(fake.settings_written, [])
        self.assertIn("not connected yet", query.edited[0])
        self.assertIn("nothing was changed", query.edited[0])


class TestServiceNameResolution(AdminBotBase):
    def test_exact_name(self):
        self.assertEqual(
            admin_bot.resolve_service_id("TikTok Video Views | Fast", SERVICES),
            1665,
        )

    def test_unique_substring(self):
        self.assertEqual(
            admin_bot.resolve_service_id("Instagram Followers", SERVICES), 1001
        )

    def test_ambiguous_name_returns_none(self):
        self.assertIsNone(
            admin_bot.resolve_service_id("TikTok Video Views", SERVICES)
        )

    def test_unknown_name_returns_none(self):
        self.assertIsNone(
            admin_bot.resolve_service_id("No Such Service", SERVICES)
        )

    async def test_name_broadcast_resolves_then_sends(self):
        fake = FakeAdminPaxyo(
            stats=STATS,
            audience={
                ("service", 1001): {
                    "segment": "service", "service_id": 1001,
                    "count": 1, "telegram_ids": [9],
                },
            },
        )
        bot = FakeBot()
        self._patch_api(fake)
        message = await self._text(
            "Send this to users who bought Instagram Followers: Hi!",
            bot=bot,
        )
        self.assertIn("Broadcast preview", message.text_sent[0])
        self.assertIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(admin_bot.PENDING[ADMIN_ID]["service_id"], 1001)
        query = await self._callback("admin_confirm", bot=bot)
        self.assertEqual(bot.sent, [(9, "Hi!")])
        self.assertEqual(query.edited, ["Sent to 1 users."])

    async def test_ambiguous_name_asks_for_id(self):
        fake = FakeAdminPaxyo(stats=STATS)
        message = await self._text(
            "Send this to users who bought TikTok Video Views: Hi!",
            fake=fake,
        )
        self.assertIn("service ID", message.text_sent[0])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)


class TestFreeForm(AdminBotBase):
    async def test_no_ai_key_gets_short_fallback(self):
        with mock.patch.object(admin_bot, "DEEPSEEK_API_KEY", ""), \
             mock.patch.object(admin_bot, "GEMINI_API_KEY", ""):
            message = await self._text(
                "What is Paxyo?", fake=FakeAdminPaxyo(stats=STATS)
            )
        self.assertIn("I didn't understand", message.text_sent[0])
        self.assertIn("How much did we make today", message.text_sent[0])

    async def test_ai_answer_used_when_configured(self):
        with mock.patch.object(
            admin_bot, "ai_reply",
            mock.AsyncMock(return_value="Paxyo sells followers, likes and views."),
        ):
            message = await self._text(
                "What is Paxyo?", fake=FakeAdminPaxyo(stats=STATS)
            )
        self.assertEqual(
            message.text_sent, ["Paxyo sells followers, likes and views."]
        )

    async def test_ai_never_called_for_broadcast(self):
        fake = FakeAdminPaxyo(
            stats=STATS,
            audience={
                ("never_deposited", None): {
                    "segment": "never_deposited", "service_id": None,
                    "count": 1, "telegram_ids": [1],
                },
            },
        )
        self._patch_api(fake)
        with mock.patch.object(
            admin_bot, "ai_reply",
            mock.AsyncMock(side_effect=AssertionError("AI must not be called")),
        ):
            message = await self._text(
                "Send this to users who never deposited: Hello!"
            )
        self.assertIn("Broadcast preview", message.text_sent[0])

    async def test_ai_never_called_for_ticker_change(self):
        self._patch_api(FakeAdminPaxyo(stats=STATS))
        with mock.patch.object(
            admin_bot, "ai_reply",
            mock.AsyncMock(side_effect=AssertionError("AI must not be called")),
        ):
            message = await self._text("Change ticker to Sale!")
        self.assertIn("Ticker display: Sale!", message.text_sent[0])

    async def test_ai_reply_returns_none_without_keys(self):
        with mock.patch.object(admin_bot, "DEEPSEEK_API_KEY", ""), \
             mock.patch.object(admin_bot, "GEMINI_API_KEY", ""):
            self.assertIsNone(await admin_bot.ai_reply("Hello"))


class TestPendingState(AdminBotBase):
    async def test_other_text_while_pending_is_a_reminder(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        await self._text("Change ticker to Sale!")
        message = await self._text("How much did we make today?")
        self.assertIn("waiting", message.text_sent[0])
        self.assertEqual(fake.settings_written, [])
        self.assertIn(ADMIN_ID, admin_bot.PENDING)

    async def test_typed_cancel_clears_pending(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        await self._text("Change ticker to Sale!")
        message = await self._text("cancel")
        self.assertEqual(message.text_sent, ["Cancelled."])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(fake.settings_written, [])

    async def test_double_confirm_runs_once(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        await self._text("Change ticker to Sale!")
        first = await self._callback("admin_confirm")
        second = await self._callback("admin_confirm")
        self.assertEqual(first.edited, ["Saved. Ticker display is now: Sale!"])
        self.assertEqual(second.edited, ["Nothing to confirm."])
        self.assertEqual(fake.settings_written, [("ticker_text", "Sale!")])


class TestRefundParsing(unittest.TestCase):
    def test_variants(self):
        for text in (
            "refund order #1841",
            "refund 1841",
            "refund order 1841",
            "refund #1841",
        ):
            self.assertEqual(
                admin_bot.parse_refund_command(text), {"order_id": 1841}
            )

    def test_not_a_refund_command(self):
        for text in (
            "can I get a refund?",
            "refund",
            "how do refunds work",
            "Hello",
        ):
            self.assertIsNone(admin_bot.parse_refund_command(text))

    def test_token_shape_and_binding(self):
        token = admin_bot.mint_admin_refund_token(1841, ADMIN_ID)
        self.assertEqual(token, _expected_refund_token())
        self.assertEqual(len(token), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in token))
        # Bound to one order + one admin: a different order or a
        # different admin mints a different token.
        self.assertNotEqual(
            token, admin_bot.mint_admin_refund_token(1842, ADMIN_ID)
        )
        self.assertNotEqual(
            token, admin_bot.mint_admin_refund_token(1841, OTHER_ID)
        )

    def test_order_record_shapes(self):
        self.assertEqual(admin_bot._order_record({"order": ORDER}), ORDER)
        self.assertEqual(admin_bot._order_record(ORDER), ORDER)
        self.assertIsNone(admin_bot._order_record("nope"))
        self.assertIsNone(admin_bot._order_record(None))


class TestRefundFlow(AdminBotBase):
    def _fake(self, order=ORDER, **kwargs):
        return FakeAdminPaxyo(stats=STATS, orders={1841: order}, **kwargs)

    async def _preview(self, fake, text="refund order #1841"):
        self._patch_api(fake)
        return await self._text(text)

    async def test_preview_shows_order_details(self):
        fake = self._fake()
        message = await self._preview(fake)
        self.assertEqual(len(message.text_sent), 1)
        preview = message.text_sent[0]
        self.assertIn("Order: #1841", preview)
        self.assertIn("TikTok Video Views", preview)
        self.assertIn("×1000", preview)
        self.assertIn("10.00 ETB", preview)
        self.assertIn("pending", preview)
        self.assertIn("779060335", preview)
        self.assertIn("Confirm", preview)
        self.assertIsNotNone(message.markups[0])
        self.assertEqual(fake.order_lookups, [1841])
        self.assertEqual(
            admin_bot.PENDING[ADMIN_ID],
            {"kind": "refund", "order_id": 1841, "telegram_id": 779060335},
        )

    async def test_nothing_refunded_before_confirm(self):
        fake = self._fake()
        await self._preview(fake)
        self.assertEqual(fake.refund_calls, [])

    async def test_confirm_tap_refunds_with_right_token_and_body(self):
        fake = self._fake()
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertEqual(len(fake.refund_calls), 1)
        call = fake.refund_calls[0]
        self.assertEqual(call["order_id"], 1841)
        self.assertEqual(call["telegram_id"], 779060335)
        self.assertEqual(call["admin_telegram_id"], ADMIN_ID)
        self.assertEqual(call["confirm_token"], _expected_refund_token())
        self.assertEqual(
            query.edited,
            ["✅ Refunded 10.00 ETB to user 779060335 for order #1841 "
             "(Paxyo balance, not cash). Provider: canceled."],
        )

    async def test_typed_yes_refunds(self):
        fake = self._fake()
        await self._preview(fake)
        message = await self._text("yes")
        self.assertEqual(len(fake.refund_calls), 1)
        self.assertEqual(
            message.text_sent,
            ["✅ Refunded 10.00 ETB to user 779060335 for order #1841 "
             "(Paxyo balance, not cash). Provider: canceled."],
        )

    async def test_duplicate_reply_shown_plainly(self):
        fake = self._fake(refund_result={
            "ok": True, "order_id": 1841, "refunded_etb": 10.00,
            "provider_status": "canceled", "duplicate": True,
        })
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertEqual(len(fake.refund_calls), 1)
        self.assertEqual(
            query.edited,
            ["Already refunded — 10.00 ETB for order #1841. "
             "No second refund was made."],
        )

    async def test_completed_order_refused_before_confirm(self):
        fake = self._fake(order=ORDER_COMPLETED)
        message = await self._preview(fake)
        self.assertEqual(
            message.text_sent,
            ["Order #1841 is already completed and cannot be refunded."],
        )
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(fake.refund_calls, [])

    async def test_order_lookup_404_is_not_connected_yet(self):
        fake = self._fake(order_none=True)
        message = await self._preview(fake)
        self.assertIn("not connected yet", message.text_sent[0])
        self.assertIn("#1841", message.text_sent[0])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(fake.refund_calls, [])

    async def test_order_lookup_failure_is_honest(self):
        fake = self._fake(order_error=True)
        message = await self._preview(fake)
        self.assertIn("Could not look up order #1841", message.text_sent[0])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)

    async def test_order_without_owner_refused(self):
        order = {k: v for k, v in ORDER.items() if k != "telegram_id"}
        fake = self._fake(order=order)
        message = await self._preview(fake)
        self.assertIn("no owner on file", message.text_sent[0])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(fake.refund_calls, [])

    async def test_409_completed_message(self):
        fake = self._fake(
            refund_error=409,
            refund_error_body={
                "error": "Order is already completed and cannot be cancelled."
            },
        )
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertEqual(
            query.edited,
            ["Order #1841 is already completed and cannot be refunded."],
        )

    async def test_409_provider_message_verbatim(self):
        fake = self._fake(
            refund_error=409,
            refund_error_body={
                "error": "Provider refused the cancel. No refund was made."
            },
        )
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertEqual(
            query.edited,
            ["No refund was made — Provider refused the cancel. "
             "No refund was made."],
        )

    async def test_502_message(self):
        fake = self._fake(
            refund_error=502,
            refund_error_body={
                "error": "Provider did not confirm the cancel. No refund was made."
            },
        )
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertEqual(
            query.edited,
            ["No refund was made — Provider did not confirm the cancel. "
             "No refund was made."],
        )

    async def test_404_order_not_found(self):
        fake = self._fake(
            refund_error=404,
            refund_error_body={"error": "Order not found."},
        )
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertEqual(query.edited, ["Order not found."])

    async def test_404_endpoint_not_live(self):
        fake = self._fake(
            refund_error=404,
            refund_error_body={"error": "Not found"},
        )
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertIn("not connected yet", query.edited[0])
        self.assertIn("nothing was refunded", query.edited[0])

    async def test_403_bad_token(self):
        fake = self._fake(
            refund_error=403,
            refund_error_body={"error": "Confirm token is not valid."},
        )
        await self._preview(fake)
        query = await self._callback("admin_confirm")
        self.assertEqual(query.edited, ["Confirm token is not valid."])

    async def test_double_confirm_runs_once(self):
        fake = self._fake()
        await self._preview(fake)
        first = await self._callback("admin_confirm")
        second = await self._callback("admin_confirm")
        self.assertIn("Refunded 10.00 ETB", first.edited[0])
        self.assertEqual(second.edited, ["Nothing to confirm."])
        self.assertEqual(len(fake.refund_calls), 1)

    async def test_cancel_refunds_nothing(self):
        fake = self._fake()
        await self._preview(fake)
        query = await self._callback("admin_cancel")
        self.assertEqual(fake.refund_calls, [])
        self.assertEqual(query.edited, ["Cancelled."])

    async def test_non_admin_refused(self):
        fake = self._fake()
        message = await self._text(
            "refund order #1841", user_id=OTHER_ID, fake=fake
        )
        self.assertEqual(message.text_sent, [admin_bot.REFUSAL])
        self.assertEqual(fake.order_lookups, [])
        self.assertEqual(fake.refund_calls, [])

    async def test_ai_never_called_for_refund(self):
        fake = self._fake()
        self._patch_api(fake)
        with mock.patch.object(
            admin_bot, "ai_reply",
            mock.AsyncMock(side_effect=AssertionError("AI must not be called")),
        ):
            message = await self._text("refund order #1841")
        self.assertIn("Refund this order?", message.text_sent[0])


class TestPromoParsing(unittest.TestCase):
    def test_create_variants(self):
        self.assertEqual(
            admin_bot.parse_promo_create_command("create promo code PAXYO20 20%"),
            {"code": "PAXYO20", "percent": 20,
             "expires_at": None, "max_uses": None},
        )
        self.assertEqual(
            admin_bot.parse_promo_create_command(
                "new promo code WELCOME10 10 percent"
            ),
            {"code": "WELCOME10", "percent": 10,
             "expires_at": None, "max_uses": None},
        )

    def test_lowercase_code_uppercased(self):
        parsed = admin_bot.parse_promo_create_command(
            "create promo code paxyo20 20%"
        )
        self.assertEqual(parsed["code"], "PAXYO20")

    def test_expires_and_max_uses(self):
        parsed = admin_bot.parse_promo_create_command(
            "create promo code PAXYO20 20% expires 2026-12-31 max 100 uses"
        )
        self.assertEqual(parsed["code"], "PAXYO20")
        self.assertEqual(parsed["percent"], 20)
        self.assertEqual(parsed["expires_at"], "2026-12-31 23:59:59")
        self.assertEqual(parsed["max_uses"], 100)

    def test_max_uses_wording_variants(self):
        self.assertEqual(
            admin_bot.parse_promo_create_command(
                "create promo code PAXYO20 20% max uses 50"
            )["max_uses"],
            50,
        )
        self.assertEqual(
            admin_bot.parse_promo_create_command(
                "create promo code PAXYO20 20% expiry 2027-01-15"
            )["expires_at"],
            "2027-01-15 23:59:59",
        )

    def test_not_a_promo_command(self):
        for text in (
            "Hello",
            "what promo codes do we have",
            "create a discount",
            "promo code PAXYO20",
        ):
            self.assertIsNone(admin_bot.parse_promo_create_command(text))


class TestPromoValidation(unittest.TestCase):
    def _parsed(self, code="PAXYO20", percent=20, expires_at=None,
                max_uses=None):
        return {
            "code": code, "percent": percent,
            "expires_at": expires_at, "max_uses": max_uses,
        }

    def test_valid(self):
        self.assertIsNone(admin_bot.validate_promo_create(self._parsed()))
        self.assertIsNone(admin_bot.validate_promo_create(
            self._parsed(expires_at="2026-12-31 23:59:59", max_uses=100)))

    def test_code_too_short(self):
        self.assertIn(
            "4–20 letters and digits",
            admin_bot.validate_promo_create(self._parsed(code="AB1")),
        )

    def test_code_bad_chars(self):
        for code in ("PAX-YO", "PAX YO", "PAX_YO"):
            self.assertIn(
                "4–20 letters and digits",
                admin_bot.validate_promo_create(self._parsed(code=code)),
            )

    def test_code_too_long(self):
        self.assertIn(
            "4–20 letters and digits",
            admin_bot.validate_promo_create(
                self._parsed(code="PAXYO20PAXYO20PAXYO20X")),
        )

    def test_percent_zero_and_over_100(self):
        for percent in (0, 101, 200):
            self.assertEqual(
                admin_bot.validate_promo_create(self._parsed(percent=percent)),
                "The percent must be between 1 and 100.",
            )

    def test_percent_missing(self):
        self.assertIn(
            "Tell me the percent too",
            admin_bot.validate_promo_create(self._parsed(percent=None)),
        )

    def test_expiry_in_the_past(self):
        self.assertEqual(
            admin_bot.validate_promo_create(
                self._parsed(expires_at="2020-01-01 23:59:59")),
            "That expiry date is in the past.",
        )

    def test_max_uses_zero(self):
        self.assertEqual(
            admin_bot.validate_promo_create(self._parsed(max_uses=0)),
            "Max uses must be at least 1.",
        )


class TestPromoFlow(AdminBotBase):
    async def _create(self, fake, text):
        self._patch_api(fake)
        return await self._text(text)

    async def test_preview_shows_code_percent_expiry_max(self):
        fake = FakeAdminPaxyo(stats=STATS)
        message = await self._create(
            fake, "create promo code PAXYO20 20% expires 2026-12-31 max 100 uses"
        )
        self.assertEqual(len(message.text_sent), 1)
        preview = message.text_sent[0]
        self.assertIn("PAXYO20", preview)
        self.assertIn("20%", preview)
        self.assertIn("2026-12-31", preview)
        self.assertIn("100", preview)
        self.assertIn("Confirm", preview)
        self.assertIsNotNone(message.markups[0])
        self.assertEqual(
            admin_bot.PENDING[ADMIN_ID],
            {"kind": "promo", "code": "PAXYO20", "percent": 20,
             "expires_at": "2026-12-31 23:59:59", "max_uses": 100},
        )

    async def test_nothing_created_before_confirm(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._create(fake, "create promo code PAXYO20 20%")
        self.assertEqual(fake.promo_calls, [])

    async def test_confirm_tap_posts_right_body(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._create(
            fake, "create promo code PAXYO20 20% expires 2026-12-31 max 100 uses"
        )
        query = await self._callback("admin_confirm")
        self.assertEqual(
            fake.promo_calls,
            [{"code": "PAXYO20", "percent": 20,
              "expires_at": "2026-12-31 23:59:59", "max_uses": 100}],
        )
        self.assertEqual(
            query.edited,
            ["✅ Promo code PAXYO20 created — 20% bonus on a deposit.\n"
             "Expires: 2026-12-31\nMax uses: 100"],
        )

    async def test_success_without_optional_fields(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._create(fake, "create promo code PAXYO20 20%")
        query = await self._callback("admin_confirm")
        self.assertEqual(
            fake.promo_calls,
            [{"code": "PAXYO20", "percent": 20,
              "expires_at": None, "max_uses": None}],
        )
        self.assertEqual(
            query.edited,
            ["✅ Promo code PAXYO20 created — 20% bonus on a deposit."],
        )

    async def test_lowercase_code_uppercased_in_body(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._create(fake, "create promo code paxyo20 20%")
        await self._callback("admin_confirm")
        self.assertEqual(fake.promo_calls[0]["code"], "PAXYO20")

    async def test_typed_yes_creates(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._create(fake, "new promo code WELCOME10 10 percent")
        message = await self._text("yes")
        self.assertEqual(len(fake.promo_calls), 1)
        self.assertEqual(
            message.text_sent,
            ["✅ Promo code WELCOME10 created — 10% bonus on a deposit."],
        )

    async def test_invalid_code_refused_before_confirm(self):
        fake = FakeAdminPaxyo(stats=STATS)
        message = await self._create(fake, "create promo code AB 10%")
        self.assertIn("4–20 letters and digits", message.text_sent[0])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(fake.promo_calls, [])

    async def test_invalid_percent_refused_before_confirm(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        for text in (
            "create promo code PAXYO20 0%",
            "create promo code PAXYO20 150%",
        ):
            message = await self._text(text)
            self.assertEqual(
                message.text_sent,
                ["The percent must be between 1 and 100."],
            )
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(fake.promo_calls, [])

    async def test_missing_percent_asks_plainly(self):
        fake = FakeAdminPaxyo(stats=STATS)
        message = await self._create(fake, "create promo code PAXYO20")
        self.assertIn("Tell me the percent too", message.text_sent[0])
        self.assertNotIn(ADMIN_ID, admin_bot.PENDING)
        self.assertEqual(fake.promo_calls, [])

    async def test_duplicate_409_shown_plainly(self):
        fake = FakeAdminPaxyo(
            stats=STATS,
            promo_error=409,
            promo_error_body={
                "error": "A promo code with that code already exists."
            },
        )
        await self._create(fake, "create promo code PAXYO20 20%")
        query = await self._callback("admin_confirm")
        self.assertEqual(len(fake.promo_calls), 1)
        self.assertEqual(
            query.edited,
            ["A promo code with that code already exists."],
        )

    async def test_404_endpoint_not_connected_yet(self):
        fake = FakeAdminPaxyo(stats=STATS, promo_error=404)
        await self._create(fake, "create promo code PAXYO20 20%")
        query = await self._callback("admin_confirm")
        self.assertIn("not connected yet", query.edited[0])
        self.assertIn("nothing was created", query.edited[0])

    async def test_double_confirm_runs_once(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._create(fake, "create promo code PAXYO20 20%")
        first = await self._callback("admin_confirm")
        second = await self._callback("admin_confirm")
        self.assertIn("PAXYO20 created", first.edited[0])
        self.assertEqual(second.edited, ["Nothing to confirm."])
        self.assertEqual(len(fake.promo_calls), 1)

    async def test_cancel_creates_nothing(self):
        fake = FakeAdminPaxyo(stats=STATS)
        await self._create(fake, "create promo code PAXYO20 20%")
        query = await self._callback("admin_cancel")
        self.assertEqual(fake.promo_calls, [])
        self.assertEqual(query.edited, ["Cancelled."])

    async def test_non_admin_refused(self):
        fake = FakeAdminPaxyo(stats=STATS)
        message = await self._text(
            "create promo code PAXYO20 20%", user_id=OTHER_ID, fake=fake
        )
        self.assertEqual(message.text_sent, [admin_bot.REFUSAL])
        self.assertEqual(fake.promo_calls, [])

    async def test_ai_never_called_for_promo(self):
        fake = FakeAdminPaxyo(stats=STATS)
        self._patch_api(fake)
        with mock.patch.object(
            admin_bot, "ai_reply",
            mock.AsyncMock(side_effect=AssertionError("AI must not be called")),
        ):
            message = await self._text("create promo code PAXYO20 20%")
        self.assertIn("Create this promo code?", message.text_sent[0])


class TestSafetyLine(AdminBotBase):
    def test_capabilities_state_refund_rule(self):
        self.assertIn("Confirm-gated admin-refund", admin_bot.CAPABILITIES)
        self.assertIn("never twice", admin_bot.CAPABILITIES)
        self.assertIn("never for completed orders", admin_bot.CAPABILITIES)
        self.assertNotIn(
            "I never touch balances, orders, deposits or refunds.",
            admin_bot.CAPABILITIES,
        )
        self.assertNotIn("never touches refunds", admin_bot.__doc__)

    async def test_start_lists_refund_and_promo(self):
        message = FakeMessage("/start")
        update = FakeUpdate(message, FakeUser(ADMIN_ID))
        await admin_bot.start_cmd(update, FakeContext())
        self.assertIn("Refund order #1841", message.text_sent[0])
        self.assertIn("Create promo code PAXYO20 20%", message.text_sent[0])

    def test_fallback_lists_refund_and_promo(self):
        self.assertIn("Refund order #1841", admin_bot.FALLBACK_REPLY)
        self.assertIn("Create promo code PAXYO20 20%", admin_bot.FALLBACK_REPLY)


if __name__ == "__main__":
    unittest.main()
