"""Analyst-verdict rerun for the service-types build.

Reproduces the inventory's method (service-types-inventory.md §2/§9):
- fixture from godofpanel-live-2026-11-15.json, rate x420, average_time
  None, blacklist 5379/5834 excluded;
- per type: cheapest question ("what is the cheapest <platform>
  <metric>" + bare "cheapest ...") and order ("order 1000 ...");
- cheapest verdict vs the §2 table's expected cheapest id AND vs the
  true pool (pool membership is the analyst's verdict notion);
- order verdict = pool membership of the top pick.
Ground-truth pools are classified here from the snapshot by the
inventory's stated rules (platform from category first, name second;
metric from the name, category fallback; bundles under each component),
NOT by importing bot.py classification. The §2 cheapest-id column is
the independent anchor.
Usage: .venv/bin/python /tmp/verdict.py
"""
import json
import re
import sys

sys.path.insert(0, "/home/hatch/workspace/paxyo-bot")
import bot  # noqa: E402

SNAP = "/home/hatch/workspace/paxyo-bot/godofpanel-live-2026-11-15.json"
INV = "/home/hatch/workspace/paxyo-bot/service-types-inventory.md"
BLACKLIST = {5379, 5834}

# ---------------------------------------------------------------- fixture
raw = json.load(open(SNAP))
fixture = []
for s in raw:
    sid = int(s["service"])
    if sid in BLACKLIST:
        continue
    fixture.append({
        "service": sid,
        "name": s["name"],
        "category": s["category"],
        "rate_etb_per_1000": float(s["rate"]) * 420,
        "average_time": None,
        "active": True,
    })

# ------------------------------------------------------- §2 table parse
rows = []
for line in open(INV):
    line = line.strip()
    if not line.startswith("|") or "Cheapest (id" in line:
        continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    if len(cells) < 5:
        continue
    plat, metric, _n, cheap, _cq, _ord = cells[:6]
    m = re.search(r"#(\d+)", cheap)
    if not m or plat in ("Platform", "---"):
        continue
    if not re.fullmatch(r"[a-z\- ]+", plat):
        continue
    rows.append({
        "platform": plat.strip(),
        "metric": metric.strip(),
        "cheapest_id": int(m.group(1)),
        "cheapest_q": _cq.strip(),
        "order": _ord.strip(),
    })
print(f"§2 rows parsed: {len(rows)}")

# ------------------------------------------- ground-truth classification
PLAT_WORDS = {
    "instagram": "instagram", "tiktok": "tiktok", "telegram": "telegram",
    "youtube": "youtube", "facebook": "facebook", "twitter": "x",
    "twtter": "x", "x": "x", "spotify": "spotify", "twitch": "twitch",
    "kick": "kick", "shopee": "shopee", "kwai": "kwai",
    "whatsapp": "whatsapp", "linkedin": "linkedin", "threads": "threads",
    "discord": "discord", "jaco": "jaco", "snapchat": "snapchat",
    "bigo": "bigo", "rutube": "rutube", "coinmarketcap": "coinmarketcap",
    "bluesky": "bluesky", "pinterest": "pinterest", "line": "line",
    "shedevrum": "shedevrum", "reddit": "reddit", "clubhouse": "clubhouse",
    "google": "google",
}


def _words(s):
    return re.findall(r"[a-z]+", (s or "").lower())


def platform_of(svc):
    name, cat = svc["name"].lower(), svc["category"].lower()
    if "private channel" in cat or "private channel" in name:
        return "max"
    if re.match(r"\s*max\s", name) or re.match(r"\s*max\s", cat):
        return "max"
    for text in (cat, name):
        ws = set(_words(text))
        for w, p in PLAT_WORDS.items():
            if w in ws:
                return p
    if "traffic" in _words(name + " " + cat):
        return "website-traffic"
    return None


def _strip_descriptors(name):
    s = (name or "").lower()
    s = re.sub(r"\[[^\]]*(real views|human views)[^\]]*\]", " ", s)
    s = re.sub(r"\bsource:[^|]*", " ", s)
    s = s.replace("views from followers", " ")
    s = s.replace("free views", " ")
    return s


