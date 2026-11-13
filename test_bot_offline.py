#!/usr/bin/env python3
"""Offline self-test for the Paxyo Order bot.

Checks intent-prompt shape, API-client URL building, service ranking,
quantity rules, language detection and price maths, plus the voice-reply
path (Google Cloud TTS payload shape, voice selection by language,
voice/text fallback) and the reply rules (text in -> text only,
voice in -> voice except the Confirm card and the post-acceptance
summary, which are always text) with the network mocked. No network
calls, no Telegram connection, no real orders.
"""

import asyncio
import json
import os
import sys
import unittest
from unittest import mock

import tornado.testing

# The test imports bot.py, which needs python-telegram-bot installed.
# Env vars are faked here so import-time config reads succeed; no secret
# is real and none is sent anywhere.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("BOT_API_SECRET", "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bot  # noqa: E402


SAMPLE_SERVICES = [
    {
        "service": 1001, "name": "Instagram Followers | Fast",
        "category": "Instagram Followers", "type": "Default",
        "rate_etb_per_1000": 42.0, "min": 10, "max": 10000,
        "average_time": "12 minutes", "active": True, "provider_service_id": 1001,
    },
    {
        "service": 1002, "name": "Instagram Followers | Slow",
        "category": "Instagram Followers", "type": "Default",
        "rate_etb_per_1000": 21.0, "min": 10, "max": 5000,
        "average_time": "2 hours", "active": True, "provider_service_id": 1002,
    },
    {
        "service": 1003, "name": "Instagram Followers | No time yet",
        "category": "Instagram Followers", "type": "Default",
        "rate_etb_per_1000": 30.0, "min": 10, "max": 5000,
        "average_time": "New Service", "active": True, "provider_service_id": 1003,
    },
    {
        "service": 5379, "name": "TikTok Likes | Cheapest",
        "category": "TikTok Likes", "type": "Default",
        "rate_etb_per_1000": 5.88, "min": 10, "max": 1000,
        "average_time": "1 minute", "active": True, "provider_service_id": 5379,
    },
    {
        "service": 5834, "name": "TikTok Likes | Fast",
        "category": "TikTok Likes", "type": "Default",
        "rate_etb_per_1000": 8.0, "min": 10, "max": 1000,
        "average_time": "1 minute", "active": True, "provider_service_id": 5834,
    },
    {
        "service": 1004, "name": "Instagram Followers | Disabled",
        "category": "Instagram Followers", "type": "Default",
        "rate_etb_per_1000": 10.0, "min": 10, "max": 1000,
        "average_time": "1 minute", "active": False, "provider_service_id": 1004,
    },
]


