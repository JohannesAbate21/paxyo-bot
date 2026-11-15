# Service-types inventory — @paxorder_bot (analyst)

**Snapshot:** `godofpanel-live-2026-11-15.json`, re-fetched 15 Nov 2026 07:03 EAT — **7,175 services**. Blacklisted services **5379 and 5834 excluded** from every count and pool below (7,173 services analysed). Paxyo price = provider rate (USD per 1000) × **420 ETB**. The snapshot has **no average-time field**; order-pick verdicts below are therefore **pool-membership verdicts** (is the pick in the right pool / is the pool empty), not fastest-first ranking verdicts — see Caveats. Cheapest verdicts are exact (cheapest = lowest rate).

**Method.** Platform from category first, name second (name wins for the metric: a category such as `Snapchat Followers & Likes` also holds a Likes+Views service, so the metric is read from the **name**, falling back to the category only when the name carries no kind). Bundles are counted under **each** component kind, so the per-platform assignment totals below exceed 7,173. Detection was tested offline against the real functions in `bot.py` (`.venv/bin/python`) with a fixture built from the snapshot (`rate_etb_per_1000 = rate × 420`, `average_time = None`, `active = True`). Phrasings tested per type: cheapest `"what is the cheapest <platform> <metric>"` and bare `"cheapest <platform> <metric>"`, order `"order 1000 <platform> <metric>"` via `pick_services(limit=3)` and `cheapest_service`. `detect_platform_metric` was used as the platform (best case — the production AI classifier is an extra layer, see §7).

## 1. Platforms in the catalogue

| Platform | Services (name/category match) | Notes |
|---|---:|---|
| instagram | 1596 | 1596 — largest; incl. 9 Instagram Channel Members, 67 story views, 95 saves, 47 impressions |
| facebook | 1119 | 1119 — incl. 422 reactions, 12 Watch Time Views (60K-min), 29 group members, 10 friend requests, 10 engagement packages |
| tiktok | 1116 | 1116 — incl. 242 live-viewers services (timed live-stream views), 14 PK battle points, 2 PR services, 1 coins |
| youtube | 875 | 875 — incl. 27 watch hours, 100 live-viewers services, 1 hype boost |
| spotify | 604 | 604 — all plays/saves/followers/listeners; NO streams-as-metric ("[Fast Streams]" is speed text on plays services) |
| telegram | 551 | 551 — views ARE post views (38 services literally named "Post Views", the rest named "Views" in post-views categories); 40 bot-start, 72 premium members, 88 auto views, 16 channel boosts |
| twitter | 429 | 429 — incl. 63 in the misspelled category `Twtter [ DO NOT USE ]`; statistics is a real product (16) |
| twitch | 163 | 163 — live viewers + followers + views only |
| kick | 152 | 152 — live viewers/views + 9 AI chatbots |
| website-traffic | 121 | 121 — popunder/popup/mobile traffic (incl. 1 service optimised for Google Play Store, listed as "google" in the raw count) |
| shopee | 86 | 86 — live-stream viewers/views + followers + likes only; NO plain views product |
| kwai | 71 | 71 — views/shares/live viewers/comments/downloads |
| whatsapp | 69 | 69 — channel members, emoji reactions, poll votes |
| max | 48 | 48 — `MAX [Private Channel]`: followers/views/reactions/comments/members/reposts/bot-start for a Telegram private channel. The word "max" must NOT become a platform word (it collides with "max 1000 views"); reach these via "private channel" phrasing or service ID. |
| linkedin | 28 | 28 — followers/likes/comments/shares/members/reposts + sends/connections/endorsements/recommendations/mass DM/newsletter subscribers |
| threads | 25 | 25 — followers/likes/comments/reshares |
| discord | 18 | 18 — online members, members, reactions, server boost, tokens |
| jaco | 15 | 15 — followers/views/likes/comments/shares/saves/downloads/wishes (Jaco app) |
| snapchat | 14 | 14 — followers/likes/views/comments/reposts/friend requests; the only views services are Likes+Views bundles |
| bigo | 12 | 12 — live viewers/views/streams |
| rutube | 11 | 11 — views/followers/likes/comments + 7 emotion (emoji) services |
| coinmarketcap | 11 | 11 — profile followers, post views/likes/reposts, watchlist |
| reddit | 9 | 9 — views/shares/reach ("Reach Boost" in names) |
| clubhouse | 7 | 7 — followers + 2 room visitors |
| bluesky | 5 | 5 — followers/likes/comments/retweets |
| pinterest | 5 | 5 — followers, pin likes, pin saves, reactions |
| line | 3 | 3 — followers/likes/comments |
| shedevrum | 1 | 1 — followers |
| google | 1 |  |
| other | 10 | 10 — opaque provider codes (`tktk`, `tktk1`, `tktkcnl`, `fcbfcr`, `Ti51`, `private 2/3/5/365`, `Private34`); no readable metric, excluded from the inventory table |

**Platforms the bot knows:** `_PLATFORMS` = instagram, tiktok, telegram, youtube, facebook, x; `_PLATFORM_WORDS` adds insta, tg, yt, fb, twitter→x. **Every other platform above (24 of them) is unknown to the bot.** `platform_from_link` knows only instagram/tiktok/t.me/youtube/facebook/x domains. `SYSTEM_PROMPT` also lists only the 6 platforms.

## 2. Full inventory — every platform+metric type (221 types)

Cheapest = lowest rate in the true pool, excl. blacklist. Cheapest-Q verdict: what `"what is the cheapest <platform> <metric>"` (and bare `"cheapest …"`) does today — RIGHT / WRONG / NONE (no pick) / NOT-A-QUESTION (not recognised as a price question at all, falls through to the order flow). Order verdict: what `"order 1000 <platform> <metric>"` picks from `pick_services` (pool-membership verdict, see Caveats). `RIGHT*` on telegram views: Telegram views ARE post views — pick #6139 is correct (see §3).

