# Paxyo Order bot (@paxorder_bot)

Telegram bot that lets Paxyo customers order social-media services by
chatting — by text, in Amharic or English. (A voice message sent to
the bot is transcribed and handled like text, but the bot does not
claim to take orders by voice — owner, 13 Nov 2026.)

- A user taps /start and their Paxyo account is created automatically.
- They write what they want. ChatGPT understands the message and
  extracts the order intent as JSON (Gemini is the fallback when no
  OpenAI key is set — see "AI provider" below).
- The bot searches the Paxyo catalogue, ranks services in the category by
  average time (fastest first), and shows the top pick with price and
  total, plus Confirm / Cancel buttons.
- On Confirm it checks the balance, then places the order through the
  Paxyo Bot API. No order is ever placed without a Confirm tap —
  EXCEPT an explicit urgent "order now" (owner override, 13 Nov
  2026): when the user explicitly says to order now and the order is
  fully specified, the bot places it at once and sends the full
  order summary in text. See "Round 5".
- /balance shows the balance. /orders shows ALL of the user's orders
  as a table (newest first). /help shows how it works.

## How it works

```
Telegram user --(text)--> bot.py (webhook, free Render web service)
    | ChatGPT (or Gemini): transcribe voice messages, extract intent JSON
    v
Paxyo Bot API on paxyo.et (https://paxyo.et/api/bot, X-Bot-Secret)
    | services / balance / create order / order status / create user
    v
Paxyo MySQL + existing website order flow --> fulfilment
```

