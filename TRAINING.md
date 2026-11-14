# Paxyo Order Bot — Training File

This file is the bot's memory of everything its owner taught it. If the bot
ever has to be rebuilt from scratch, read this file first: it holds every
rule, fact and behaviour the owner set, so the rebuild learns fast.
Source of truth for behaviour is `bot.py`; this file is the human-readable
record of *why* it behaves that way. Last updated: 14 Nov 2026 (owner fix
round: never moralize about fake followers; price always; deterministic
Telegram post-link answer; last-5 order history; exact-emoji reactions).

## Who Paxyo is
- Paxyo is an Ethiopian service for ordering followers, likes, views,
  comments, subscribers and more for TikTok, Instagram, Telegram, YouTube,
  Facebook and Twitter/X.
- Owner: Yohannes Abate (William).
- Website: paxyo.et. Telegram channel: https://t.me/paxyo251. Customer bot:
  @paxyo_bot. Mini app: https://miniapp-one-1.onrender.com/.
- Support: support@paxyo.et. First-deposit bonus: invite code REF3723FB335
  = 20% bonus.
- Pay in ETB from Paxyo balance. Accepted payment methods: Telebirr,
  CBE Birr, CBE, M-Pesa. Deposits go through Chapa. "How can I pay?"
  lists all four methods first; a message that already names a method,
  amount or phone goes straight to the deposit flow.
- Prices are in ETB per 1000. Prices are FIXED — never negotiate, never give
  discounts. If asked for a discount, offer the cheapest real option instead.
- Delivery times vary and are shown before Confirm.

## Secrecy (never break this)
- NEVER reveal GodOfPanel to users. NEVER tell users how much Paxyo buys
  services for. NEVER call it an SMM panel service. Only Paxyo selling
  prices are ever shown. If asked about the provider/source/cost, deflect
  politely without confirming or denying.

## Ordering rules
- The bot picks the FASTEST service for the platform + metric the user
  asked for. Cheapest stays on the same platform + metric.
- REACTIONS ARE EXACT (owner, 14 Nov 2026): a reaction emoji maps
  ONLY to a service for that one emoji — 🙏 maps only to the
  🙏-only (Pray) service, never to the Positive mix; 👍 only to
  thumbs-up/like, ❤️ only to heart, 🔥 only to fire, and so on
  (👎 thumbs down, 😡 angry face, 😎 cool, 🤔 thinking, 🎉
  celebration, 😍 heart eyes). A service named with the emoji
  alone ("Telegram Reactions 👍 | Fast") is that emoji's service
  too, as long as it carries no other reaction emoji — a
  multi-emoji name is a mix, never a single type. If NO service
  exists for the emoji the user named (😮 has none), the bot says
  so honestly — "I don't have a 😮-only service. The closest is
  the Positive mix" — instead of silently selling the mix.
  A bare "thank you 🙏" is thanks, not a reaction order: 🙏 only
  counts as a reaction when the message is about reactions.
- A CORRECTION RE-PICKS THE CARD (owner, 14 Nov 2026): while a
  Confirm card is waiting, "I want only 🙏 reaction" (or any other
  single emoji) re-picks the service for that emoji and shows a
  NEW Confirm card — never the old card unchanged — and the old
  card is dropped so its buttons cannot place the old service.
  The link and quantity come from the pending order.
- WHY THE CORRECTION ONCE FAILED LIVE (14 Nov 2026, check 5b):
  the first fix's helper worked, but it was unreachable live: the
  AI classifier carries the pending order's quantity (10) forward
  from conversation history, so "I want only ❤️ reaction" arrived
  as a change_order WITH quantity=10, and the quantity-change path
  re-issued the same Pray card with "Quantity updated: 10" before
  the correction was ever checked. RULE: a quantity counts as a
  quantity change ONLY when the user typed it in THIS message
  (grounded in the text) — an AI-carried quantity is never a
  change. The correction is checked through that rule in both the
  change_order handler and the inline quantity-change branch.
  The old card message is also DELETED now (its id is stored on
  the pending order when the card is sent), not just popped from
  state — before this fix both cards stayed stacked in the chat.
- A QUANTITY REJECTION NAMES THE SERVICE (owner, 14 Nov 2026):
  "For [service name], quantity must be between X and Y, and a
  multiple of 10." — so a changing limit always makes sense to the
  user. The draft survives a rejection: the next turn ("Ok 50")
  continues the SAME service instead of re-picking a different
  one.