class TestAverageTime(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(bot.parse_average_time("12 minutes"), 12)

    def test_hours_and_minutes(self):
        self.assertEqual(bot.parse_average_time("28 hours 1 minute"), 1681)

    def test_days(self):
        self.assertEqual(bot.parse_average_time("1 day"), 1440)

    def test_hours(self):
        self.assertEqual(bot.parse_average_time("2 hours 30 minutes"), 150)

    def test_new_service(self):
        self.assertIsNone(bot.parse_average_time("New Service"))
        self.assertIsNone(bot.parse_average_time(None))
        self.assertIsNone(bot.parse_average_time(""))


class TestPickServices(unittest.TestCase):
    def test_fastest_first_no_time_last(self):
        picks = bot.pick_services(SAMPLE_SERVICES, platform="instagram")
        ids = [s["service"] for s in picks]
        self.assertEqual(ids, [1001, 1002, 1003])

    def test_blacklisted_never_picked(self):
        picks = bot.pick_services(SAMPLE_SERVICES, platform="tiktok")
        self.assertEqual(picks, [])

    def test_disabled_never_picked(self):
        picks = bot.pick_services(SAMPLE_SERVICES, platform="instagram")
        self.assertNotIn(1004, [s["service"] for s in picks])

    def test_hint_filter(self):
        picks = bot.pick_services(
            SAMPLE_SERVICES, platform="instagram", service_hint="followers"
        )
        self.assertTrue(all("followers" in s["name"].lower() for s in picks))


class TestQuantity(unittest.TestCase):
    def test_ok(self):
        self.assertIsNone(bot.validate_quantity(1000, SAMPLE_SERVICES[0]))

    def test_not_multiple_of_10(self):
        self.assertEqual(
            bot.validate_quantity(1005, SAMPLE_SERVICES[0]), "not_multiple_of_10"
        )

    def test_below_min(self):
        self.assertEqual(bot.validate_quantity(0, SAMPLE_SERVICES[0]), "invalid")

    def test_above_max(self):
        self.assertEqual(
            bot.validate_quantity(20000, SAMPLE_SERVICES[0]), "above_max"
        )


class TestIntentJson(unittest.TestCase):
    def test_plain_json(self):
        out = bot.extract_json(
            '{"platform": "instagram", "service_hint": "followers", '
            '"link": "https://instagram.com/p/x", "quantity": 1000}'
        )
        self.assertEqual(out["platform"], "instagram")
        self.assertEqual(out["quantity"], 1000)

    def test_fenced_json(self):
        out = bot.extract_json(
            'Here it is:\n```json\n{"platform": "tiktok", "service_hint": '
            '"views", "link": "https://tiktok.com/@x/video/1", "quantity": 500}'
            '\n```'
        )
        self.assertEqual(out["platform"], "tiktok")
        self.assertEqual(out["quantity"], 500)

    def test_garbage(self):
        self.assertIsNone(bot.extract_json("no json here at all"))


class TestLanguage(unittest.TestCase):
    def test_amharic_detected(self):
        self.assertTrue(bot.is_amharic("1000 views እፈልጋለሁ"))
        self.assertEqual(bot.lang_of("1000 views እፈልጋለሁ"), "am")

    def test_english(self):
        self.assertFalse(bot.is_amharic("I want 1000 views"))
        self.assertEqual(bot.lang_of("I want 1000 views"), "en")


class TestApiClient(unittest.TestCase):
    def test_services_url_and_secret_header(self):
        req = bot.build_api_request("GET", "/services")
        self.assertEqual(str(req.url), "https://paxyo.et/api/bot/services")
        self.assertEqual(req.headers["X-Bot-Secret"], "test-secret")

    def test_balance_url(self):
        req = bot.build_api_request("GET", "/balance?telegram_id=779060335")
        self.assertIn("telegram_id=779060335", str(req.url))

    def test_order_body_has_idempotency_key(self):
        req = bot.build_api_request(
            "POST",
            "/orders",
            {
                "telegram_id": 1,
                "service_id": 1001,
                "link": "https://x",
                "quantity": 1000,
                "idempotency_key": "abc123",
            },
        )
        import json as _json

        body = _json.loads(req.content)
        self.assertEqual(body["idempotency_key"], "abc123")
        self.assertEqual(body["quantity"], 1000)


class TestPricing(unittest.TestCase):
    def test_total_maths(self):
        # rate 42 ETB / 1000, qty 1000 -> 42.00; qty 500 -> 21.00
        self.assertEqual(bot.estimated_total_etb(42.0, 1000), 42.0)
        self.assertEqual(bot.estimated_total_etb(42.0, 500), 21.0)
        self.assertEqual(bot.estimated_total_etb(1.26, 10), 0.01)


class TestPrompt(unittest.TestCase):
    def test_system_prompt_shape(self):
        prompt = bot.SYSTEM_PROMPT
        self.assertIn("JSON only", prompt)
        self.assertIn("never place an order", prompt.lower())
        self.assertIn("GodOfPanel", prompt)
        self.assertIn("platform", prompt)


class FakeMessage:
    """Stand-in for a telegram.Message, recording what was sent."""

    def __init__(self, text=""):
        self.text = text
        self.text_sent = []
        self.voice_sent = []
        self.markups = []

    async def reply_text(self, text, reply_markup=None):
        self.text_sent.append(text)
        self.markups.append(reply_markup)

    async def reply_voice(self, voice):
        self.voice_sent.append(voice)


class TestVoiceStyle(unittest.TestCase):
    def test_voice_prompt_is_williams_complete_prompt(self):
        # The owner's voice prompt, pasted verbatim. If any of these
        # phrases is missing, the prompt was edited down by mistake.
        # (Whitespace is normalised first: the prompt is wrapped across
        # lines in the source, but the words are exactly as pasted.)
        p = " ".join(bot.VOICE_STYLE_PROMPT.split())
        self.assertIn("expert Amharic voice actor", p)
        self.assertIn("short-form sponsor segment", p)
        self.assertIn("calm, confident podcast host", p)
        self.assertIn("not a TV commercial", p)
        self.assertIn("never a direct translation feel from English", p)
        self.assertIn("matured native speaker", p)
        self.assertIn("The voice and the language together", p)

    def test_tts_payload_shape_amharic(self):
        payload = bot.build_tts_payload("ሰላም!", "am")
        self.assertEqual(payload["input"], {"text": "ሰላም!"})
        self.assertEqual(payload["voice"]["languageCode"], "am-ET")
        self.assertEqual(payload["voice"]["name"], "am-ET-Wavenet-A")
        audio = payload["audioConfig"]
        self.assertEqual(audio["audioEncoding"], "OGG_OPUS")
        self.assertEqual(audio["speakingRate"], 1.0)
        self.assertEqual(audio["pitch"], 0)

    def test_tts_payload_shape_english(self):
        payload = bot.build_tts_payload("Hello!", "en")
        self.assertEqual(payload["input"], {"text": "Hello!"})
        self.assertEqual(payload["voice"]["languageCode"], "en-US")
        self.assertEqual(payload["voice"]["name"], "en-US-Wavenet-D")
        self.assertEqual(payload["audioConfig"]["audioEncoding"], "OGG_OPUS")

    def test_tts_payload_unsupported_language_returns_none(self):
        # The bot never guesses a voice for a language it has none for.
        self.assertIsNone(bot.build_tts_payload("Bonjour!", "fr"))
        self.assertIsNone(bot.build_tts_payload("Bonjour!", "xx"))

    def test_tts_voice_env_overrides(self):
        with mock.patch.object(bot, "GOOGLE_CLOUD_TTS_VOICE", "am-ET-Standard-B"), \
             mock.patch.object(bot, "GOOGLE_CLOUD_TTS_VOICE_EN", "en-US-Wavenet-C"):
            self.assertEqual(
                bot.build_tts_payload("ሰላም!", "am")["voice"]["name"],
                "am-ET-Standard-B",
            )
            self.assertEqual(
                bot.build_tts_payload("Hello!", "en")["voice"]["name"],
                "en-US-Wavenet-C",
            )


class TestVoiceReply(unittest.IsolatedAsyncioTestCase):
    async def test_speak_reply_none_when_tts_returns_no_audio(self):
        # This is the no-key / API-failure case: the pipeline returns
        # None and the caller falls back to text.
        with mock.patch("bot.cloud_tts_speak", return_value=None):
            self.assertIsNone(await bot.speak_reply("ሰላም!", "am"))

    async def test_speak_reply_returns_ogg(self):
        # Cloud TTS returns OGG Opus directly — no conversion step.
        with mock.patch("bot.cloud_tts_speak", return_value=b"OggS-fake"):
            self.assertEqual(await bot.speak_reply("Hello!", "en"), b"OggS-fake")

    async def test_speak_reply_skips_long_text(self):
        with mock.patch("bot.cloud_tts_speak") as speak:
            self.assertIsNone(await bot.speak_reply("x" * 5000, "en"))
            speak.assert_not_called()

    async def test_reply_message_voice_success(self):
        msg = FakeMessage()
        with mock.patch("bot.speak_reply", return_value=b"OggS-fake"):
            await bot.reply_message(msg, "Hello!", "en", voice=True)
        self.assertEqual(len(msg.voice_sent), 1)
        self.assertEqual(msg.text_sent, [])

    async def test_reply_message_falls_back_to_text(self):
        msg = FakeMessage()
        with mock.patch("bot.speak_reply", return_value=None):
            await bot.reply_message(msg, "Hello!", "en", voice=True)
        self.assertEqual(msg.text_sent, ["Hello!"])
        self.assertEqual(msg.voice_sent, [])

    async def test_reply_message_markup_forces_text(self):
        # The Confirm card carries buttons, so it is always text even
        # when the user spoke — a voice message cannot carry buttons.
        msg = FakeMessage()
        with mock.patch("bot.speak_reply") as speak:
            await bot.reply_message(
                msg, "Confirm?", "en", voice=True, reply_markup="KB"
            )
        speak.assert_not_called()
        self.assertEqual(msg.text_sent, ["Confirm?"])
        self.assertEqual(msg.voice_sent, [])


class FakeUser:
    def __init__(self, user_id=1, language_code="en"):
        self.id = user_id
        self.language_code = language_code
        self.username = "testuser"
        self.first_name = "Test"


class FakeUpdate:
    def __init__(self, message, user=None):
        self.message = message
        self.effective_user = user or FakeUser()


class FakePaxyo:
    """Stand-in for PaxyoClient with a fat balance."""

    def __init__(self, balance=1000.0):
        self._balance = balance
        self.orders_created = []

    async def services(self):
        return SAMPLE_SERVICES

    async def balance(self, telegram_id):
        return {"found": True, "balance": self._balance}

    async def create_order(self, telegram_id, service_id, link, quantity, idempotency_key):
        self.orders_created.append((service_id, link, quantity))
        return {"order": {"id": 1827, "status": "pending"}}

    async def order_status(self, order_id, telegram_id):
        return {"status": "pending"}

    async def create_user(self, telegram_id, username=None, first_name=None):
        return {"created": True}


class FakeQuery:
    def __init__(self, data, message_text=""):
        self.data = data
        self.message = FakeMessage(message_text)
        self.edited = []
        self.answered = False

    async def answer(self):
        self.answered = True

    async def edit_message_text(self, text):
        self.edited.append(text)


class FakeCallbackUpdate:
    def __init__(self, query, user=None):
        self.callback_query = query
        self.effective_user = user or FakeUser()
        self.message = query.message


def make_pending(user_id=1):
    return {
        "user_id": user_id,
        "service": SAMPLE_SERVICES[0],
        "link": "https://instagram.com/p/x",
        "quantity": 1000,
        "total": 42.0,
    }


FULL_INTENT = {
    "platform": "instagram",
    "service_hint": "followers",
    "link": "https://instagram.com/p/x",
    "quantity": 1000,
}


class TestReplyRules(unittest.IsolatedAsyncioTestCase):
    """The owner's reply rules: text in -> text only; voice in -> voice
    except the Confirm card and the post-acceptance summary, which are
    always text; orders in Amharic and English, by text and by voice."""

    def setUp(self):
        bot.PENDING.clear()
        bot.LAST_ORDER.clear()
        bot.PARTIAL.clear()

    def tearDown(self):
        bot.PENDING.clear()
        bot.LAST_ORDER.clear()
        bot.PARTIAL.clear()

    async def test_text_in_never_produces_voice(self):
        msg = FakeMessage()
        update = FakeUpdate(msg)
        intent = {**FULL_INTENT, "link": None}
        with mock.patch("bot.extract_intent", new=mock.AsyncMock(return_value=intent)), \
             mock.patch("bot.speak_reply") as speak:
            await bot.handle_order_text(update, None, "I want 1000 Instagram followers")
        speak.assert_not_called()
        self.assertEqual(msg.text_sent, ["Please send the link the order is for."])
        self.assertEqual(msg.voice_sent, [])

    async def test_voice_in_produces_voice_for_plain_reply(self):
        msg = FakeMessage()
        update = FakeUpdate(msg)
        intent = {**FULL_INTENT, "link": None}
        with mock.patch("bot.extract_intent", new=mock.AsyncMock(return_value=intent)), \
             mock.patch("bot.speak_reply", new=mock.AsyncMock(return_value=b"OggS-fake")):
            await bot.handle_order_text(update, None, "transcribed voice", voice=True)
        self.assertEqual(len(msg.voice_sent), 1)
        self.assertEqual(msg.text_sent, [])

    async def test_confirm_card_is_text_even_for_voice(self):
        msg = FakeMessage()
        update = FakeUpdate(msg)
        with mock.patch("bot.extract_intent", new=mock.AsyncMock(return_value=dict(FULL_INTENT))), \
             mock.patch("bot.paxyo", FakePaxyo()), \
             mock.patch("bot.speak_reply") as speak:
            await bot.handle_order_text(update, None, "transcribed voice order", voice=True)
        speak.assert_not_called()
        self.assertEqual(len(msg.text_sent), 1)
        self.assertIn("Instagram Followers | Fast", msg.text_sent[0])
        self.assertIsNotNone(msg.markups[0])  # the Confirm/Cancel buttons
        self.assertEqual(msg.voice_sent, [])

    async def test_amharic_text_order_gets_amharic_confirm_card(self):
        msg = FakeMessage()
        user = FakeUser(language_code="am")
        update = FakeUpdate(msg, user=user)
        with mock.patch("bot.extract_intent", new=mock.AsyncMock(return_value=dict(FULL_INTENT))), \
             mock.patch("bot.paxyo", FakePaxyo()):
            await bot.handle_order_text(update, None, "1000 Instagram followers እፈልጋለሁ")
        self.assertEqual(len(msg.text_sent), 1)
        self.assertIn("እባክዎ ያረጋግጡ", msg.text_sent[0])
        self.assertEqual(msg.voice_sent, [])

    async def test_voice_acceptance_places_order_and_sends_text_summary(self):
        bot.PENDING["abc123"] = make_pending()
        msg = FakeMessage()
        user = FakeUser(language_code="am")
        update = FakeUpdate(msg, user=user)
        fake_paxyo = FakePaxyo()
        with mock.patch("bot.extract_intent") as intent, \
             mock.patch("bot.paxyo", fake_paxyo), \
             mock.patch("bot.speak_reply") as speak:
            await bot.handle_order_text(update, None, "አዎ", voice=True)
        intent.assert_not_called()  # acceptance is checked before intent
        speak.assert_not_called()  # the summary is always text
        self.assertEqual(msg.voice_sent, [])
        self.assertEqual(len(msg.text_sent), 1)
        summary = msg.text_sent[0]
        for fragment in (
            "Order ተፈጽሟል", "Instagram Followers | Fast", "1000",
            "https://instagram.com/p/x", "42.00", "1827", "pending",
        ):
            self.assertIn(fragment, summary)
        self.assertEqual(bot.PENDING, {})
        self.assertEqual(bot.LAST_ORDER[1], 1827)
        self.assertEqual(len(fake_paxyo.orders_created), 1)

    async def test_text_acceptance_also_places_order(self):
        bot.PENDING["abc123"] = make_pending()
        msg = FakeMessage()
        update = FakeUpdate(msg)
        with mock.patch("bot.extract_intent") as intent, \
             mock.patch("bot.paxyo", FakePaxyo()), \
             mock.patch("bot.speak_reply") as speak:
            await bot.handle_order_text(update, None, "yes")
        intent.assert_not_called()
        speak.assert_not_called()
        self.assertEqual(len(msg.text_sent), 1)
        self.assertIn("Order placed!", msg.text_sent[0])
        self.assertIn("1827", msg.text_sent[0])

    async def test_acceptance_without_pending_is_not_an_order(self):
        msg = FakeMessage()
        update = FakeUpdate(msg)
        intent = {"platform": None, "service_hint": None, "link": None, "quantity": None}
        with mock.patch("bot.extract_intent", new=mock.AsyncMock(return_value=intent)), \
             mock.patch("bot.speak_reply") as speak:
            await bot.handle_order_text(update, None, "yes")
        speak.assert_not_called()
        self.assertEqual(len(msg.text_sent), 1)
        self.assertIn("did not understand", msg.text_sent[0])

    async def test_button_confirm_sends_same_text_summary(self):
        bot.PENDING["abc123"] = make_pending()
        query = FakeQuery("confirm:abc123", message_text="Please confirm:")
        update = FakeCallbackUpdate(query)
        with mock.patch("bot.paxyo", FakePaxyo()):
            await bot.on_callback(update, None)
        self.assertTrue(query.answered)
        self.assertEqual(len(query.edited), 1)
        summary = query.edited[0]
        for fragment in (
            "Order placed!", "Instagram Followers | Fast", "1000",
            "https://instagram.com/p/x", "42.00", "1827", "pending",
        ):
            self.assertIn(fragment, summary)
        self.assertEqual(bot.PENDING, {})
        self.assertEqual(bot.LAST_ORDER[1], 1827)

    def test_is_acceptance_words(self):
        for word in ("yes", "Yes!", "OK", "confirm", "place it", "አዎ", "እሺ", "ይሁን"):
            self.assertTrue(bot.is_acceptance(word), word)
        for word in (
            "I want 1000 followers",
            "yes, I want 1000 followers",
            "confirm the order for 500 views",
            "",
            "maybe",
        ):
            self.assertFalse(bot.is_acceptance(word), word)


def intent_of(intent_type, **fields):
    """An extract_intent result of one type, with order fields None
    unless given."""
    out = {
        "intent": intent_type,
        "platform": None,
        "service_hint": None,
        "link": None,
        "quantity": None,
    }
    out.update(fields)
    return out


class TestConversationalIntents(unittest.IsolatedAsyncioTestCase):
    """The owner's 13 Nov 2026 live test: balance, order history, a
    greeting and 'I don't want to' must be understood, not answered
    with 'I did not understand'."""

    def setUp(self):
        bot.PENDING.clear()
        bot.LAST_ORDER.clear()
        bot.PARTIAL.clear()

    def tearDown(self):
        bot.PENDING.clear()
        bot.LAST_ORDER.clear()
        bot.PARTIAL.clear()

    async def _send(self, text, intent, paxyo=None, user=None):
        msg = FakeMessage()
        update = FakeUpdate(msg, user=user or FakeUser())
        with mock.patch("bot.extract_intent", new=mock.AsyncMock(return_value=intent)), \
             mock.patch("bot.paxyo", paxyo or FakePaxyo()), \
             mock.patch("bot.speak_reply") as speak:
            await bot.handle_order_text(update, None, text)
        self.assertEqual(msg.voice_sent, [])  # text in -> text only
        return msg

    async def test_balance_question_answers_with_balance(self):
        msg = await self._send(
            "How much is my balance", intent_of("balance")
        )
        self.assertEqual(msg.text_sent, ["Balance: 1,000.00 ETB"])

    async def test_balance_question_variant(self):
        # The owner's exact words: "How to check order balance".
        msg = await self._send(
            "How to check order balance", intent_of("balance")
        )
        self.assertEqual(msg.text_sent, ["Balance: 1,000.00 ETB"])

    async def test_order_history_question_answers_with_last_order(self):
        bot.LAST_ORDER[1] = 1827
        msg = await self._send(
            "I meant how to check my order history", intent_of("orders")
        )
        self.assertEqual(
            msg.text_sent, ["Order placed!\nOrder ID: 1827\nStatus: pending"]
        )

    async def test_order_history_with_no_orders(self):
        msg = await self._send(
            "Where is my order?", intent_of("orders")
        )
        self.assertEqual(msg.text_sent, ["You have no orders yet."])

    async def test_amharic_greeting_gets_amharic_greeting(self):
        # The owner's exact message: "ሰላም አማርኛ ትችላለህ".
        msg = await self._send(
            "ሰላም አማርኛ ትችላለህ",
            intent_of("greeting"),
            user=FakeUser(language_code="am"),
        )
        self.assertEqual(len(msg.text_sent), 1)
        self.assertIn("ሰላም", msg.text_sent[0])
        self.assertIn("Paxyo Order bot", msg.text_sent[0])
        self.assertNotIn("አልገባኝም", msg.text_sent[0])

    async def test_greeting_steers_to_ordering(self):
        msg = await self._send("Hello", intent_of("greeting"))
        self.assertIn("Tell me the service you want", msg.text_sent[0])

    async def test_off_topic_steers_back_in_one_line(self):
        msg = await self._send(
            "Who will win the football tonight?", intent_of("off_topic")
        )
        self.assertEqual(
            msg.text_sent,
            ["I'm the Paxyo order bot — I can only help with Paxyo orders. "
             "What would you like to order?"],
        )

    async def test_cancel_without_pending_says_cancelled(self):
        # The owner's exact words: "What if I don't want to".
        msg = await self._send(
            "What if I don't want to", intent_of("cancel")
        )
        self.assertEqual(msg.text_sent, ["Order cancelled."])

    async def test_cancel_with_pending_clears_it(self):
        bot.PENDING["abc123"] = make_pending()
        msg = await self._send("I don't want to", intent_of("cancel"))
        self.assertEqual(msg.text_sent, ["Order cancelled."])
        self.assertEqual(bot.PENDING, {})

    async def test_deposit_question_explains_deposit(self):
        msg = await self._send(
            "How do I add money?", intent_of("deposit")
        )
        self.assertIn("paxyo.et", msg.text_sent[0])
        self.assertIn("Telebirr", msg.text_sent[0])

    async def test_help_intent_gives_help(self):
        msg = await self._send(
            "How does this work?", intent_of("help")
        )
        self.assertIn("How it works", msg.text_sent[0])

    async def test_paxyo_info_answers_from_knowledge(self):
        msg = FakeMessage()
        update = FakeUpdate(msg)
        answer = "Paxyo is a social media services panel at paxyo.et."
        with mock.patch(
            "bot.extract_intent",
            new=mock.AsyncMock(return_value=intent_of("paxyo_info")),
        ), mock.patch("bot.paxyo", FakePaxyo()), mock.patch(
            "bot.gemini_generate", new=mock.AsyncMock(return_value=answer)
        ) as gen, mock.patch("bot.speak_reply") as speak:
            await bot.handle_order_text(update, None, "What is Paxyo?")
        speak.assert_not_called()
        self.assertEqual(msg.text_sent, [answer])
        system = gen.call_args.kwargs["system"]
        self.assertIn("paxyo.et", system)
        self.assertIn("GodOfPanel", system)  # the never-mention rule

    async def test_paxyo_info_falls_back_when_model_empty(self):
        msg = FakeMessage()
        update = FakeUpdate(msg)
        with mock.patch(
            "bot.extract_intent",
            new=mock.AsyncMock(return_value=intent_of("paxyo_info")),
        ), mock.patch("bot.paxyo", FakePaxyo()), mock.patch(
            "bot.gemini_generate", new=mock.AsyncMock(return_value="")
        ), mock.patch("bot.speak_reply"):
            await bot.handle_order_text(update, None, "What is Paxyo?")
        self.assertEqual(
            msg.text_sent,
            ["Paxyo is a social media services panel — followers, likes "
             "and views at paxyo.et. What would you like to order?"],
        )

    async def test_order_intent_still_flows_end_to_end(self):
        msg = await self._send(
            "I want 1000 Instagram followers https://instagram.com/p/x",
            intent_of("order", **FULL_INTENT),
        )
        self.assertEqual(len(msg.text_sent), 1)
        self.assertIn("Instagram Followers | Fast", msg.text_sent[0])
        self.assertIsNotNone(msg.markups[0])  # the Confirm card
        self.assertEqual(bot.PARTIAL, {})  # moved to PENDING

    async def test_unclear_with_nothing_still_not_understood(self):
        msg = await self._send("asdf qwer", intent_of("unclear"))
        self.assertIn("did not understand", msg.text_sent[0])

    async def test_extract_intent_returns_intent_field(self):
        payload = json.dumps(
            {"intent": "balance", "platform": None, "service_hint": None,
             "link": None, "quantity": None}
        )
        with mock.patch(
            "bot.gemini_generate", new=mock.AsyncMock(return_value=payload)
        ):
            result = await bot.extract_intent("How much is my balance")
        self.assertEqual(result["intent"], "balance")
        self.assertIsNone(result["platform"])

    def test_system_prompt_lists_intent_types(self):
        for word in (
            "balance", "orders", "deposit", "help", "greeting",
            "paxyo_info", "cancel", "off_topic", "unclear",
        ):
            self.assertIn(word, bot.SYSTEM_PROMPT)


class TestMultiTurnOrder(unittest.IsolatedAsyncioTestCase):
    """The worst bug from the owner's second screenshot (13 Nov 2026):
    a TikTok link, then a bare '2000', must complete the order — the
    bot used to forget the conversation between turns."""

    def setUp(self):
        bot.PENDING.clear()
        bot.LAST_ORDER.clear()
        bot.PARTIAL.clear()

    def tearDown(self):
        bot.PENDING.clear()
        bot.LAST_ORDER.clear()
        bot.PARTIAL.clear()

    async def _turns(self, turns):
        """Send several messages in sequence, sharing one FakeMessage so
        text_sent accumulates; returns (msg, fake_paxyo)."""
        msg = FakeMessage()
        update = FakeUpdate(msg)
        fake_paxyo = FakePaxyo()
        intents = [intent for _, intent in turns]
        with mock.patch(
            "bot.extract_intent", new=mock.AsyncMock(side_effect=intents)
        ), mock.patch("bot.paxyo", fake_paxyo), mock.patch("bot.speak_reply"):
            for text, _ in turns:
                await bot.handle_order_text(update, None, text)
        return msg, fake_paxyo

    async def test_link_then_bare_quantity_completes_order(self):
        # The exact failing sequence from the screenshot.
        msg, _ = await self._turns([
            ("https://instagram.com/p/x", intent_of(
                "order", platform="instagram", link="https://instagram.com/p/x")),
            ("2000", intent_of("order", quantity=2000)),
        ])
        self.assertEqual(msg.text_sent[0], "How many? (for example 1000)")
        self.assertEqual(len(msg.text_sent), 2)
        self.assertIn("Instagram Followers | Fast", msg.text_sent[1])
        self.assertIn("84.00", msg.text_sent[1])  # 42 ETB/1000 x 2000
        self.assertIsNotNone(msg.markups[1])  # the Confirm card
        self.assertEqual(bot.PARTIAL, {})
        self.assertEqual(len(bot.PENDING), 1)
        pending = next(iter(bot.PENDING.values()))
        self.assertEqual(pending["quantity"], 2000)
        self.assertEqual(pending["link"], "https://instagram.com/p/x")

    async def test_service_then_link_then_quantity(self):
        msg, _ = await self._turns([
            ("I want Instagram followers", intent_of(
                "order", platform="instagram", service_hint="followers")),
            ("https://instagram.com/p/x", intent_of(
                "order", link="https://instagram.com/p/x")),
            ("1000", intent_of("order", quantity=1000)),
        ])
        self.assertEqual(
            msg.text_sent[0], "Please send the link the order is for."
        )
        self.assertEqual(msg.text_sent[1], "How many? (for example 1000)")
        self.assertIn("Instagram Followers | Fast", msg.text_sent[2])
        self.assertIsNotNone(msg.markups[2])
        self.assertEqual(bot.PARTIAL, {})

    async def test_bare_quantity_with_no_context_asks_platform(self):
        msg, _ = await self._turns([
            ("2000", intent_of("unclear", quantity=2000)),
        ])
        self.assertEqual(
            msg.text_sent,
            ["Which platform? (Instagram, TikTok, Telegram, YouTube...)"],
        )
        self.assertEqual(bot.PARTIAL[1]["quantity"], 2000)
        self.assertEqual(bot.PENDING, {})

    async def test_bare_link_with_no_context_asks_platform(self):
        msg, _ = await self._turns([
            ("https://instagram.com/p/x", intent_of(
                "order", link="https://instagram.com/p/x")),
        ])
        self.assertEqual(
            msg.text_sent,
            ["Which platform? (Instagram, TikTok, Telegram, YouTube...)"],
        )
        self.assertEqual(
            bot.PARTIAL[1]["link"], "https://instagram.com/p/x"
        )

    async def test_new_platform_starts_a_new_order(self):
        msg, _ = await self._turns([
            ("I want 1000 Instagram followers", intent_of(
                "order", platform="instagram", service_hint="followers",
                quantity=1000)),
            ("Actually make it TikTok views", intent_of(
                "order", platform="tiktok", service_hint="views")),
        ])
        self.assertEqual(
            msg.text_sent[0], "Please send the link the order is for."
        )
        # The Instagram pieces were dropped; the bot asks for the
        # TikTok link instead of completing an Instagram order.
        self.assertEqual(
            msg.text_sent[1], "Please send the link the order is for."
        )
        self.assertEqual(bot.PARTIAL[1]["platform"], "tiktok")
        self.assertNotIn("link", bot.PARTIAL[1])
        self.assertNotIn("quantity", bot.PARTIAL[1])
        self.assertEqual(bot.PENDING, {})

    async def test_cancel_clears_partial_state(self):
        msg, _ = await self._turns([
            ("I want 1000 Instagram followers", intent_of(
                "order", platform="instagram", service_hint="followers",
                quantity=1000)),
            ("I don't want to", intent_of("cancel")),
        ])
        self.assertEqual(msg.text_sent[1], "Order cancelled.")
        self.assertEqual(bot.PARTIAL, {})
        # A bare number afterwards starts fresh — nothing stale merges in.
        msg2, _ = await self._turns([
            ("2000", intent_of("unclear", quantity=2000)),
        ])
        self.assertEqual(
            msg2.text_sent,
            ["Which platform? (Instagram, TikTok, Telegram, YouTube...)"],
        )


class FakeCloudTTSResponse:
    """Stand-in for an httpx response from Cloud TTS."""

    def __init__(self, payload=None, error=None):
        self._payload = payload or {}
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Stand-in for httpx.AsyncClient, recording POSTs."""

    def __init__(self, response):
        self._response = response
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.posts.append({"url": url, "headers": headers, "json": json})
        return self._response


def cloud_ogg_response():
    """A successful Cloud TTS response carrying fake OGG audio."""
    import base64 as _b64

    return FakeCloudTTSResponse(
        {"audioContent": _b64.b64encode(b"OggS-fake").decode()}
    )


class TestCloudTTS(unittest.IsolatedAsyncioTestCase):
    """cloud_tts_speak against a mocked HTTP client."""

    def _patched_client(self, response):
        client = FakeAsyncClient(response)
        return mock.patch("bot.httpx.AsyncClient", return_value=client), client

    async def test_returns_decoded_ogg_and_sends_key_header(self):
        patcher, client = self._patched_client(cloud_ogg_response())
        with patcher, mock.patch.object(bot, "GOOGLE_CLOUD_TTS_API_KEY", "test-cloud-key"):
            self.assertEqual(await bot.cloud_tts_speak("Hello!", "en"), b"OggS-fake")
        self.assertEqual(len(client.posts), 1)
        post = client.posts[0]
        self.assertEqual(post["url"], bot.GOOGLE_CLOUD_TTS_URL)
        self.assertEqual(post["headers"]["x-goog-api-key"], "test-cloud-key")
        self.assertEqual(post["json"], bot.build_tts_payload("Hello!", "en"))

    async def test_amharic_uses_amharic_voice(self):
        patcher, client = self._patched_client(cloud_ogg_response())
        with patcher, mock.patch.object(bot, "GOOGLE_CLOUD_TTS_API_KEY", "test-cloud-key"):
            await bot.cloud_tts_speak("ሰላም!", "am")
        voice = client.posts[0]["json"]["voice"]
        self.assertEqual(voice["languageCode"], "am-ET")
        self.assertEqual(voice["name"], "am-ET-Wavenet-A")

    async def test_no_key_returns_none_without_network(self):
        with mock.patch("bot.httpx.AsyncClient") as client_cls, \
             mock.patch.object(bot, "GOOGLE_CLOUD_TTS_API_KEY", ""):
            self.assertIsNone(await bot.cloud_tts_speak("Hello!", "en"))
        client_cls.assert_not_called()

    async def test_http_error_returns_none(self):
        patcher, client = self._patched_client(
            FakeCloudTTSResponse(error=Exception("400 Bad Request"))
        )
        with patcher, mock.patch.object(bot, "GOOGLE_CLOUD_TTS_API_KEY", "test-cloud-key"):
            self.assertIsNone(await bot.cloud_tts_speak("Hello!", "en"))

    async def test_missing_audio_content_returns_none(self):
        patcher, _ = self._patched_client(FakeCloudTTSResponse({}))
        with patcher, mock.patch.object(bot, "GOOGLE_CLOUD_TTS_API_KEY", "test-cloud-key"):
            self.assertIsNone(await bot.cloud_tts_speak("Hello!", "en"))

    async def test_unsupported_language_returns_none_without_network(self):
        with mock.patch("bot.httpx.AsyncClient") as client_cls, \
             mock.patch.object(bot, "GOOGLE_CLOUD_TTS_API_KEY", "test-cloud-key"):
            self.assertIsNone(await bot.cloud_tts_speak("Bonjour!", "fr"))
        client_cls.assert_not_called()


class TestWebhook(unittest.TestCase):
    """Webhook URL/path/port building from the environment.

    The module was imported with TELEGRAM_BOT_TOKEN=test-token, so the
    default webhook path is "test-token" in these tests.
    """

    def test_path_defaults_to_bot_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bot.get_webhook_path(), "test-token")

    def test_path_env_override(self):
        with mock.patch.dict(os.environ, {"WEBHOOK_PATH": "my-secret-path"}):
            self.assertEqual(bot.get_webhook_path(), "my-secret-path")

    def test_path_strips_surrounding_slashes(self):
        with mock.patch.dict(os.environ, {"WEBHOOK_PATH": "/my-path/"}):
            self.assertEqual(bot.get_webhook_path(), "my-path")

    def test_base_url_prefers_webhook_url(self):
        env = {
            "WEBHOOK_URL": "https://example.com",
            "RENDER_EXTERNAL_URL": "https://paxorder-bot.onrender.com",
        }
        with mock.patch.dict(os.environ, env):
            self.assertEqual(bot.get_webhook_base_url(), "https://example.com")

    def test_base_url_falls_back_to_render_external_url(self):
        with mock.patch.dict(
            os.environ,
            {"RENDER_EXTERNAL_URL": "https://paxorder-bot.onrender.com"},
            clear=True,
        ):
            self.assertEqual(
                bot.get_webhook_base_url(), "https://paxorder-bot.onrender.com"
            )

    def test_base_url_empty_when_neither_set(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bot.get_webhook_base_url(), "")

    def test_base_url_strips_trailing_slash(self):
        with mock.patch.dict(
            os.environ,
            {"RENDER_EXTERNAL_URL": "https://paxorder-bot.onrender.com/"},
            clear=True,
        ):
            self.assertEqual(
                bot.get_webhook_base_url(), "https://paxorder-bot.onrender.com"
            )

    def test_build_webhook_url(self):
        with mock.patch.dict(
            os.environ,
            {"RENDER_EXTERNAL_URL": "https://paxorder-bot.onrender.com"},
            clear=True,
        ):
            self.assertEqual(
                bot.build_webhook_url(),
                "https://paxorder-bot.onrender.com/test-token",
            )

    def test_build_webhook_url_raises_without_base(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                bot.build_webhook_url()

    def test_port_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bot.get_webhook_port(), 8443)

    def test_port_from_env(self):
        with mock.patch.dict(os.environ, {"PORT": "10000"}):
            self.assertEqual(bot.get_webhook_port(), 10000)

    def test_port_invalid_falls_back(self):
        with mock.patch.dict(os.environ, {"PORT": "not-a-port"}):
            self.assertEqual(bot.get_webhook_port(), 8443)


class TestBuildApplication(unittest.TestCase):
    def test_seven_handlers_registered(self):
        # start, balance, orders, help, text, voice, callback
        app = bot.build_application()
        total = sum(len(handlers) for handlers in app.handlers.values())
        self.assertEqual(total, 7)


class TestWebhookServer(tornado.testing.AsyncHTTPTestCase):
    """Real HTTP server: health endpoint + Telegram webhook path.

    Runs PTB's TelegramHandler (via build_webhook_app) on an ephemeral
    port. No Telegram connection, no network beyond localhost.
    """

    def get_app(self):
        return bot.build_webhook_app(bot.build_application())

    def test_health_endpoint_returns_ok(self):
        resp = self.fetch("/")
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.body, b"ok")

    def test_unknown_path_404(self):
        resp = self.fetch("/nope")
        self.assertEqual(resp.code, 404)

    def test_webhook_path_rejects_get(self):
        # TelegramHandler only supports POST.
        resp = self.fetch("/test-token")
        self.assertEqual(resp.code, 405)

    def test_webhook_path_accepts_telegram_post(self):
        resp = self.fetch(
            "/test-token",
            method="POST",
            body=json.dumps({"update_id": 12345}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.code, 200)


class TestMainWebhook(unittest.TestCase):
    def test_main_runs_webhook_server_on_render_port(self):
        env = {
            "RENDER_EXTERNAL_URL": "https://paxorder-bot.onrender.com",
            "PORT": "10000",
        }
        with mock.patch.dict(os.environ, env), \
             mock.patch("bot.PaxyoClient"), \
             mock.patch("bot.run_webhook_server") as run:
            bot.main()
        run.assert_called_once()
        app_arg, port_arg = run.call_args.args
        self.assertEqual(port_arg, 10000)
        total = sum(len(h) for h in app_arg.handlers.values())
        self.assertEqual(total, 7)

    def test_main_exits_without_webhook_base_url(self):
        # Secrets are the test values from import time, so only the
        # missing webhook base URL should stop startup.
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("bot.PaxyoClient"):
            with self.assertRaises(SystemExit):
                bot.main()


class TestServeWebhook(unittest.IsolatedAsyncioTestCase):
    async def test_sets_webhook_listens_and_stops(self):
        env = {"RENDER_EXTERNAL_URL": "https://paxorder-bot.onrender.com"}
        app = mock.AsyncMock()
        stop = asyncio.Event()
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("bot.build_webhook_app") as build_app, \
             mock.patch("bot.HTTPServer") as server_cls:
            server = server_cls.return_value
            task = asyncio.create_task(bot.serve_webhook(app, 10000, stop_event=stop))
            for _ in range(100):
                if app.bot.set_webhook.await_count:
                    break
                await asyncio.sleep(0.01)
            app.bot.set_webhook.assert_awaited_once_with(
                url="https://paxorder-bot.onrender.com/test-token",
                max_connections=40,
            )
            build_app.assert_called_once_with(app)
            server.listen.assert_called_once_with(10000, address="0.0.0.0")
            stop.set()
            await asyncio.wait_for(task, timeout=5)
        app.stop.assert_awaited_once()
        app.shutdown.assert_awaited_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
