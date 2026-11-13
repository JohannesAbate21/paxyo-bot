# Paxyo Order bot (@paxorder_bot)

Telegram bot that lets Paxyo customers order social-media services by
chatting — text or voice message, in Amharic or English.

- A user taps /start and their Paxyo account is created automatically.
- They write what they want (or send a voice message). ChatGPT
  understands the message and extracts the order intent as JSON
  (Gemini is the fallback when no OpenAI key is set — see
  "AI provider" below).
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
    | ChatGPT (or Gemini): transcribe voice, extract intent JSON
    v
Paxyo Bot API on paxyo.et (https://paxyo.et/api/bot, X-Bot-Secret)
    | services / balance / create order / order status / create user
    v
Paxyo MySQL + existing website order flow --> fulfilment
```

Money rules: the AI only listens and talks. All totals are computed
server-side by the Paxyo API. The bot never invents a price, never sells
blacklisted services (5379, 5834) or inactive services, and never orders
without Confirm. Quantity must be a multiple of 10 and inside the
service min/max.

## Files

- `bot.py` — the whole bot (handlers, Paxyo API client, OpenAI +
  Gemini clients).
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
| `GROQ_API_KEY` | Groq (console.groq.com) — create a free API key, paste it into Render. No card needed. The bot uses it first; without it, it falls back to OpenAI, then Gemini. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` (default, 1,000 requests/day free). The small `llama-3.1-8b-instant` allows 14,400/day free. |
| `OPENAI_API_KEY` | OpenAI (platform.openai.com) — create an API key, add $5 of credit, paste the key into Render. The bot uses it second (after Groq); without it, it falls back to Gemini. Setup is paused: the owner's card was declined (13 Nov 2026), so no key exists yet. |
| `OPENAI_MODEL` | `gpt-4o-mini` (default). gpt-4o-mini retires 2027-01-14, so switch this to its replacement when OpenAI says so — no code change needed. |
| `GOOGLE_CLOUD_TTS_API_KEY` | Google Cloud project (Cloud Text-to-Speech API enabled, billing on) — "Create API key", paste it into Render. The AI Studio (Gemini) key does NOT work for it. Until this is set, voice replies fall back to text. |
| `GOOGLE_CLOUD_TTS_VOICE` | `am-ET-Wavenet-A` (default) — the Amharic voice. |
| `GOOGLE_CLOUD_TTS_VOICE_EN` | `en-US-Wavenet-D` (default) — the English voice. |
| `PORT` | Set by Render automatically. The bot listens on it (default 8443 when run elsewhere). |
| `RENDER_EXTERNAL_URL` | Set by Render automatically — the service's public URL, e.g. `https://paxorder-bot.onrender.com`. The webhook URL is built from it. |
| `WEBHOOK_URL` | Optional override for `RENDER_EXTERNAL_URL` (local testing behind ngrok, etc.). |
| `WEBHOOK_PATH` | Optional secret path for Telegram updates. Defaults to the bot token itself (secret, so unguessable). |

## AI provider (Groq first, ChatGPT second, Gemini fallback)

`ai_generate` / `ai_transcribe` / `ai_vision` in `bot.py` are the
only AI entry points. When `GROQ_API_KEY` is set they call Groq
(`groq_generate` with the model from `GROQ_MODEL`, default
`llama-3.3-70b-versatile`, 1,000 requests/day free;
`groq_transcribe` with Whisper `whisper-large-v3-turbo`). Groq
is free — no card needed, just a key from console.groq.com — and
its API is OpenAI-compatible, so the code mirrors the OpenAI
calls. When no Groq key is set they call OpenAI (`openai_generate`
with the model from `OPENAI_MODEL`, default `gpt-4o-mini`;
`openai_transcribe` with Whisper `whisper-1`; `openai_vision`
with the same model and a base64 image data URI). When neither
key is set they call the existing `gemini_*` functions, which are
unchanged. Pictures stay on OpenAI/Gemini vision — Groq is not
used for them. A provider that fails after its retries falls
through to the next one, so the bot only goes silent when every
configured provider failed (and then `extract_intent` answers
from `local_intent`). The Groq and OpenAI calls retry 429/500/503
twice (after 5s, then 15s), mirroring `_gemini_post`.
**OpenAI setup is paused (13 Nov 2026):** the owner's card was
declined, so no OpenAI key exists yet — Groq is the live provider.
**gpt-4o-mini retires 2027-01-14** — switch `OPENAI_MODEL` to its
replacement then; no code change is needed. ChatGPT cost, when it
is used: about $0.0004 per chat reply, so $5 of credit covers
roughly 10,000 chats.

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
handling, the health endpoint, the app's 8 handlers, and the webhook
server lifecycle) with the network mocked. It also covers the durable
last-link memory (recent orders), repeating-order plans (Confirm
required, stop/list) and the scheduler loop (due runs once,
balance-short pause, catch-up after sleep).