def _kinds_from_text(s, is_name=True):
    s = _strip_descriptors(s) if is_name else (s or "").lower()
    ws = set(_words(s))
    kinds = set()

    def has(*phrases):
        return any(p in s for p in phrases)

    # packages are ADDED to the component kinds (see truth_kinds)
    _pkg = None
    if has("growth package", "growth packages", "discover package",
           "discover packages", "discovery package", "discovery packages"):
        _pkg = "growth package"
    if has("engagement package", "engagement packages"):
        _pkg = "engagement package"
        if "emotion" in ws or "emotions" in ws:
            kinds.add("emotions")
    if has("comment reply likes", "comment reply like"):
        kinds.add("comment reply likes")
    elif has("comment replies", "comment reply"):
        kinds.add("comment replies")
    if has("comment reactions", "comment reaction"):
        kinds.add("comment reactions")
    if has("comment likes", "comment like"):
        kinds.add("comment likes")
    if has("live chat comments", "live stream chat comments") or (
            "chat comments" in s and "live" in ws) or (
            "chats" in ws and "live" in ws and "chatbot" not in ws):
        kinds.add("live chat comments")
    if has("live stream views", "livestream views", "live viewers",
           "live viewer", "live stream viewer", "live broadcast views"):
        kinds.add("live viewers")
    elif has("live stream likes", "live stream shares"):
        kinds.add("live viewers")
        if "like" in ws:
            kinds.add("likes")
        if "share" in ws:
            kinds.add("shares")
    elif "live stream" in s or "livestream" in s:
        if not (ws & {"likes", "shares", "comments", "views", "viewers",
                      "chat", "chatbot", "engagement"}):
            kinds.add("live viewers")
    if has("story poll votes", "story votes"):
        kinds.add("story poll votes")
    if has("story views"):
        kinds.add("story views")
    if has("story likes"):
        kinds.add("story likes")
    if has("story comments"):
        kinds.add("story comments")
    if has("story link click"):
        kinds.add("story link click")
    if has("story slider"):
        kinds.add("story slider")
    if has("post views"):
        kinds.add("post views")
    if has("poll votes", "poll vote"):
        kinds.add("poll votes")
    if has("contest votes", "contest vote"):
        kinds.add("contest votes")
    if has("profile visits", "profile visit"):
        kinds.add("profile visits")
    if has("bot start"):
        kinds.add("bot start")
    if has("premium members", "premium member"):
        kinds.add("premium members")
    if has("online members", "online member"):
        kinds.add("online members")
    if has("channel boost", "boost channel"):
        kinds.add("channel boost")
    if has("server boost"):
        kinds.add("server boost")
    if has("monthly listeners"):
        kinds.add("monthly listeners")
        kinds.add("listeners")
    if has("quote tweets", "quote tweet"):
        kinds.add("quote tweets")
    if has("tweet statistics"):
        kinds.add("statistics")
    if has("tweet views", "tweet view"):
        kinds.add("views")
    if has("friend requests", "friend request"):
        kinds.add("friend requests")
    if has("direct messages", "direct message", "mass dm"):
        kinds.add("direct messages")
    if " dm " in f" {s} " or s.rstrip().endswith(" dm"):
        kinds.add("direct messages")
    if has("reels sound use"):
        kinds.add("reels sound use")
    if has("template pack"):
        kinds.add("template pack")
    if has("tag a person"):
        kinds.add("tag a person")
    if has("room visitors", "room visitor"):
        kinds.add("room visitors")
    if has("linkedin sends"):
        kinds.add("linkedin sends")
    if has("pk battle points"):
        kinds.add("pk battle points")
    if has("ai chatbot", "chatbot"):
        kinds.add("ai chatbot")
    if has("hype boost"):
        kinds.add("hype boost")
    if has("pr service"):
        kinds.add("pr service")
    if "watch hour" in s or "watch time" in s:
        kinds.add("watch hours")
    # story leftovers: "Story Likes + Views" -> views are story views
    if "story" in ws:
        if "views" in ws and "story views" not in kinds:
            kinds.add("story views")
        if "likes" in ws and "story likes" not in kinds:
            kinds.add("story likes")
    # auto: subscription meaning only — "auto" directly before the
    # metric ("AUTO Likes", "[Auto] ... Views", "+ Auto Views"),
    # never "<N> Days Auto" / "Lifetime Auto" (auto-refill).
    _wlist = _words(s)
    _auto_fill = {"video", "live", "stream", "broadcast", "post",
                  "channel"} | set(PLAT_WORDS)
    for i, w in enumerate(_wlist):
        if w == "auto":
            j = i + 1
            while j < len(_wlist) and _wlist[j] in _auto_fill:
                j += 1
            if j >= len(_wlist):
                continue
            nxt = _wlist[j]
            auto_map = {"likes": "auto likes", "views": "auto views",
                        "comments": "auto comments",
                        "reactions": "auto reactions"}
            if nxt in auto_map:
                kinds.add(auto_map[nxt])
                kinds.discard(nxt)
                kinds.discard("post views")
    # single-word kinds (with singular/plural)
    singles = {
        "followers": "followers", "follower": "followers",
        "likes": "likes", "like": "likes",
        "views": "views", "view": "views",
        "subscribers": "subscribers", "subscriber": "subscribers",
        "members": "members", "member": "members",
        "shares": "shares", "share": "shares",
        "comments": "comments", "comment": "comments",
        "reactions": "reactions", "reaction": "reactions",
        "saves": "saves", "save": "saves",
        "plays": "plays", "play": "plays",
        "retweets": "retweets", "retweet": "retweets",
        "reposts": "reposts", "repost": "reposts",
        "reshares": "reshares", "reshare": "reshares",
        "quotes": "quotes", "quote": "quotes",
        "bookmarks": "bookmarks", "bookmark": "bookmarks",
        "statistics": "statistics", "statistic": "statistics",
        "mentions": "mentions", "mention": "mentions",
        "impressions": "impressions", "impression": "impressions",
        "reach": "reach",
        "listeners": "listeners", "listener": "listeners",
        "downloads": "downloads", "download": "downloads",
        "coins": "coins", "coin": "coins",
        "tokens": "tokens", "token": "tokens",
        "wishes": "wishes", "wish": "wishes",
        "watchlist": "watchlist",
        "emotions": "emotions", "emotion": "emotions",
        "traffic": "traffic",
        "reviews": "reviews", "review": "reviews",
        "connections": "connections", "connection": "connections",
        "endorsements": "endorsements",
        "endorsement": "endorsements",
        "recommendations": "recommendations",
        "recommendation": "recommendations",
    }
    if "reaction" in ws:  # "Like 👍" in a Reactions name is the emoji
        for w in ("like", "likes"):
            singles.pop(w, None)
    if "watchlist" in ws:
        singles.pop("follower", None)
        singles.pop("followers", None)
    if "statistics" in ws or "quote" in ws:
        singles.pop("tweet", None)
        singles.pop("tweets", None)
    _tweet_pending = False
    for w in _words(s):
        if w in ("tweet", "tweets"):
            # "Tweet" is the product only when it IS the product:
            # "Twitter Tweets" is tweets, "Tweet Views" is views.
            _tweet_pending = True
            continue
        if w in singles:
            kinds.add(singles[w])
    if not kinds and _tweet_pending:
        kinds.add("tweets")
    if "reshares" in kinds:
        # A Threads reshare IS the share action there.
        kinds.add("shares")
    if "viewers" in ws and "live viewers" not in kinds:
        kinds.add("live viewers")
    if _pkg:
        kinds.add(_pkg)
    return kinds