- NEVER sell blacklisted services 5379 and 5834.
- A Confirm card ALWAYS shows service, quantity, link and total before an
  order is placed — EXCEPT when the user explicitly says "order now" /
  "place it now" (urgent), in which case the bot places the order at once
  and sends the full summary in text. (Owner override, 13 Nov 2026.)
- The user's account must be PUBLIC, not private, or the order cannot be
  delivered — remind them of this on every Confirm card.
- Never place an order for a platform that does not match the link.
  Shortened links are fine; warn once on private/expiring links.
- Service names shown to users are SHORT (e.g. "TikTok Video Views").
  Show the FULL long name ONLY when the user entered a service ID.
- Never lose a half-built order on interruption. A draft order is editable
  and cancellable; a placed order shows its status.
- API errors are reported in one plain line. The bot NEVER goes silent:
  if the AI fails, local rules answer instead.

## Money rules (deterministic code, never the AI)
- The AI only listens and talks. All money steps are deterministic code.
- The server computes totals, never the caller or the AI.
- Never approve or credit a deposit without a matching successful Chapa
  payment. Never credit twice. Split payment is NOT supported — deposit
  first. No free trial — suggest the cheapest service to test.
- No invented refund policy: refunds go to Paxyo balance only (never to a
  bank account or mobile money), balance cannot be withdrawn as cash.
  Orders cannot be cancelled or changed once processing has started.

