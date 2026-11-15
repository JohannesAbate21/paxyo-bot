#!/usr/bin/env python3
"""Generate golden-dataset 05-customizations-english.md and
06-customizations-amharic.md (15 Nov 2026, William 21:10 EAT).

~1,000 realistic customer messages about the Paxyo order
customizations — setting one, changing one, asking about current
settings, turning one off, setting two at once — in plain words,
with typos and voice-to-text style, in English and Amharic.

Covers all 40 customization options. Most examples are for the
APPROVED ones (4, 6, 8, 11-20, 21, 24, 25, 26, 27, 30, 31-40);
the NOT-approved ones (1, 2, 3, 5, 7, 9, 10, 22, 23, 28, 29) get
a few each, and their "Bot should" says the normal way applies —
the bot must never pretend to set something William did not
approve. Three approved options (30 watch-my-post, 33 wait for a
lower price, 35 monthly report) are remembered by the bot but
their doing part is not switched on yet — their "Bot should"
says so honestly, the same pattern as drip-feed before its
server file landed.

Deterministic: same seed -> same files. Run:
    python3 generate_customizations.py
It writes the two .md files next to itself and prints the counts.
The "Bot should" lines are the spec: setting one, changing one,
asking, turning off — in the user's language, one short line.
"""

import random
import re

SEED = 20261115

# --- slot pools -------------------------------------------------------
P = ["tiktok", "instagram", "telegram", "youtube", "facebook"]
M = ["views", "followers", "likes", "comments", "subscribers", "members"]
Q = [500, 1000, 2000, 5000, 10000]
E = [2, 5, 10, 20, 50, 100]
H = [1, 2, 3, 6, 12]
D = [1, 2, 3, 7]
SID = [5535, 6001, 6139, 7000, 7501]
CAP = [50, 100]
MONEY = [100, 500, 1000, 2000]
LINK = [
    "https://tiktok.com/@x/video/1",
    "https://instagram.com/p/x",
    "https://t.me/channelname/123",
]
WEEKDAY = ["monday", "tuesday", "wednesday", "thursday", "friday"]

AP = {
    "tiktok": "ቲክቶክ", "instagram": "ኢንስታግራም",
    "telegram": "ቴሌግራም", "youtube": "ዩቲዩብ",
    "facebook": "ፌስቡክ",
}
AM = {
    "views": "እይታዎች", "followers": "ተከታዮች", "likes": "ላይኮች",
    "comments": "አስተያየቶች", "subscribers": "ሰብስክራይበርዎች",
    "members": "አባላት",
}
AM_WEEKDAY = {
    "monday": "ሰኞ", "tuesday": "ማክሰኞ", "wednesday": "ረቡዕ",
    "thursday": "ሐሙስ", "friday": "ዓርብ",
}

TYPO_MAP = {
    "cheapest": "cheepest", "fastest": "fastist", "views": "veiw",
    "followers": "folowers", "always": "alwasy", "message": "mesage",
    "service": "servise", "order": "oder", "please": "pls",
    "never": "nevr", "repeat": "repet", "balance": "balence",
    "refill": "refil", "confirm": "confrm", "change": "chnage",
    "before": "befor", "small": "smal", "deliver": "delivre",
    "usually": "usualy", "quantity": "quantitiy",
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
        "p": P, "m": M, "q": Q, "e": E, "h": H, "d": D,
        "sid": SID, "cap": CAP, "money": MONEY, "link": LINK,
        "day": WEEKDAY,
    }
    out = {}
    # Amharic slots pick their English base first.
    if "ap" in keys and "p" not in keys:
        out["p"] = rng.choice(P)
    if "am" in keys and "m" not in keys:
        out["m"] = rng.choice(M)
    if "aday" in keys and "day" not in keys:
        out["day"] = rng.choice(WEEKDAY)
    for key in keys:
        if key in ("ap", "am", "aday"):
            continue
        out[key] = rng.choice(pools[key])
    # Amharic renderings ride along when a platform/metric is picked.
    if "p" in out:
        out["ap"] = AP[out["p"]]
    if "m" in out:
        out["am"] = AM[out["m"]]
    if "day" in out:
        out["aday"] = AM_WEEKDAY[out["day"]]
    return out


def fill(template, values):
    try:
        return template.format(**values)
    except KeyError:
        return template


def build_section(section, lang, rng):
    """Emit the section's items for one language."""
    templates = section["en"] if lang == "en" else section["am"]
    count = section["count_en"] if lang == "en" else section["count_am"]
    should = section["should_en"] if lang == "en" else section["should_am"]
    if isinstance(should, str):
        should = [should]
    items = []
    seen = set()
    guard = 0
    idx = 0
    while len(items) < count and guard < count * 40:
        guard += 1
        template = templates[idx % len(templates)]
        idx += 1
        keys = re.findall(r"\{(\w+)\}", template)
        values = slots_for(rng, keys)
        text = fill(template, values)
        if lang == "en":
            text = typo(text, rng)
        if text in seen:
            continue
        seen.add(text)
        items.append((text, should[(len(items)) % len(should)]))
    if len(items) < count:
        raise SystemExit(
            f"section {section['id']}: only {len(items)}/{count} "
            f"unique {lang} items — add more templates"
        )
    return items