def truth_kinds(svc):
    name, cat = svc["name"], svc["category"]
    low = (name + " " + cat).lower()
    # package kind is ADDED to the name's own kinds (#821 is also
    # the cheapest facebook comments / emotions / reach service).
    kinds = _kinds_from_text(name, is_name=True)
    if not kinds:
        kinds = _kinds_from_text(cat, is_name=False)
    if any(p in low for p in ("growth package", "growth packages",
                              "discover package", "discover packages",
                              "discovery package", "discovery packages")):
        kinds = set(kinds) | {"growth package"}
    if any(p in low for p in ("engagement package",
                              "engagement packages")):
        kinds = set(kinds) | {"engagement package"}
        if "emotion" in _words(name) or "emotions" in _words(name):
            kinds.add("emotions")
    return kinds


# true pools: (platform, metric) -> set of service ids
pools = {}
for svc in fixture:
    plat = platform_of(svc)
    if plat is None:
        continue
    for k in truth_kinds(svc):
        pools.setdefault((plat, k), set()).add(svc["service"])
# Telegram views ARE post views; plain views pool includes post views
for (plat, k), ids in list(pools.items()):
    if k == "post views":
        pools.setdefault((plat, "views"), set()).update(ids)
# A story poll vote IS a poll vote (Instagram's poll votes are all
# story poll votes, e.g. #344)
for (plat, k), ids in list(pools.items()):
    if k == "story poll votes":
        pools.setdefault((plat, "poll votes"), set()).update(ids)