## Remembering and repeating orders

- **Last link:** "order on that link again" resolves the link (and the
  service, when none is named) from the user's most recent order via
  `GET /api/bot/orders?telegram_id=&limit=5`, so it works after a
  restart. With no previous order the bot asks for the link.
- **Repeating orders:** "order 1k views on that link every 3 hours"
  builds a plan and shows a short summary (service, quantity, link,
  every 3 hours, cost per order) with Confirm/Cancel — nothing starts
  without Confirm. `/schedules` lists active plans; "stop the
  repeating order" cancels one (buttons when there are several).
  Shortest repeat: every 30 minutes.
- **Scheduler:** a background loop every 60 seconds asks the server
  for due schedules (`GET /api/bot/recurring/due`), checks the balance
  first, places the order (idempotency key per schedule+slot), then
  marks it ran. Balance too low pauses the schedule and tells the
  user. A schedule that slept only ever runs once on wake.

## Choosing a service

- The bot picks the fastest service automatically — unless the user
  names one. "use service 6139", "service #5535", "order with 7246",
  "the cheapest Instagram followers" or "same service as last time"
  all use THAT service for the order, and the Confirm card shows it
  as "Name (#id)" so the user sees which one is being used.
- A named service is validated first: it must exist, be active, and
  never be blacklisted (5379, 5834 — refused even if asked for by
  ID). A bad one is refused in one line with a one-tap "Use the
  fastest one" button that resumes the same order. A description
  ("cheapest ...") ranks by price; otherwise fastest-first. "Same
  service as last time" takes the service from the most recent order.

## Deposit by chat

- "let me deposit 10 br by telebirr and my phone number is 099387383"
  (and many ways of saying it, in English or Amharic) starts a
  deposit: the bot asks for only the missing pieces — amount, then
  method (Telebirr or CBE), then phone — and shows a short Confirm
  summary. Nothing is created until confirmed.
- On Confirm it calls `POST /api/bot/deposits` and replies with
  short payment instructions in the user's language. When Chapa
  pushes a USSD prompt to the user's phone (Direct Charge), the bot
  says the request is on its way and to approve it with the PIN;
  when the server returns a code or a link instead, it shows the
  USSD code to dial and/or the checkout link to open. Either way it
  says the balance updates automatically once the payment succeeds.
  The bot never credits anything itself — crediting is server-side
  (Chapa verify/recheck). If the deposit endpoint is not live yet,
  the bot says so in one line and points at paxyo.et.
- Slang and typos are tolerated: "teleirr", "telebir", "amd", "blance",
  "oder", "histry", "dipost" and similar are fixed by a small explicit
  map before classification, and Latin-letter Amharic ("selam") is
  accepted. Phones are normalized to the 2519xxxxxxxx form
  (09… / 07… / 251… / +251… accepted). Amounts over 100,000 ETB are
  refused in one line.
- **Checking a deposit:** "did my deposit go through?", "I paid but my
  balance didn't change", "check my deposit", or a bare "I paid" /
  "I approved it" rechecks the most recent deposit — the in-session
  deposit id first, else the newest from
  `GET /api/bot/deposits?telegram_id=&limit=5` — through
  `GET /api/bot/deposits/{id}?telegram_id=`, which re-verifies with
  Chapa before answering. Completed: the fresh balance is shown.
  Still pending: the user is told to approve the prompt on their
  phone and ask again. Failed: the server's reason, or a generic
  line — the bot never invents one. No deposits: one short line
  offering to start one. Endpoints not live yet: one short line
  pointing at Deposit History on paxyo.et.

## Photos

- A picture sent to the bot is read with ChatGPT vision
  (`ai_vision`, falling back to `gemini_vision` with no OpenAI key;
  same model as text) and routed by what it shows:
  a payment receipt is shown back with the amount/reference found
  and offered a recheck ("Yes, check it" button, or a bare "yes") —
  the same Chapa recheck as "did my deposit go through?"; a
  profile/post screenshot starts the order flow with the extracted
  link (platform from the link's domain, so it goes straight to
  "how many?"); anything else gets the summary plus one short
  follow-up question. A receipt the model cannot read asks for the
  amount in text; a username without a link asks for the link.
- Pictures are capped at 10 MB (refused in one line) and are kept in
  memory only — never written to disk, and sent nowhere except the
  one AI call the user asked for by sending the picture. A
  vision failure, timeout or unreadable result gets one short
  fallback line and is never retried in a loop. A photo sent while
  an order or deposit is being built answers that pending question
  when it makes sense (a receipt while a deposit is pending, a link
  while an order is being built).

## Amharic prompt