| Platform | Metric | Services | Cheapest (id, ETB/1000) | Cheapest-Q | Order |
|---|---|---:|---|---|---|
| instagram | followers | 517 | #2099 — 110.21 | RIGHT | RIGHT |
| instagram | likes | 510 | #5050 — 0.42 | RIGHT | RIGHT |
| spotify | plays | 466 | #8161 — 37.80 | NOT-A-QUESTION | RIGHT |
| facebook | reactions | 422 | #5923 — 29.40 | RIGHT | RIGHT |
| tiktok | followers | 396 | #1104 — 172.20 | RIGHT | RIGHT |
| instagram | comments | 377 | #7692 — 140.24 | RIGHT | RIGHT |
| youtube | views | 344 | #2494 — 125.71 | WRONG | RIGHT |
| tiktok | likes | 277 | #4019 — 6.30 | RIGHT | RIGHT |
| telegram | members | 272 | #6040 — 2.65 | RIGHT | RIGHT |
| telegram | views | 258 | #6534 — 5.46 | RIGHT* | RIGHT* |
| facebook | likes | 246 | #3470 — 81.90 | RIGHT | RIGHT |
| tiktok | live viewers | 242 | #4332 — 9.24 | RIGHT | RIGHT |
| facebook | followers | 237 | #3614 — 44.35 | RIGHT | RIGHT |
| youtube | likes | 154 | #1774 — 18.90 | RIGHT | RIGHT |
| twitch | live viewers | 148 | #3308 — 73.92 | NOT-A-QUESTION | RIGHT |
| tiktok | views | 136 | #1861 — 1.51 | RIGHT | WRONG |
| kick | live viewers | 127 | #7517 — 29.40 | NOT-A-QUESTION | RIGHT |
| spotify | followers | 127 | #8288 — 55.44 | RIGHT | RIGHT |
| website-traffic | traffic | 121 | #7135 — 508.20 | NOT-A-QUESTION | RIGHT |
| twitter | followers | 119 | #621 — 189.00 | RIGHT | RIGHT |
| youtube | comments | 116 | #943 — 273.00 | RIGHT | RIGHT |
| youtube | subscribers | 116 | #5414 — 1.60 | RIGHT | RIGHT |
| facebook | comments | 115 | #821 — 504.00 | RIGHT | RIGHT |
| tiktok | comments | 108 | #8771 — 84.00 | RIGHT | RIGHT |
| telegram | reactions | 105 | #6534 — 5.46 | RIGHT | RIGHT |
| facebook | live viewers | 100 | #7614 — 14.70 | RIGHT | RIGHT |
| youtube | live viewers | 100 | #1774 — 18.90 | RIGHT | RIGHT |
| instagram | saves | 95 | #1814 — 8.40 | RIGHT | RIGHT |
| telegram | auto views | 88 | #6150 — 1.05 | RIGHT | RIGHT |
| youtube | shares | 88 | #7002 — 449.06 | RIGHT | RIGHT |
| twitter | retweets | 82 | #4145 — 83.79 | NOT-A-QUESTION | RIGHT |
| shopee | live viewers | 81 | #4773 — 420.00 | NOT-A-QUESTION | RIGHT |
| telegram | premium members | 72 | #8940 — 441.00 | RIGHT | RIGHT |
| instagram | growth package | 71 | #3071 — 525.00 | RIGHT | RIGHT |
| twitter | likes | 70 | #4145 — 83.79 | RIGHT | RIGHT |
| instagram | story views | 67 | #343 — 1.26 | RIGHT | RIGHT |
| spotify | saves | 64 | #8512 — 95.76 | NOT-A-QUESTION | RIGHT |
| instagram | reposts | 63 | #6280 — 90.72 | RIGHT | RIGHT |
| instagram | views | 63 | #1681 — 0.29 | RIGHT | RIGHT |
| twitter | comments | 63 | #4132 — 1,228.92 | RIGHT | RIGHT |
| instagram | auto likes | 57 | #5791 — 18.06 | RIGHT | RIGHT |
| instagram | impressions | 47 | #343 — 1.26 | RIGHT | RIGHT |
| twitter | views | 47 | #8598 — 0.42 | RIGHT | RIGHT |
| kwai | views | 45 | #2580 — 96.60 | RIGHT | WRONG |
| instagram | story comments | 44 | #5492 — 420.00 | RIGHT | RIGHT |
| whatsapp | emoji reactions | 42 | #8778 — 8.23 | RIGHT | RIGHT |
| whatsapp | reactions | 42 | #8778 — 8.23 | RIGHT | RIGHT |
| telegram | bot start | 40 | #6307 — 67.20 | WRONG | RIGHT |
| twitter | quotes | 39 | #6053 — 420.00 | NOT-A-QUESTION | RIGHT |
| telegram | post views | 38 | #6139 — 1.05 | RIGHT | RIGHT |
| facebook | views | 37 | #7428 — 9.66 | RIGHT | WRONG |
| instagram | reach | 31 | #5113 — 18.90 | RIGHT | RIGHT |
| facebook | members | 29 | #4403 — 110.04 | RIGHT | RIGHT |
| tiktok | shares | 28 | #2774 — 8.19 | RIGHT | RIGHT |
| facebook | shares | 27 | #3 — 323.99 | RIGHT | RIGHT |
| youtube | watch hours | 27 | #2408 — 441.00 | RIGHT | RIGHT |
| twitter | shares | 24 | #7555 — 41.58 | RIGHT | RIGHT |
| spotify | growth package | 23 | #8311 — 1,501.92 | NOT-A-QUESTION | RIGHT |
| twitter | bookmarks | 22 | #6053 — 420.00 | NOT-A-QUESTION | RIGHT |
| whatsapp | members | 21 | #8772 — 80.64 | RIGHT | RIGHT |
| telegram | online members | 19 | #7649 — 504.00 | RIGHT | RIGHT |
| kick | followers | 18 | #5869 — 140.70 | RIGHT | RIGHT |
| facebook | comment reactions | 17 | #4425 — 412.31 | RIGHT | RIGHT |
| kwai | shares | 17 | #5093 — 251.37 | RIGHT | RIGHT |
| max | reactions | 17 | #7865 — 2,417.81 | WRONG | WRONG |
| max | views | 17 | #7864 — 1,088.01 | WRONG | WRONG |
| telegram | channel boost | 16 | #7642 — 6,300.00 | RIGHT | RIGHT |
| twitter | statistics | 16 | #7549 — 0.42 | NOT-A-QUESTION | RIGHT |
| youtube | comment likes | 16 | #6006 — 67.20 | RIGHT | RIGHT |
| facebook | reviews | 15 | #4437 — 2,478.42 | RIGHT | RIGHT |
| instagram | auto views | 15 | #6664 — 0.67 | RIGHT | RIGHT |
| youtube | traffic | 15 | #3995 — 193.20 | RIGHT | RIGHT |
| discord | server boost | 14 | #6024 — 627.35 | NOT-A-QUESTION | RIGHT |
| tiktok | pk battle points | 14 | #1879 — 46.20 | RIGHT | RIGHT |
| instagram | profile visits | 13 | #343 — 1.26 | RIGHT | RIGHT |
| twitch | followers | 13 | #2922 — 42.00 | RIGHT | RIGHT |
| twitter | tweets | 13 | #110 — 17,388.00 | NOT-A-QUESTION | WRONG |
| bigo | live viewers | 12 | #4900 — 30.87 | NOT-A-QUESTION | RIGHT |
| facebook | watch hours | 12 | #4001 — 357.00 | RIGHT | RIGHT |
| instagram | shares | 12 | #8791 — 0.84 | RIGHT | RIGHT |
| telegram | story views | 12 | #2407 — 96.60 | RIGHT | RIGHT |
| threads | followers | 12 | #2110 — 348.64 | RIGHT | RIGHT |
| instagram | story poll votes | 11 | #344 — 63.00 | RIGHT | RIGHT |
| tiktok | live chat comments | 11 | #5296 — 420.00 | NONE | NONE |
| facebook | emotions | 10 | #821 — 504.00 | RIGHT | RIGHT |
| facebook | engagement package | 10 | #821 — 504.00 | RIGHT | RIGHT |
| facebook | friend requests | 10 | #5206 — 2,100.00 | NONE | NONE |
| facebook | reach | 10 | #821 — 504.00 | RIGHT | RIGHT |
| kwai | live viewers | 10 | #6338 — 407.40 | NOT-A-QUESTION | NONE |
| max | followers | 10 | #7875 — 3,053.15 | WRONG | WRONG |
| twitter | listeners | 10 | #2014 — 41.79 | NOT-A-QUESTION | RIGHT |
| twitter | reposts | 10 | #6053 — 420.00 | NOT-A-QUESTION | NONE |
| instagram | members | 9 | #3163 — 412.78 | RIGHT | RIGHT |
| kick | ai chatbot | 9 | #7811 — 12,023.93 | NOT-A-QUESTION | RIGHT |
| tiktok | saves | 9 | #6533 — 2.10 | RIGHT | RIGHT |
| instagram | comment likes | 8 | #5649 — 572.88 | WRONG | RIGHT |
| instagram | poll votes | 8 | #344 — 63.00 | RIGHT | RIGHT |
| reddit | views | 8 | #6459 — 16.80 | RIGHT | RIGHT |
| kick | live chat comments | 7 | #3104 — 394,010.11 | NONE | NONE |
| rutube | emotions | 7 | #12 — 413.57 | NOT-A-QUESTION | NONE |
| threads | comments | 7 | #1996 — 3,461.14 | RIGHT | RIGHT |
| twitter | live viewers | 7 | #29 — 630.00 | NOT-A-QUESTION | RIGHT |
| twitter | quote tweets | 7 | #5660 — 25,200.00 | NOT-A-QUESTION | UNCERTAIN |
| youtube | live chat comments | 7 | #7682 — 693.00 | RIGHT | RIGHT |
| coinmarketcap | followers | 6 | #5572 — 672.00 | RIGHT | RIGHT |
| instagram | comment replies | 6 | #831 — 630.00 | NONE | NONE |
| kwai | comments | 6 | #5097 — 138.60 | RIGHT | RIGHT |
| linkedin | reactions | 6 | #5457 — 3,990.00 | RIGHT | RIGHT |
| reddit | reach | 6 | #6463 — 63.00 | NOT-A-QUESTION | RIGHT |
| tiktok | auto views | 6 | #8803 — 21.00 | RIGHT | RIGHT |
| youtube | reactions | 6 | #480 — 42.00 | RIGHT | RIGHT |
| clubhouse | followers | 5 | #38 — 1,974.00 | RIGHT | RIGHT |
| facebook | comment replies | 5 | #4608 — 1,653.75 | NONE | NONE |
| jaco | followers | 5 | #7497 — 3,780.00 | RIGHT | RIGHT |
| snapchat | followers | 5 | #8763 — 1,999.20 | RIGHT | RIGHT |
| threads | likes | 5 | #2129 — 300.22 | RIGHT | RIGHT |
| whatsapp | poll votes | 5 | #8773 — 362.88 | NOT-A-QUESTION | RIGHT |
| youtube | auto views | 5 | #7757 — 319.20 | RIGHT | RIGHT |
| coinmarketcap | watchlist | 4 | #5573 — 7,087.50 | NOT-A-QUESTION | RIGHT |
| facebook | comment likes | 4 | #3670 — 4,620.00 | WRONG | RIGHT |
| facebook | story views | 4 | #2672 — 323.99 | RIGHT | RIGHT |
| jaco | comments | 4 | #7509 — 3,360.00 | RIGHT | RIGHT |
| linkedin | followers | 4 | #8731 — 4,410.00 | RIGHT | RIGHT |
| shopee | followers | 4 | #5880 — 315.00 | RIGHT | RIGHT |
| snapchat | likes | 4 | #8765 — 1,600.20 | RIGHT | RIGHT |
| spotify | monthly listeners | 4 | #8155 — 811.44 | NOT-A-QUESTION | RIGHT |
| threads | reshares | 4 | #1994 — 253.85 | NOT-A-QUESTION | NONE |
| threads | shares | 4 | #1994 — 253.85 | RIGHT | RIGHT |
| tiktok | auto likes | 4 | #8799 — 180.60 | WRONG | WRONG |
| tiktok | reposts | 4 | #7761 — 247.80 | RIGHT | RIGHT |
| twitter | mentions | 4 | #7553 — 2.10 | NOT-A-QUESTION | NONE |
| kick | viewers | 3 | #4072 — 21,000.00 | NOT-A-QUESTION | WRONG |
| kick | views | 3 | #6456 — 12.60 | RIGHT | WRONG |
| linkedin | comments | 3 | #8733 — 4,410.00 | RIGHT | RIGHT |
| linkedin | likes | 3 | #5453 — 3,360.00 | RIGHT | RIGHT |
| tiktok | comment likes | 3 | #7670 — 29.40 | WRONG | RIGHT |
| twitter | impressions | 3 | #8598 — 0.42 | NOT-A-QUESTION | RIGHT |
| twitter | profile visits | 3 | #8598 — 0.42 | NOT-A-QUESTION | RIGHT |
| bluesky | comments | 2 | #5220 — 7,560.00 | RIGHT | RIGHT |
| clubhouse | room visitors | 2 | #43 — 3,990.00 | NOT-A-QUESTION | RIGHT |
| discord | reactions | 2 | #6015 — 1,617.00 | RIGHT | RIGHT |
| instagram | emoji reactions | 2 | #7930 — 46.20 | RIGHT | RIGHT |
| instagram | reactions | 2 | #7930 — 46.20 | RIGHT | RIGHT |
| instagram | tag a person | 2 | #8709 — 7,560.00 | RIGHT | RIGHT |
| instagram | template pack | 2 | #7442 — 1,995.00 | RIGHT | RIGHT |
| kwai | likes | 2 | #2671 — 71.40 | RIGHT | RIGHT |
| linkedin | connections | 2 | #5452 — 10,500.00 | NOT-A-QUESTION | RIGHT |
| linkedin | members | 2 | #5451 — 10,500.00 | RIGHT | RIGHT |
| linkedin | reposts | 2 | #8734 — 3,150.00 | NOT-A-QUESTION | RIGHT |
| max | comments | 2 | #7888 — 14,781.35 | WRONG | WRONG |
| pinterest | followers | 2 | #129 — 840.00 | RIGHT | RIGHT |
| reddit | shares | 2 | #6460 — 16.80 | RIGHT | WRONG |
| snapchat | comments | 2 | #8739 — 3,780.00 | RIGHT | RIGHT |
| snapchat | friend requests | 2 | #5446 — 5,880.00 | NOT-A-QUESTION | RIGHT |
| snapchat | views | 2 | #8765 — 1,600.20 | NONE | NONE |
| tiktok | pr service | 2 | #7937 — 63,000.00 | WRONG | WRONG |
| twitch | views | 2 | #4981 — 14.41 | RIGHT | RIGHT |
| youtube | viewers | 2 | #7001 — 449.06 | AMBIG | AMBIG |
| bluesky | followers | 1 | #5216 — 751.80 | RIGHT | RIGHT |
| bluesky | likes | 1 | #5217 — 42,000,000.00 | RIGHT | RIGHT |
| bluesky | retweets | 1 | #5218 — 12,600.00 | NOT-A-QUESTION | NONE |
| coinmarketcap | likes | 1 | #5570 — 10,500.00 | RIGHT | RIGHT |
| coinmarketcap | post views | 1 | #5571 — 420.00 | RIGHT | RIGHT |
| coinmarketcap | reposts | 1 | #5575 — 10,500.00 | NOT-A-QUESTION | NONE |
| discord | members | 1 | #2873 — 6,520.50 | RIGHT | RIGHT |
| discord | tokens | 1 | #6023 — 150,971.73 | NOT-A-QUESTION | NONE |
| facebook | auto views | 1 | #466 — 827,316.00 | RIGHT | RIGHT |
| google | plays | 1 | #7092 — 960.50 | — | — |
| google | traffic | 1 | #7092 — 960.50 | — | — |
| instagram | reels sound use | 1 | #8712 — 25,200.00 | RIGHT | RIGHT |
| instagram | story likes | 1 | #7862 — 46.20 | WRONG | WRONG |
| instagram | story link click | 1 | #6296 — 336.00 | RIGHT | RIGHT |
| instagram | story slider | 1 | #6297 — 357.00 | RIGHT | RIGHT |
| jaco | downloads | 1 | #7506 — 840.00 | NOT-A-QUESTION | NONE |
| jaco | likes | 1 | #7503 — 2,100.00 | RIGHT | RIGHT |
| jaco | saves | 1 | #7504 — 2,100.00 | NOT-A-QUESTION | NONE |
| jaco | shares | 1 | #7505 — 2,520.00 | RIGHT | RIGHT |
| jaco | views | 1 | #7502 — 105.00 | RIGHT | RIGHT |
| jaco | wishes | 1 | #7507 — 2,100.00 | NOT-A-QUESTION | RIGHT |
| kick | poll votes | 1 | #6458 — 630.00 | NOT-A-QUESTION | RIGHT |
| kwai | comment likes | 1 | #2628 — 2,100.00 | RIGHT | RIGHT |
| kwai | downloads | 1 | #2627 — 357.00 | NOT-A-QUESTION | NONE |
| kwai | followers | 1 | #5092 — 2,266.74 | RIGHT | RIGHT |
| line | comments | 1 | #47 — 6,720.00 | RIGHT | RIGHT |
| line | followers | 1 | #45 — 5,040.00 | WRONG | WRONG |
| line | likes | 1 | #46 — 3,360.00 | WRONG | WRONG |
| linkedin | direct messages | 1 | #7940 — 115,500.00 | NOT-A-QUESTION | NONE |
| linkedin | endorsements | 1 | #7926 — 46,200.00 | NOT-A-QUESTION | RIGHT |
| linkedin | linkedin sends | 1 | #7924 — 3,696.00 | NOT-A-QUESTION | RIGHT |
| linkedin | recommendations | 1 | #7929 — 504,000.00 | NOT-A-QUESTION | RIGHT |
| linkedin | shares | 1 | #5454 — 14,700.00 | WRONG | WRONG |
| linkedin | subscribers | 1 | #7939 — 9,240.00 | RIGHT | RIGHT |
| max | bot start | 1 | #7885 — 14,266.48 | NOT-A-QUESTION | WRONG |
| max | members | 1 | #7863 — 10,880.02 | WRONG | WRONG |
| max | reposts | 1 | #7884 — 3,308.00 | NOT-A-QUESTION | WRONG |
| pinterest | likes | 1 | #203 — 3,570.00 | RIGHT | RIGHT |
| pinterest | reactions | 1 | #206 — 2,281.44 | RIGHT | RIGHT |
| pinterest | saves | 1 | #204 — 5,880.00 | NOT-A-QUESTION | NONE |
| rutube | comments | 1 | #11 — 801.70 | RIGHT | RIGHT |
| rutube | followers | 1 | #9 — 413.57 | RIGHT | RIGHT |
| rutube | likes | 1 | #10 — 413.57 | RIGHT | RIGHT |
| rutube | views | 1 | #8 — 121.80 | RIGHT | RIGHT |
| shedevrum | followers | 1 | #2033 — 1,171.80 | RIGHT | RIGHT |
| shopee | likes | 1 | #5884 — 126.00 | RIGHT | RIGHT |
| snapchat | reposts | 1 | #8738 — 3,780.00 | NOT-A-QUESTION | RIGHT |
| spotify | likes | 1 | #8746 — 4,410.00 | RIGHT | RIGHT |
| telegram | contest votes | 1 | #7740 — 105,000.00 | RIGHT | RIGHT |
| telegram | poll votes | 1 | #2858 — 144.40 | RIGHT | RIGHT |
| tiktok | coins | 1 | #3828 — 5,460.00 | RIGHT | RIGHT |
| tiktok | growth package | 1 | #2733 — 68,158.86 | NONE | NONE |
| tiktok | story likes | 1 | #3154 — 168.00 | RIGHT | RIGHT |
| tiktok | story views | 1 | #5089 — 168.00 | NONE | NONE |
| tiktok | traffic | 1 | #7096 — 603.75 | RIGHT | RIGHT |
| twitter | auto views | 1 | #8610 — 806.40 | RIGHT | RIGHT |
| twitter | direct messages | 1 | #2188 — 46,200.00 | NOT-A-QUESTION | NONE |
| twitter | saves | 1 | #7560 — 63,000.00 | NOT-A-QUESTION | RIGHT |
| twitter | tag a person | 1 | #8730 — 7,560.00 | NOT-A-QUESTION | RIGHT |
| whatsapp | saves | 1 | #8744 — 6,300.00 | NOT-A-QUESTION | NONE |
| youtube | comment replies | 1 | #6337 — 1,239.00 | NONE | NONE |
| youtube | hype boost | 1 | #6743 — 218,400.00 | RIGHT | RIGHT |
| youtube | saves | 1 | #2736 — 18,588.15 | NONE | NONE |

