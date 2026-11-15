#!/usr/bin/env python3
"""Generate golden-dataset 07-admin-english.md (15 Nov 2026, William
21:19 EAT — same as the user-bot training datasets, but for the
admin chat bot @atlasdeskadmin_bot, ALL in English).

Exactly 1,000 realistic questions/messages William (the admin)
would send to the admin bot, in plain words, with typos and
voice-to-text style like real messages. Covers every admin
capability: money and profit, deposits, orders, users, services,
broadcasts, promo codes, disputes, win-backs, loyalty bonuses,
satisfaction, fraud watch, uptime / provider status, confused
chats, morning and weekly reports, settings (ticker, price
multiplier), resellers, and general admin chat.

The "Bot should" lines are the spec. Routing rules they follow:
- Money totals, order/user counts, deposits totals and the top
  service come from /admin/stats (deterministic parsing).
- Net-profit questions are answered from the stats record's
  net_profit_etb figure; when it is missing the bot says so.
- Most-profitable services, satisfaction, weekly and morning
  reports, deposits by method, open disputes and quiet users are
  plain-language routes to the matching report (same as the
  /profitable, /satisfaction, /weekly, /deposits_by_method,
  /disputes, /morning and /winbacks commands).
- One order's status is looked up by its number; listing orders,
  stuck orders or users is NOT possible in chat — the bot asks
  for the order number instead.
- Broadcasts, ticker changes, refunds and promo codes show a
  preview and wait for Confirm — never on one message.
- Loyalty bonuses, fraud flags, confused chats, resellers, a
  user's balance and the provider balance cannot be looked up in
  chat — the bot says so honestly and never invents a figure.
  The price multiplier cannot be changed in chat either (only
  the ticker); the bot points to Settings in the admin panel.
- Never reveal the provider name or buy prices.

Deterministic: same seed -> same file. Run:
    python3 generate_admin_questions.py
It writes 07-admin-english.md next to itself and prints the
count. The file must have exactly 1,000 "User:" lines, 0
duplicates, and no provider names.
"""

import random
import re

SEED = 20261115

# --- slot pools -------------------------------------------------------
WIN = ["today", "this week", "last 7 days", "this month",
       "last month", "yesterday"]
N = [3, 7, 14, 30]
OID = [1841, 1848, 1849, 1850, 1852, 1900, 1901, 1905]
SID = [6139, 5535, 1665, 1104, 1861, 6537]
CODE = ["PAXYO20", "WELCOME10", "FLAT100", "SAVE50", "PAXYO50",
        "NEWYEAR"]
PCT = [10, 20, 25, 50]
ETB = [50, 100, 200, 500, 1000, 2000, 5000]
USER = ["alex", "sam", "daniel", "abebe", "selam", "henok",
        "meron", "yonas"]
DID = [1, 2, 3, 5, 7, 9]
METHOD = ["Telebirr", "CBE", "M-Pesa", "CBE Birr"]
SVC = ["TikTok views", "TikTok followers", "Telegram post views",
       "YouTube views", "Instagram followers"]
MSG = ["New offer this week!", "Prices dropped, order now!",
       "Weekend deal is live", "Order now and save 10%",
       "New services added"]
DATE = ["2026-12-31", "2026-11-30", "2027-01-31"]
CAP = [100, 200, 500]

TYPO_MAP = {
    "profit": "profite", "revenue": "revenu",
    "deposit": "deposite", "deposits": "deposites",
    "broadcast": "broadcst", "refund": "refuned",
    "promo": "prom", "dispute": "disput",
    "satisfaction": "satisfacion", "weekly": "wekly",
    "morning": "mornig", "users": "usrs", "orders": "ordrs",
    "service": "servise", "ticker": "tickr",
    "winback": "winbak", "loyalty": "loyalti",
    "fraud": "fruad", "report": "reprot",
    "balance": "balence", "message": "mesage",
    "change": "chnage", "money": "mony", "made": "mad",
    "today": "tody", "earned": "ernd",
    "customers": "custmers", "please": "pls",
    "never": "nevr",
}