# ------------------------------------------------------------ verdicts
PHRASE = {
    "website-traffic": "website traffic",
    "x": "twitter",  # analyst phrasing uses the platform name
}


def phrase_for(plat, metric):
    p = PHRASE.get(plat, plat)
    if plat == "max":
        return f"private channel {metric}"
    if plat == "website-traffic":
        return "website traffic"
    return f"{p} {metric}"


cheapest = {"RIGHT": 0, "WRONG": 0, "NONE": 0, "NOT-A-QUESTION": 0,
            "EXACT": 0, "SKIP": 0}
order = {"RIGHT": 0, "WRONG": 0, "NONE": 0, "SKIP": 0}
cheapest_bad, order_bad = [], []
for row in rows:
    plat, metric = row["platform"], row["metric"]
    if plat == "google":
        cheapest["SKIP"] += 1
        order["SKIP"] += 1
        continue
    ph = phrase_for(plat, metric)
    # pool keys are canonical: twitter -> x; "emoji reactions" is
    # the reactions kind.
    pool_plat = "x" if plat == "twitter" else plat
    pool_metric = "reactions" if metric == "emoji reactions" else metric
    if pool_metric == "viewers":
        pool_metric = "live viewers"  # inventory §4d: bare viewers
    pool = pools.get((pool_plat, pool_metric), set())
    # ---- cheapest question
    q = f"what is the cheapest {ph}"
    if not bot.is_cheapest_question(q) and not bot.is_price_question(q):
        cheapest["NOT-A-QUESTION"] += 1
        cheapest_bad.append((plat, metric, "NOT-A-QUESTION", q))
    else:
        dplat, _dmetric = bot.detect_platform_metric(q)
        # Analyst convention: the platform comes from
        # detect_platform_metric (best case), the hint is the
        # user's own typed phrase (platform + metric as typed).
        pick = bot.cheapest_service(fixture, platform=dplat,
                                    service_hint=ph)
        if pick is None:
            cheapest["NONE"] += 1
            cheapest_bad.append((plat, metric, "NONE", q))
        elif int(pick["service"]) in pool:
            cheapest["RIGHT"] += 1
            if int(pick["service"]) == row["cheapest_id"]:
                cheapest["EXACT"] += 1
            else:
                cheapest_bad.append((plat, metric,
                                     f"RIGHT-pool/WRONG-price #{pick['service']} vs §2 #{row['cheapest_id']}", q))
        else:
            cheapest["WRONG"] += 1
            cheapest_bad.append((plat, metric,
                                 f"WRONG #{pick['service']} not in pool (exp #{row['cheapest_id']})", q))
    # ---- order
    dplat, _dmetric = bot.detect_platform_metric(f"order 1000 {ph}")
    picks = bot.pick_services(fixture, platform=dplat,
                              service_hint=ph, limit=3)
    if not picks:
        order["NONE"] += 1
        order_bad.append((plat, metric, "NONE", f"order 1000 {ph}"))
    elif int(picks[0]["service"]) in pool:
        order["RIGHT"] += 1
    else:
        order["WRONG"] += 1
        order_bad.append((plat, metric,
                          f"WRONG #{picks[0]['service']} not in pool", f"order 1000 {ph}"))

print("\nCHEAPEST:", cheapest, " total counted:",
      sum(v for k, v in cheapest.items() if k != "EXACT"))
print("ORDER   :", order, " total counted:",
      sum(v for k, v in order.items() if k != "SKIP"))
print(f"\nCheapest exact-id matches (§2 cheapest): {cheapest['EXACT']}")
print("\n--- cheapest failures / price mismatches ---")
for b in cheapest_bad:
    print("  ", b)
print("\n--- order failures ---")
for b in order_bad:
    print("  ", b)