## 3. Covered vs missing — the counts

- **221 platform+metric types** in the snapshot (10 opaque `Other` codes unclassifiable, not counted).
- `kind_from_text` returns only **10 metric kinds verbatim**: followers, likes, views, subscribers, members, shares, comments, reactions, comment likes, watch hours. Everything else is kind=None (or a wrong kind — see §4).
- **Cheapest question** (`"what is the cheapest …"` / bare `"cheapest …"`): **RIGHT 138** (137 raw + telegram views, corrected — see below), **WRONG 17**, **NONE 10**, **NOT-A-QUESTION 54**, AMBIG 1 (youtube viewers), UNCERTAIN 1 (twitter quote tweets, order only). **83 of 221 types (38%) do not get the right cheapest answer** (81 failing + 2 google rows untested — see Caveats).
- **Order** (`"order 1000 …"`): **RIGHT 172** (171 raw + telegram views, corrected), **WRONG 21**, **NONE 25**. **46 of 221 types (21%) do not order the right pool.** (Order verdicts are pool-membership verdicts; ranking by real average time is untested — see Caveats.)
- Correction: the raw test marked "cheapest telegram views" WRONG because the pick #6139 is a *post views* service and my ground truth kept views/post-views apart. Verified: Telegram has no separate plain-views product — post views ARE Telegram views, and "cheapest telegram post views" returns the identical pick #6139 (1.05 ETB). Counted as RIGHT. The same correction applies to the order verdict (#6138 post views).
- "youtube viewers" is AMBIGUOUS, not a failure: the pick #7852 is a live-stream-views service and "viewers" most plausibly means concurrent live viewers on YouTube. "twitter quote tweets" order pick #110 is UNCERTAIN (category says Quote Tweet, name says Tweets).

