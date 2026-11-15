<?php
// ============================================================================
// Provider drip-feed for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot: customization #15 ("spread
// 10,000 views over 2 days, not all at once").
//
// PROVIDER SUPPORT — CHECKED FIRST (15 Nov 2026, before building):
// both providers support drip-feed through the standard SMM panel
// API v2: the normal `add` call with `runs` (>= 2) and `interval`
// (gap in minutes) added. `quantity` is the PER-RUN quantity; the
// total charged is quantity x runs, up front. GodOfPanel: 6,297 of
// 7,175 services carry `dripfeed: true` in the live catalogue
// snapshot (workspace/custom-connectors/custom.godofpanel/
// services-2026-11-12.json); SMM Social Media: only 14 of 3,301
// (workspace/custom-connectors/custom.smmsocialmedia/
// services-2026-11-15.json) — in practice drip-feed is a GodOfPanel
// feature. Evidence: Boostero API docs (https://boostero.com/api,
// "Drip-feed" section), flashypanels, orbismm; GodOfPanel's own
// API doc page sits behind login, so the parameter names are
// confirmed via the v2 convention plus GodOfPanel's own live
// `dripfeed` flags. Sending drip-feed params to a service WITHOUT
// the flag returns an error — the flag MUST be checked first, and
// this file does (see the splice). One small live test order (under
// the 5 ETB cap, with William's approval) is still needed as final
// proof that the provider accepts the params end to end.
//
// WHY A SERVER CHANGE IS NEEDED: the bot cannot mint money or fake
// a drip. The provider charges quantity x runs up front, and the
// server debits the user's Paxyo balance atomically at placement —
// so the server must compute the total from the per-run quantity
// x runs, check the balance against THAT total, debit it, store
// the drip markers on the order row, and forward runs/interval to
// the provider. The bot never sends a total and never fakes a drip
// with separate orders. When the fields are absent, both order
// endpoints behave byte-for-byte as they do today.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/orders/dripfeed-status
//     -> {"ok":true,"dripfeed_live":true}
//     The bot probes this before ever showing a drip-feed Confirm
//     card: when the endpoint is not installed yet it 404s, the bot
//     treats drip-feed as not live, and tells the customer honestly
//     instead of placing a normal order for a drip request. The
//     reply is deliberately tiny — the bot only needs to know the
//     endpoint exists.
//
//   SPLICE into POST /orders (bot.php) and POST /orders/smm
//   (api-order-smm.php): both accept two OPTIONAL fields — runs,
//   interval — validated and applied as described in the SPLICE
//   section at the bottom of this file. Nothing about the existing
//   order flow changes when the fields are absent.
//
// MONEY FLOW (example: 10,000 views over 2 days):
//   Customer confirms 10,000 views for 420.00 ETB, spread over
//   2 days. The bot sends quantity 1000, runs 10, interval 288
//   (10 runs of 1,000, 288 minutes apart — 2 days total).
//   The server computes total = rate x (1000 x 10) / 1000 = 420.00,
//   checks the balance against 420.00, debits 420.00 up front, and
//   stores the order row with quantity 10000 (the TOTAL the
//   customer ordered) plus drip_runs 10, drip_interval 288,
//   drip_per_run_qty 1000. The provider is called with
//   quantity 1000, runs 10, interval 288. The provider delivers
//   1,000, waits 288 minutes, delivers the next 1,000, and so on.
//   A provider failure refunds the full 420.00 debit — the user
//   was only ever debited once, up front.
//
// TABLE (orders gains three NULLABLE columns, added automatically,
// SHOW COLUMNS guards — safe to run twice, and safe when the
// columns already exist):
//   drip_runs        INT — the number of runs the provider was asked for.
//   drip_interval    INT — the gap in minutes between runs.
//   drip_per_run_qty INT — the quantity of one run (the provider's
//                    quantity). NULL in all three means a normal order.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-order-dripfeed.php   (this file must pass)
//   2. Apply the SPLICE edits at the bottom of this file to bot.php
//      (POST /orders) and to server/api-order-smm.php
//      (bot_smm_place_order + smm_place) — the SMM edits quote the
//      workspace copy of api-order-smm.php line for line; the bot.php
//      edits follow the same pattern and must be matched to bot.php's
//      actual local variable names (bot.php lives on the server only
//      — there is no workspace copy to quote).
//   3. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block). Do the same for api-order-smm.php ONLY if that file
//      is spliced into bot.php the same way — if it is a standalone
//      include, the dispatch lives in bot.php alone.
//   4. Re-run php -l on bot.php and on api-order-smm.php after the
//      splices. A parse error in bot.php breaks the whole Bot API.
//   5. Run the LIVE CURL TEST at the bottom of this file.
// ============================================================================