def typo(text, rng):
    """One small typo / voice-to-text flavour, or the text unchanged."""
    roll = rng.random()
    if roll < 0.06:
        # voice-to-text: lowercased, no punctuation, "u" for "you".
        out = text.lower().rstrip("?.!").replace("you", "u")
        return out
    if roll < 0.18:
        for good, bad in TYPO_MAP.items():
            if re.search(r"\b" + good + r"\b", text, re.IGNORECASE):
                return re.sub(
                    r"\b" + good + r"\b", bad, text, count=1,
                    flags=re.IGNORECASE,
                )
    return text


def slots_for(rng, keys):
    """One value per slot key, drawn from the pools."""
    pools = {
        "win": WIN, "n": N, "oid": OID, "sid": SID, "code": CODE,
        "pct": PCT, "etb": ETB, "user": USER, "did": DID,
        "method": METHOD, "svc": SVC, "msg": MSG, "date": DATE,
        "cap": CAP,
    }
    return {key: rng.choice(pools[key]) for key in keys}


def fill(template, values):
    try:
        return template.format(**values)
    except KeyError:
        return template


def build_section(section, rng):
    """Emit the section's items."""
    templates = section["en"]
    count = section["count"]
    should = section["should"]
    if isinstance(should, str):
        should = [should]
    items = []
    seen = set()
    guard = 0
    idx = 0
    while len(items) < count and guard < count * 60:
        guard += 1
        template = templates[idx % len(templates)]
        idx += 1
        keys = re.findall(r"\{(\w+)\}", template)
        values = slots_for(rng, keys)
        text = fill(template, values)
        text = typo(text, rng)
        if text in seen:
            continue
        seen.add(text)
        items.append((text, should[len(items) % len(should)]))
    if len(items) < count:
        raise SystemExit(
            f"section {section['id']}: only {len(items)}/{count} "
            f"unique items — add more templates"
        )
    return items