## 4. Missing / wrong types — failing phrasing, actual resolution, proposed fix

Fix vocabulary used below: **M** = add to `_METRICS`; **K** = phrase check in `kind_from_text` (like `_has_watch_hours`); **N** = multi-word detection in `_name_kinds`; **C** = `_kinds_compatible` exception for bundles; **H** = `_hint_word_matches` spelling/plural handling; **P** = add to `_PLATFORM_WORDS` (+ `_PLATFORMS`); **G** = `is_cheapest_question` / `_CHEAPEST_BARE_WORDS` gate; **S** = `SYSTEM_PROMPT` platform/metric list; **A** = Amharic word in `_AMHARIC_METRICS`. Do NOT implement here — this is the builder's spec.

### 4a. Unknown platform — cheapest question is not even recognised (NOT-A-QUESTION, 54 types)

For every type in this section, `"what is the cheapest <platform> <metric>"` returns `is_cheapest_question = False` and `is_price_question = False`, so the message falls through to the classifier/order flow (asks for a link / starts an order) instead of answering with a price. `kind_from_text` is None and `detect_platform_metric` returns `(None, None)` (or `(x, None)` for twitter, which still fails the gate because the gate checks `_PLATFORMS`, which contains `x` but not the word `twitter` the user typed). Note: `cheapest_service`/`pick_services` themselves would often find the right service if called — the gate is what blocks it.

| Types (platform — metrics) | Failing phrasing | Fix |
|---|---|---|
| spotify — plays (466), saves (64), growth package (23), monthly listeners (4) | "what is the cheapest spotify plays" → not a question; no price, falls to order flow | P: spotify→spotify; M/K/N: plays, saves, monthly listeners; S: add spotify; A: Amharic for plays/saves |
| twitch — live viewers (148) | "what is the cheapest twitch live viewers" → not a question | P: twitch; K/N: live viewers (see §4d) |
| kick — live viewers (127), ai chatbot (9), poll votes (1) | "what is the cheapest kick live viewers" → not a question | P: kick; K/N: live viewers, ai chatbot, poll votes |
| website-traffic — traffic (121) | "what is the cheapest website traffic" → not a question | P: website→website-traffic (or a dedicated kind); K/N: traffic; note: users say "website traffic" / "traffic for my site" |
| shopee — live viewers (81) | "what is the cheapest shopee live viewers" → not a question (shopee has NO plain views product — all 81 views services are live) | P: shopee; K/N: live viewers |
| discord — server boost (14), tokens (1) | "what is the cheapest discord server boost" → not a question | P: discord; K/N: server boost, tokens |
| bigo — live viewers (12) | "what is the cheapest bigo live viewers" → not a question | P: bigo; K/N: live viewers |
| kwai — live viewers (10), downloads (1) | "what is the cheapest kwai live viewers" → not a question | P: kwai; K/N: live viewers, downloads |
| rutube — emotions (7) | "what is the cheapest rutube emotions" → not a question | P: rutube; K/N: emotions (emoji reactions on Rutube) |
| reddit — reach (6) | "what is the cheapest reddit reach" → not a question | P: reddit; K/N: reach |
| whatsapp — poll votes (5), saves (1) | "what is the cheapest whatsapp poll votes" → not a question | P: whatsapp; K/N: poll votes, saves |
| linkedin — reposts (2), connections (2), linkedin sends (1), endorsements (1), recommendations (1), direct messages (1) | "what is the cheapest linkedin connections" → not a question | P: linkedin; K/N: reposts, connections, linkedin sends, endorsements, recommendations, direct messages |
| snapchat — friend requests (2), reposts (1) | "what is the cheapest snapchat friend requests" → not a question | P: snapchat; K/N: friend requests, reposts |
| clubhouse — room visitors (2) | "what is the cheapest clubhouse room visitors" → not a question | P: clubhouse; K/N: room visitors |
| coinmarketcap — watchlist (4), reposts (1) | "what is the cheapest coinmarketcap watchlist" → not a question | P: coinmarketcap; K/N: watchlist, reposts |
| bluesky — retweets (1) | "what is the cheapest bluesky retweets" → not a question | P: bluesky; K/N: retweets |
| pinterest — saves (1) | "what is the cheapest pinterest saves" → not a question | P: pinterest; K/N: saves |
| jaco — saves (1), downloads (1), wishes (1) | "what is the cheapest jaco saves" → not a question | P: jaco; K/N: saves, downloads, wishes |
| threads — reshares (4) | "what is the cheapest threads reshares" → not a question | P: threads; K/N: reshares (catalogue word is "Reshare", singular — see §6 plural bug) |
| max — reposts (1), bot start (1) | "what is the cheapest max reposts" → not a question; and the pick would be cross-platform anyway (see §4c) | Do NOT add "max" as a platform word (collides with "max 1000 views"). Reach MAX services via "private channel" phrasing or service ID. |
| twitter — retweets (82), quotes (39), bookmarks (22), statistics (16), reposts (10), listeners (10), quote tweets (7), live viewers (7), mentions (4), profile visits (3), impressions (3), tag a person (1), direct messages (1), saves (1) | "what is the cheapest twitter retweets" → not a question (gate: kind None AND the word is "twitter", but `_PLATFORMS` holds `x`, not `twitter`) | G: gate must accept the word "twitter" (or detect_platform_metric must map it before the gate); P: twitter already maps →x in `_PLATFORM_WORDS`; M/K/N: retweets, quotes, quote tweets, bookmarks, statistics, mentions, impressions, profile visits, listeners, tag a person, direct messages, saves. NOTE: "cheapest x retweets" DOES pass the gate ("x" is in `_PLATFORMS`) but `detect_platform_metric("… x retweets")` returns `(None, None)` — "x" is not a key in `_PLATFORM_WORDS`. Fix both sides consistently. |