def render(path, title, intro, sections, lang, rng):
    lines = [title, "", intro, ""]
    total = 0
    for section in sections:
        items = build_section(section, lang, rng)
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
        "id": "ask", "title": "Asking about current settings",
        "count_en": 25, "count_am": 15,
        "en": [
            "what are my settings", "show me my settings",
            "what did i set", "what have i set",
            "am i on cheapest first?", "am i on fastest first?",
            "what is my usual quantity",
            "do i have quiet hours on?",
            "what are my quiet hours", "when are my quiet hours",
            "what is my price limit",
            "did i set a default link",
            "what link do you use for me",
            "what is my spending limit",
            "which services do you never use for me",
            "what language am i locked to",
            "show my preferences", "list my settings",
            "what is my balance alert",
            "do i have a weekly limit",
        ],
        "am": [
            "ቅንብሮቼ ምንድናቸው? [What are my settings?]",
            "ቅንብሮቼን አሳይኝ [Show me my settings]",
            "ምን አዘጋጅቻለሁ? [What have I set?]",
            "ርካሹን እየተጠቀምኩ ነው? [Am I using the cheapest?]",
            "ፈጣኑን እየተጠቀምኩ ነው? [Am I using the fastest?]",
            "የእኔ የተለመደው መጠን ስንት ነው? [What is my usual quantity?]",
            "የጸጥታ ሰዓቴ ስንት ነው? [What are my quiet hours?]",
            "የዋጋ ገደቤ ስንት ነው? [What is my price limit?]",
            "ሊንኬ ምንድን ነው? [What is my link?]",
            "የሳምንቱ ገደቤ አለኝ? [Do I have a weekly limit?]",
            "የእኔ ቅንብሮች ምንድናቸው? [What are my settings?]",
            "ቅንብሮቼን ንገረኝ [Tell me my settings]",
            "ምን እንደቀየርኩ አሳይኝ [Show me what I changed]",
            "የእኔ ምርጫዎች ምንድናቸው? [What are my choices?]",
            "ፈጣን እየተጠቀምኩ ነው? [Am I using fast?]",
        ],
        "should_en": "List the settings they set, one short line each; when nothing is set, say so and name the normal way.",
        "should_am": "Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.",
    },
    {
        "id": "two", "title": "Setting two at once",
        "count_en": 20, "count_am": 10,
        "en": [
            "cheapest first and don't message me at night",
            "ask me first and use the fastest",
            "never slower than {h} hour and refill only",
            "cheapest first and top up the missing part",
            "quiet hours 10pm to 7am and cheapest first",
            "my link is {link} and i usually order {q} {p} {m}",
            "cheapest first and place small orders without asking",
            "use the fastest and don't message me at night",
            "ask me first and never slower than {h} hours",
            "refill only and cheapest first",
        ],
        "am": [
            "ርካሹን መጀመሪያ ተጠቀም እና በሌሊት መልእክት አትላክልኝ [Use the cheapest first and don't message me at night]",
            "አስቀድመህ ጠይቀኝ እና ፈጣኑን ተጠቀም [Ask me first and use the fastest]",
            "ከ{h} ሰዓት በላይ የሚወስድ አትጠቀም እና ሪፊል ያላቸውን ብቻ ተጠቀም [Never slower than {h} hours and refill only]",
            "ሊንኬ {link} ነው እና እንደተለመደው {q} እዘዝ [My link is {link} and I usually order {q}]",
            "ርካሹን መጀመሪያ ተጠቀም እና አስቀድመህ ጠይቀኝ [Use the cheapest first and ask me first]",
            "በሌሊት መልእክት አትላክልኝ እና ሪፊል ያላቸውን ብቻ ተጠቀም [Don't message me at night and refill only]",
            "ሊንኬ {link} ነው እና እንደተለመደው {q} {am} እዘዝ [My link is {link} and I usually order {q} {m}]",
            "ርካሹን ተጠቀም እና ከ{h} ሰዓት በላይ የሚወስድ አትጠቀም [Use the cheapest and never slower than {h} hours]",
            "አስቀድመህ ጠይቀኝ እና በሌሊት መልእክት አትላክልኝ [Ask me first and don't message me at night]",
        ],
        "should_en": "Set both settings and confirm both in one short reply.",
        "should_am": "Reply in Amharic — set both settings and confirm both in one short reply.",
    },
    {
        "id": "off", "title": "Turning one off, clearing all",
        "count_en": 20, "count_am": 15,
        "en": [
            "turn off cheapest first", "stop asking me first",
            "remove the speed limit", "stop using my saved link",
            "forget my usual quantity", "remove the price limit",
            "stop the refill-only rule", "stop my repeats",
            "don't top up anymore", "stop placing orders without asking",
            "cancel quiet hours", "reset my settings",
            "clear all my settings", "turn off my favourites",
            "no more monthly reports", "stop auto-cancel",
            "unban my services", "stop trying new services",
            "unlock my language", "stop the double confirm",
        ],
        "am": [
            "ርካሹን አቁም [Stop the cheapest]",
            "አስቀድመህ መጠየቅ አቁም [Stop asking first]",
            "የፍጥነት ገደቡን አቁም [Turn off the speed limit]",
            "የተቀመጠው ሊንኬን ሰርዝ [Delete my saved link]",
            "የጸጥታ ሰዓቱን ሰርዝ [Delete quiet hours]",
            "ቅንብሮቼን ሁሉ ሰርዝ [Clear all my settings]",
            "ቅንብሮቼን ዳግም አስጀምር [Reset my settings]",
            "የተለመደው ሊንኬን እርሳ [Forget my usual link]",
            "የድግግሞሽ መርሐግብሩን አቁም [Turn off the repeat schedule]",
            "የአገልግሎት እገዳዬን አቁም [Turn off my service ban]",
            "ፈጣን መጀመር አቁም [Turn off fast start]",
            "ድርብ ማረጋገጫ አቁም [Turn off double confirm]",
            "የሳምንቱን ገደብ ሰርዝ [Delete the weekly limit]",
            "የዋጋ ገደቡን አቁም [Turn off the price limit]",
            "ሪፊል ብቻ አቁም [Turn off refill only]",
            "ድግግሞሹን አቁም [Stop the repeat]",
            "መጨመሩን አቁም [Stop the top-up]",
            "ሳትጠይቅ ማስገባት አቁም [Stop placing without asking]",
            "የተለመደው መጠኔን እርሳ [Forget my usual quantity]",
            "ተወዳጆቼን እርሳ [Forget my favourites]",
        ],
        "should_en": "Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.",
        "should_am": "Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.",
    },
    {
        "id": "4", "title": "4 — Fastest-first vs cheapest-first",
        "count_en": 34, "count_am": 20,
        "en": [
            "cheapest first", "always use the cheapest",
            "i prefer the cheapest", "use the cheapest first from now on",
            "cheapest first for my {p} {m}", "cheapest {p} {m}",
            "fastest first", "always use the fastest",
            "i prefer the fastest", "use the fastest first from now on",
            "fastest first for my {p} {m}", "stop using the cheapest",
            "go back to fastest first", "i want the cheapest services",
            "pick the cheapest one", "give me the cheapest",
        ],
        "am": [
            "ርካሹን መጀመሪያ ተጠቀም [Use the cheapest first]",
            "ሁልጊዜ ርካሹን ተጠቀም [Always use the cheapest]",
            "ርካሹን እመርጣለሁ [I prefer the cheapest]",
            "ከአሁን በኋላ ርካሹን መጀመሪያ ተጠቀም [From now on use the cheapest first]",
            "ፈጣኑን መጀመሪያ ተጠቀም [Use the fastest first]",
            "ሁልጊዜ ፈጣኑን ተጠቀም [Always use the fastest]",
            "ፈጣኑን እመርጣለሁ [I prefer the fastest]",
            "የ{p} {m} ርካሹን ተጠቀም [Use the cheapest {p} {m}]",
            "የ{p} {m} ፈጣኑን ተጠቀም [Use the fastest {p} {m}]",
            "የ{ap} {am} ርካሹን ተጠቀም [Use the cheapest {p} {m}]",
            "የ{ap} {am} ፈጣኑን ተጠቀም [Use the fastest {p} {m}]",
            "ርካሹን ለ{ap} {am} ተጠቀም [Use the cheapest for {p} {m}]",
            "ፈጣኑን ለ{ap} {am} ተጠቀም [Use the fastest for {p} {m}]",
            "ሁልጊዜ ርካሹን ለ{ap} ተጠቀም [Always use the cheapest for {p}]",
        ],
        "should_en": "Remember the pick order (cheapest or fastest first) and confirm it in one short line.",
        "should_am": "Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.",
    },
    {
        "id": "6", "title": "6 — Ask-first vs just do it",
        "count_en": 30, "count_am": 20,
        "en": [
            "ask me before you change service",
            "ask me first", "always ask me before you move my order",
            "ask me before you try another service",
            "don't move my order without asking",
            "ask me before you switch service",
            "just do it", "don't ask me first", "no need to ask",
            "just move it yourself", "turn off ask first",
            "don't ask me to change service", "move it yourself",
            "ask me before you change it",
            "ask me before you move my {p} {m} order",
            "ask me first when my {p} {m} gets stuck",
            "don't change my {p} {m} service without asking",
        ],
        "am": [
            "አገልግሎቱ ከተጣበቀ አስቀድመህ ጠይቀኝ [If the service gets stuck ask me first]",
            "አገልግሎት ከመቀየርህ በፊት ጠይቀኝ [Ask me before you change service]",
            "ሁልጊዜ አስቀድመህ ጠይቀኝ [Always ask me first]",
            "ሳትጠይቀኝ አታንቀሳቅስ [Don't move it without asking me]",
            "በራስህ አድርገው [Just do it yourself]",
            "መጠየቅ አያስፈልግም [No need to ask]",
            "አስቀድመህ መጠየቅ አቁም [Turn off ask first]",
            "የ{ap} {am} ከተጣበቀ አስቀድመህ ጠይቀኝ [If my {p} {m} gets stuck ask me first]",
            "አገልግሎት ከመቀየርህ በፊት ለ{ap} {am} ጠይቀኝ [Ask me before you change my {p} {m} service]",
        ],
        "should_en": "Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.",
        "should_am": "Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.",
    },
    {
        "id": "8", "title": "8 — Max slowness",
        "count_en": 20, "count_am": 15,
        "en": [
            "never slower than {h} hour", "only use fast services",
            "no slow services", "only faster than {h} hours",
            "never use a service slower than {h} hours",
            "any speed is fine", "no speed limit",
            "don't care about speed", "turn off the speed limit",
            "only use fast services for my {p} {m}",
            "never slower than {h} hours for {p} {m}",
        ],
        "am": [
            "ከ{h} ሰዓት በላይ የሚወስድ አገልግሎት አትጠቀም [Don't use a service that takes more than {h} hours]",
            "ፈጣን አገልግሎቶችን ብቻ ተጠቀም [Only use fast services]",
            "ዝግ ያለ አገልግሎት አትጠቀም [Don't use a slow service]",
            "ፍጥነት አያስፈልገኝም [Speed doesn't matter to me]",
            "የፍጥነት ገደብ የለኝም [I have no speed limit]",
            "ከ{h} ሰዓት በላይ ለ{ap} {am} አትጠቀም [Don't use a service slower than {h} hours for {p} {m}]",
            "ለ{ap} {am} ፈጣን ብቻ ተጠቀም [Only use fast ones for {p} {m}]",
        ],
        "should_en": "Remember the slowest service allowed (or clear the limit) and confirm it in one short line.",
        "should_am": "Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.",
    },
    {
        "id": "11", "title": "11 — Default link",
        "count_en": 20, "count_am": 15,
        "en": [
            "my link is {link}", "remember my link {link}",
            "my usual link is {link}", "use {link} as my link",
            "forget my link", "don't use my link",
            "my link is {link} use it always",
            "remember this link {link}",
            "use {link} for all my orders",
        ],
        "am": [
            "ሊንኬ {link} ነው [My link is {link}]",
            "ሊንኬን አስታውስ {link} [Remember my link {link}]",
            "የእኔ የተለመደው ሊንክ {link} ነው [My usual link is {link}]",
            "ሊንኬን እርሳ [Forget my link]",
            "ይህን ሊንክ አስታውስ {link} [Remember this link {link}]",
            "ሊንኬን ወደ {link} ቀይር [Change my link to {link}]",
            "ሊንኬ {link} ነው ሁልጊዜ ተጠቀምበት [My link is {link}, always use it]",
            "ነባሪ ሊንኬ {link} አድርግ [Make {link} my default link]",
        ],
        "should_en": "Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.",
        "should_am": "Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.",
    },
    {
        "id": "12", "title": "12 — Default quantity",
        "count_en": 20, "count_am": 15,
        "en": [
            "i usually order {q} {p} {m}",
            "my usual quantity is {q}",
            "usually order {q} {m}",
            "remember my usual quantity {q} for {p} {m}",
            "forget my usual quantity",
            "my usual order is {q} {p} {m}",
            "i usually order {q} {m}",
        ],
        "am": [
            "እንደተለመደው {q} {ap} {am} እዘዝ [I usually order {q} {p} {m}]",
            "የእኔ የተለመደው መጠን {q} ነው [My usual quantity is {q}]",
            "እንደተለመደው {q} {am} እፈልጋለሁ [I usually want {q} {m}]",
            "የተለመደው መጠኔን እርሳ [Forget my usual quantity]",
        ],
        "should_en": "Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.",
        "should_am": "Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.",
    },
    {
        "id": "13", "title": "13 — Price ceiling per 1,000",
        "count_en": 20, "count_am": 15,
        "en": [
            "never pay more than {e} per 1000",
            "no more than {e} birr per 1000",
            "max {e} per 1000", "don't pay over {e} per 1000",
            "any price is fine", "no price limit",
            "never pay more than {e} birr per 1000 for {p} {m}",
            "turn off the price limit",
        ],
        "am": [
            "ከ1000 በላይ {e} ብር አትክፈል [Don't pay more than {e} birr per 1000]",
            "ከ1000 {e} ብር በላይ አትክፈል [Never pay more than {e} birr per 1000]",
            "ዋጋ አያስፈልገኝም [Price doesn't matter]",
            "የዋጋ ገደብ የለኝም [I have no price limit]",
            "ከ1000 {e} ብር በላይ ለ{ap} {am} አትክፈል [Never pay more than {e} birr per 1000 for {p} {m}]",
        ],
        "should_en": "Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.",
        "should_am": "Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.",
    },
    {
        "id": "14", "title": "14 — Refill-only",
        "count_en": 15, "count_am": 12,
        "en": [
            "refill only", "only use services with refill",
            "only refill", "don't care about refill",
            "turn off refill only", "only services with refill",
            "refill doesn't matter",
            "only use {p} {m} services with refill",
        ],
        "am": [
            "ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill]",
            "ሪፊል ብቻ [Refill only]",
            "ሪፊል አያስፈልገኝም [Refill doesn't matter]",
            "ለ{ap} {am} ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill for {p} {m}]",
            "ሪፊል ያላቸውን {ap} {am} ብቻ ተጠቀም [Only use {p} {m} with refill]",
        ],
        "should_en": "Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.",
        "should_am": "Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.",
    },
    {
        "id": "15", "title": "15 — Drip-feed",
        "count_en": 30, "count_am": 15,
        "en": [
            "spread {q} {m} over {d} days",
            "drip-feed {q} {m} over {h} hours",
            "deliver it slowly over {d} days",
            "spread my {q} {m} over 2 days",
            "drip feed it", "spread {q} {p} {m} over {d} days",
            "deliver {q} views gradually over {d} days",
            "drip-feed my {q} {m} over {h} hours",
            "place it normally", "no drip", "forget the drip",
        ],
        "am": [
            "{q} {am} በ{d} ቀን አሰራጭ [Spread {q} {m} over {d} days]",
            "በዝግታ በ{d} ቀን አድርስ [Deliver it slowly over {d} days]",
            "ድሪፕ ፊድ አድርግ [Drip-feed it]",
            "በተለመደው መንገድ አስገባ [Place it normally]",
        ],
        "should_en": "Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.",
        "should_am": "Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.",
    },
    {
        "id": "16", "title": "16 — Auto-repeat",
        "count_en": 30, "count_am": 15,
        "en": [
            "always repeat my {p} {m} every {day}",
            "repeat my {p} {m} every day",
            "repeat it every {h} hours",
            "always repeat my orders every week",
            "stop repeating my orders", "don't repeat my orders",
            "repeat my {p} {m} every monday",
            "always repeat my {p} {m} every {d} days",
            "don't repeat anymore", "turn off auto-repeat",
        ],
        "am": [
            "የ{ap} {am}ዬን በየ{aday} ድገም [Repeat my {p} {m} every {day}]",
            "በየቀኑ ድገም [Repeat it every day]",
            "በየሳምንቱ ድገም [Repeat it every week]",
            "ድግግሞሹን አቁም [Stop the repeat]",
            "ትዕዛዞቼን መድገም አቁም [Stop repeating my orders]",
        ],
        "should_en": "Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.",
        "should_am": "Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.",
    },
    {
        "id": "17", "title": "17 — Top up the missing part",
        "count_en": 20, "count_am": 15,
        "en": [
            "top up the missing part",
            "always top up the missing part",
            "order the missing part yourself",
            "fill the rest yourself", "just refund",
            "don't top up", "no top-up",
            "top up the missing part for me",
            "if it is short, order the rest",
            "top up the missing {m} yourself",
            "if my {p} {m} is short, order the rest",
            "fill the missing {m} yourself",
        ],
        "am": [
            "የቀረውን ክፍል እራስህ አዝዝ [Order the missing part yourself]",
            "ሁልጊዜ የቀረውን ጨምር [Always top up the missing part]",
            "ገንዘቡን ብቻ መልስ [Just refund the money]",
            "መጨመር አያስፈልግም [No need to top up]",
            "የቀረውን {am} እራስህ አዝዝ [Order the missing {m} yourself]",
            "የ{ap} {am} የቀረውን ጨምር [Top up the missing {p} {m}]",
        ],
        "should_en": "Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.",
        "should_am": "Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.",
    },
    {
        "id": "18", "title": "18 — Place small orders without asking",
        "count_en": 34, "count_am": 20,
        "en": [
            "place small orders without asking",
            "orders under {cap} birr just place them",
            "don't ask me to confirm small orders",
            "skip the confirmation for small orders",
            "ask me to confirm again",
            "turn off placing without asking",
            "place my small orders without asking",
            "orders under {cap} just place them",
            "don't ask me to confirm",
            "skip the confirm for small orders",
            "small orders just place them",
            "turn off no-confirm",
            "orders under {cap} birr for {p} {m} just place them",
            "don't ask me to confirm orders under {cap} birr",
            "place my {p} {m} orders under {cap} birr without asking",
        ],
        "am": [
            "ትንንሽ ትዕዛዞችን ሳትጠይቀኝ አስገባ [Place small orders without asking me]",
            "ከ{cap} ብር በታች ያሉ ትዕዛዞችን አስገባ [Place orders under {cap} birr]",
            "ትንንሽ ትዕዛዞችን ሳታረጋግጥ አስገባ [Place small orders without confirming]",
            "እንደገና እንድታረጋግጥ ጠይቀኝ [Ask me to confirm again]",
            "ሳትጠይቅ ማስገባት አቁም [Stop placing without asking]",
            "ከ{cap} ብር በታች ያሉ {ap} {am} አስገባ [Place {p} {m} under {cap} birr]",
            "ትንንሽ {ap} {am} ሳትጠይቀኝ አስገባ [Place small {p} {m} without asking me]",
            "ከ{cap} ብር በታች ሳታረጋግጥ አስገባ [Place under {cap} birr without confirming]",
        ],
        "should_en": "Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.",
        "should_am": "Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.",
    },
    {
        "id": "19", "title": "19 — Quiet hours",
        "count_en": 20, "count_am": 15,
        "en": [
            "don't message me at night", "no messages at night",
            "quiet hours", "don't message me after 10pm",
            "message me only in the morning",
            "don't message me from 10pm to 7am",
            "turn off quiet hours", "message me anytime",
            "no quiet hours", "don't message me from 11pm",
            "only message me in the morning",
            "don't message me after {h}pm",
            "quiet hours from {h}pm to 7am",
        ],
        "am": [
            "በሌሊት መልእክት አትላክልኝ [Don't message me at night]",
            "በሌሊት ምንም አትላክልኝ [Send nothing at night]",
            "ከምሽቱ 10 ሰዓት እስከ ጠዋት 7 ሰዓት መልእክት አትላክልኝ [Don't message me from 10pm to 7am]",
            "ጠዋት ብቻ መልእክት ላክልኝ [Message me only in the morning]",
            "የጸጥታ ሰዓቱን አቁም [Turn off quiet hours]",
            "በማንኛውም ጊዜ መልእክት ላክልኝ [Message me anytime]",
            "ከምሽቱ 11 ሰዓት ጀምሮ መልእክት አትላክልኝ [Don't message me from 11pm]",
            "እስከ ጠዋት 8 ሰዓት ድረስ መልእክት አትላክልኝ [Don't message me until 8am]",
            "ማታ መልእክት አትላክልኝ [Don't message me in the evening]",
            "ሌሊት ላይ አትላክልኝ [Don't send at night]",
            "ሌሊት ዝም በል [Be quiet at night]",
            "ከምሽቱ 9 ሰዓት ጀምሮ ዝም በል [Be quiet from 9pm]",
            "ጠዋት 7 ሰዓት ላይ መልእክት ላክልኝ [Send me messages at 7am]",
            "የሌሊት መልእክቶችን ጠዋት ላክልኝ [Send the night messages in the morning]",
            "ምሽት ላይ መልእክት አትላክልኝ [Don't message me in the evening]",
        ],
        "should_en": "Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.",
        "should_am": "Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.",
    },
    {
        "id": "20", "title": "20 — Delivery deadline",
        "count_en": 20, "count_am": 15,
        "en": [
            "i need it by friday 5pm",
            "need {q} {m} by tomorrow 5pm",
            "i need it in {h} hours",
            "deliver by {day} 5pm", "place it anyway",
            "forget the deadline", "ignore the deadline",
            "i need {q} {p} {m} by {day}",
            "it must be done by tomorrow",
        ],
        "am": [
            "እስከ ዓርብ 5 ሰዓት ድረስ ያስፈልገኛል [I need it by Friday 5 o'clock]",
            "እስከ ነገ 5 ሰዓት ድረስ ያስፈልገኛል [I need it by tomorrow 5 o'clock]",
            "በ{h} ሰዓት ውስጥ ያስፈልገኛል [I need it within {h} hours]",
            "ያለ ገደቡ አስገባ [Place it without the deadline]",
            "ገደቡን እርሳ [Forget the deadline]",
            "እስከ {aday} 5 ሰዓት ድረስ ያስፈልገኛል [I need it by {day} 5 o'clock]",
            "እስከ ነገ {h} ሰዓት ድረስ ያስፈልገኛል [I need it by tomorrow {h} o'clock]",
        ],
        "should_en": "Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.",
        "should_am": "Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.",
    },
]
SECTIONS += [
    {
        "id": "21", "title": "21 — Favourite services",
        "count_en": 15, "count_am": 8,
        "en": [
            "my favourite service is {sid}",
            "make service {sid} my favourite",
            "favourite this service",
            "use my favourites first",
            "my favourite is {sid}",
            "forget my favourites",
            "my favourites are {sid} and 6001",
            "i love service {sid}, use it first",
        ],
        "am": [
            "የምወደው አገልግሎት {sid} ነው [My favourite service is {sid}]",
            "አገልግሎት {sid}ን ተወዳጅ አድርግ [Make service {sid} a favourite]",
            "ተወዳጆቼን መጀመሪያ ተጠቀም [Use my favourites first]",
            "ተወዳጆቼን እርሳ [Forget my favourites]",
        ],
        "should_en": "Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.",
        "should_am": "Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.",
    },
    {
        "id": "24", "title": "24 — Low balance alert",
        "count_en": 15, "count_am": 8,
        "en": [
            "warn me when my balance is below {money} birr",
            "tell me when my balance gets low",
            "low balance alert at {money}",
            "alert me if my balance drops below {money}",
            "turn off low balance alert",
            "tell me when my balance is under {money} birr",
            "warn me when my balance is low",
            "warn me when my balance drops below {money}",
        ],
        "am": [
            "ሚዛኔ ከ{money} ብር በታች ሲሆን ንገረኝ [Tell me when my balance is below {money} birr]",
            "ሚዛኔ ሲቀንስ ንገረኝ [Tell me when my balance drops]",
            "የሚዛን ማስጠንቅቂያ አቁም [Turn off the balance alert]",
            "ሚዛኔ ከ{money} ብር በታች ከሆነ አሳውቀኝ [Alert me when my balance is below {money} birr]",
        ],
        "should_en": "Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.",
        "should_am": "Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.",
    },
    {
        "id": "25", "title": "25 — Weekly spending limit",
        "count_en": 15, "count_am": 8,
        "en": [
            "don't let me spend more than {money} birr a week",
            "weekly spending limit {money}",
            "limit my spending to {money} a week",
            "max {money} birr per week",
            "turn off weekly limit", "no weekly limit",
            "i want to spend max {money} birr per week",
        ],
        "am": [
            "በሳምንት ከ{money} ብር በላይ አታውጣ [Don't spend more than {money} birr a week]",
            "የሳምንቱ ወጪ ገደብ {money} ነው [My weekly spending limit is {money}]",
            "የሳምንቱን ገደብ አቁም [Turn off the weekly limit]",
        ],
        "should_en": "Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.",
        "should_am": "Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.",
    },
    {
        "id": "26", "title": "26 — One-tap usual order",
        "count_en": 15, "count_am": 8,
        "en": [
            "order my usual", "give me the usual",
            "same as usual please", "one tap my usual order",
            "just order my usual", "the usual please",
            "order the usual", "my usual please",
            "order my usual {p} {m}",
            "give me my usual {q} {m}",
        ],
        "am": [
            "እንደተለመደው እዘዝ [Order as usual]",
            "የተለመደውን ስጠኝ [Give me the usual]",
            "እንደተለመደው አስገባ [Place it as usual]",
            "የተለመደውን {ap} {am} እዘዝ [Order my usual {p} {m}]",
            "እንደተለመደው {q} {am} እዘዝ [Order {q} {m} as usual]",
        ],
        "should_en": "Reuse the last order's service, link and quantity and show the Confirm card.",
        "should_am": "Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.",
    },
    {
        "id": "27", "title": "27 — Pause my repeats",
        "count_en": 15, "count_am": 8,
        "en": [
            "pause my repeats", "pause all my repeating orders",
            "pause my schedules", "pause the repeats",
            "resume my repeats", "unpause my repeats",
            "pause my repeating orders",
            "pause my {p} {m} repeats", "pause the {p} repeats",
        ],
        "am": [
            "የሚደገሙ ትዕዛዞቼን አቁም [Pause my repeating orders]",
            "ድግግሞሹን አቁም [Pause the repeat]",
            "የሚደገሙትን እንደገና ጀምር [Resume my repeats]",
            "የ{ap} {am} ድግግሞሽ አቁም [Pause the {p} {m} repeat]",
            "ድግግሞሹን ለ{ap} {am} አቁም [Pause the repeat for {p} {m}]",
        ],
        "should_en": "Pause every repeating order (or resume them) and confirm how many were paused.",
        "should_am": "Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.",
    },
    {
        "id": "30", "title": "30 — Watch my post and top up",
        "count_en": 15, "count_am": 8,
        "en": [
            "watch my post and top it up",
            "watch this post {link}, top up when it drops",
            "keep an eye on my post",
            "watch my {p} post and refill it",
            "stop watching my post",
            "watch my post and add more when it drops",
            "watch {link} and top it up",
        ],
        "am": [
            "ፖስቴን ተከታትለህ ጨምር [Watch my post and add more]",
            "ፖስቴን ተከታተል [Watch my post]",
            "ፖስቴን መከታተል አቁም [Stop watching my post]",
            "የ{ap} ፖስቴን ተከታተል [Watch my {p} post]",
            "ፖስቴን ተከታትለህ {am} ጨምር [Watch my post and add {m}]",
        ],
        "should_en": "Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.",
        "should_am": "Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.",
    },
    {
        "id": "31", "title": "31 — Saved links list",
        "count_en": 10, "count_am": 6,
        "en": [
            "save this link as my {p} link {link}",
            "remember my {p} link {link}",
            "save my links", "use my {p} link",
            "forget my saved links", "show my saved links",
            "save {link} as my {p} link",
        ],
        "am": [
            "ይህን ሊንክ እንደ {ap} ሊንኬ አስቀምጥ {link} [Save this link as my {p} link]",
            "የ{ap} ሊንኬን ተጠቀም [Use my {p} link]",
            "የተቀመጡ ሊንኮቼን እርሳ [Forget my saved links]",
        ],
        "should_en": "Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.",
        "should_am": "Reply in Amharic — remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.",
    },
    {
        "id": "32", "title": "32 — Best time to deliver",
        "count_en": 10, "count_am": 6,
        "en": [
            "when is the best time to order {m}?",
            "best time to deliver {p} {m}",
            "when should i order for fastest delivery",
            "what time is best for {m}",
            "when is the best time to order {p} {m}",
        ],
        "am": [
            "{am} ለማዘዝ የተሻለው ጊዜ መቼ ነው? [When is the best time to order {m}?]",
            "ፈጣን ለማድረስ መቼ ማዘዝ አለብኝ? [When should I order for fastest delivery?]",
        ],
        "should_en": "Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.",
        "should_am": "Reply in Amharic — answer with the fastest service's start time for what they asked.",
    },
    {
        "id": "33", "title": "33 — Wait for a lower price",
        "count_en": 10, "count_am": 6,
        "en": [
            "wait until {p} {m} are below {e} birr",
            "tell me when the price drops below {e}",
            "wait for a lower price for {p} {m}",
            "stop waiting for a lower price",
            "wait for the price to drop",
        ],
        "am": [
            "ዋጋው እስከ {e} ብር እስኪወርድ ጠብቅ [Wait until the price drops to {e} birr]",
            "ዋጋው ሲቀንስ ንገረኝ [Tell me when the price drops]",
            "መጠበቅ አቁም [Stop waiting]",
        ],
        "should_en": "Remember the price to wait for and say plainly the price watch isn't switched on yet.",
        "should_am": "Reply in Amharic — remember the price to wait for and say plainly the price watch isn't switched on yet.",
    },
    {
        "id": "34", "title": "34 — Auto-cancel if too slow",
        "count_en": 10, "count_am": 6,
        "en": [
            "cancel it if it takes longer than {h} hours",
            "auto-cancel if too slow",
            "cancel my order if it's slow",
            "turn off auto-cancel",
            "cancel it if it takes longer than {h} hour",
        ],
        "am": [
            "ከ{h} ሰዓት በላይ ከወሰደ ሰርዝ [Cancel it if it takes more than {h} hours]",
            "ዝግ ከሆነ በራስ-ሰርዝ [Auto-cancel if it is slow]",
            "ራስ-ሰርዝ አቁም [Turn off auto-cancel]",
        ],
        "should_en": "Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.",
        "should_am": "Reply in Amharic — remember the auto-cancel time (or turn it off) and confirm it.",
    },
    {
        "id": "35", "title": "35 — Monthly report",
        "count_en": 10, "count_am": 6,
        "en": [
            "send me a monthly report",
            "monthly spending report",
            "monthly report please", "stop the monthly report",
            "i want a monthly report",
            "send me the monthly report please",
            "monthly report for my spending",
            "give me a report every month",
            "monthly summary please",
            "stop sending monthly reports",
        ],
        "am": [
            "የወር ሪፖርት ላክልኝ [Send me a monthly report]",
            "የወር ወጪ ሪፖርት [Monthly spending report]",
            "የወር ሪፖርቱን አቁም [Stop the monthly report]",
            "የወር ሪፖርት እፈልጋለሁ [I want a monthly report]",
            "የወር ሪፖርት ላክልኝ እባክህ [Please send me a monthly report]",
            "የወር ማጠቃለያ ላክልኝ [Send me a monthly summary]",
        ],
        "should_en": "Remember the monthly report (or stop it) and say plainly it isn't switched on yet.",
        "should_am": "Reply in Amharic — remember the monthly report (or stop it) and say plainly it isn't switched on yet.",
    },
    {
        "id": "36", "title": "36 — Start fast only",
        "count_en": 10, "count_am": 6,
        "en": [
            "only use services that start fast",
            "start fast only", "fast start only",
            "only fast-start services", "turn off start fast only",
            "only use fast-start {p} {m}",
            "services that start fast only",
        ],
        "am": [
            "ፈጣን የሚጀምሩትን ብቻ ተጠቀም [Only use ones that start fast]",
            "ፈጣን መጀመር ብቻ [Fast start only]",
            "ፈጣን መጀመር አቁም [Turn off fast start only]",
            "ፈጣን የሚጀምር {ap} {am} ብቻ ተጠቀም [Only use fast-starting {p} {m}]",
            "ፈጣን መጀመር ለ{ap} {am} [Fast start for {p} {m}]",
        ],
        "should_en": "Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.",
        "should_am": "Reply in Amharic — remember start-fast-only (or turn it off) and confirm it.",
    },
    {
        "id": "37", "title": "37 — Language lock",
        "count_en": 10, "count_am": 6,
        "en": [
            "always reply in amharic",
            "speak to me in amharic only",
            "lock my language to english",
            "only english please",
            "reply in whatever language i use",
            "turn off language lock",
            "always reply in english",
            "speak to me in english only",
        ],
        "am": [
            "ሁልጊዜ በአማርኛ መልስ [Always reply in Amharic]",
            "በአማርኛ ብቻ ንገረኝ [Tell me in Amharic only]",
            "በእንግሊዝኛ ብቻ መልስ [Reply in English only]",
            "የቋንቋ መቆለፊያውን አቁም [Turn off the language lock]",
            "ሁልጊዜ በእንግሊዝኛ መልስ [Always reply in English]",
            "በአማርኛ ብቻ መልስ [Reply in Amharic only]",
        ],
        "should_en": "Remember the locked reply language (or unlock it) and confirm it; always reply in that language.",
        "should_am": "Reply in Amharic — remember the locked reply language (or unlock it) and confirm it; always reply in that language.",
    },
    {
        "id": "38", "title": "38 — Double confirm for big orders",
        "count_en": 10, "count_am": 6,
        "en": [
            "ask me twice for big orders",
            "double confirm orders over {money} birr",
            "confirm big orders twice",
            "turn off double confirm",
            "ask twice when the order is over {money} birr",
        ],
        "am": [
            "ለትላልቅ ትዕዛዞች ሁለት ጊዜ ጠይቀኝ [Ask me twice for big orders]",
            "ከ{money} ብር በላይ ሁለት ጊዜ አረጋግጥ [Double-confirm over {money} birr]",
            "ድርብ ማረጋገጫውን አቁም [Turn off double confirm]",
            "ትልልቅ ትዕዛዞችን ሁለት ጊዜ አረጋግጥ [Double-confirm big orders]",
        ],
        "should_en": "Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.",
        "should_am": "Reply in Amharic — remember the double-confirm level (or turn it off) and confirm it.",
    },
    {
        "id": "39", "title": "39 — Never use these services",
        "count_en": 10, "count_am": 6,
        "en": [
            "never use service {sid}",
            "don't use {sid} again", "ban service {sid}",
            "never use these services: {sid}",
            "unban service {sid}", "clear my banned services",
            "don't ever use service {sid}",
        ],
        "am": [
            "አገልግሎት {sid}ን በጭራሽ አትጠቀም [Never use service {sid}]",
            "አገልግሎት {sid}ን አትጠቀም [Don't use service {sid}]",
            "አገልግሎት {sid}ን አስወግድ [Remove service {sid}]",
        ],
        "should_en": "Remember the banned service(s) and confirm it; never pick them.",
        "should_am": "Reply in Amharic — remember the banned service(s) and confirm it; never pick them.",
    },
    {
        "id": "40", "title": "40 — Try new services",
        "count_en": 10, "count_am": 6,
        "en": [
            "try new services", "use new services",
            "let me try the new ones",
            "don't use new services", "turn off try new",
            "i want to try new services",
            "try the new {p} {m} services",
        ],
        "am": [
            "አዳዲስ አገልግሎቶችን ሞክር [Try new services]",
            "አዳዲሶቹን እፈልጋለሁ [I want the new ones]",
            "አዳዲስ አገልግሎቶችን አትጠቀም [Don't use new services]",
            "አዳዲስ {ap} {am} ሞክር [Try new {p} {m}]",
            "አዳዲሶቹን ሞክር [Try the new ones]",
        ],
        "should_en": "Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.",
        "should_am": "Reply in Amharic — remember try-new-services (or turn it off) and confirm it.",
    },
]
NOT_APPROVED = [
    {
        "id": "1", "title": "1 — Split test on/off (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "turn off the test order", "don't do a test order",
            "place it all at once, no test",
            "no test order for my orders",
            "never do a test order",
        ],
        "am": [
            "የሙከራ ትዕዛዝ አታድርግ [Don't do a test order]",
            "ሙከራውን አቁም [Stop the test]",
        ],
        "should_en": "Say the test order is how big orders are placed; it cannot be turned off.",
        "should_am": "Reply in Amharic — say the test order is how big orders are placed; it cannot be turned off.",
    },
    {
        "id": "2", "title": "2 — Test size (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "make the test 20%", "test with 1000 first",
            "make the test bigger", "test with half first",
            "make the test 5%", "make the test smaller",
        ],
        "am": [
            "ሙከራውን 20% አድርግ [Make the test 20%]",
            "ሙከራውን አሳድግ [Make the test bigger]",
        ],
        "should_en": "Say the test is always 10% of the order.",
        "should_am": "Reply in Amharic — say the test is always 10% of the order.",
    },
    {
        "id": "3", "title": "3 — The 400 ETB line (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "change the test line to 1000 birr",
            "test orders over 200 birr only",
            "make the test line 100 birr",
            "move the test line to 500 birr", "test line 1000",
        ],
        "am": [
            "የሙከራ መስመሩን 1000 ብር አድርግ [Make the test line 1000 birr]",
            "የሙከራ መስመሩን ቀይር [Change the test line]",
        ],
        "should_en": "Say orders over 400 ETB get a test order; the line cannot be changed.",
        "should_am": "Reply in Amharic — say orders over 400 ETB get a test order; the line cannot be changed.",
    },
    {
        "id": "5", "title": "5 — How much extra is allowed (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "allow 20% extra", "you can spend 30% more for me",
            "allow more extra", "let paxyo cover 20%",
            "paxyo can cover more",
        ],
        "am": [
            "20% ተጨማሪ ፍቀድ [Allow 20% extra]",
            "ተጨማሪ ወጪ ፍቀድ [Allow extra spending]",
        ],
        "should_en": "Say the extra Paxyo covers is at most 10% of the confirmed total.",
        "should_am": "Reply in Amharic — say the extra Paxyo covers is at most 10% of the confirmed total.",
    },
    {
        "id": "7", "title": "7 — How many tries (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "try 10 times", "only try twice",
            "try more services", "try just once",
            "try 3 times",
        ],
        "am": [
            "10 ጊዜ ሞክር [Try 10 times]",
            "ሁለት ጊዜ ብቻ ሞክር [Try only twice]",
        ],
        "should_en": "Say the bot tries up to 5 services, then refunds.",
        "should_am": "Reply in Amharic — say the bot tries up to 5 services, then refunds.",
    },
    {
        "id": "9", "title": "9 — PIN ONE SERVICE (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "pin service {sid}",
            "always use service {sid}, don't change",
            "use only service {sid}",
            "never change from service {sid}",
            "stick to service {sid}",
        ],
        "am": [
            "አገልግሎት {sid}ን ቋሚ አድርግ [Pin service {sid}]",
            "አገልግሎት {sid}ን ብቻ ተጠቀም [Use only service {sid}]",
        ],
        "should_en": "Say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.",
        "should_am": "Reply in Amharic — say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.",
    },
    {
        "id": "10", "title": "10 — SPENDING CAP (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "never spend more than {money} birr on one order",
            "spending cap {money}",
            "cap my spending at {money} birr per order",
            "cap my spending", "spending cap {money} birr",
        ],
        "am": [
            "በአንድ ትዕዛዝ ከ{money} ብር በላይ አታውጣ [Never spend more than {money} birr on one order]",
            "የወጪ ገደብ {money} [Spending cap {money}]",
        ],
        "should_en": "Say an order never costs more than the confirmed total; there is no separate spending cap.",
        "should_am": "Reply in Amharic — say an order never costs more than the confirmed total; there is no separate spending cap.",
    },
    {
        "id": "22", "title": "22 — Split across services (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "split this order across services",
            "use two services for one order",
            "split my order between services",
            "split it between services",
        ],
        "am": [
            "ትዕዛዜን በአገልግሎቶች መካከል ከፍል [Split my order between services]",
            "ሁለት አገልግሎቶችን ተጠቀም [Use two services]",
        ],
        "should_en": "Say one order goes on one service; it cannot be split across services.",
        "should_am": "Reply in Amharic — say one order goes on one service; it cannot be split across services.",
    },
    {
        "id": "23", "title": "23 — Delivery report (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "send me a report after each delivery",
            "delivery report for every order",
            "report after every delivery",
            "i want a report after delivery",
        ],
        "am": [
            "ከእያንዳንዱ ማድረስ በኋላ ሪፖርት ላክልኝ [Send me a report after each delivery]",
            "የማድረስ ሪፖርት እፈልጋለሁ [I want a delivery report]",
        ],
        "should_en": "Say the bot already tells them when an order is delivered.",
        "should_am": "Reply in Amharic — say the bot already tells them when an order is delivered.",
    },
    {
        "id": "28", "title": "28 — Price alert for my usual service (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "tell me when my usual service gets cheaper",
            "alert me when my usual price drops",
            "watch the price of my usual service",
            "tell me when my usual gets cheaper",
        ],
        "am": [
            "የተለመደው አገልግሎቴ ዋጋ ሲቀንስ ንገረኝ [Tell me when my usual service gets cheaper]",
            "የተለመደው ዋጋ ሲቀንስ ንገረኝ [Tell me when my usual price drops]",
        ],
        "should_en": "Say the bot cannot watch the price of one service yet.",
        "should_am": "Reply in Amharic — say the bot cannot watch the price of one service yet.",
    },
    {
        "id": "29", "title": "29 — All or nothing (NOT approved)",
        "count_en": 5, "count_am": 2,
        "en": [
            "all or nothing",
            "if it can't all deliver, refund everything",
            "don't partially deliver",
            "all or nothing for me",
        ],
        "am": [
            "ሁሉም ወይም ምንም [All or nothing]",
            "በחלקው አታድርስ [Don't deliver partially]",
        ],
        "should_en": "Say a short delivery is refunded for the missing part; all-or-nothing is not offered.",
        "should_am": "Reply in Amharic — say a short delivery is refunded for the missing part; all-or-nothing is not offered.",
    },
]