Money rules: the AI only listens and talks. All totals are computed
server-side by the Paxyo API. The bot never invents a price, never sells
blacklisted services (5379, 5834) or inactive services, and never orders
without Confirm — except an explicit urgent "order now" (owner
override, 13 Nov 2026, see "Round 5"). Quantity must be a multiple
of 10 and inside the service min/max.

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
| `DEEPSEEK_API_KEY` | DeepSeek (platform.deepseek.com) — create an API key, paste it into Render. The bot uses it first; without it, it falls back to Qwen, then Groq, then OpenAI, then Gemini, then Kilo, then OpenRouter, then GLM. New accounts get 5M free tokens for 30 days. |
| `DEEPSEEK_MODEL` | `deepseek-chat` (default, V4.1 Flash). $0.15/1M input, $0.60/1M output off-peak (double at peak). |
| `QWEN_API_KEY` | Qwen (Alibaba Cloud Model Studio, international) — create an API key, paste it into Render. The bot uses it second (after DeepSeek); without it, it falls back to Groq, then OpenAI, then Gemini, then Kilo, then OpenRouter, then GLM. |
| `QWEN_MODEL` | `qwen-turbo` (default). $0.05/1M input, $0.20/1M output — about 3x cheaper than DeepSeek. |
| `GROQ_API_KEY` | Groq (console.groq.com) — create a free API key, paste it into Render. No card needed. The bot uses it third (after DeepSeek and Qwen); without it, it falls back to OpenAI, then Gemini, then Kilo, then OpenRouter, then GLM. |
| `GROQ_MODEL` | `openai/gpt-oss-120b` (default, 1,000 requests/day free). The small `llama-3.1-8b-instant` allows 14,400/day free. Groq retires models without warning — the old default `llama-3.3-70b-versatile` 404s for free accounts (13 Nov 2026) — so if Groq 404s, change this setting in Render, no code change needed. |
| `OPENAI_API_KEY` | OpenAI (platform.openai.com) — create an API key, add $5 of credit, paste the key into Render. The bot uses it fourth (after DeepSeek, Qwen and Groq); without it, it falls back to Gemini, then Kilo, then OpenRouter, then GLM. Setup is paused: the owner's card was declined (13 Nov 2026), so no key exists yet. |
| `OPENAI_MODEL` | `gpt-4o-mini` (default). gpt-4o-mini retires 2027-01-14, so switch this to its replacement when OpenAI says so — no code change needed. |
| `OPENROUTER_API_KEY` | OpenRouter (openrouter.ai) — create an API key, paste it into Render. No card needed. The bot uses it second-to-last (after Kilo); without it, it falls back to GLM. Free `:free` models cost $0/token: 50 requests/day, 1,000/day after a one-time $10 credit purchase (owner's choice, 14 Nov 2026). |
| `OPENROUTER_MODEL` | `openrouter/free` (default) — the router picks a currently-free model automatically, so the rotating free lineup cannot break the integration. Pin a model here (e.g. a `:free` model id) to use a specific one instead. |
| `KILO_MODEL` | `kilo-auto/free` (default) — the router picks a currently-free model automatically, so the rotating free lineup cannot break the integration. Pin a model here (e.g. a `:free` model id) to use a specific one instead. No key is needed for Kilo at all. |
| `KILO_URL` | `https://api.kilo.ai/api/gateway` (default) — the Kilo Code gateway, OpenAI-compatible. No auth header is sent. |
| `GLM_API_KEY` | GLM (Z.AI / Zhipu, open.bigmodel.cn) — create an API key, paste it into Render. The bot uses it last, only when every other provider failed; without it, there is no last resort. |
| `GLM_MODEL` | `glm-4.7-flash` (default). FREE ($0 input/output) but rate-limited (~1 request/second) and can be slow — last resort only. |
| `GOOGLE_CLOUD_TTS_API_KEY` | Google Cloud project (Cloud Text-to-Speech API enabled, billing on) — "Create API key", paste it into Render. The AI Studio (Gemini) key does NOT work for it. Until this is set, voice replies fall back to text. |
| `GOOGLE_CLOUD_TTS_VOICE` | `am-ET-Wavenet-A` (default) — the Amharic voice. |
| `GOOGLE_CLOUD_TTS_VOICE_EN` | `en-US-Wavenet-D` (default) — the English voice. |
| `PORT` | Set by Render automatically. The bot listens on it (default 8443 when run elsewhere). |
| `RENDER_EXTERNAL_URL` | Set by Render automatically — the service's public URL, e.g. `https://paxorder-bot.onrender.com`. The webhook URL is built from it. |
| `WEBHOOK_URL` | Optional override for `RENDER_EXTERNAL_URL` (local testing behind ngrok, etc.). |
| `WEBHOOK_PATH` | Optional secret path for Telegram updates. Defaults to the bot token itself (secret, so unguessable). |

## AI provider (DeepSeek first, Qwen second, Groq third, ChatGPT fourth, Gemini fifth, Kilo sixth, OpenRouter seventh, GLM last resort)

`ai_generate` / `ai_transcribe` / `ai_vision` in `bot.py` are the
only AI entry points. When `DEEPSEEK_API_KEY` is set they call
DeepSeek (`deepseek_generate` with the model from `DEEPSEEK_MODEL`,
default `deepseek-chat`, V4.1 Flash: $0.15/1M input, $0.60/1M
output off-peak, double at peak; new accounts get 5M free tokens
for 30 days). DeepSeek's API is OpenAI-compatible, so the code
mirrors the Groq calls. When no DeepSeek key is set they call Qwen
(`qwen_generate` with the model from `QWEN_MODEL`, default
`qwen-turbo`, $0.05/1M input, $0.20/1M output — about 3x cheaper
than DeepSeek — via Alibaba's international DashScope endpoint,
also OpenAI-compatible). When no Qwen key is set they call Groq
(`groq_generate` with the model from `GROQ_MODEL`, default
`openai/gpt-oss-120b`, 1,000 requests/day free (Groq retired the
old default `llama-3.3-70b-versatile` for free accounts, 13 Nov
2026 — the model is an env var so the next retirement is a
setting change, not a code change);
`groq_transcribe` with Whisper `whisper-large-v3-turbo`). Groq
is free — no card needed, just a key from console.groq.com. When
no Groq key is set they call OpenAI (`openai_generate`
with the model from `OPENAI_MODEL`, default `gpt-4o-mini`;
`openai_transcribe` with Whisper `whisper-1`; `openai_vision`
with the same model and a base64 image data URI). When no key at
all is set they call the existing `gemini_*` functions, and after
Gemini they call Kilo (`kilo_generate` with the model from
`KILO_MODEL`, default `kilo-auto/free` — the router picks a
currently-free model automatically; $0, no key, no signup, no
Authorization header, 200 requests/hour per IP — it only runs
after Gemini failed, so it never burns its per-IP hourly cap),
and after Kilo they call OpenRouter (`openrouter_generate` with the model
from `OPENROUTER_MODEL`, default `openrouter/free` — the router
picks a currently-free model automatically; free `:free` models
cost $0/token, 50 requests/day, 1,000/day after a one-time $10
credit purchase — it only runs after Kilo failed, so it never
burns its daily cap), and after OpenRouter they call GLM
(`glm_generate` with the model from
`GLM_MODEL`, default `glm-4.7-flash`, FREE but rate-limited at
~1 request/second and slow — last resort only). DeepSeek, Qwen,
Kilo, OpenRouter and GLM have no voice transcription — `ai_transcribe`
stays on Groq Whisper — and pictures stay on OpenAI/Gemini vision
— DeepSeek, Qwen, Kilo, OpenRouter and GLM are not used for them. A provider that fails
after its retries falls through to the next one, so the bot only
goes silent when every configured provider failed (and then
`extract_intent` answers from `local_intent`). The DeepSeek, Qwen,
Groq, OpenAI, Kilo, OpenRouter and GLM calls retry 429/500/503 twice (after 5s, then 15s),
mirroring `_gemini_post`.
**DeepSeek is the live provider (13 Nov 2026, evening):** Groq's
free tier hit its daily token limit (73% used by 21:48 EAT) and
Groq had temporarily disabled Developer (paid) upgrades, so the
owner said "use DeepSeek". **Qwen and GLM were added the same
evening (13 Nov 2026):** Qwen-Turbo as the cheaper second provider
and GLM-4.7-Flash as the free last resort. **OpenAI setup is paused (13 Nov 2026):**
the owner's card was declined, so no OpenAI key exists yet.
**gpt-4o-mini retires 2027-01-14** — switch `OPENAI_MODEL` to its
replacement then; no code change is needed. ChatGPT cost, when it
is used: about $0.0004 per chat reply, so $5 of credit covers
roughly 10,000 chats.

### Amharic translate-bridge (Gemini translates, the main AI thinks)

DeepSeek, Qwen and Groq have unproven Amharic, but Gemini is
strong on it — so a message in Ethiopic fidels is translated to
English by Gemini first (`translate_to_english`, in
`handle_order_text`), the whole flow runs in English, and prose
replies are translated back to Amharic in `reply_message`
(`translate_to_amharic`) before sending. English messages never
touch the bridge. If either translation call fails (Gemini 429,
no key), the original text is used instead — the bot never goes
silent and never drops an order over a translation failure, and
the local Amharic handling (round-7 Amharic metric words,
Amharic reply templates) still applies. Confirm cards, buttons,
prices, links and service IDs are never translated — only the
prose reply text is, and only when the message has no buttons
attached.

## Voice messages

A voice message sent to the bot is downloaded and transcribed
(Groq Whisper `whisper-large-v3-turbo`, via `ai_transcribe`), the
transcription is shown back to the user ("You said: ..."), and the
transcribed text is then handled exactly like the same typed
message. Replies are always text. The bot does not claim to take
orders by voice (owner, 13 Nov 2026 — the claims were removed
until the voice path is verified working live; they can be
re-added then). A download failure or a transcription failure gets
one plain line, never silence; a video note gets one plain line
too. GIFs and stickers also always get a reply — a caption is
handled as the user's message, otherwise a short friendly steer
back to ordering.

The Google Cloud Text-to-Speech pipeline (`speak_reply`,
`GOOGLE_CLOUD_TTS_API_KEY`, voices `am-ET-Wavenet-A` /
`en-US-Wavenet-D`) is still in the code but is not used for replies
right now: `on_voice` answers in text (`voice=False`). See
"Why Cloud TTS, not Gemini TTS" below for the voice history.

## Reply rules

- Text message in → text reply, always. The bot never answers a text
  message with a voice message.
- Voice message in → transcribed, then answered in text (see
  "Voice messages" above). The order summary / Confirm step and the
  post-acceptance summary are always text.
- After the user accepts an order — by tapping Confirm, by replying
  "yes" to a Confirm card, or by typing "yes" / "አዎ" (or similar) —
  the bot places the order and shows the full summary **in text**:
  service, quantity, link, total charge, order ID and status. So a
  voice confirmation always ends with a readable text record of what
  was ordered.
- Orders work in Amharic and English, by text.

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
voice path (Google Cloud TTS payload shape, voice selection by
language, transcription shown back, voice/text fallback) and the
reply rules (text in never produces voice, voice in is transcribed
and answered in text, Amharic and English orders) with the network
mocked, and the webhook wiring (webhook URL/path building from
`WEBHOOK_URL` / `RENDER_EXTERNAL_URL` / `WEBHOOK_PATH`, port
handling, the health endpoint, the app's 12 handlers, and the webhook
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
language, and nothing is ever placed without an explicit Confirm —
except an explicit urgent "order now" (owner override, 13 Nov 2026,
see "Round 5").

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
- **Policy and trust:** "can my account get banned or shadow
  banned?" gets the owner's answer — NO, anybody can buy followers
  for you, so your account can't be banned for it without your
  permission (owner, 13 Nov 2026; this replaces the earlier
  no-zero-risk line for this specific question — the live Terms
  §12 still says Paxyo is not responsible for account restrictions
  or bans). "Real Ethiopian followers" gets an honest answer
  (global network, not guaranteed real Ethiopian people) plus a
  slower service when one exists; refunds follow the Terms (back
  to Paxyo balance only, never to a bank or mobile-money account,
  balance can't be withdrawn as cash); orders can't be cancelled
  or changed once processing has started; Addis-only targeting is
  not available; no free likes (smallest order is the service
  minimum, cheapest service suggested).
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
  silence. (DeepSeek is now the first AI — see "AI provider" —
  because Groq's free tier hit its daily token limit and Groq had
  temporarily disabled paid upgrades; the fallback chain is
  DeepSeek → Qwen → Groq → ChatGPT → Gemini → Kilo → OpenRouter → GLM → local classifier.)
- **Prices showed 0.00 ETB.** The Paxyo API returns each service
  with `id` and `price` (ETB per 1000); the bot read `service` and
  `rate_etb_per_1000`, which the API does not send. `PaxyoClient.
  services()` now normalises the API shape to the bot's shape in
  one place, so prices, cheapest-first sorting, and order
  placement all see real values.

## Round 4 (13 Nov 2026 — live-test gaps)

Four gaps found in the live retest, plus one the owner added:

- **Budget answers state quantities.** "How much views can 10 br
  get me?" listed per-1000 prices but never said how many views.
  The budget answer now says the quantity each option buys
  (`qty_for_amount`: floor of amount / rate × 1000, rounded down
  to a multiple of 10) — about 520 views on the fastest one,
  about 6,620 on the cheapest.
- **Speed questions are answered from the pending service.**
  "How fast would those 1000 views arrive?" after a Confirm card
  got a generic line, because the classifier called it
  `paxyo_info` and the order flow never saw it. The question is
  now intercepted before intent dispatch and answered from the
  pending service's average time ("usually starts within
  5 minutes"). A number equal to the pending quantity is a
  reference to that order, not new information.
- **A quantity change reuses the pending link.** "Could I get 200
  views instead?" asked for the link again. It now updates the
  Confirm card in place (same service, same link, new quantity
  and total). A different platform or kind is still a new order.
- **Cheapest stays on the platform.** "Something cheaper" in a
  TikTok views chat offered Twitter Tweet Statistics. Cheaper /
  discount / budget replies now fall back to the platform and
  metric of the pending Confirm card or the order being built.
- **The bot knows Paxyo.** `PAXYO_KNOWLEDGE` now carries the
  owner (Yohannes Abate / William), paxyo.et, the Telegram
  channel, @paxyo_bot, the mini app, support@paxyo.et, Telebirr /
  CBE deposits via Chapa, and the 20% first-deposit bonus
  (invite code REF3723FB335). `paxyo_facts_answer` answers
  owner / what-is / how-to-pay / where-to-find questions from
  those local facts when the AI is down. The secrecy rule is
  unchanged: never the supplier, never what Paxyo pays.
- **Video likes / comment likes / comments are three services.**
  "Likes for my comment" must offer Tiktok Comment Likes, "likes
  for my video" video likes, "comments on my video" a comments
  service. `kind_from_text` reads the kind from the user's own
  words (singular and plural count the same), and
  `pick_services` only matches services whose name carries the
  asked kinds — so a comments request never gets Comment Likes
  (its name also says "likes") and a video-likes request never
  gets a comment-likes service.

## Round 5 (13 Nov 2026 — live-test gaps + owner additions)

- **Fastest fallback uses the stored metric.** "Use the fastest
  one" in a TikTok views order offered Tiktok Comment Likes,
  because the failed message had dropped the metric. The fallback
  now merges the platform + metric of the order being built
  (`PARTIAL`) before picking, so it shows a views service.
- **Bare quantities are understood.** "1000 please" / "200 please"
  after "How many?" are read as the quantity and complete the
  order, instead of being misread as a service search. A bare
  number is a quantity only when it is a multiple of 10 (so a
  service ID like 6139 never counts).
- **Website answers mention paxyo.et.** "Do you have a website?"
  now answers from the local facts (`paxyo_find`), which lists
  paxyo.et alongside the channel and the mini app.
- **Short service names.** Confirm cards, service lists, budget
  options and cheapest replies show the core name only
  ("TikTok Video Views", "Tiktok Comment Likes") — bracketed tags
  and pipe-separated descriptors are stripped by
  `short_service_name()`. The full long name is shown only when
  the user entered a service ID ("service 1665", "#1665") —
  tracked across turns of the same order (`named_by_id` in
  `PARTIAL`), not just the current message.
- **Price questions are answered directly.** "How much are tiktok
  views?" / "What's the price of 1000 views?" are answered from
  the catalogue (ETB per 1000, and the total when a quantity is
  given) without asking for the link first.
- **Replies / quotes are read in context.** A reply to one of the
  bot's own messages is routed by what was asked: "1000" replied
  to "How many?" is the quantity; "yes" replied to a Confirm card
  confirms it; "first one" replied to budget options picks the
  first option.
- **Orders table.** /orders (or "show my orders") shows ALL of the
  user's orders in a monospace table — ID, short service name,
  quantity, total in ETB, status with an icon — newest first, up
  to 20 (the API max). When the API returns nothing but this
  session placed an order, its status line is shown instead.
- **No voice-order claims.** No greeting, help, start or menu text
  claims the bot takes orders by voice (owner: "we don't now").
  The voice transcription code stays — a voice message sent to
  the bot is still transcribed and answered.
- **Voice messages fixed.** The old handler lumped download and
  transcription into one try block, so a download failure looked
  like a transcription failure and an exception inside the order
  flow could go silent. Download and transcription are separate
  now, the transcription is shown ("You said: ..."), the
  transcribed text is handled like typed text, and any failure
  gets one plain line, never silence. Replies are text.
- **GIFs and stickers always get a reply.** A caption is handled
  as the user's message; otherwise a short friendly steer back to
  ordering. Video notes get one plain line.
- **Humor + general knowledge + off-topic steering.** A light
  playful line (rotating, never at the user's expense) appears on
  happy paths such as an order being placed. The first two
  off-topic messages get a brief general answer plus a small
  nudge toward ordering; the third (and beyond) steers back to
  ordering with a short friendly line. An ordering message resets
  the counter. The secrecy rule is unchanged.
- **Offensive users.** An insult gets a firm, blunt pushback in
  one short line (never polite, never apologetic, never a slur
  back); a second insult refuses to continue; a third goes
  silent. Any non-offensive message resets the count.
- **Real delivery-time answers.** "How long would tiktok views
  take?" now gives the fastest matching service's average time
  ("usually starts within 5 minutes") plus the order-now nudge —
  with a pending Confirm card and without one. The vague
  "shown before you confirm / varies by service" line is gone:
  when no time is on file the bot says the Confirm card will show
  it, with the same nudge.
- **Conversation memory.** The last ~10 exchanges per user are
  kept in memory and included in the AI prompt, so the bot can
  refer back ("last time you ordered TikTok views"). They persist
  to a local `chat_history.json` (best effort) so they survive a
  bot restart — but Render's free disk is ephemeral on redeploy,
  so this is not permanent storage. The "the usual" / last-order
  memory is unchanged.
- **"Same like as usual."** "Same like as usual please order 1k
  views" replays the last order's service and link with quantity
  1000. The "usual" handler now accepts a new quantity in the
  same message (it wins over the last order's quantity).
- **Urgent "order now" skips the Confirm card.** An EXPLICIT
  order-now phrase ("please order now", "place it now", "just
  place it", "order it now", "do it now") with a fully specified
  order places it immediately — from the message itself, from the
  order being built, or from the pending Confirm card — and sends
  the full order summary in text. A vague "I want views" still
  goes through the Confirm card. If a detail is missing, the bot
  asks for it instead of placing. This is an explicit owner
  override of the old "no order without a Confirm tap" rule
  (13 Nov 2026, urgent order-now only).
- **Ban / shadowban answer.** "Can my social media account get
  banned or shadow banned?" is answered NO, with the owner's
  reasoning: anybody can buy followers for you, so your account
  can't be banned or shadowbanned for it without your permission. (EN + AM; round 6 added the shadowban wording.)
- **Payment methods.** The how-to-pay answer lists all four:
  Telebirr, CBE Birr, CBE, and M-Pesa. **Follow-up still owed:**
  deposit-by-chat only supports Telebirr/CBE today
  (`normalize_method` + the Chapa flow have no M-Pesa path), so
  an M-Pesa deposit by chat does NOT work yet — it needs a new
  payment path. The payment answer lists all four anyway.
- **Public-account reminder.** Every Confirm card says the
  account must be public (not private) — a private account can't
  receive the order. "Does my account need to be public?" is
  answered the same way.
- **Terms & Conditions.** The bot answers from Paxyo's actual
  terms (`paxyo-terms.md`, fetched from paxyo.et/home.php, 15
  sections, committed with this code): refunds go back to Paxyo
  balance only (never to a bank/mobile-money account), balance
  can't be withdrawn as cash, orders can't be cancelled or
  modified once processing has started, accounts must be public.
  "Show me the terms" points to paxyo.et. A terms question the
  file does not cover says so and offers support — nothing is
  invented.

## Round 6 (13 Nov 2026 — live-test gaps)

- **Cancel clears the stored order.** Tapping Cancel on a Confirm
  card (or saying "cancel") now drops the draft, any other open
  Confirm card for that user, the budget choice and any
  fastest-fallback token — and remembers the cancelled order's link
  and quantity (`CANCELLED_DRAFT`). If the AI then returns those
  exact values from conversation history for a fresh order, they
  are dropped and the bot asks for the link instead of auto-showing
  the cancelled card. A link or quantity the user types in the new
  message is a deliberate fresh choice and is kept. The record
  clears when an order is placed (round 7 tightened this: a fresh
  link in a turn that never becomes an order no longer clears it).
  The last PLACED order is untouched, so "the usual" keeps
  working.
- **"Same like as usual" reuses the link even when the AI
  misclassifies it.** The phrasing ("the usual", "same as
  yesterday", "same as last", "as usual", "my usual") is caught
  locally before the classifier, so "same like as usual please
  order 1k views" shows the Confirm card with the last order's
  service, link and quantity 1000 even when the AI would read it
  as a plain order (which used to ask for the link).
- **A mismatched link is explained once, never looped.** The link
  the user just pasted always wins over the AI's link, so a pasted
  link is never "missed" and the bot never repeats "Please send the
  link the order is for." with no explanation. For TikTok links
  only (their URL shapes are unambiguous): a video link for a
  followers order, or a profile link for a views/likes order, gets
  one plain line ("That link is a video — followers go to your
  profile, so please send your profile link instead.") and the bad
  link is dropped from the draft. Other platforms' links are left
  alone — the same shapes serve several metrics there, and the
  provider confirms the order on the Confirm card.
- **"How can I pay?" lists the methods first.** The bare question
  now answers with all four payment methods (Telebirr, CBE Birr,
  CBE, M-Pesa) before any deposit amount is asked. A message that
  already names a method, an amount or a phone is a deposit in
  progress, not a question — the deposit flow keeps it. "How do I
  add money?" / "how do I deposit?" stay deposit-flow entries (the
  existing tests pin them to asking for the amount).
- **Orders table totals carry the ETB label** (e.g. "3.78 ETB",
  not a bare number).
- **Ban answer covers shadowban.** "Can my social media account
  get banned or shadow banned?" is answered NO for both, with the
  owner's reasoning (EN + AM).

First attempt at these fixes was too broad and broke 33 existing
tests: the grounding guard dropped any link/quantity the AI
returned that the message text did not contain (the suite's mocked
intents legitimately carry details the text phrases without
digits/links), the pay-methods guard swallowed "How do I add
money?", and the kind check fired on the sample `instagram.com/p/x`
link used for followers orders. All three were rescoped as above;
the suite is green again (439 tests: 428 existing + 11 new).

## Round 7 (13 Nov 2026 — live-test gaps: state leakage)

- **A new metric replaces the old draft, never merges with it.**
  The live retest found the main bug was state leaking across
  turns: a followers draft survived into the next turn, so an
  Amharic views order got the followers answer, and a remembered
  200-view draft auto-showed a Confirm card. Now, when a message
  names a metric different from the stored draft's metric, the
  draft is dropped and the order starts fresh — and a link or
  quantity the AI carried over from the old order's history is
  dropped too, unless the user typed it in this message. A
  clarification of the same metric ("likes for my comment" is still
  likes) does not reset the draft, and a reply to the bot's question
  is explicit context, never dropped.
- **Amharic metric words are read.** `kind_from_text` only saw
  Latin words, so an Amharic views order ("እይታዎች") inherited the
  previous turn's followers hint from the AI. Amharic metric words
  (እይታዎች views, ተከታዮች followers, ላይኮች likes, አስተያየቶች
  comments, and more) now count the same way, so the message's own
  metric wins over a history-poisoned AI hint.
- **A misclassified order is still an order.** "I want TikTok
  followers for <video link>" came back from the AI as "safety",
  so the link-mismatch answer never fired in that turn. A local
  guard now runs after classification: a message that pastes a link
  (or @handle) and names a metric with an order verb ("want",
  "order", "buy", "get me", "give me", "need", Amharic እፈል- /
  ትዕዛዝ / ይዘዝ / ይግዝ) is forced to intent "order", with missing
  fields filled from the message itself. Genuine questions are
  untouched: price, ban, payment and public-account questions are
  answered by their own checks, and a message with no order verb
  ("is this link safe?") is not an order.
- **"Order now" parses the quantity before the metric.** "please
  order now 200 TikTok views for this video: <link>" asked "How
  many?" because the AI did not return the quantity. A number
  written right before the metric is now read as the quantity, so
  the order is placed at once. Only a number immediately before
  the metric counts — a stray number elsewhere ("my balance is
  100") is never read as the quantity.
- **"Use the fastest one" appears when the metric is ambiguous.**
  Until now the button only appeared when a service named by ID was
  refused, so in two live retests it never appeared at all. It is
  now offered on the "Which one do you want — views, likes?"
  question too, so the user can skip the choice and take the
  fastest service for the platform.
- **The cancelled record clears only on a placed order.** (See the
  Round 6 note above.)

450 tests: 439 existing + 11 new, all passing, no existing test
changed.

## Round 8 (14 Nov 2026 — the bot talks like a normal AI)

Live case from the owner's screenshot: the user ordered 👍
reactions, then asked "Do you understand what I said first" — and
the bot just repeated "Please send the link the order is for."
William: a normal AI says what it understood first.

- **"Do you understand" gets a restatement, not the link prompt.**
  A local guard (`conversation_reply`, before the order flow)
  catches confirm-understanding phrasings ("do you understand",
  "did you get that", "what did I say", "are you listening" —
  English and Amharic) and answers by restating the order being
  built — service, quantity, link if given, and what is still
  missing ("Yeah, I got it — you want 👍 reactions for your
  Telegram channel post, 1,000 of them. I just need the link to the
  post."). With a Confirm card pending it restates the card; with
  no context it says it is listening and has no order yet.
- **Emoji are read.** 👍 is the thumbs-up reaction, ❤️ heart, 🔥
  fire, 😂 laugh, 😮 wow, 😢 sad, 👀 views (`EMOJI_MEANINGS`,
  `emoji_meanings`, `reaction_emoji`). "reactions" is now a metric,
  so "I want 👍 this reaction" orders the 👍 Telegram reaction
  service, and a bare "👍" in an order context is understood too.
  The classifier prompt also says emoji carry meaning. 🙏 maps to
  thanks, never to a reaction type.
- **Mid-order questions are answered first.** "What do you mean",
  "why are you asking that" (and a bare "what?" / "huh?" while an
  order is being built) get an explanation of what the bot needs
  and why, then the order continues — the previous prompt is never
  repeated verbatim. The draft and any Confirm card stay untouched.
- **Free chat, with room to talk.** Greetings, small talk,
  comments, feelings and opinions ("haha nice", "I'm tired today,
  I need views for my new video", "do you think this video will
  go viral") get a natural AI answer plus one soft line back to
  the order ("Just send the link when you're ready...") instead of
  snapping back to the next order question. Pure small talk with
  no order being built still counts toward the round-5 2–3 turn
  steering. Real questions are never swallowed: ban, price,
  source, payment, usual, order-now, links, quantities, service
  IDs and deposit fields all fall through to their own handlers.
  When the AI is down, a local fallback answers (`local_chat_reply`).
- **Duplicate greeting guard.** A redelivered /start (same update
  id — the greeting went out twice at 07:26) now greets once
  (`_update_seen` in `start`). A genuine second /start still
  greets again.

498 tests: 472 existing + 26 new, all passing, no existing test
changed.

## Round 8.1 (14 Nov 2026 — the round-8 retest fixes)

Live retest of round 8 (09:29–09:37 EAT) found four gaps:

- **The restatement keeps the quantity.** A price question ("how
  much 1k") now stores what it asked about in the draft
  (`_remember_price_question` in `price_answer_text`), and the
  restatement looks back at the same metric in chat history
  (`_recent_quantity`, normalised so "1k" reads as 1000) — so
  "Do you understand what I said first" restates "👍 reactions
  for your Telegram channel post, 1,000" and never asks "how many"
  again. Three round-8 tests were updated to the new replies (a
  bare 👍 and a 👍 order message now get the acknowledgement
  first, not the stock link line).
- **A bare emoji is acknowledged as the reaction choice.**
  A message that IS just the emoji ("👍") in a reactions order
  gets "Got it — 👍 reactions. Send the link to the post..."
  first, then the link ask; with no order context it gets a
  natural reply naming the reaction ("Got it — 👍 thumbs-up
  reactions!...") and the draft is still started, so the next
  link completes a reactions order. A bare emoji while a
  NON-reactions order is being built is just an acknowledgement —
  it never hijacks that order: the emoji-only kind no longer
  wipes or rewrites the draft (`_text_has_words` guard in
  `handle_order_text`).
- **Feelings are acknowledged before tips.** Free-chat replies
  acknowledge the human part first (`_feeling_ack`: laugh +
  tired together get "Haha — get some rest when you can! 🙂"),
  then the AI's answer and the soft steer — so "haha nice, I'm
  tired today but I need views for my new video" gets the rest
  wish before the views tips, in the AI path and in the local
  fallback (`local_chat_reply`).
- **Telegram reactions are matched deterministically.**
  `pick_services` now takes `reaction_emoji` and, for a
  reactions request, only single-post reactions services in the
  emoji's family (`_reactions_pool`): 👍 → Thumbs up / Like,
  ❤️ → Heart, 🔥 → Fire, no emoji → the Positive mix — picked
  by the existing fastest-average-time rule. A "Bot Start"
  service and an "Auto … 10 Future Posts" service are never
  offered for a single-post order, so the same 👍 wording no
  longer quotes 81.90 one time and 336.00 the next: it quotes
  the thumbs-up service (e.g. #6541, 5.46 ETB per 1000).
  Reactions short names keep the type ("Telegram Reactions +
  Free Views — Thumbs up 👍") so the Confirm card says which
  reaction is being bought.

511 tests: 498 existing + 13 new, all passing.

## Next batch (14 Nov 2026 — reseller/contact answers + never-drop claim)

Owner instructions, built after round 8.1 settled:

- **Reseller questions go to William.** A user who wants to sell
  Paxyo's services themselves ("I want to resell", "how do I
  become a reseller", "can I sell your services", "I want to sell
  followers") gets one short line: contact William at t.me/paxyo.
  New `reseller` intent in the classifier prompt, `is_reseller_request`
  local guard (runs before the source-question guard — "resell" is a
  source-question word, but "I want to resell" is the user asking to
  sell), and a `local_intent` branch before the order fallback (so
  "I want to sell followers" is not misread as an order). Asking
  whether PAXYO is a reseller ("are you a reseller?") still deflects
  as a source question. The reply never uses the word "resell"
  itself, so the secrecy guard stays clean.
- **Contact / support questions go to William.** "I need support",
  "let me talk to a human", "how do I contact you", "who is the
  owner" → "You can reach William (Yohannes Abate) at t.me/paxyo —
  he will help you." New `contact` intent + `is_contact_request`
  guard + `local_intent` branch. Asking again just repeats the same
  one line. A reported problem ("my payment failed on the website,
  fix my account") is NOT a contact request — it keeps the existing
  `support_issue` redirect.
- **Telegram reactions, Telegram views and Facebook reactions never
  drop — only those three.** When the user asks about drops / fading
  / disappearing for one of them, the bot says so
  (`never_drop_kind` from the message + intent platform/metric, and
  `_service_never_drop_kind` from a pending or draft service's
  category/name). The claim fires in three places: the direct-answer
  check (before the terms answer, so a covered question never gets
  the generic "drops may occur" line), the Confirm-card drop answer
  (`pending_confirm_answer`), and the draft drop answer. For every
  other service — TikTok followers/likes/views, Instagram, YouTube,
  Telegram followers/members — the existing terms/refund answer
  stands, and the claim is never volunteered unprompted (an order
  or a price question never mentions it). Drop words recognised:
  drop, disappear, fade, fall off, go away, vanish, decrease,
  go down (the pending-order phrases gained fade / go away /
  vanish too).

546 tests: 511 existing + 35 new, all passing.

## Paused services (14 Nov 2026 — CapCut Pro, Canva Pro, SMS OTP)

Owner instruction: Paxyo used to offer cheap premium
subscriptions (CapCut Pro, Canva Pro, ...) and an SMS OTP
verification service — both are PAUSED now. When a user asks for
any of them ("I want CapCut Pro", "do you sell Canva Pro",
"cheap premium subscriptions", "can I get Netflix/Spotify
premium", "I need SMS OTP verification", "OTP number for
verification"), the bot answers in one short line: that one is
paused right now, we will let you know when it's ready. No date,
no price, never "available", and never a social-media service
offered instead. Asking again just repeats the same line.

New `paused_services` intent in the classifier prompt,
`is_paused_services_request` local guard (runs before the
classifier, like the reseller/contact guards) and a `local_intent`
branch before the order fallback. The guard is deliberately
narrow: it matches the brand names (capcut, canva, netflix,
"spotify premium", "youtube premium", "premium subscription(s)")
and OTP-service phrasing — but never a message that names a
social-media metric ("premium followers", "Spotify followers",
"premium views" are real orders) and never "Telegram Premium"
(a real Bot Start service; the catalogue has 293 "premium"
services, mostly Telegram Premium members, plus Spotify
followers/likes — CapCut/Canva/Netflix/OTP have none). The metric
check is word-based on plurals only, so "I would like CapCut Pro"
still matches (the verb "like" is not the metric "likes"). The
paused answer is never volunteered: greetings and help never
mention these services.

565 tests: 546 existing + 19 new, all passing.