`bot.py` ships with a default English `SYSTEM_PROMPT` (marked
replaceable) that tells the AI to extract the order intent as JSON.
The owner may replace it with their own Amharic prompt. Replies to
users are in the user's language: Amharic in means Amharic out
(Ethiopic fidels mixed with English, never Latin-letter Amharic).

The owner's **voice** prompt — how the bot sounds when it speaks —
is separate: `VOICE_STYLE_PROMPT` in `bot.py`, pasted by him verbatim.
See "Voice replies" and "Reply rules" above for what it does and for
why the voice provider is Google Cloud TTS (Gemini TTS was verified
to return no audio for Amharic).

## Messy real-world inputs (owner edge-case spec, 13 Nov 2026)

Users type messy, incomplete, unexpected prompts. The bot handles
them instead of breaking; every reply stays short and in the user's
language, and nothing is ever placed without an explicit Confirm.

- **Ambiguous:** "give me the usual" replays the last order as a
  Confirm card (doubled on request, capped at the service max);
  "boost my latest video" admits the bot cannot see the profile and
  asks for the link; budget-first ("10k for 500 birr") lists the
  cheapest and fastest options that fit, or the max quantity the
  budget buys; goal-based ("make my TikTok go viral") asks which
  metric matters first.
- **Multi-order:** split an order across N links (one Confirm places
  them all, each with its own idempotency key; missing links are
  counted); several services/targets in one message become one batch
  Confirm card, with the unclear part listed and asked about;
  drip-feed ("1,000 every hour") maps to the recurring feature
  (intervals under 30 minutes are refused); a friend's handle is
  shown exactly as typed with a spelling double-check on the card.
- **Links:** a platform/link mismatch is flagged in one line and the
  order waits for the correction — never placed mismatched.
  Shortened links are accepted; private accounts and expiring story
  links get one warning on the Confirm card. A profile screenshot
  mid-order fills the link; a mixed Amharic-English voice note still
  extracts platform/link/quantity.
- **Mid-order:** changing the quantity edits a draft (a placed order
  shows its live status instead); cancelling a draft cancels at once
  (a placed order shows status and the support path); "why hasn't it
  started yet?" answers with the real status plus the service's
  average time, never a bare "soon"; a short delivery is checked
  first — still running says so, finished short points at support
  with no refund/refill promise and no second order without Confirm.
- **Payment:** split payment is not supported (deposit the Telebirr
  half first, then the order uses the wallet); "how many can my
  balance buy?" reverse-calculates from the real balance, floored to
  a multiple of 10 and capped by the service min/max; discounts are
  refused in one line with the cheapest real option offered instead.
- **Policy and trust:** ban risk and "real Ethiopian followers" get
  an honest answer (gradual and widely used, no zero-risk guarantee,
  global network, not guaranteed real Ethiopian people) plus a slower
  service when one exists; drops/refunds are never promised — support
  reviews them; Addis-only targeting is not available; no free likes
  (smallest order is the service minimum, cheapest service suggested).
- **Adversarial:** a user-supplied price is never applied — prices
  are fixed by Paxyo, cheapest real option offered; caption/posting
  tips are brief, then back to ordering; website payment/account
  problems redirect to the deposit recheck or Deposit History at
  paxyo.et — the bot cannot fix the website account.
- **Guardrails:** a half-built order survives any interruption (the
  user is told where it stands — "still waiting for Confirm" or
  "still building"); every Confirm shows service, quantity, link and
  total; API errors are one short plain line, never raw.

## Later phase (not built in this version)

Stall-fallback: if the picked service stalls, cancel/refund and move
to the next-fastest service in the category. The code is structured
for it — `PaxyoClient.order_status()` already fetches live order
status, and there is a TODO in `main()` where a monitor can be added
(a background task polling recent orders). It is deliberately not in
this version.

## Reliability (added 13 Nov 2026 — the silence fix)

Two bugs found live on 13 Nov, both fixed here:

- **The bot went silent.** When Gemini's free-tier key hit its
  per-minute limit (HTTP 429), the classify call raised and the
  message got no reply at all. Now `_gemini_post` retries 429/503
  twice (after 5s, then 15s), and `extract_intent` falls back to a
  local classifier (`local_intent`) when Gemini is unreachable, so
  the bot always answers — balance, orders, deposits, recurring,
  and plain orders all work without the AI. A message it still
  cannot classify gets a short "busy right now" line, never
  silence. (Groq is now the first AI — see "AI provider" —
  because the free Gemini key kept hitting its limit and the
  OpenAI card payment was declined; the fallback chain is
  Groq → ChatGPT → Gemini → local classifier.)
- **Prices showed 0.00 ETB.** The Paxyo API returns each service
  with `id` and `price` (ETB per 1000); the bot read `service` and
  `rate_etb_per_1000`, which the API does not send. `PaxyoClient.
  services()` now normalises the API shape to the bot's shape in
  one place, so prices, cheapest-first sorting, and order
  placement all see real values.