EN_TITLE = "# Golden dataset — Part 5: Order customizations (English)"
EN_INTRO = (
    "Realistic user messages about the Paxyo order customizations for "
    "@paxorder_bot, with the correct bot behaviour for each. Rules the "
    "\"Bot should\" lines follow: the bot understands plain words in "
    "chat and remembers each setting per user; the NORMAL way stays the "
    "default for everyone who sets nothing; a setting is confirmed back "
    "in chat in one short line; 'what are my settings' lists what they "
    "set, one line each; turning one off confirms it; the bot never "
    "pretends to set something William did not approve — for the "
    "NOT-approved options it says the normal way applies, in one short "
    "line; a Confirm card always comes before an order is placed, "
    "except an explicit opt-in for small orders under the cap (at most "
    "100 ETB) or an explicit \"order now\"; never reveal the provider name or "
    "buy prices. Approved: 4, 6, 8, 11-20, 21, 24, 25, 26, 27, 30, "
    "31-40. NOT approved: 1, 2, 3, 5, 7, 9, 10, 22, 23, 28, 29. "
    "Three approved options (30, 33, 35) are remembered but their "
    "doing part is not switched on yet — the bot says so honestly."
)

AM_TITLE = "# Golden dataset — Part 6: Order customizations (Amharic)"
AM_INTRO = (
    "Realistic user messages in Amharic about the Paxyo order "
    "customizations for @paxorder_bot, with the correct bot behaviour "
    "for each (English translation in brackets, as in Part 4). Rules "
    "the \"Bot should\" lines follow: the bot replies in Amharic; it "
    "understands plain words in chat and remembers each setting per "
    "user; the NORMAL way stays the default for everyone who sets "
    "nothing; a setting is confirmed back in chat in one short line; "
    "'what are my settings' lists what they set, one line each; "
    "turning one off confirms it; the bot never pretends to set "
    "something William did not approve — for the NOT-approved options "
    "it says the normal way applies, in one short line; a Confirm card "
    "always comes before an order is placed, except an explicit "
    "opt-in for small orders under the cap (at most 100 ETB) or an "
    "explicit \"order now\"; never reveal the provider name or buy prices. "
    "Approved: 4, 6, 8, 11-20, 21, 24, 25, 26, 27, 30, 31-40. "
    "NOT approved: 1, 2, 3, 5, 7, 9, 10, 22, 23, 28, 29. Three "
    "approved options (30, 33, 35) are remembered but their doing "
    "part is not switched on yet — the bot says so honestly."
)


def main():
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    rng = random.Random(SEED)
    all_sections = SECTIONS + NOT_APPROVED
    en_total = render(
        os.path.join(here, "05-customizations-english.md"),
        EN_TITLE, EN_INTRO, all_sections, "en", rng,
    )
    am_total = render(
        os.path.join(here, "06-customizations-amharic.md"),
        AM_TITLE, AM_INTRO, all_sections, "am", rng,
    )
    print(f"english: {en_total} items")
    print(f"amharic: {am_total} items")
    print(f"total: {en_total + am_total} items")


if __name__ == "__main__":
    main()