// --- drip tables + columns (self-contained, drp_ prefix) ---

function drp_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function drp_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function drp_add_order_columns($db) {
    // SHOW COLUMNS guards: safe to run on every order call, and
    // safe when the columns already exist (an ALTER on an existing
    // column would error, so each column is checked first).
    $have = [];
    $res = $db->query("SHOW COLUMNS FROM orders");
    if ($res) {
        while ($row = $res->fetch_assoc()) {
            $have[strtolower((string)$row['Field'])] = true;
        }
        $res->close();
    }
    if (empty($have['drip_runs'])) {
        $db->query("ALTER TABLE orders ADD COLUMN drip_runs INT NULL");
    }
    if (empty($have['drip_interval'])) {
        $db->query("ALTER TABLE orders ADD COLUMN drip_interval INT NULL");
    }
    if (empty($have['drip_per_run_qty'])) {
        $db->query("ALTER TABLE orders ADD COLUMN drip_per_run_qty INT NULL");
    }
}

// --- the drip fields, read + validated (shared by both splices) ---
// Returns [runs, interval, error]: runs/interval are null when the
// request carries no drip fields at all (a normal order); error is
// null on success, otherwise a message for the handler's 400.
// The bot enforces interval >= 30 and an even split before it ever
// sends these fields; the server enforces the provider's own floor
// (runs >= 2, interval >= 1) and never trusts the bot's arithmetic.

function drp_read_fields($in) {
    $has_runs = isset($in['runs']) && $in['runs'] !== null && $in['runs'] !== '';
    $has_interval = isset($in['interval']) && $in['interval'] !== null && $in['interval'] !== '';
    if (!$has_runs && !$has_interval) {
        return [null, null, null];
    }
    if (!$has_runs || !$has_interval) {
        return [null, null, 'runs and interval must be sent together.'];
    }
    if (!is_numeric($in['runs']) || (int)$in['runs'] < 2) {
        return [null, null, 'runs must be an integer of at least 2.'];
    }
    if (!is_numeric($in['interval']) || (int)$in['interval'] < 1) {
        return [null, null, 'interval must be an integer of at least 1 minute.'];
    }
    return [(int)$in['runs'], (int)$in['interval'], null];
}

// --- the status probe ---

function bot_dripfeed_status() {
    // GET /orders/dripfeed-status -> the bot's capability probe. It
    // also ensures the columns exist, so the first probe after
    // install prepares the schema (the order endpoints call the
    // same ensure function, so a probe is never required).
    $db = drp_db();
    if ($db === null) drp_fail(500, 'Database is not available.');
    drp_add_order_columns($db);
    bot_ok(['ok' => true, 'dripfeed_live' => true]);
}