Twitter note: there is NO twitter "engagement package" type — the 3 services with "Engagements" in the name (e.g. #8598 Views + Impressions + Engagements + Profile Visits) are bundles counted under their components (views, impressions, profile visits); the fix is the component kinds, not a package kind.

### 4b. Unknown metric on a KNOWN platform — cheapest works only in the "what is" form, bare form fails; order pool is unguarded

On instagram/facebook/youtube/telegram, `"what is the cheapest <platform> <new-metric>"` passes the gate (platform word present) and the hint-word filter usually rescues the cheapest pick — but bare `"cheapest <platform> <new-metric>"` fails the `_CHEAPEST_BARE_WORDS` check (the new words are not in the set), and the order path has no kind guard for these metrics (hint_kinds is empty), so any service whose name merely contains the words can be picked. Fix: M/K/N for the kind + G: add the kind words to `_CHEAPEST_BARE_WORDS` (or, better, base the bare check on `kind_from_text(text) is not None` instead of a word list).

| Type | Failing phrasing | Resolves to today | Fix (kind string → expected cheapest answer / order pick) |
|---|---|---|---|
| instagram saves (95) | bare "cheapest instagram saves" → not a question; "what is…" → RIGHT (hint-word rescue) | bare form falls to order flow | M/K/N: "saves" → kind `saves`; true cheapest #1814 8.40 ETB; order pick = fastest IG saves service |
| instagram impressions (47), reach (31) | bare "cheapest instagram impressions" → not a question | falls to order flow | M/K/N: "impressions", "reach"; note most are Likes + [Reach + Impressions] bundles — C exception: a likes+reach+impressions bundle counts for an impressions/reach request |
| instagram story views (67) | "cheapest instagram story views" → kind `views` (WRONG kind); bare form → not a question | cheapest quotes plain IG views; order can pick plain views | K/N: "story views" → kind `story views`; C: "Story Likes + Views" bundle (#7862) counts for story views |
| instagram story comments (44), story likes (1), story poll votes (8), story link click (1), story slider (1) | "cheapest instagram story comments" → kind `comments` | quotes plain comments | K/N: "story comments", "story likes", "story poll votes" (incl. "story votes"), "story link click", "story slider" |
| instagram profile visits (13) | "cheapest instagram profile visits" → kind None; bare → not a question | falls to order flow | K/N: "profile visits" → kind `profile visits` |
| instagram comment replies (6), comment reactions (2 — IG emoji reactions), emoji reactions (2) | "cheapest instagram comment replies" → kind `comments`, then NONE (see §4e) | no pick at all | K/N: "comment replies", "comment reactions", "emoji reactions"; H: replies→reply |
| instagram auto likes (57), auto views (15) | "cheapest instagram auto likes" → kind `likes` | quotes plain likes, not the AUTO subscription | K/N: "auto likes", "auto views" → kinds `auto likes`/`auto views`; the AUTO services are subscriptions (per-subscription pricing — see §8) |
| instagram growth package (71) | "cheapest instagram growth package" → kind None; pick is a likes/comments/saves bundle (#3071) | WRONG pool | K/N: "growth package"/"discover package" → kind `growth package` (category `Instagram Growth Packages`); cheapest #7557 1,470.00 ETB |
| instagram channel members (9) | "cheapest instagram channel members" → kind `members` | RIGHT already (IG members ARE channel members) — no fix needed, keep as regression test | — (covered) |
| facebook group members (29) | "cheapest facebook group members" → kind `members` | RIGHT already (FB members ARE group members) — keep as regression test | — (covered) |
| facebook story views (4) | "cheapest facebook story views" → kind `views` | quotes plain FB views | K/N: "story views" |
| facebook comment reactions (17), comment replies (5), comment likes (4 — see §4c) | "cheapest facebook comment reactions" → kind `comments` | quotes plain comments | K/N: "comment reactions", "comment replies"; H: replies→reply |
| facebook friend requests (10) | "cheapest facebook friend requests" → kind None, then NONE | no pick | K/N: "friend requests"; H: requests→request |
| facebook reviews (15) | "cheapest facebook reviews" → kind None | falls to order flow; and "views" substring-matches "reviews" (§6) | K/N: "reviews" |
| facebook watch time (12) | "cheapest facebook watch time" → kind `watch hours` | RIGHT already (#4001-pool) — keep as regression test | — (covered; the watch-hours fix already covers "watch time") |
| facebook engagement package (10) | "cheapest facebook engagement package" → RIGHT (#821, 504.00 ETB, via hint words) | RIGHT | Keep as regression test; K/N: "engagement package" → kind `engagement package` so the bare form works too |
| youtube live viewers (100), live chat comments (7) | "cheapest youtube live viewers" → kind None; bare → not a question | falls to order flow | K/N: "live viewers" (incl. "live stream views", "livestream views", "live stream" alone — #5230) |
| youtube comment likes (16), comment replies (4), comment reply likes (3) | "cheapest youtube comment likes" → kind `comment likes` (right kind) but pool is contaminated (§4c) | quotes a bundle, not comment likes | N: two-word kind in `_name_kinds` (§4c fix); K/N: "comment replies", "comment reply likes" |
| youtube saves (1) | "cheapest youtube saves" → kind None, then NONE | no pick ("saves" vs catalogue "Save") | M/K/N: "saves"; H: saves→save |
| youtube hype boost (1) | "cheapest youtube hype boost" → kind None | falls to order flow | K/N: "hype boost" → kind `hype boost` (#6743, 218,400.00 ETB — per-1000 price is meaningless for a boost; see §8) |
| telegram post views (38) | "cheapest telegram post views" → kind `views` | RIGHT in practice (#6139, 1.05 ETB — same as plain "telegram views") | K/N: "post views" → kind `post views` (with TG views ≡ post views); keep both phrasings as regression tests |
| telegram story views (12) | "cheapest telegram story views" → kind `views` | quotes plain TG (post) views | K/N: "story views" |
| telegram premium members (72) | "cheapest telegram premium members" → kind `members` | cheapest members pick may be a NON-premium members service | K/N: "premium members" → kind `premium members`; note the paused-services guard must NOT treat "Telegram Premium" as paused (it is a members product, already handled) |
| telegram online members (19) | "cheapest telegram online members" → kind `members` | cheapest members pick may be regular members, not online | K/N: "online members" → kind `online members` |
| telegram bot start (47) | "cheapest telegram bot start" → kind None; pick #209 (a POST VIEWS service whose CATEGORY says "Bot Start") | WRONG — sells post views for a bot-start order | K/N: "bot start" → kind `bot start`; §6 category-contamination fix (hint words must come from the NAME) |
| telegram auto views (88), auto reactions (—) | "cheapest telegram auto views" → kind `views` | RIGHT by luck in the re-test (#6150 "[Auto] Telegram Post Views", 1.05 ETB) — but the kind guard cannot tell auto from plain | K/N: "auto views", "auto reactions" → kinds `auto views`/`auto reactions` |
| telegram poll votes (1), contest votes (1) | "cheapest telegram poll votes" → kind None; bare → not a question | falls to order flow | K/N: "poll votes", "contest votes" |
| telegram likes/dislikes (6/3) | "cheapest telegram likes" → kind `likes` | the only "Like" services are REACTIONS ("Like 👍" in `Telegram Reactions`) — a likes request must not be answered with reactions, and vice versa | N: "Like 👍"/"DisLike 👎" inside a Reactions name count as `reactions`, never as `likes`/`dislikes` |
| telegram channel boost (16) | "cheapest telegram channel boost" → kind None | falls to order flow | K/N: "channel boost" → kind `channel boost` (boosts for a channel, sold by days — see §8) |
| tiktok story views (1), story likes (2) | "cheapest tiktok story views" → kind `views`, then NONE | no pick (#5089 is a Story Views + Likes bundle, excluded by `_kinds_compatible`) | K/N: "story views", "story likes"; C: story-views+story-likes bundle counts for either |
| tiktok live chat comments (11) | "order 1000 tiktok live chat comments" → kind `comments`, then NONE | no pick ("[Real Views]" in the name adds a `views` kind — §6) | K/N: "live chat comments"; N: ignore "Real Views"/"Human Views" descriptor text in `_name_kinds` |
| tiktok auto likes (4), auto views (6) | "cheapest tiktok auto likes" → kind `likes`; pick #2954 plain likes (180.60 ETB is the true auto-likes cheapest #8799) | WRONG — sells one-off likes for an AUTO subscription | K/N: "auto likes", "auto views" |
| tiktok comment likes (3) | kind `comment likes` is right, but pick #4332 is a LIVE STREAM LIKES service (its CATEGORY is `Tiktok Live Stream Services [ Like + Share + Comments ]`) | WRONG — category contamination (§6) | N + §6 fix; true cheapest #7670 29.40 ETB |
| tiktok pr service (2) | "cheapest tiktok pr service" → kind None; pick #6533 (a saves service) | WRONG | K/N: "pr service" → kind `pr service` (#7937, 63,000.00 ETB) — niche; low priority |
| tiktok coins (1) | "cheapest tiktok coins" → kind None | falls to order flow | K/N: "coins" → kind `coins` (#3828, 5,460.00 ETB) |
| tiktok pk battle points (14) | "cheapest tiktok pk battle points" → kind None | falls to order flow | K/N: "pk battle points" → kind `pk battle points` |
| tiktok traffic (1) | "cheapest tiktok traffic" → kind None | falls to order flow | K/N: "traffic" (1 service, #7096, 603.75 ETB) |

### 4c. Wrong pool — the kind is known but the pick is a different product

| Phrasing | Got | Should be | Root cause / fix |
|---|---|---|---|
| "what is the cheapest youtube views" | #1928 YouTube Live Stream Views, **54.60 ETB** | #2494 YouTube Views + Likes, **125.71 ETB** (cheapest plain-views pool) | `_name_kinds` has no `live viewers` kind, so a 15-minute concurrent-viewers product sits in the plain-views pool and wins on price. Fix: K/N `live viewers` ("live stream views", "livestream views", "live viewers", "live stream" alone) + C: live services are NOT views. Same contamination in the order pool: youtube views pool 374 services, **59 live-stream**; tiktok views pool 290, **194 live-stream (67%)**; kwai views pool 44, 10 live-stream; facebook views pool 144, **100 live-stream + 15 reviews-named**. Instagram views pool is clean (106, 0 live). |
| "order 1000 tiktok views" / "order 1000 kwai views" / "order 1000 shopee views" / "order 1000 kick views" | top pick is a live-stream service (#3859 TikTok Live Stream Views 15-min; #6338 Kwai; #880 Shopee; #7517 Kick) | fastest plain-views service | Same live-viewers contamination. (Order verdicts are pool-membership verdicts — fixture had no average times — but a 15-minute live service is also the fastest by time, so this is expected to recur live.) |
| "order 1000 facebook views" | #8723 Facebook Page Reviews | fastest plain FB views service | `_hint_word_matches` is substring-based: "views" matches "reviews". Fix §6: whole-word matching. Facebook views pool contains 15 reviews-named services. |
| "what is the cheapest instagram comment likes" | #3399 "Instagram Custom Comments + Likes + Saves" bundle (147.00 ETB) | #5649 Instagram Comment Likes, **572.88 ETB** | `pick_services` builds hint_kinds from individual WORDS ({likes, comments}) instead of the two-word kind, so any likes+comments bundle qualifies. IG comment-likes pool: 75 services, only **5 true comment-likes**. Fix: compute hint_kinds from `kind_from_text`'s two-word kind; N: "comment likes" only when the name says "comment like(s)" as a unit; reject likes+comments bundles for a comment-likes request. TikTok comment-likes pool: 11 services, 3 true. |
| "what is the cheapest facebook comment likes" | #4592 (a comment-REPLIES service) | #3670 Facebook Comment Likes, **4,620.00 ETB** | Same two-word-kind gap + "reply likes" confusion. Fix: N: "comment reply likes" is its own kind, distinct from "comment likes". |
| "what is the cheapest telegram bot start" | #209 Telegram Post Views (2.52 ETB) | #6307 Telegram Bot Start, **67.20 ETB** | Category contamination: #209's CATEGORY is `Telegram Post Views | Reactions | Bot Start`, so the hint words "bot"+"start" match a post-views service. Fix §6: match hint words against the NAME (category only as fallback). |
| "what is the cheapest instagram story likes" | #2986 plain Instagram Likes | #7862 Instagram Story Likes + Views, **46.20 ETB** | No `story likes` kind — "likes" is the only kind seen. Fix: K/N `story likes`. |
| "what is the cheapest tiktok auto likes" | #2954 plain TikTok Likes | #8799 Tiktok AUTO Likes, **180.60 ETB** | No `auto likes` kind. Fix: K/N `auto likes`. |
| "what is the cheapest tiktok pr service" | #6533 (a saves service) | #7937 TikTok PR Service, **63,000.00 ETB** | No `pr service` kind; hint words match anything with "tiktok"+"service". Niche. |
| "cheapest max views / followers / reactions / comments / members" | picks from Instagram/Twitch/Telegram/Kwai (e.g. #1681 IG views, #2922 Twitch followers, #6534 TG reactions) | MAX private-channel services (#7864 views 1,088.01 ETB, #7875 followers 3,053.15 ETB, #7865 reactions 2,417.81 ETB, #7888 comments 14,781.35 ETB, #7863 members 10,880.02 ETB) | Platform "max" unknown → no platform filter → global pool. Do NOT add "max" as a platform word (see §1). Fix: reach MAX via "private channel" phrasing (names contain "Members to a Private Channel") or service ID. |
| "order 1000 linkedin shares / line followers / line likes / reddit shares" | YouTube/Twitch/Instagram services (#7085 YT shares, #4988 Twitch followers, #2986 IG likes, #7083 YT shares "Source: Reddit") | the LinkedIn/LINE/Reddit service | Unknown platform → global pool; #7083 matches "reddit" only because its NAME says "Source: Reddit". Fix: P for linkedin/line/reddit + §6 ("Source: X" is not the platform). |
| "order 1000 twitter tweets" | #8729 (a RETWEETS service) | fastest "Twitter Tweets" service (#110, 17,388.00 ETB) | Substring: "tweets" matches "retweets". Fix §6 whole-word matching. |
| "order 1000 max bot start" | #5934 (an Instagram likes service) | #7885 MAX Bot Start, 14,266.48 ETB | Unknown platform + substring "max" matching "Max" in names. Same fix as max rows above. |

### 4d. Multi-word kinds the bot has no phrase check for (the watch-hours pattern, generalised)

`_has_watch_hours` is the only multi-word phrase check. Every kind below needs the same treatment — a phrase check in `kind_from_text` checked BEFORE the single-word scan (word order matters: "story views" must win over "views", "comment likes" already does this correctly), a `_METRICS` entry, multi-word detection in `_name_kinds`, and a `_kinds_compatible` exception where the catalogue sells the kind only as a bundle (marked *). Phrasings are the natural user forms; variants in brackets are spellings the hint filter must also accept (`_hint_word_matches`: "watchhour"/"watchtime" precedent).

| Kind (phrase → kind string) | Platforms (services) | Bundle exception needed? |
|---|---|---|
| "live viewers" / "live stream views" / "livestream views" / "live views" → `live viewers` | youtube 100, twitch 148, kick 127, shopee 81, facebook 100, twitter 7, tiktok 242, bigo 12, kwai 10 | No — but the reverse: live services must be EXCLUDED from plain `views` pools |
| "story views" / "story likes" / "story comments" / "story poll votes" ("story votes") / "story link click" / "story slider" → same strings | instagram 67/1/44/11/1/1, telegram 12 story views, facebook 4 story views, tiktok 1/2 | * YES: #5089 TikTok Story Views + Likes and #7862 IG Story Likes + Views are two-kind bundles — a story-views request must accept {story views, story likes} |
| "post views" → `post views` | telegram 83, coinmarketcap 1 | Telegram views ≡ post views (see §3) |
| "comment replies" / "comment reply likes" / "comment reactions" / "live chat comments" → same strings | instagram 6, facebook 5, youtube 4 (+3 reply likes), tiktok 11 live chat, kick 7 live chat | — |
| "poll votes" / "contest votes" → same strings | instagram 8 (story), telegram 1+1, whatsapp 5, kick 1 | — |
| "profile visits" → `profile visits` | instagram 13, twitter 3 (+ bundles) | — |
| "bot start" → `bot start` | telegram 47, max 1 | — |
| "premium members" / "online members" → same strings | telegram 72 / 19, discord 1 online | — |
| "auto likes" / "auto views" / "auto comments" / "auto reactions" → same strings | instagram 57/15, telegram 88 auto views, tiktok 4/6, youtube 5 auto views, facebook 1 auto views, twitter 1 auto views | Note: "[Auto] Telegram Post Views" (non-adjacent) counts as auto views |
| "channel boost" / "server boost" → same strings | telegram 16 / discord 14 | Sold by days — see §8 |
| "saves" → `saves` | instagram 95, spotify 64, pinterest 1, whatsapp 1, youtube 1, jaco 1, twitter 1 (bookmarks are X's saves — separate kind below) | * YES for snapchat views (only Likes+Views bundles exist) — see §4e |
| "plays" → `plays` | spotify 466 (track/playlist/album/web/search/language/power plays + radio-source streams), google 1 | — |
| "retweets" / "reposts" / "reshares" / "quotes" / "quote tweets" → same strings | twitter 82/10/—/39/7, bluesky 1 retweets, linkedin 2 reposts, threads 4 reshares, snapchat 1 reposts, coinmarketcap 1 reposts, max 1 reposts, jaco — | — |
| "bookmarks" → `bookmarks` | twitter 22 (incl. Post Package bundles) | — |
| "statistics" → `statistics` | twitter 16 (detail expand, profile visit, link click, mention click…) | Note: a statistics service is a bundle of stats — its components (profile visits, impressions) are also kinds |
| "mentions" / "impressions" / "reach" → same strings | twitter 4 / 3, instagram 52 / 31, reddit 6 reach | * Impressions/reach mostly ride on Likes + [Reach + Impressions] bundles — accept the bundle for an impressions/reach request |
| "listeners" / "monthly listeners" → same strings | twitter 10 (Space listeners), spotify 4 monthly | — |
| "friend requests" / "reviews" / "direct messages" → same strings | facebook 10 / 15, twitter 1 DM, linkedin 1 DM, snapchat 2 friend requests | — |
| "downloads" / "coins" / "tokens" / "wishes" / "watchlist" / "tag a person" / "room visitors" / "connections" / "endorsements" / "recommendations" / "linkedin sends" / "reels sound use" / "pr service" / "template pack" / "emotions" / "hype boost" / "pk battle points" / "ai chatbot" → same strings | kwai 1, jaco 1, tiktok 1, discord 1, jaco 1, coinmarketcap 4, twitter 1 + instagram 1, clubhouse 2, linkedin 2/1/1/1/1, instagram 1, tiktok 2, instagram 2, rutube 7, youtube 1, tiktok 14, kick 9 | Niche (1–14 services each); implement after the big kinds |
| "growth package" / "engagement package" → same strings | instagram 48, tiktok 1, facebook 10 | Package = bundle by definition; the kind is the package itself |
| "dislikes" → `dislikes` | telegram 3 (all are Reactions services named "DisLike 👎") | Do NOT add as a standalone kind — route through reactions (emoji 👎). A word-only "dislikes" request has no non-reactions service. |
| "viewers" (bare) → ambiguous | youtube 2 (both live-stream-views services), others 0 | Treat bare "viewers" as `live viewers` (concurrent viewers), not `views`. |
| "tweets" → `tweets` | twitter 13 (services literally named "Twitter Tweets") | Ambiguous product (posting tweets vs tweet stats) — verify with the owner before wiring an order path; cheapest answer is #110 17,388.00 ETB. |

### 4e. NONE — the pool is empty although the service exists (10 cheapest / 25 order types)

| Type | Why the pool is empty | Fix |
|---|---|---|
| tiktok live chat comments (11), kick live chat comments (7) | `_name_kinds` counts "views" from the descriptor "[Real Views]" / "[Human Views]" in the name, so kinds = {comments, views} ⊄ {comments} | N: ignore "Real Views"/"Human Views"/"Views From Followers" descriptor text; K/N `live chat comments` |
| facebook friend requests (10) | "requests" has no singular fallback — `_hint_word_matches` only plural-handles words in `_METRICS` | H: generalise singular/plural handling to ALL hint words (requests→request, replies→reply, messages→message, mentions→mention, reshares→reshare, retweets→retweet, reposts→repost, tokens→token, downloads→download, saves→save) |
| instagram comment replies (6), facebook comment replies (5), youtube comment replies (4) | "replies" vs catalogue "Reply" (singular) — same plural bug | H: replies→reply; K/N `comment replies` |
| snapchat views (2) | The only views services are Likes+Views bundles; kinds {likes, views} ⊄ {views} | C: for snapchat (or generally), a likes+views bundle counts for a views request — same pattern as the watch-hours/views exception. True cheapest #8765 1,600.20 ETB. |
| tiktok story views (1) | #5089 is a Story Views + Likes bundle; kinds {views, likes} ⊄ {views} | C: story-views+story-likes bundle counts for a story-views request (after the §4d kind exists) |
| tiktok growth package (1) | User word "growth" is not in the service wording ("TikTok Quality Access & Discover Package") | K/N: accept "discover package" as `growth package`; low priority — users rarely say "growth package" |
| youtube saves (1) | "saves" vs catalogue "Save" (singular, #2736 bundle) | H: saves→save; M/K/N `saves` |
| twitter reposts (10), threads reshares (4), twitter mentions (4), twitter direct messages (1), linkedin direct messages (1), discord tokens (1), bluesky retweets (1), pinterest saves (1), coinmarketcap reposts (1), jaco saves (1), jaco downloads (1), kwai downloads (1), whatsapp saves (1), rutube emotions (7), kwai live viewers (10) | Same plural bug (reposts/reshares/mentions/messages/tokens/retweets/saves/downloads vs singular catalogue words) OR unknown platform (kwai/rutube/whatsapp) with no kind to rescue the gate | H for the plurals; P + K/N for the platforms/kinds |
| youtube engagement package | No such product on YouTube (earlier count was a wording artefact: "Real Engagement" in a views service name). Correctly NONE — see §5. | — |

## 5. Phrasings with genuinely NO service — the bot must answer honestly, never guess

Verified against the snapshot (all 7,175 services). For these, `cheapest_service`/`pick_services` already return NONE today — the gap is what the bot SAYS next: `price_answer_text` falls through to `t("price_ask_service")` ("Which service? Tell me the platform and what you want…"), which is not an honest "we don't have that". The order flow likewise has no "doesn't exist" line for non-reactions types (the reactions path already has one for emoji-only services).

| Phrasing | Why there is no service | What the bot does today | Required answer |
|---|---|---|---|
| "cheapest telegram followers" / "order 1000 telegram followers" | Telegram has no followers product (the 20 name hits are "Members … Views From Followers" — followers as the SOURCE of members, not the metric) | NONE → "Which service?" | "Telegram doesn't have followers — you can order Telegram members instead." (Offer members, never silently sell members for a followers order.) |
| "cheapest youtube channel joins" / "cheapest instagram channel joins" / "order 100 youtube channel members" (joins) | No service named "join" anywhere; the closest are channel MEMBERS (IG 9, Telegram premium members) | NONE → "Which service?" | "We don't have channel joins — channel members are the closest thing." |
| "order 10 facebook 🙏 reactions" / "cheapest facebook pray reactions" | No Facebook 🙏-only service (HANDOVER: no Facebook 🙏 reactions service exists). 🙏 exists on Telegram (#1723) and WhatsApp (#8784, #5399). | NONE (reactions pool empty) → honest no-service path already exists for emoji; word-only "pray" also returns NONE (via the word filter) | Keep the honest path; make sure the word-only form gets the same "no 🙏-only service for Facebook, closest is the Positive mix" answer, not silence. |
| "order 10 instagram ❤️ reactions" | No Instagram ❤️-only service — only #7930 Positive Emoji Reaction mix (and 1 more) | NONE → honest no-service path | Keep; offer the Positive mix, never sell the mix as ❤️-only. |
| "cheapest youtube engagement package" | No YouTube engagement-package product (only Facebook has an `Engagement Packages` category, 10 services) | NONE → "Which service?" | "We don't have a YouTube engagement package — Facebook has one." |
| "cheapest facebook 🙏 reactions" (word form "pray reactions") | Same as above — no FB 🙏-only service | NONE | Same honest answer as the emoji form. |
| Any other type whose pool is empty after the fixes (§4e) | — | — | Same rule: name the missing thing, offer the closest real thing, never a silent guess or a different product. |

Reactions cross-check (already correct — regression tests): generic "cheapest facebook reactions" → #5923 👍 29.40 ETB; "cheapest instagram reactions" → #7930 Positive mix 46.20 ETB; "cheapest telegram reactions" → #6534 Positive mix 5.46 ETB; "order 10 facebook ❤️ reactions" → #5105 ❤️ 29.40 ETB; "order 10 telegram 🙏 reactions" → #1723 Pray 🙏 12.60 ETB.

## 6. Mechanism findings (root causes, each verified by a direct unit check)

1. **Substring matching in `_hint_word_matches`** (`word in hay`): `"views"` matches `"reviews"` (→ #8723 Facebook Page Reviews in the facebook-views pool), `"likes"` matches `"dislike"`, `"tweets"` matches `"retweets"` (→ #8729 retweets sold for a tweets order), `"x"` matches `"Max"`. Fix: whole-word matching (word boundaries) for hint words; keep the existing singular/plural variant logic, generalised (§4e).
2. **Category contamination**: the hint-word filter matches against `name + " " + category`. #209 (a post-views service) wins "cheapest telegram bot start" because its CATEGORY contains "Bot Start"; #4332 (live-stream likes) wins "cheapest tiktok comment likes" because its CATEGORY contains "Comments"; #7083 (YouTube shares) matches "reddit shares" because its NAME says "Source: Reddit". Fix: match hint words against the NAME; use the category only as a fallback when the name carries no kind.
3. **Plural handling only for `_METRICS` words**: "requests/replies/messages/mentions/reshares/retweets/reposts/tokens/downloads/saves" have no singular fallback, so 10+ types return empty pools although the service exists in singular form. Fix: generalise the variant logic to all hint words.
4. **Bare-cheapest gate**: `is_cheapest_question` requires the bare word set ⊆ `_CHEAPEST_BARE_WORDS`. Multi-word kinds fail even on known platforms: bare "cheapest youtube live viewers", "cheapest instagram story views", "cheapest telegram post views", "cheapest instagram saves" are all False (and `is_price_question` False too). The "what is the cheapest …" form works when the gate passes (platform or kind present). Fix: add all new kind words to the set, or base the bare check on `kind_from_text() is not None`.
5. **Gate/platform mismatch**: `is_cheapest_question` checks `_PLATFORMS` (contains `x`, not `twitter`), while `detect_platform_metric` checks `_PLATFORM_WORDS` (contains `twitter`→x, not `x`). Consequences: "what is the cheapest twitter retweets" fails the gate; "what is the cheapest x retweets" passes the gate but `detect_platform_metric` returns `(None, None)`. Fix: make both use the same word set.
6. **`_name_kinds` has no multi-word kinds and counts descriptor words as metrics**: "YouTube Live Stream Views" → {views} (should be {live viewers}); "Telegram Reactions + Free Views | Like" → {reactions, views, likes} (the "Like" is the emoji name, the "views" a free bonus); "TikTok Custom Live Chat Comments [Real Views]" → {comments, views} ("Real Views" is a quality descriptor); "Telegram Members … Views From Followers" → {members, views, followers} ("followers" is the source). Fix: detect multi-word kinds first (live viewers, story views, comment likes, post views, auto views…), ignore known descriptor phrases, and treat "views from followers" / "source from followers" as source, not metric.
7. **Two-word kinds are built from single words in `pick_services`**: hint_kinds for "comment likes" is {likes, comments} (from the words), so any likes+comments bundle qualifies (IG pool 75, only 5 true comment-likes). Fix: derive hint_kinds from `kind_from_text` (which already returns the two-word kind) instead of re-splitting words.
8. **AI prompt layer (untested offline, but it gates production)**: `SYSTEM_PROMPT` lists platform as one of 6 only and gives service_hint examples only for followers/likes/views/members; `FEW_SHOT_EXAMPLES` show only followers/views/reactions. All offline tests above used the deterministic detectors (best case). In production the AI classifier can drop the platform/metric before the deterministic code ever sees it — the prompt needs the same platform + metric list as the deterministic code. Also `services_for_prompt` only shows candidate services when BOTH platform and metric are detected, so unknown types get no candidates in the prompt at all.
9. **Amharic gap**: `_AMHARIC_METRICS` covers 8 words (views/followers/likes/comments/subscribers/shares/members + comment). No Amharic word exists for any new kind (watch hours included — it works only via the Latin phrase). Every new kind needs its Amharic form added, or Amharic speakers asking for e.g. saves/plays/live viewers will silently mis-resolve.
10. **Kind guard vs bundles**: `_kinds_compatible` has exactly two exceptions (reactions+views, watch-hours+views). Every bundle-only kind needs one: story views+story likes, likes+views (snapchat), likes+reach+impressions, views+likes (youtube #2494). Without them the pool is empty (§4e) or the wrong pool wins (§4c).

## 7. Most surprising wrong-pool case (besides watch hours)

**"What is the cheapest youtube views" → #1928 YouTube Live Stream Views, 54.60 ETB/1000** — a 15-minute concurrent-viewers product, quoted as the cheapest "views" although the cheapest plain-views service is #2494 at 125.71 ETB/1000. The bot under-quotes by more than half for the wrong product, and the same pool contamination is worse on TikTok: the plain-views order pool (290 services) is **67% live-stream services (194)**, so "order 1000 tiktok views" is more likely than not to land on a timed live product. (Runner-up: "order 1000 facebook views" → #8723 Facebook Page Reviews, via the "views"-inside-"reviews" substring match.)

## 8. Catalogue anomalies the builder should know about (not bot bugs)

- **#5217 BlueSky Likes, rate 100000.00 USD/1000 → 42,000,000.00 ETB/1000.** Almost certainly a provider data error (misplaced decimal / placeholder). It is the "cheapest" BlueSky likes service only because it is the ONLY one with that exact wording — flag to the owner; do not quote it as a real price.
- **Per-piece services priced as per-1000**: #6384 "Instagram Tag 3 Friends" rate 1250.00 ("1 Piece $1.25") → 525,000.00 ETB/1000 is meaningless; the real price is 525.00 ETB per piece. Same pattern wherever a name says "1 Piece" — the ×420 per-1000 maths does not apply.
- **Subscription/duration services (97 with "subscription" in name/category)**: AUTO likes/views, bot-start durations, channel boosts by days (e.g. #466 Facebook Auto Live Stream Views, 30-day subscription, rate 1969.80 USD → 827,316.00 ETB "per 1000"), Telegram Premium Boost by days. Their "per 1000" rate is really a per-subscription price — quoting it as ETB/1000 misleads. The cheapest-answer path should label these as subscriptions, not per-1000.
- **Facebook Watch Time Views (12 services, "60K Minutes")** are the Facebook watch-hours product — covered by the existing `_has_watch_hours` ("watch time") check; verified RIGHT.
- **"Twitter Statistics" (16) is a real product** (detail expand, profile visit, link click, mention click) — not a fallback bucket.
- **MAX (48 services)** is a Telegram private-channel product line, not a platform; see §1.

## 9. Caveats — read before building from this file

- **Order verdicts are pool-membership verdicts.** The fixture set `average_time = None` for every service (the snapshot has no average-time field; live times come from the mini-app backend). `pick_services` sorts fastest-first, so with real times the top pick inside a contaminated pool can differ from the one recorded here — but a wrong-pool service can only be picked if it is IN the pool, and pool membership is what was tested. Cheapest verdicts are exact (rate-sorted, time-independent).
- **Tests used the deterministic detectors as the platform source** (`detect_platform_metric`). In production the AI classifier supplies `intent.platform`/`service_hint` first; the SYSTEM_PROMPT gap (§6.8) means production can fail earlier than these tests show, especially for unknown platforms.
- **Ground-truth judgements**: Telegram views ≡ post views (verified: identical pick #6139 for both phrasings); Shopee has no plain-views product (all 81 views services are live); "tweets"/"quote tweets" are ambiguous products (see §4d); "youtube viewers" is ambiguous (counted AMBIG, not a failure).
- **Counts**: bundles are counted under each component kind, so per-platform assignment totals exceed the service count. "Services" in §2 is the count of services in the true pool for that type, not a partition.
- **Snapshot date**: 15 Nov 2026 07:03 EAT, 7,175 services. Rates move daily (e.g. #5535's rate rose 0.003 → 0.0044 the same morning) — re-check the cheapest IDs at deploy time; the kinds and the fixes do not depend on rates.

## 10. Regression tests to keep (already RIGHT — do not break)

- "what is the cheapest youtube watch hour" → #2408 Views + Watch Hours, 441.00 ETB (the original fault, fixed).
- "cheapest tiktok views" → #1861-class pool (live cheapest TikTok views); "cheapest tiktok followers" → #1104 172.20 ETB; "cheapest telegram post views" → #6139 1.05 ETB; "cheapest facebook watch time" → watch-hours pool.
- "cheapest instagram followers" / "cheapest instagram channel members" / "cheapest facebook group members" (members = channel/group members).
- Reactions: FB ❤️ → #5105; TG 🙏 → #1723; generic TG reactions → #6534 Positive mix 5.46 ETB; IG ❤️ → honest no-service; FB 🙏 → honest no-service.
- "cheapest telegram followers" → NONE (no silent guess — but the reply must become the honest "doesn't exist" line, §5).
