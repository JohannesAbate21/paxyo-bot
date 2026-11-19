#!/usr/bin/env python3
"""Hourly auto-refill worker for @paxorder_bot (keep-above-target).

Runs ONE tick and exits (--once, the default), or ticks forever once an
hour (--loop). It is the server-side half of the auto-refill feature:
the bot side (bot.py, merged to main 83868ef) takes the user's setup
and keeps the refill in memory; this worker is what actually checks
the count every hour and tops the account back up to its target.

ONE TICK, PER ACTIVE REFILL (from GET /refills?status=active):
  1. Claim the row (POST /refills/{id}/claim). A claim held by a
     crashed run goes stale after 30 minutes and can be reclaimed,
     so two overlapping runs can never order twice for one refill.
  2. Run bot.py's auto_refill_check() on the record. The check is
     the exact function the bot's tests cover — this worker never
     reimplements the count chain, the budgets or the guards. A
     missing ENSEMBLEDATA_API_TOKEN just means that provider is
     skipped (count_tokens_from_env returns None for it); the
     chain falls through to the next provider and never crashes.
  3. On a "top_up" decision, place the order through the EXISTING
     order endpoints — POST /orders (GOP) or POST /orders/smm
     (SMM), chosen by service_provider() exactly like
     create_order_for_service() does. The server debits the
     balance atomically at placement, so this file never touches
     money itself. The idempotency key is deterministic per
     decision (refill id + current count + quantity): if the
     worker crashes after placing but before finishing, the next
     run replays to the same order instead of a second one.
  4. Tell the user in Telegram what happened (placed, or failed
     to confirm). Skip / cap / no-count decisions are silent —
     they are logged, not messaged.
  5. Finish the row (POST /refills/{id}/finish): releases the
     claim and persists last_count, last_check, count_usage,
     spent_today and spent_date, so the next hour (and any
     restart) picks up where this one left off. A finish runs
     even when the check or the order failed — a stuck 'checking'
     row would block the refill for 30 minutes.

IDEMPOTENCY: running the tick twice in an hour is safe. The
record's own last_count/last_check is a 30-minute durable cache,
the claim blocks overlap, the daily cap (1,000 ETB, from bot.py)
bounds spend, and the order idempotency key replays a
crash-retry to the same order.

RUNNING IT (see INSTALL.md for the full steps):
  Fly (primary): a second process in fly.toml ("worker") running
    `python refill_worker.py --loop` — one always-on small machine
    that ticks, sleeps 3600s, ticks again. A deploy updates it
    with the bot, so it can never go stale.
  Fly (cheaper alternative): a scheduled machine running
    `python refill_worker.py --once` every hour.
  By hand: `python refill_worker.py --once` (one tick, exits),
    `--dry-run` (check only: no orders, no finishes, no messages),
    `--refill-id N` (one refill only, for the live test),
    `--self-test` (fully offline: a canned TikTok page, no
    network, no server, no money — proves the worker runs the
    real bot check).

ENV (same secrets the bot already uses on Fly; nothing new is
hard-coded here, and no token is ever logged):
  PAXYO_API_BASE      default https://paxyo.et/api/bot
  BOT_API_SECRET      required (the X-Bot-Secret the server checks)
  TELEGRAM_BOT_TOKEN  required for the user's notification; when it
                      is absent the worker still checks and orders
                      but logs that it could not notify
  ENSEMBLEDATA_API_TOKEN  optional (absent = that provider skipped)
  SCRAPEEVERYTHING_API_KEY, YOUTUBE_API_KEY  optional, same rule
  COUNT_PROXY_URL     optional (Decodo residential proxy for the
                      own scraper; absent = direct fetching only)

EXIT CODES: 0 = tick done (per-refill failures are logged, not
fatal); 1 = the refill list itself could not be read; 2 =
missing BOT_API_SECRET. A 404 on the list means the server
endpoint is not installed yet — that logs one line and exits 0.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from bot import (  # noqa: E402  (bot.py is the deployed bot, same image)
        AUTO_REFILL_DAILY_CAP_ETB,
        auto_refill_check,
        count_proxy_from_env,
        count_tokens_from_env,
        service_provider,
    )
except ImportError as _exc:
    # This file ships next to bot.py in the bot image; run anywhere
    # else it cannot find the check it exists to run. Say so plainly
    # instead of dying on a bare traceback.
    print("refill_worker: cannot import bot.py (%s); run it from the bot repo" % _exc,
          file=sys.stderr)
    raise SystemExit(2)

log = logging.getLogger("refill_worker")

API_BASE = os.environ.get("PAXYO_API_BASE", "https://paxyo.et/api/bot").rstrip("/")
BOT_SECRET = (os.environ.get("BOT_API_SECRET") or "").strip()
TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
CHECK_INTERVAL_SECONDS = 3600  # one hour, the owner's choice
MAX_REFILLS_PER_TICK = 50  # stale-first list; the next hour gets the rest
STALE_CLAIM_MINUTES = 30  # server-side, mirrors api-auto-refill.php


# ------------------------------------------------------------------ server
class RefillApi:
    """Thin client for the refill endpoints (api-auto-refill.php).
    One httpx client per tick; the X-Bot-Secret header is on every
    call, exactly like PaxyoClient in bot.py."""

    def __init__(self):
        # trust_env=False, like PaxyoClient in bot.py: ignore any
        # proxy env vars so the client talks directly to paxyo.et.
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={"X-Bot-Secret": BOT_SECRET},
            timeout=30.0,
            trust_env=False,
        )

    async def close(self):
        await self._client.aclose()

    async def list_active(self):
        resp = await self._client.get("/refills", params={"status": "active"})
        if resp.status_code == 404:
            return None  # endpoint not installed yet — caller logs and stops
        resp.raise_for_status()
        data = resp.json()
        refills = data.get("refills", []) if isinstance(data, dict) else []
        return refills if isinstance(refills, list) else []

    async def get_one(self, refill_id):
        resp = await self._client.get(
            "/refills", params={"status": "all", "telegram_id": 0}
        )
        resp.raise_for_status()
        data = resp.json()
        for row in data.get("refills", []) if isinstance(data, dict) else []:
            if int(row.get("id") or 0) == int(refill_id):
                return row
        return None

    async def claim(self, refill_id):
        resp = await self._client.post(f"/refills/{refill_id}/claim", json={})
        resp.raise_for_status()
        return bool(resp.json().get("claimed"))

    async def finish(self, refill_id, fields):
        resp = await self._client.post(f"/refills/{refill_id}/finish", json=fields)
        resp.raise_for_status()
        return bool(resp.json().get("finished"))

    async def place_order(self, record, quantity, idempotency_key):
        """The existing order endpoints, exactly like
        create_order_for_service(): SMM services go to /orders/smm,
        everything else to /orders. The server computes the total
        from the live rate, debits atomically, and returns the
        placed order ({"order": {"id", "status", "total"}})."""
        service = record.get("service") or {}
        body = {
            "telegram_id": int(record["telegram_id"]),
            "service_id": int(service["service"]),
            "link": record["link"],
            "quantity": int(quantity),
            "idempotency_key": idempotency_key,
        }
        path = "/orders/smm" if service_provider(service) == "smm" else "/orders"
        resp = await self._client.post(path, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data.get("order", data) if isinstance(data, dict) else {}


# ------------------------------------------------------------------- notify
async def notify_user(telegram_id, text):
    """One plain-text Telegram message to the refill's owner. No
    parse mode (links in the text stay inert), no long dash (the
    bot's dash rule covers every @paxorder_bot reply). Returns
    True when Telegram accepted it; a failure is logged, never
    raised — a missed message must not fail the tick."""
    if not TELEGRAM_TOKEN:
        log.warning("no TELEGRAM_BOT_TOKEN: skipping notification to %s", telegram_id)
        return False
    try:
        from telegram import Bot

        bot = Bot(TELEGRAM_TOKEN)
        await bot.send_message(chat_id=int(telegram_id), text=text)
        return True
    except Exception as exc:  # noqa: BLE001  (notify must never break the tick)
        log.warning("notify to %s failed: %s", telegram_id, exc)
        return False


def _service_name(record):
    service = record.get("service") or {}
    return str(service.get("name") or "your service").strip()


# --------------------------------------------------------------------- tick
def _today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _record_for_check(row):
    """A DB row -> the bot-side record dict auto_refill_check()
    takes. Resets the daily spend when the UTC date rolled over:
    spent_today belongs to spent_date, and a new day starts at 0."""
    record = {
        "id": row.get("id"),
        "telegram_id": row.get("telegram_id"),
        "service": row.get("service") or {},
        "link": row.get("link") or "",
        "target": row.get("target"),
        "metric": row.get("metric"),
        "platform": row.get("platform"),
        "spent_today": row.get("spent_today") or 0,
        "spent_date": row.get("spent_date"),
        "last_count": row.get("last_count"),
        "last_check": row.get("last_check"),
        "count_usage": dict(row.get("count_usage") or {}),
    }
    today = _today_utc()
    if record["spent_date"] != today:
        record["spent_today"] = 0
        record["spent_date"] = today
    return record


def _finish_fields(decision):
    """What the worker persists after a check, whatever the
    decision was: the count, the usage budgets and the spend."""
    return {
        "last_count": decision.get("last_count"),
        "last_check": decision.get("last_check"),
        "count_usage": decision.get("count_usage") or {},
        "spent_today": decision.get("spent_today", 0),
        "spent_date": decision.get("spent_date"),
    }


async def check_one_refill(api, row, *, dry_run=False):
    """One refill, one hour: claim, check, maybe order, finish.
    Returns the decision dict. Never raises for one refill's
    failure — a bad row must not block the rest of the tick."""
    record = _record_for_check(row)
    refill_id = record["id"]
    try:
        claimed = await api.claim(refill_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("refill %s: claim failed: %s", refill_id, exc)
        return {"action": "error", "reason": "claim_failed"}
    if not claimed:
        log.info("refill %s: already claimed by another run, skipping", refill_id)
        return {"action": "skip", "reason": "already_claimed"}
    # Default decision: if the check itself raises, the claim is
    # still released by the finally below with the record's
    # persisted fields unchanged — one bad refill never blocks
    # the rest of the tick.
    decision = {
        "action": "error", "current": record.get("last_count"),
        "quantity": None, "cost": None, "provider": None,
        "reason": "check_failed",
        "count_usage": dict(record.get("count_usage") or {}),
        "last_count": record.get("last_count"),
        "last_check": record.get("last_check"),
        "spent_today": record.get("spent_today") or 0,
        "spent_date": record.get("spent_date"),
    }
    try:
        try:
            decision = await auto_refill_check(
                record,
                tokens=count_tokens_from_env(),
                proxy=count_proxy_from_env(),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("refill %s: check raised: %s", refill_id, exc)
            return decision
        # The check does not know about the date rollover: carry
        # the reset spend through to the finish call.
        decision["spent_today"] = record["spent_today"]
        decision["spent_date"] = record["spent_date"]
        action = decision.get("action")
        log.info(
            "refill %s: %s current=%s target=%s qty=%s cost=%s provider=%s reason=%s",
            refill_id, action, decision.get("current"), record.get("target"),
            decision.get("quantity"), decision.get("cost"),
            decision.get("provider"), decision.get("reason"),
        )
        if dry_run or action != "top_up":
            return decision
        # Deterministic per decision: a crash-retry after placing
        # but before finishing replays to the same order.
        key = "refill-%s-%s-%s" % (
            refill_id, decision.get("current"), decision.get("quantity"),
        )
        try:
            order = await api.place_order(
                record, int(decision["quantity"]), key,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("refill %s: top-up order failed: %s", refill_id, exc)
            await notify_user(
                int(record["telegram_id"]),
                "I could not confirm the top-up for your %s, so I will "
                "check again in an hour." % _service_name(record),
            )
            return decision
        order_id = order.get("id") or order.get("order_id") or "?"
        server_total = order.get("total", order.get("charge"))
        try:
            spent = round(float(server_total), 2)
        except (TypeError, ValueError):
            spent = decision.get("cost") or 0
        decision["spent_today"] = float(record["spent_today"] or 0) + float(spent)
        decision["order_id"] = order_id
        log.info("refill %s: top-up placed order %s for %s ETB", refill_id, order_id, spent)
        await notify_user(
            int(record["telegram_id"]),
            "Your %s dropped to %s (target %s), so I ordered %s more "
            "for %s ETB. I will check again in an hour."
            % (
                _service_name(record),
                f"{decision.get('current'):,}",
                f"{record.get('target'):,}",
                f"{decision.get('quantity'):,}",
                f"{float(spent):.2f}",
            ),
        )
        return decision
    finally:
        # Always release the claim and persist the check, even when
        # the check or the order failed — a stuck 'checking' row
        # would block the refill until the 30-minute stale window.
        if decision is not None and not dry_run:
            try:
                await api.finish(refill_id, _finish_fields(decision))
            except Exception as exc:  # noqa: BLE001
                log.warning("refill %s: finish failed: %s", refill_id, exc)


async def run_tick(api, *, dry_run=False, refill_id=None):
    """One hourly tick over every active refill. Returns the
    number of refills processed."""
    if refill_id is not None:
        row = await api.get_one(refill_id)
        rows = [row] if row else []
        if not rows:
            log.warning("refill %s: not found", refill_id)
            return 0
    else:
        rows = await api.list_active()
        if rows is None:
            log.info("refills endpoint not installed yet: nothing to do")
            return 0
    rows = rows[:MAX_REFILLS_PER_TICK]
    if len(rows) == MAX_REFILLS_PER_TICK:
        log.info("tick capped at %s refills; the next hour gets the rest",
                 MAX_REFILLS_PER_TICK)
    done = 0
    for row in rows:
        if str(row.get("status") or "active") != "active":
            continue
        await check_one_refill(api, row, dry_run=dry_run)
        done += 1
    log.info("tick done: %s refill(s) checked (dry_run=%s)", done, dry_run)
    return done


# ---------------------------------------------------------------- self-test
_CANNED_TIKTOK_PAGE = (
    '<html><head><title>Video</title></head><body>'
    '<script id="SIGI_STATE" type="application/json">'
    '{"ItemModule": {"7666462351436107015": {"stats": {"playCount": 14200}}}}'
    "</script></body></html>"
)


async def _self_test():
    """Fully offline proof the worker runs the real bot check: a
    canned TikTok page (playCount 14200) stands in for the network,
    no server, no money, no messages. Prints the decision as JSON.
    Target 15000, rate 18.90 ETB/1000: the drop is 800, so the
    decision must be top_up for 800 at 15.12 ETB."""
    async def fake_http_get(method, url, params=None, json_body=None,
                           headers=None, proxy=None, timeout=10.0):
        return 200, _CANNED_TIKTOK_PAGE

    record = {
        "id": "self-test",
        "telegram_id": 1,
        "service": {
            "service": 1665,
            "name": "TikTok Video Views",
            "rate_etb_per_1000": 18.90,
            "provider": "gop",
            "combined_id": "gop:1665",
        },
        "link": "https://vt.tiktok.com/ZSp349gen/",
        "target": 15000,
        "metric": "views",
        "platform": "tiktok",
        "spent_today": 0,
        "spent_date": _today_utc(),
        "last_count": None,
        "last_check": None,
        "count_usage": {},
    }
    decision = await auto_refill_check(
        record,
        tokens={"ensembledata": None, "socialholmes": None,
                "scrapeeverything": None, "youtube": None,
                "telegram": None},
        http_get=fake_http_get,
        proxy=None,
    )
    print(json.dumps(decision, indent=2, sort_keys=True))
    ok = (
        decision.get("action") == "top_up"
        and decision.get("current") == 14200
        and decision.get("quantity") == 800
        and decision.get("provider") == "own_scraper"
    )
    return 0 if ok else 1


# ---------------------------------------------------------------------- main
def _log_tick_http_error(log_fn, exc):
    """Log a tick HTTP error with a truncated response body plus the
    Server and Content-Type response headers, so a 403 from a layer
    in front of bot.php (hosting firewall / WAF) can be told apart
    from a bot.php JSON error. Only the response body and two
    response headers are logged — never request headers, and any
    occurrence of the bot secret in the body is redacted first."""
    resp = exc.response
    try:
        body = resp.text or ""
    except Exception:  # noqa: BLE001
        body = ""
    if BOT_SECRET and BOT_SECRET in body:
        body = body.replace(BOT_SECRET, "[redacted]")
    body = " ".join(body.split())[:500]
    log_fn(
        "tick failed: HTTP %s body=%r server=%r content-type=%r",
        resp.status_code, body,
        resp.headers.get("server", ""),
        resp.headers.get("content-type", ""),
    )


async def _amain(args):
    if args.self_test:
        return await _self_test()
    if not BOT_SECRET:
        log.error("BOT_API_SECRET is not set: cannot call the server")
        return 2
    api = RefillApi()
    try:
        if args.loop:
            while True:
                try:
                    await run_tick(api, dry_run=args.dry_run,
                                   refill_id=args.refill_id)
                except httpx.HTTPStatusError as exc:
                    _log_tick_http_error(log.warning, exc)
                except Exception as exc:  # noqa: BLE001
                    log.warning("tick failed: %s", exc)
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            await run_tick(api, dry_run=args.dry_run, refill_id=args.refill_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.info("refills endpoint not installed yet: nothing to do")
                return 0
            _log_tick_http_error(log.error, exc)
            return 1
        except Exception as exc:  # noqa: BLE001
            log.error("tick failed: %s", exc)
            return 1
        return 0
    finally:
        await api.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="Paxyo auto-refill hourly worker")
    parser.add_argument("--once", action="store_true",
                        help="run one tick and exit (default)")
    parser.add_argument("--loop", action="store_true",
                        help="tick once an hour, forever (Fly worker process)")
    parser.add_argument("--dry-run", action="store_true",
                        help="check only: no orders, no finishes, no messages")
    parser.add_argument("--refill-id", type=int, default=None,
                        help="check one refill only (live test)")
    parser.add_argument("--self-test", action="store_true",
                        help="offline proof: canned page, no network, no money")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
