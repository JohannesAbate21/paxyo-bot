# Paxyo Order bot (@paxorder_bot)

Telegram bot that lets Paxyo customers order social-media services by
chatting — text or voice message, in Amharic or English.

- A user taps /start and their Paxyo account is created automatically.
- They write what they want (or send a voice message). Gemini understands
  the message and extracts the order intent as JSON.
- The bot searches the Paxyo catalogue, ranks services in the category by
  average time (fastest first), and shows the top pick with price and
  total, plus Confirm / Cancel buttons.
- On Confirm it checks the balance, then places the order through the
  Paxyo Bot API. No order is ever placed without a Confirm tap.
- /balance shows the balance. /orders shows the status of the last order.
  /help shows how it works.

## How it works

```
Telegram user --(text/voice)--> bot.py (webhook, free Render web service)
    | Gemini: transcribe voice, extract intent JSON
    v
Paxyo Bot API on paxyo.et (https://paxyo.et/api/bot, X-Bot-Secret)
    | services / balance / create order / order status / create user
    v
Paxyo MySQL + existing website order flow --> GodOfPanel (provider)
```

Money rules: the AI only listens and talks. All totals are computed
server-side by the Paxyo API. The bot never invents a price, never sells
blacklisted services (5379, 5834) or inactive services, and never orders
without Confirm. Quantity must be a multiple of 10 and inside the
service min/max.

## Files

- `bot.py` — the whole bot (handlers, Paxyo API client, Gemini client).
- `requirements.txt` — python-telegram-bot 21+, httpx.
- `render.yaml` — Render free web service definition (webhook mode).
- `test_bot_offline.py` — offline self-test, no network, no real orders.
- `README.md` — this file.

## Configuration (environment variables only)

| Variable | Value / where it comes from |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The @paxorder_bot token, from the BotFather chat on Telegram. Never commit it. |
| `PAXYO_API_BASE` | `https://paxyo.et/api/bot` (default; set in render.yaml). |
| `BOT_API_SECRET` | From `config_secret.php` on the paxyo.et server. Read it in the DirectAdmin Terminal (`grep BOT_API_SECRET public_html/config_secret.php`) and paste the value into Render. Never put it in a file or in chat. |
| `GEMINI_API_KEY` | Google AI Studio (aistudio.google.com) — "Get API key", create a key, paste it into Render. |
| `GEMINI_MODEL` | `gemini-3.5-flash` (default). gemini-2.5-flash is retired for new users; gemini-3.8-flash returned 503 when tested. |
| `GOOGLE_CLOUD_TTS_API_KEY` | Google Cloud project (Cloud Text-to-Speech API enabled, billing on) — "Create API key", paste it into Render. The AI Studio (Gemini) key does NOT work for it. Until this is set, voice replies fall back to text. |
| `GOOGLE_CLOUD_TTS_VOICE` | `am-ET-Wavenet-A` (default) — the Amharic voice. |
| `GOOGLE_CLOUD_TTS_VOICE_EN` | `en-US-Wavenet-D` (default) — the English voice. |
| `PORT` | Set by Render automatically. The bot listens on it (default 8443 when run elsewhere). |
| `RENDER_EXTERNAL_URL` | Set by Render automatically — the service's public URL, e.g. `https://paxorder-bot.onrender.com`. The webhook URL is built from it. |
| `WEBHOOK_URL` | Optional override for `RENDER_EXTERNAL_URL` (local testing behind ngrok, etc.). |
| `WEBHOOK_PATH` | Optional secret path for Telegram updates. Defaults to the bot token itself (secret, so unguessable). |

## Voice replies

A voice message in gets a voice message back; a text message in gets
text back — never the other way round. Voice replies use **Google
Cloud Text-to-Speech**: Amharic replies use voice `am-ET-Wavenet-A`
(override with `GOOGLE_CLOUD_TTS_VOICE`), English replies use
`en-US-Wavenet-D` (override with `GOOGLE_CLOUD_TTS_VOICE_EN`). Any
other language falls back to text — the bot never guesses a voice.
Cloud TTS returns OGG Opus directly, the format Telegram voice
messages need, so **no ffmpeg is needed on Render**. If voice
synthesis fails for any reason, the bot answers by text instead — it
never breaks an order over voice.

## Reply rules

- Text message in → text reply, always. The bot never answers a text
  message with a voice message.
- Voice message in → voice reply (Google Cloud TTS), except:
  - the order summary / Confirm step, which is always text (a voice
    message cannot carry inline buttons);
  - the post-acceptance summary, which is always text (see below).
- After the user accepts an order — by tapping Confirm, by saying
  "yes" / "አዎ" (or similar) in a voice message, or by typing it —
  the bot places the order and shows the full summary **in text**:
  service, quantity, link, total charge, order ID and status. So a
  voice confirmation always ends with a readable text record of what
  was ordered.
- Orders work in Amharic and English, by text and by voice.

The owner's voice prompt (`VOICE_STYLE_PROMPT` in `bot.py`, pasted by
him verbatim) is kept as documentation of the desired delivery —
relaxed, fast-paced but controlled, informative, like a calm,
confident podcast host, never theatrical, never hype. Cloud TTS takes
no style prompt of its own; the request uses speaking rate 1.0 and
pitch 0, which approximate that delivery.