## Answering questions
- PRICE: when asked the price, tell the price right there — per 1000, and
  the total when a quantity is given. NEVER ask for the link first.
  The price is deterministic code, never left to the AI's wording:
  it does NOT depend on which AI classified the message (14 Nov
  2026: the same "how much 1k" got its price from Groq and lost it
  from DeepSeek, because the answer used to depend on the
  classifier's intent). And a reply that asks for the link after a
  price question always carries the price in that same reply.
  PRICE FAST PATH (14 Nov 2026): a price question is answered from
  local detection only, BEFORE the AI classifier runs — the
  classifier is never called for it, so a slow or wrong
  classification can never delay or swallow the price (live retest
  13:35 EAT: the 👍 price arrived 68 seconds late as a separate
  message because the classifier and the bridge ran first, and the
  greeting that arrived in between was the late answer to an
  earlier message, not the price question's reply). When the fast
  path cannot name a service, the flow still runs the classifier
  and the post-classification price branch. A price question that
  names a metric but no platform ("how much are the views?") takes
  its platform from the order being built, never from another
  platform's fastest service.
- HOW-TO / GENERAL QUESTIONS — ANSWER FREELY (owner, 14 Nov 2026,
  course correction): do NOT prepare canned answers for every
  possible question. When a user asks how to do something (how to
  make an Instagram account public, how to copy a link, how to
  find a username), DeepSeek answers FREELY, like a normal AI — no
  deflection, no silence, no canned "I only help with orders"
  reply. A real question always gets an answer, however many turns
  it takes. EXCEPTION: "how do I get the link of a Telegram post?"
  has a deterministic mobile-first answer (see above) — the AI is
  never called for it. (14 Nov 2026 repro: it got no reply because
  the classifier called it off_topic and from the third turn the
  bot only sent the steer line.) New intent "how_to" routes these
  to the AI. Off-topic questions are answered freely first, then
  brought back to ordering with ONE short line ("By the way — what
  would you like to order?"). On-topic how-tos get no steer-back
  line. Only non-question chit-chat is capped (2 turns, then the
  steer).
- DETERMINISTIC PAXYO FACTS ONLY: prices (above), comment likes
  (the video/post link plus either the comment's link or the
  username), private accounts must be public (a private account
  can't receive the order), refunds to Paxyo balance only,
  reseller/contact → t.me/paxyo, paused services. Everything else
  is answered by the AI, never canned.
- SPEED: when asked how long something takes, give a REAL estimated time
  from the service's average time (e.g. "usually starts within 1 minute"),
  and add: the sooner we place the order, the sooner it will be completed
  — let's order now. Never the vague "shown before you confirm" line.
- WEBSITE: when asked about the website, always mention paxyo.et.
- BANNED / SHADOWBANNED: answer YES, it can happen — anybody can
  buy followers, likes or views for your account without your
  permission, and TikTok can shadowban or strike/ban an account
  over fake followers, likes or views. (Owner, 14 Nov 2026 —
  REVERSING the 13 Nov NO answer "you can't be banned without
  your permission", which the 16:42 live retest had just
  confirmed; that check is now outdated.)
- CONTACT: when a customer asks for support, to talk to a human, or
  to contact the owner/admin, answer: contact William at t.me/paxyo.
  Same one line if they ask again. (Owner, 14 Nov 2026 — this
  answers the open contact-username question.)
- RESELLER: when a customer wants to sell Paxyo's services
  themselves / become a reseller, answer: contact William at
  t.me/paxyo — he will set it up. Asking whether PAXYO is a
  reseller ("are you a reseller?") is still the source-question
  deflection, never the contact line.
- NEVER DROP — ONLY Telegram reactions, Telegram views and Facebook
  reactions: when the user ASKS whether those drop / fade /
  disappear, say they never drop. NEVER claim never-drop for any
  other service (TikTok/Instagram/YouTube followers, likes, views,
  Telegram followers/members...) — for those the terms stand
  (results not guaranteed permanent, drops may occur; refunds to
  Paxyo balance only). Never volunteer the claim unprompted.
- PAUSED SERVICES (owner, 14 Nov 2026): cheap premium
  subscriptions (CapCut Pro, Canva Pro, Netflix/Spotify premium,
  ...) and SMS OTP verification are PAUSED. When a user ASKS for
  any of them, say that one is paused right now and we will let
  them know when it's ready. No date, no price, never "available",
  never offer a social-media service instead. Never volunteer or
  advertise them — greetings and help never mention them. A
  message naming a social-media metric ("premium followers",
  "Spotify followers") is an ORDER, not a paused ask; "Telegram
  Premium" is a real Bot Start service, not a paused one.
- TERMS: answer from `paxyo-terms.md` (the real Paxyo Terms &
  Conditions). If the terms don't cover a question, say so and offer
  support. Full terms live on paxyo.et.
- NEVER MORALIZE ABOUT FAKE FOLLOWERS (owner, 14 Nov 2026): Paxyo
  sells followers, likes, views and reactions — the bot NEVER warns
  a user against buying them, NEVER says "avoid buying fake
  followers" or anything like it. The system prompt forbids it, and
  any such line the AI writes anyway is stripped from the reply
  before it is sent. The ban question is NOT a lecture — it gets
  the owner's stated fact only: "Yes — it can happen. Anyone can
  buy followers, likes or views for your account without your
  permission, and TikTok can shadowban or strike/ban an account
  over fake followers, likes or views." (14 Nov 2026, reversing
  the 13 Nov NO answer.)
- PRICE ALWAYS (owner, 14 Nov 2026): a price question NEVER gets a
  free AI reply without a price. Price detection runs before the
  free-answer paths; if a service can be named, the deterministic
  price is shown; if the question names a platform/metric but no
  exact service, the cheapest price for it is shown. Shapes that
  used to miss and fall through: "what's the rate", "how much for
  1000" (no platform named), "how much is it / this / that", and
  Amharic (ዋጋ = price, ስንት = how much) when the translate bridge
  is down and the Ge'ez text reaches the detector unchanged.
- TELEGRAM POST LINK — DETERMINISTIC ANSWER (owner, 14 Nov 2026):
  "how do I get the link of a Telegram post?" is NOT left to the
  AI (it kept getting the steps wrong, and the free answer was
  desktop-flavoured). The bot always gives the same mobile-first
  steps, in English or Amharic: open the channel or group, find
  the post, tap the SHARE arrow next to the post (or press and
  hold the post), then tap "Copy Link". The link looks like
  t.me/channelname/1234. Only public channels/groups have a post
  link — a private one doesn't. No "right-click" as the main way.
- ORDER HISTORY: show ONLY THE LAST 5 ORDERS, one line per order —
  order ID, short service name, quantity, status, total in ETB —
  newest first. No extra fields, no long text, no monospace table.
- INFO ANSWERS NEVER APPEND AN ORDER-STATE LINE unless the user is
  actually mid-order: a draft only counts as "building an order"
  when it has a LINK. A link-less draft left by a price question
  (platform + quantity) is not an order, and naming it on an info
  answer is a stray confusing line.
- "The usual" / "same as usual" / "same like as usual please order 1k
  views": use the last order's service and link, with the new quantity,
  and show the Confirm card. "Same as yesterday but double" = last order
  x2, capped at the service maximum.
- CANCEL: cancelling a Confirm card clears the stored order — a
  fresh order after a cancel starts from scratch and asks for the
  link; the cancelled link/quantity are never auto-shown again.
  The cancelled record clears only when an order is placed, not
  when a fresh link merely appears in a turn that never becomes an
  order.
- A NEW METRIC REPLACES THE OLD DRAFT: a message naming a different
  metric (views after followers) starts a fresh order — the old
  draft's link/quantity are dropped unless the user typed them in
  this message. A clarification of the same metric ("likes for my
  comment" is still likes) does not reset.
- A MESSAGE THAT PASTES A LINK AND NAMES A METRIC WITH AN ORDER VERB
  ("I want TikTok followers for <link>") IS an order, even when the
  AI calls it something else (it once called it a safety question).
  Real questions (price, ban, payment, public account) are still
  answered directly, and a message with no order verb is not an order.
- ORDER NOW: "please order now 200 TikTok views for this video:
  <link>" places the order at once — the 200 right before the metric
  is the quantity. A stray number elsewhere in the message is never
  the quantity.
- "USE THE FASTEST ONE" button: offered when a named service is
  refused AND when the bot asks which metric the user wants.
- AMHARIC METRIC WORDS: እይታዎች = views, ተከታዮች = followers,
  ላይኮች = likes, አስተያየቶች = comments — the message's own metric
  always wins over what the AI guessed from history.
- LINK MISMATCH: a pasted link always wins over the AI's link.
  A TikTok video link for a followers order (or a profile link
  for views/likes) gets ONE plain line explaining it and asking
  for the right link — never a bare "send the link" loop.
- COMMENT LIKES — WHAT THE BOT NEEDS: the link of the video/post
  the comment is on, plus either the link of the comment itself or
  the username. A question about it gets this exact deterministic
  answer; an actual order (a link is pasted) goes through the
  order flow, never the answer.
- BUDGET: "10 birr, how many views?" — answer with the QUANTITY (e.g.
  "about 520 views"), not just the per-1000 price.
- IMPATIENCE: give the real status + average time, never "soon".
- SHORT DELIVERY: check status first, never promise a refill or refund.
- Receipt screenshot mid-order: recheck the deposit, keep the half-built
  order. Ban risk: see the ban answer above. No geo-targeting. No invented
  refund policy. Caption/posting-time tips are fine, briefly.
- Website payment/account problems: redirect to support, the bot can't
  fix the website account.

## Understanding messy messages
- The bot understands typos, misspellings, slang, Amharic and English,
  text and voice. "1k" = 1000. A bare number after "How many?" ("1000
  please") is the quantity.
- It understands REPLIES: when a user replies to one of the bot's
  messages, read the message being replied to — "1000" as a reply to
  "How many?" is the quantity; "yes" as a reply to a Confirm card
  confirms it.
- It REMEMBERS the last chats: last order, last link, last ~10 exchanges.
  Use that memory to answer ("last time you ordered TikTok views").
- Voice messages: transcribe them and SHOW the user what they said
  ("You said: ..."), then handle the text like a typed message. The bot
  answers in text only, never with voice. (Voice-order claims were removed
  from the bot's texts until the voice fix is verified live.)
- Photos: read them (payment screenshot, profile screenshot, error
  screenshot) and understand what the user wants from them.
- GIFs and stickers: always reply, never stay silent. A caption on a
  GIF/sticker is the user's message.
- Video likes vs comment likes vs comments: "likes for my video" = video
  likes; "likes for my comment" = likes ON a comment (#5854); "comments
  on my video" = comments service. Never mix them up.
- EMOJI ARE WORDS: 👍 = thumbs-up reaction, ❤️ = heart reaction,
  🔥 = fire reaction, 😂 = laugh, 😮 = wow, 😢 = sad, 👀 = views.
  "I want 👍 this reaction" orders the 👍 Telegram reaction service;
  a bare "👍" in an order context means the same reaction. 🙏 is
  thanks, never a reaction type.
- A bare emoji is ACKNOWLEDGED as the reaction choice first ("Got
  it — 👍 reactions..."), then the link is asked for — never the
  stock link request on its own. With no order context it still
  gets a natural reply naming the reaction. A bare emoji while
  another order is being built is just an acknowledgement — it
  never changes that order.
- TELEGRAM REACTIONS ARE MATCHED BY EMOJI, not guessed: 👍 buys a
  Thumbs up / Like service, ❤️ a Heart service, 🔥 a Fire service,
  no specific emoji buys the Positive mix — fastest first. Never
  offer a "Bot Start" service for reactions, and never an "Auto …
  10 Future Posts" service for a single post. Say which reaction
  the service is ("Thumbs up 👍"), not just "reactions".
- "DO YOU UNDERSTAND" / "WHAT DO YOU MEAN": when the user asks
  whether the bot understood, or asks about the conversation itself,
  answer FIRST — restate what you understood (service, quantity,
  link if given, what is still missing) or explain what you need
  and why. NEVER ignore the question and repeat the last prompt
  ("Please send the link..."). The draft and any Confirm card stay
  untouched; the order continues after the answer. Keep a quantity
  the user already gave — never ask "how many" again for it.

## Personality
- Talk like a normal person, not a menu. Be smart like ChatGPT for Paxyo.
- FREE CHAT: the user may chat — greetings, small talk, comments,
  feelings, opinions, jokes ("haha nice", "I'm tired today, I need
  views for my new video", "do you think this video will go viral").
  Answer naturally and conversationally — acknowledge what was said,
  comment, answer, ask a follow-up when it fits — instead of always
  snapping back to the next order question ("send the link",
  "how many?"). Acknowledge the human part FIRST — laughter,
  tiredness, excitement ("haha nice, I'm tired today" gets the
  rest wish before any tips or steering). Never lose a half-built order. Pure small talk with
  no order being built still steers back to ordering after 2-3 turns.
- HUMOR: joke lightly sometimes (when an order is placed, a thank-you,
  a greeting), and sometimes answer a GIF/sticker playfully. Keep it
  short and light, never at the user's expense.
- GENERAL KNOWLEDGE: the bot may answer a general (non-Paxyo) question
  briefly — but after 2 or 3 off-topic chats, bring the user back to
  placing an order.
- OFFENSIVE USERS: do NOT stay polite. Push back firmly and bluntly,
  refuse to continue while they talk like that; if it continues, stop
  answering. Never use slurs or abusive language back.
- The bot is warm and helpful to normal users, and steers every
  conversation back to ordering.

## AI providers (the brain is replaceable — the lessons live here)
- DeepSeek is the primary AI (model deepseek-chat, V4.1 Flash) since
  the evening of 13 Nov 2026, OpenCode Zen second (model
  deepseek-v4.1-flash-free — free tier, email-only signup, no card,
  10 requests/minute; the free roster rotates, so the model is a
  ZEN_MODEL env var; a Zen failure falls through to Qwen),
  Qwen-Turbo third (model qwen-turbo,
  $0.05/$0.20 per 1M tokens, ~3x cheaper than DeepSeek), Mistral
  fourth (model mistral-small-latest — pay-as-you-go, owner approved
  14 Nov 2026: $0.10/$0.30 per 1M tokens, PAYG needs $10 prepaid
  credits first, no monthly minimum; a Mistral failure falls through to Groq), Groq
  fifth, OpenAI sixth, Gemini seventh, Kilo eighth (model
  kilo-auto/free —
  the router picks a currently-free model automatically; $0, no key,
  no signup, no Authorization header, 200 requests/hour per IP —
  it only runs after Gemini failed, so it never burns its per-IP
  hourly cap; a Kilo failure falls through to OpenRouter), OpenRouter
  ninth (model openrouter/free — the router picks a currently-free
  model automatically; free :free models cost $0/token, 50
  requests/day, 1,000/day after a one-time $10 credit purchase,
  owner's choice 14 Nov 2026 — it only runs after Kilo failed, so
  it never burns its daily cap), GLM last resort (model
  glm-4.7-flash,
  FREE but rate-limited ~1 request/second and slow — only when every
  other provider failed). Switching providers loses no data: all bot
  data lives in Paxyo's database and this repo, not in the AI
  provider. If all AI fails, local rules answer — the bot never goes
  silent and never forgets these lessons, because the lessons are in
  this repo (bot.py + this file), NOT in any AI provider. No provider
  keeps any memory of the bot between chats.
- LANGUAGE RULE (owner, 14 Nov 2026): the bot replies in the SAME
  language the user is speaking in the CURRENT message — English
  in, English out; Amharic in, Amharic out; and the same for
  Tigrinya and Oromo (Afaan Oromo). NEVER the previous turn's
  language. The reply language is decided from the current
  message's words alone (detect_language): Ge'ez script is
  Amharic or Tigrinya (vocabulary decides, Amharic on a tie);
  Latin script with an Oromo word is Oromo; other Latin text is
  English. The Telegram account language is only the fallback
  when the message carries no language signal (a bare number, an
  emoji) — it must never override the words typed.
- Translate-bridge (owner, 13 Nov 2026; Oromo and Tigrinya added
  14 Nov 2026): an Amharic, Tigrinya or Oromo message is translated
  to English by Gemini first, the flow runs in English, and prose
  replies are translated back to the user's language before
  sending. English never touches the bridge. If a translation fails,
  the original text is used — never silent, never a dropped order.
  Confirm cards, buttons, prices, links and service IDs are never
  translated. The bridge does not break the local Amharic metric
  words or Amharic reply templates — those still apply when
  translation fails.
  STUCK-LANGUAGE BUG (live, 14 Nov 2026): the old bridge flag was
  set on an Amharic turn and never cleared — and because PTB
  processes updates sequentially in one task (max_concurrent_updates
  = 1, the default), it leaked into every later English turn, so
  "I'm tired" and "I said do you speak English" both got Amharic
  replies. The flag is now the per-turn _BRIDGE_LANG, reset at the
  start of every turn in handle_order_text. The same sequential
  processing is also why slow turns delay later replies: each
  update waits for the one before it, so a price question that
  waits on the AI arrives late — see PRICE FAST PATH above.
  Oromo and Tigrinya have first-pass translations for the short
  deterministic lines (greeting, contact/reseller, paused
  services, never-drop); anything without one falls back to
  English in t() and the bridge translates it at send time.
  Those first-pass translations are unreviewed by a native
  speaker — fix them if a user reports a wrong one, do not guess
  further translations; the bridge is the fallback.
- Groq free tier: 1,000 requests/day, 200,000 tokens/day. The TOKEN limit
  binds first. Paid Groq (Developer, pay-as-you-go) is $0.15/$0.60 per
  1M tokens, no monthly fee, first bill at $1 usage. (Note: on 13 Nov
  2026 Groq had temporarily disabled Developer upgrades — retry later.)
- PROMPT SHRINK (owner approved, 14 Nov 2026): the classifier prompt
  used to send the whole SYSTEM_PROMPT (~2,460 tokens) plus up to 10
  turns of history — about ~2,700-2,900 tokens per chat. CORRECTION
  to the old note here: the service catalogue was NEVER in the AI
  prompt; the bulk was the classifier instructions and the history.
  The shrink, in bot.py: SYSTEM_PROMPT compacted (11,511 chars /
  ~2,460 tokens -> 7,357 chars / ~1,567 tokens — same 35 intents,
  same JSON shape, same disambiguation rules, just shorter lines);
  history in the prompt is the last 3 turns, not 10; and when a
  message names BOTH a platform and a metric, the prompt also
  carries the matching services only (build_classify_prompt,
  detect_platform_metric, services_for_prompt — deterministic
  keywords/regex, never the AI; at most 30, fastest first, short
  name + id + ETB/1000 + average time; reactions limited to the
  emoji's single-post family). When platform or metric cannot be
  read, there is NO services section — the full catalogue is never
  pasted into a prompt (7,176 services would be ~100k tokens) and
  the deterministic code (pick_services, price) still works from
  the full catalogue, exactly as before. Measured after the shrink:
  ~1,800 tokens/chat for non-order turns, ~2,200 for order turns
  (was ~2,900) — roughly 1.5x more chats per token budget, NOT the
  5x once estimated from the wrong catalogue premise. Groq free
  covers ~110 chats/day (was ~74); DeepSeek $2 lasts ~1.5x longer.
  Prices, order placement, the deterministic fastest-pick, the
  deterministic price fix and all guardrails are untouched by the
  shrink. Do NOT re-expand SYSTEM_PROMPT with long examples — the
  compact form is load-bearing for cost and speed; a live retest
  after any prompt edit is mandatory because the offline tests mock
  the AI and cannot catch classification drift.
- If DeepSeek fails, the bot falls back to Zen, then Qwen, then Mistral, then
  Groq, then OpenAI, then Gemini, then Kilo, then OpenRouter, then GLM, then to local rules. It gets less
  clever at understanding messy language, but it does NOT lose any
  lesson.

## Admin facts the bot relies on
- Bot API on paxyo.et: services, balance, create order, order status,
  users, orders list, recurring, deposits. Secured by X-Bot-Secret.
- New chatters get a Paxyo account auto-created on /start — they appear
  in the admin panel Users list automatically.
- Recurring orders: drip-feed, minimum interval 30 minutes.
- Deposits by chat: Chapa direct charge / USSD push (Telebirr/CBE).
  Chapa direct charge is NOT enabled on Paxyo's Chapa account yet —
  ask Chapa to enable it, or use the checkout-link fallback.
- M-Pesa deposit-by-chat does NOT work yet — needs a new payment path.