def render(path, title, intro, sections, rng):
    lines = [title, "", intro, ""]
    total = 0
    for section in sections:
        items = build_section(section, rng)
        total += len(items)
        lines.append(f"## {section['title']}")
        lines.append("")
        for i, (text, should) in enumerate(items, 1):
            lines.append(f"{i}. User: {text}")
            lines.append(f"   Bot should: {should}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return total
SECTIONS = [
    {
        "id": "money", "title": "Money and profit", "count": 100,
        "en": [
            "how much did we make {win}",
            "how much money did we make {win}",
            "what is our revenue {win}",
            "how much did we earn {win}",
            "what did we earn {win}",
            "how much profit did we make {win}",
            "what is our net profit {win}",
            "what is our profit {win}",
            "how much money came in {win}",
            "what are our earnings {win}",
            "how much did we make in the last {n} days",
            "how much money did we make in the last {n} days",
            "total revenue {win}",
            "how much revenue {win}",
            "what was our revenue {win}",
            "how much profit {win}",
            "show me revenue {win}",
            "how much did we make {win}?",
            "how much money have we made {win}",
            "what is the revenue {win}",
            "how much have we earned {win}",
            "profit {win}",
            "what is our profit margin {win}",
            "earnings {win}",
            "how much money did we earn {win}",
            "how much net profit {win}",
        ],
        "should": "Answer from /admin/stats with the revenue (or the net profit for profit questions) for the window; for yesterday on its own, say yesterday is not available yet and suggest today or the last 7 days; never invent a figure.",
    },
    {
        "id": "deposits", "title": "Deposits", "count": 85,
        "en": [
            "how many deposits did we get {win}",
            "how much did we get in deposits {win}",
            "total deposits {win}",
            "how many deposits {win}",
            "how many deposits did we get in the last {n} days",
            "deposits by method",
            "show deposits by method",
            "show me deposits by method",
            "deposits by payment method",
            "how much came in by {method} {win}",
            "how much came by {method} {win}",
            "which payment method brings the most",
            "which payment method brings the most money",
            "deposit breakdown",
            "show me the deposit breakdown",
            "any big deposits {win}",
            "any big deposits",
            "deposits over {etb} ETB {win}",
            "are there pending deposits",
            "how many deposits are pending",
            "show pending deposits",
            "any deposits over {etb} ETB",
        ],
        "should": "Deposit totals come from /admin/stats; by-method questions show the deposits_by_method report; big or pending deposits cannot be listed in chat — say so honestly and point to the Deposits list in the admin panel.",
    },
    {
        "id": "orders", "title": "Orders", "count": 85,
        "en": [
            "how many orders did we get {win}",
            "how many orders {win}",
            "how many orders are completed {win}",
            "how many orders did we get in the last {n} days",
            "what is the status of order #{oid}",
            "check order #{oid}",
            "order #{oid} status",
            "where is order #{oid}",
            "is order #{oid} done",
            "is order #{oid} finished",
            "what happened to order #{oid}",
            "list orders {win}",
            "show me the orders {win}",
            "show me orders {win}",
            "any stuck orders",
            "show me stuck orders",
            "are there stuck orders",
            "cancel order #{oid}",
            "refund order #{oid}",
            "refund order {oid}",
            "refund #{oid}",
        ],
        "should": "Order counts come from /admin/stats; one order's status is looked up by its number; listing orders or stuck orders is not possible in chat — ask for the order number; cancelling is not done from chat — offer the refund flow instead; refunds show a preview and wait for Confirm.",
    },
    {
        "id": "users", "title": "Users", "count": 80,
        "en": [
            "how many users {win}",
            "how many new users {win}",
            "how many users joined {win}",
            "how many users do we have",
            "how many new users joined {win}",
            "how many users are there",
            "who are our top customers",
            "who orders the most",
            "who spends the most",
            "what is @{user}'s balance",
            "how much has @{user} spent",
            "how much did @{user} spend",
            "how many users never deposited",
            "how many users deposited",
            "how many users never deposited {win}",
            "show me top customers",
        ],
        "should": "User counts come from /admin/stats (new users for the window); a single user's balance, top customers, and never-deposited or deposited user counts cannot be looked up in chat — say so honestly; for never-deposited users, offer a broadcast, whose preview shows the count.",
    },
    {
        "id": "services", "title": "Services", "count": 65,
        "en": [
            "what is our top service {win}",
            "most ordered service {win}",
            "best selling service {win}",
            "most popular service {win}",
            "what is the top service {win}",
            "show me the most profitable services",
            "which services make the most money",
            "what services earn the most",
            "which services are the most profitable",
            "show me the top 10 profitable services",
            "what is the price of service {sid}",
            "how much is service {sid}",
            "how much does service {sid} cost",
            "price of service {sid}",
        ],
        "should": "Top service comes from /admin/stats; most-profitable questions show the profitable-services list; prices are not quoted in chat — point to the Services list in the admin panel.",
    },
    {
        "id": "broadcasts", "title": "Broadcasts", "count": 80,
        "en": [
            "send this to users who never deposited: {msg}",
            "send this to users who deposited before: {msg}",
            "send this to users who bought service {sid}: {msg}",
            "send this to users who bought {svc}: {msg}",
            "send this to all users: {msg}",
            "send this to everyone: {msg}",
            "broadcast to all users: {msg}",
            "broadcast to users who never deposited: {msg}",
            "message all users saying {msg}",
            "message everyone saying {msg}",
            "tell all users: {msg}",
            "send to everyone: {msg}",
            "send this to users who never deposited",
            "send a message to all users",
            "broadcast {msg}",
            "send this to users who bought service {sid}",
            "send this to users who ordered service {sid}: {msg}",
            "message users who never deposited: {msg}",
        ],
        "should": "Show the audience count and the exact message, wait for Confirm — never send on one message; when no message is given, ask what it should say; when no audience is given, ask who it should go to.",
    },
    {
        "id": "promo", "title": "Promo codes", "count": 80,
        "en": [
            "create promo code {code} {pct}%",
            "create promo code {code} {pct} percent",
            "make a promo code {code} {pct}%",
            "make promo code {code} {pct}%",
            "new promo code {code} {pct}%",
            "create promo code {code} {etb} ETB",
            "create promo code {code} {pct}% expires {date}",
            "create promo code {code} {pct}% max {n} uses",
            "create promo code {code} {pct}% expires {date} max {n} uses",
            "list promo codes",
            "show promo codes",
            "show me the promo codes",
            "list all promo codes",
            "turn off promo code {code}",
            "turn off {code}",
            "disable promo code {code}",
            "disable {code}",
            "deactivate promo code {code}",
        ],
        "should": "Creating shows a preview and waits for Confirm; listing shows every code; turning off shows a preview and waits for Confirm; bad codes are refused before any Confirm.",
    },
    {
        "id": "disputes", "title": "Disputes", "count": 55,
        "en": [
            "any open disputes",
            "show disputes",
            "list disputes",
            "show me the disputes",
            "how many disputes are open",
            "are there any disputes",
            "show me open disputes",
            "show me all disputes",
            "any disputes open",
            "close dispute #{did}",
            "close dispute {did}",
            "resolve dispute #{did}",
            "resolve dispute {did}",
        ],
        "should": "Listing shows the open disputes; closing shows the dispute and waits for Confirm; a wrong id says there is no open dispute with that number.",
    },
    {
        "id": "winbacks", "title": "Win-backs", "count": 45,
        "en": [
            "who went quiet",
            "show me quiet users",
            "how many users went quiet",
            "win back quiet users",
            "message users who went quiet",
            "who hasn't ordered in two weeks",
            "users who went quiet",
            "show me who went quiet",
            "winback quiet users",
            "who went quiet this month",
            "who has gone quiet",
            "show me the quiet users",
            "list quiet users",
            "how many quiet users are there",
            "any quiet users",
            "message the quiet users",
            "send a winback to quiet users",
            "who hasn't ordered lately",
            "who hasn't ordered in a while",
            "users with no orders in 14 days",
            "who has not ordered for two weeks",
            "find users who went quiet",
            "show me users who went quiet",
            "win back the quiet ones",
            "anyone gone quiet",
            "who stopped ordering",
            "users who stopped ordering",
            "show me who stopped ordering",
            "who went quiet {win}",
            "how many users went quiet {win}",
        ],
        "should": "Show the count of quiet users first, wait for Confirm, then send one personal message each; nobody is messaged twice in 30 days.",
    },
    {
        "id": "loyalty", "title": "Loyalty bonuses", "count": 35,
        "en": [
            "who got a loyalty bonus",
            "any loyalty bonuses {win}",
            "did anyone get a bonus {win}",
            "how much bonus did we give {win}",
            "who reached 10 orders",
            "who got the 10 percent bonus",
            "any bonuses given {win}",
            "who got a bonus",
        ],
        "should": "Loyalty bonuses cannot be looked up in chat — say so honestly; the bonus is credited automatically after 10 completed orders and the admin is told when it happens.",
    },
    {
        "id": "satisfaction", "title": "Satisfaction", "count": 40,
        "en": [
            "how satisfied are our users",
            "what is our satisfaction score",
            "how are users rating us",
            "show me the feedback score",
            "how many thumbs up did we get",
            "what do users think of us",
            "show satisfaction",
            "user feedback score",
            "how happy are our users",
            "what is the feedback score",
            "what is the satisfaction",
            "show me satisfaction",
            "satisfaction score please",
            "how do users rate us",
            "what is our rating",
            "user ratings",
            "how are the ratings",
            "show me user ratings",
            "what is the thumbs up rate",
            "how many thumbs down did we get",
            "thumbs up vs thumbs down",
            "feedback summary",
            "show me the feedback",
            "how is our feedback",
            "are users happy",
            "are our users happy",
            "what do users say about us",
            "user reviews",
            "how do customers rate us",
            "customer feedback",
        ],
        "should": "Show the thumbs-up/thumbs-down score from the satisfaction endpoint; when it is not connected yet, say so honestly.",
    },
    {
        "id": "fraud", "title": "Fraud watch", "count": 35,
        "en": [
            "any fraud flags",
            "show me fraud alerts",
            "did anyone try to cheat",
            "any suspicious users",
            "fraud watch",
            "any fraud today",
            "any fraud {win}",
            "show me the fraud flags",
            "any fraud alerts today",
            "show fraud alerts",
            "any suspicious activity",
            "anyone cheating",
            "did anyone cheat",
            "fraud reports",
            "show me suspicious users",
            "any cheaters",
            "suspicious orders",
            "anyone gaming the system",
            "check for fraud",
            "any fraud attempts",
            "any scam",
            "any scammers",
            "is anyone abusing the system",
            "abuse reports",
        ],
        "should": "Fraud flags are watched by the order bot and sent to the admin when one appears — there is no list to ask for in chat; never invent a flag.",
    },
    {
        "id": "uptime", "title": "Uptime and provider status", "count": 35,
        "en": [
            "is the bot up",
            "is everything working",
            "is the provider up",
            "are we online",
            "did the bot go down",
            "is paxyo.et up",
            "check the provider balance",
            "how much money is left with the provider",
            "is the website up",
            "is the bot working",
            "is the system up",
            "is paxyo up",
            "is the admin bot working",
            "is the order bot up",
            "is the order bot working",
            "did anything go down",
            "is the server up",
            "are we down",
            "is everything ok",
            "is everything okay",
            "status check",
            "how is the provider doing",
            "is the provider balance ok",
            "is the provider reachable",
            "is the bot online",
            "is the bot down",
            "is the website working",
            "is the website down",
            "is the panel up",
            "is the admin panel up",
            "is the panel working",
            "is the bot alive",
            "is the bot responding",
            "is the bot awake",
        ],
        "should": "Answer briefly — you are up because you are replying; for the provider or the website, say honestly there is no live check in chat and never invent a status; the provider balance alert comes to you when it drops below $3.",
    },
    {
        "id": "confused", "title": "Confused chats", "count": 30,
        "en": [
            "any confused chats",
            "show me confused chats",
            "what did users not understand",
            "which chats confused the bot",
            "confused chats today",
            "show me the confused chats",
            "show confused",
            "any confused users",
            "what confused users",
            "list confused chats",
            "show me the confused ones",
            "which users were confused",
            "confused messages",
            "what are users confused about",
            "show confusion",
            "any confusion today",
            "confusion report",
            "which chats were confusing",
            "what did the bot not understand",
            "show me what users did not understand",
            "users the bot did not understand",
            "any chats the bot failed",
            "failed chats",
            "any confused chats {win}",
            "show me confused chats {win}",
        ],
        "should": "Confused chats live in the Confused chats section of the admin panel — this bot can't list them in chat; never invent one.",
    },
    {
        "id": "reports", "title": "Reports", "count": 55,
        "en": [
            "morning report",
            "show me the morning report",
            "yesterday's money report",
            "yesterday's numbers",
            "yesterday's report",
            "weekly report",
            "show me the weekly report",
            "this week vs last week",
            "how are we doing",
            "daily summary",
            "sales report",
            "give me a report",
            "send me the morning report",
            "morning money report",
            "show me yesterday's numbers",
            "this week's report",
            "last week's report",
            "weekly summary",
            "show me the weekly summary",
            "this week report",
            "give me the morning report",
            "give me the weekly report",
            "show me today's numbers",
            "today's numbers",
            "send me the weekly report",
            "show me the morning money report",
            "yesterday's sales report",
            "show me the morning money",
            "yesterday's money",
            "weekly growth report",
            "show me weekly growth",
            "this week's numbers",
            "last week's numbers",
            "give me today's numbers",
        ],
        "should": "Morning and weekly reports come from their reports; 'how are we doing', the daily summary and the sales report come from /admin/stats with every figure on one line each; a bare 'give me a report' asks which one — morning, weekly, or today's numbers.",
    },
    {
        "id": "settings", "title": "Settings", "count": 40,
        "en": [
            "change ticker to {msg}",
            "set ticker to {msg}",
            "update the ticker to {msg}",
            "change the ticker display to {msg}",
            "change the ticker text to {msg}",
            "change the announcement to {msg}",
            "change the price multiplier to {cap}",
            "what is the price multiplier",
            "change the selling price multiplier",
            "set the price multiplier to {cap}",
            "set ticker to {msg}",
        ],
        "should": "Ticker changes show a preview and wait for Confirm; other settings cannot be changed in chat — say so honestly and point to Settings in the admin panel.",
    },
    {
        "id": "resellers", "title": "Resellers", "count": 20,
        "en": [
            "how many resellers do we have",
            "list resellers",
            "who are our resellers",
            "how much did resellers sell {win}",
            "add a reseller",
            "show me resellers",
            "how many resellers",
            "reseller list",
            "show resellers",
            "who are the resellers",
            "how are resellers doing",
            "reseller sales",
            "reseller report",
            "list all resellers",
            "show me all resellers",
            "any new resellers",
            "how many resellers {win}",
        ],
        "should": "Resellers are managed in the admin panel — this bot can't list them in chat; never invent a reseller.",
    },
    {
        "id": "general", "title": "General admin chat", "count": 35,
        "en": [
            "hi",
            "hello",
            "good morning",
            "good evening",
            "good afternoon",
            "what can you do",
            "help",
            "what are your commands",
            "thank you",
            "thanks",
            "good job",
            "who are you",
            "what can you do for me",
            "hey",
            "good day",
            "morning",
            "evening",
            "what can this bot do",
            "show me what you can do",
            "list your commands",
            "show commands",
            "thanks a lot",
            "thank you very much",
            "great job",
            "well done",
            "who made you",
            "hi there",
            "hello there",
            "hey there",
            "thank you so much",
            "awesome",
            "perfect",
        ],
        "should": "Greetings and thanks get a brief friendly reply; 'help' or 'what can you do' lists the capabilities; 'who are you' says you are the Paxyo admin bot.",
    },
]

TITLE = "# Golden dataset — Part 7: Admin questions (English)"

INTRO = (
    "Realistic questions William sends to the admin chat bot "
    "@atlasdeskadmin_bot, with the correct bot behaviour for each. "
    "Rules the \"Bot should\" lines follow: live figures come from "
    "/admin/stats or the matching report endpoint, never invented; "
    "every change (broadcast, ticker, refund, promo code, closing "
    "a dispute) shows a preview and waits for Confirm; what the bot "
    "cannot do in chat (list orders or users, a user's balance, "
    "loyalty bonuses, fraud flags, confused chats, resellers, the "
    "provider balance) it says honestly and never invents; never "
    "reveal the provider name or buy prices."
)


def main():
    rng = random.Random(SEED)
    total = render(
        "07-admin-english.md", TITLE, INTRO, SECTIONS, rng
    )
    want = sum(s["count"] for s in SECTIONS)
    print(f"wrote 07-admin-english.md: {total} items (want {want})")
    assert total == 1000, f"total {total} != 1000"
    assert want == 1000, f"sections sum {want} != 1000"


if __name__ == "__main__":
    main()