**Why Cloud TTS, not Gemini TTS (13 Nov 2026):** Gemini TTS was
tried first and verified live to return **no audio at all for
Amharic** — plain sentences, a style prefix, a different voice, and
the owner's exact prompt all came back HTTP 200 with an empty
candidate (`finishReason: OTHER`). The key's TTS free-tier quota is
also only 10 requests/day (exhausted during testing), and the
higher-quality Pro TTS model has 0 quota on it. The likely reason it
works in AI Studio for the owner but not through the API: AI Studio
runs on his Pro account quota, the API key is free-tier. Cloud TTS
has real Amharic voices and a free tier of 1M WaveNet / 4M Standard
characters a month, far more than this bot will use.

**Live test pending:** the Cloud TTS API key does not exist yet — it
comes from the Google Cloud project (Cloud Text-to-Speech API
enabled, billing on). Until `GOOGLE_CLOUD_TTS_API_KEY` is set, voice
replies fall back to text.

## Deploy on Render (exact steps) — free web service, webhook mode

The bot runs as a **free Render web service**, not a background worker
(background workers have no free option — cheapest is $7/month). Telegram
pushes updates to a webhook URL instead of the bot polling: on startup
the bot sets its own webhook to
`<RENDER_EXTERNAL_URL>/<bot-token>` and serves Render's health check at
`GET /` ("ok"). The webhook path defaults to the bot token, so it is
unguessable; `WEBHOOK_PATH` / `WEBHOOK_URL` override it when set.

1. Push this folder to a Git repo (GitHub/GitLab) and connect it to
   Render, or use Render's "New +" and pick this repo. **The code must
   live in a Git repo first** — Render deploys from a repo, not from a
   local folder.
2. In Render: **New + → Web Service**.
3. Pick the repo and branch. Render detects Python from
   `requirements.txt`. Choose the **Free** plan.
4. Build command: `pip install -r requirements.txt`
5. Start command: `python bot.py`
6. Environment: **Python 3**. Add the secret variables under
   **Environment Variables** (mark the four secrets as Secret, not
   plain values). The `render.yaml` in this folder also defines the
   web service with the same commands, the non-secret defaults, and
   `healthCheckPath: /`.
7. Click **Create Web Service**. The logs should show
   `Telegram webhook set (base https://paxorder-bot.onrender.com)` and
   `Listening on 0.0.0.0:$PORT`. (The full webhook URL is never logged:
   it contains the bot token as its path.)
8. Open Telegram and send /start to @paxorder_bot. It should greet you
   and create your account. Try an order with a small quantity first.

Free-tier caveat: a Render free web service **sleeps after ~15 minutes
idle**, so the first message after a quiet period can take ~30-50s
while the service wakes up. Later messages answer immediately. A paid
instance (from about $7/month) stays awake and answers immediately.

If the service URL ever changes (rename / recreate), the bot sets the
new webhook itself on its next startup — nothing has to be changed in
BotFather. If you ever need to remove the webhook (back to polling
during development), call `delete_webhook` on the Bot API yourself;
the bot always sets the webhook on startup.

## Run locally (testing only)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
TELEGRAM_BOT_TOKEN=... BOT_API_SECRET=... GEMINI_API_KEY=... python bot.py
```

## Self-test (no network, no real orders)

```bash
python3 test_bot_offline.py
```

It checks average-time parsing, fastest-first ranking, blacklisted and
inactive exclusion, quantity rules, intent-JSON extraction, language
detection, API request URL/header building, price maths, the
voice-reply path (Google Cloud TTS payload shape, voice selection by
language, voice/text fallback) and the reply rules (text in never
produces voice, voice in produces voice except the Confirm card and
the post-acceptance text summary, Amharic and English orders) with
the network mocked, and the webhook wiring (webhook URL/path building
from `WEBHOOK_URL` / `RENDER_EXTERNAL_URL` / `WEBHOOK_PATH`, port
handling, the health endpoint, the app's 7 handlers, and the webhook
server lifecycle) with the network mocked.

## Amharic prompt

`bot.py` ships with a default English `SYSTEM_PROMPT` (marked
replaceable) that tells Gemini to extract the order intent as JSON.
The owner may replace it with their own Amharic prompt. Replies to
users are in the user's language: Amharic in means Amharic out
(Ethiopic fidels mixed with English, never Latin-letter Amharic).

The owner's **voice** prompt — how the bot sounds when it speaks —
is separate: `VOICE_STYLE_PROMPT` in `bot.py`, pasted by him verbatim.
See "Voice replies" and "Reply rules" above for what it does and for
why the voice provider is Google Cloud TTS (Gemini TTS was verified
to return no audio for Amharic).

## Later phase (not built in this version)

Stall-fallback: if the picked service stalls, cancel/refund and move
to the next-fastest service in the category. The code is structured
for it — `PaxyoClient.order_status()` already fetches live order
status, and there is a TODO in `main()` where a monitor can be added
(a background task polling recent orders). It is deliberately not in
this version.