// ============================================================================
// SPLICE — apply these edits to the order endpoints. The SMM edits
// quote the workspace copy of server/api-order-smm.php (941 lines)
// line for line; the bot.php edits follow the same pattern and must
// be matched to bot.php's actual local variable names (bot.php lives
// on the server only — there is no workspace copy to quote).
//
// The pattern is the same in both endpoints:
//   (a) read runs/interval with drp_read_fields, right after the
//       quantity is read — 400 when only one is sent, or when the
//       values are below the provider's floor;
//   (b) check the service's dripfeed flag (the live services list
//       the handler already fetched carries it — $svc['dripfeed']
//       on the SMM side; the same field on the GOP services list)
//       — 400 "This service does not offer drip-feed." when it is
//       false. NEVER forward drip params to a service without the
//       flag: the provider returns an error and the order fails
//       after the debit. (The bot also checks the flag before
//       showing the card, so this is the second line of defence.)
//   (c) the per-run quantity is validated against min/max and the
//       multiple-of-10 rule, exactly as quantity is today; the
//       TOTAL quantity is per-run x runs, and the total charged is
//       rate x total / 1000 — the balance check and the debit use
//       THAT total, never the per-run total;
//   (d) store the order row with quantity = the TOTAL quantity
//       (what the customer ordered) plus the three drip columns;
//   (e) call the provider with quantity = the PER-RUN quantity
//       plus runs + interval;
//   (f) on provider failure refund the FULL total (the whole debit).
//
// --- SMM: server/api-order-smm.php, bot_smm_place_order() ---
//
// EDIT 1 — after the quantity is read (line ~588):
//   $quantity = (int)($in['quantity'] ?? 0);
//   if ($quantity <= 0) smm_fail(400, 'quantity must be positive.');
//   if ($quantity % 10 !== 0) smm_fail(400, 'quantity must be a multiple of 10.');
// becomes:
//   $quantity = (int)($in['quantity'] ?? 0);
//   if ($quantity <= 0) smm_fail(400, 'quantity must be positive.');
//   if ($quantity % 10 !== 0) smm_fail(400, 'quantity must be a multiple of 10.');
//   // Drip-feed (api-order-dripfeed.php): two OPTIONAL fields from
//   // the bot. quantity is the PER-RUN quantity; the total charged
//   // is quantity x runs, up front. Both fields or neither.
//   list($drip_runs, $drip_interval, $drip_error) = drp_read_fields($in);
//   if ($drip_error !== null) smm_fail(400, $drip_error);
//   $drip_total_qty = $drip_runs !== null ? $quantity * $drip_runs : $quantity;
//
// EDIT 2 — after the service is found and the rate read (line ~627),
// right after the min/max check (line ~633):
//   $min = (int)($svc['min'] ?? 0);
//   $max = (int)($svc['max'] ?? 0);
//   if (($min > 0 && $quantity < $min) || ($max > 0 && $quantity > $max)) {
//       smm_fail(400, 'quantity must be between ' . $min . ' and ' . $max . ' for this service.');
//   }
// becomes (the min/max check already ran on the per-run quantity
// above it, unchanged):
//   $min = (int)($svc['min'] ?? 0);
//   $max = (int)($svc['max'] ?? 0);
//   if (($min > 0 && $quantity < $min) || ($max > 0 && $quantity > $max)) {
//       smm_fail(400, 'quantity must be between ' . $min . ' and ' . $max . ' for this service.');
//   }
//   // Drip-feed: the service must offer it, or the provider will
//   // refuse the order after the debit. The live services list
//   // carries the flag (see the service shape at the top of this
//   // file: "dripfeed":bool). Only 14 of 3,301 SMM services have
//   // it — a drip order on any other SMM service is refused here,
//   // before any money moves.
//   if ($drip_runs !== null && empty($svc['dripfeed'])) {
//       smm_fail(400, 'This service does not offer drip-feed.');
//   }
//   drp_add_order_columns($db);
//
// EDIT 3 — the total (line ~640):
//   $total = round(((float)$rate_inr / SMM_INR_PER_USD) * SMM_SELL_MULTIPLIER_ETB * $quantity / 1000, 2);
//   if ($total < 0) $total = 0.0;
//   if ($balance < $total) smm_fail(409, 'Insufficient balance.');
// becomes:
//   // Drip-feed: the total is the per-run quantity x runs — the
//   // provider charges the whole drip up front.
//   $total = round(((float)$rate_inr / SMM_INR_PER_USD) * SMM_SELL_MULTIPLIER_ETB * $drip_total_qty / 1000, 2);
//   if ($total < 0) $total = 0.0;
//   if ($balance < $total) smm_fail(409, 'Insufficient balance.');
//
// EDIT 4 — the order insert (line ~660):
//   $stmt = $db->prepare("INSERT INTO orders (telegram_id, service_id, link, quantity, total, status, idempotency_key) VALUES (?, ?, ?, ?, ?, 'pending', ?)");
//   $stmt->bind_param('iisids', $telegram_id, $service_id, $link, $quantity, $total, $key);
// becomes:
//   // Drip-feed: the row stores the TOTAL quantity the customer
//   // ordered, plus the drip markers — so the mini-app history
//   // shows one 10,000 order, not ten 1,000 orders.
//   $stmt = $db->prepare("INSERT INTO orders (telegram_id, service_id, link, quantity, total, status, idempotency_key, drip_runs, drip_interval, drip_per_run_qty) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)");
//   $stmt->bind_param('iisidsiii', $telegram_id, $service_id, $link, $drip_total_qty, $total, $key, $drip_runs, $drip_interval, $quantity);
//
// EDIT 5 — the provider call (line ~685):
//   $placed = smm_place($service_id, $link, $quantity);
// becomes:
//   $placed = smm_place($service_id, $link, $quantity, $drip_runs, $drip_interval);
//
// EDIT 6 — smm_place() itself (line ~361):
//   function smm_place($service_id, $link, $quantity) {
//       if (smm_provider_key() === null) {
//           return ['order_id' => null, 'error' => 'Provider is not configured.'];
//       }
//       $res = smm_provider_raw('add', ['service' => $service_id, 'link' => $link, 'quantity' => $quantity]);
// becomes:
//   function smm_place($service_id, $link, $quantity, $runs = null, $interval = null) {
//       if (smm_provider_key() === null) {
//           return ['order_id' => null, 'error' => 'Provider is not configured.'];
//       }
//       // Drip-feed: quantity is the per-run quantity; runs and
//       // interval ride along only when both are set. The provider
//       // charges quantity x runs up front.
//       $params = ['service' => $service_id, 'link' => $link, 'quantity' => $quantity];
//       if ($runs !== null && $interval !== null) {
//           $params['runs'] = (int)$runs;
//           $params['interval'] = (int)$interval;
//       }
//       $res = smm_provider_raw('add', $params);
// (The refund on provider failure already refunds $total — which
// is now the full drip total — so no edit is needed there. The
// order reply already returns 'total' => $total, the full total.)
//
// --- GOP: public_html/api/bot.php, POST /orders ---
//
// Apply the same six edits to the GOP order handler, matching
// bot.php's actual locals: read runs/interval with drp_read_fields
// after the quantity is read; check the service's dripfeed flag
// on the GOP services list the handler already fetched for the
// live rate (fail 400 "This service does not offer drip-feed."
// when it is false — 6,297 of 7,175 GOP services have it); compute
// the total from the per-run quantity x runs and debit that;
// insert the order row with the total quantity plus the three drip
// columns; call the provider's `add` with quantity = the per-run
// quantity plus runs + interval (the GOP provider call takes the
// same three params — see the SMM smm_place edit above for the
// shape); refund the full total on provider failure. When the
// fields are absent the handler must behave byte-for-byte as it
// does today. The split-cover fields (split_group_id, split_part,
// confirmed_total_etb, paxyo_cover_etb) and the drip fields never
// ride on the same order: a drip order is placed whole, never
// split-tested, so the two splices never interact — but both must
// be applied to the same total/debit/insert lines, so apply them
// together and re-run php -l after each.
//
// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'orders/dripfeed-status' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_dripfeed_status(); }
//
// (Add the same bot_rate_limit(...) call the other GET endpoints use
// to that dispatch line — copy the exact call from the balance
// handler. The bot calls this at most once per process — it caches
// the answer — so the probe costs one request per deploy.)
//
// LIVE CURL TEST — read this whole block before running it. The test
// places a REAL small drip order on the operating account, with
// William's approval, and checks the drip math on the balance. It
// uses a cheap GodOfPanel service WITH the dripfeed flag, a small
// quantity, and a short interval, so the totals stay under 5 ETB.
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 0. Pick a service first: it must have dripfeed:true in the
//   #    live catalogue, a low rate, and a low minimum. From the
//   #    snapshot (workspace/custom-connectors/custom.godofpanel/
//   #    services-2026-11-12.json) find one, then confirm the flag
//   #    live — the snapshot is from 12 Nov and flags can change:
//   #    (use the GodOfPanel connector to fetch the live services
//   #    list and grep the service id for "dripfeed": true.)
//   # 1. The probe answers live:
//   curl -s "https://paxyo.et/api/bot/orders/dripfeed-status" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"dripfeed_live":true}
//   # 2. runs without interval is refused (no order, no debit):
//   curl -s -X POST https://paxyo.et/api/bot/orders \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"service_id":<ID>,"link":"https://www.tiktok.com/@x/video/1","quantity":100,"runs":2,"idempotency_key":"drip-test-half"}'
//   -> expect 400 ("runs and interval must be sent together").
//   # 3. A service WITHOUT the dripfeed flag is refused (no order,
//   #    no debit) — pick any cheap service with dripfeed:false:
//   curl -s -X POST https://paxyo.et/api/bot/orders \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"service_id":<NO-FLAG-ID>,"link":"https://www.tiktok.com/@x/video/1","quantity":100,"runs":2,"interval":30,"idempotency_key":"drip-test-noflag"}'
//   -> expect 400 ("This service does not offer drip-feed.").
//   # 4. A real drip order places and debits quantity x runs:
//   #    check the balance before and after — it must fall by the
//   #    FULL total (per-run qty x runs), not by one run:
//   curl -s -X POST https://paxyo.et/api/bot/orders \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"service_id":<FLAG-ID>,"link":"https://www.tiktok.com/@x/video/1","quantity":100,"runs":2,"interval":30,"idempotency_key":"drip-test-ok"}'
//   -> expect the order row, with the row carrying drip_runs 2,
//      drip_interval 30, drip_per_run_qty 100, quantity 200, and
//      total = the rate for 200; the balance fell by that total.
//   # 5. The provider order exists and is a drip (check the
//   #    provider order id on the row, then the provider status):
//   mysql -e "SELECT id, quantity, total, drip_runs, drip_interval, drip_per_run_qty FROM orders WHERE id=<the new order id>;"
//   -> expect quantity 200, drip_runs 2, drip_interval 30,
//      drip_per_run_qty 100.
//   Then leave the test order running — it is the honest record of
//   what happened, and the two runs will deliver over the next
//   hour. Do NOT delete the order row.
// ============================================================================
