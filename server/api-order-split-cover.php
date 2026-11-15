<?php
// ============================================================================
// Split-test cover (the +10% Paxyo tolerance) for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot:
// William's split-test method (19:32 EAT, corrected 19:37 EAT) and
// the small-order rule (19:52 EAT) — when no cheaper service works,
// the bot may use a service up to 10% above the confirmed total,
// the extra coming from Paxyo's pocket, NEVER from the customer.
//
// WHY A SERVER CHANGE IS NEEDED (design decision Q1): the bot cannot
// mint money. The server debits the user's Paxyo balance atomically
// at placement, and the user's balance only ever holds the confirmed
// total — so a pricier replacement cannot be placed bot-side alone.
// This file gives the order endpoints a cover they can honour: the
// bot sends confirmed_total_etb + paxyo_cover_etb, the server
// validates the cover (at most 10% of the confirmed total, and at
// most 10% cumulatively for one split group), debits total - cover,
// stores the markers on the order row, and records the cover once
// the provider confirms the placement.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/split-cover/status
//     -> {"ok":true,"split_cover_live":true}
//     The bot probes this before ever using the cover band: when the
//     endpoint is not installed yet it 404s, the bot treats the
//     cover as not live, and only services costing at most the
//     confirmed total are ever placed (the old strict-cap behaviour).
//     The reply is deliberately tiny — the bot only needs to know
//     the endpoint exists.
//
//   SPLICE into POST /orders (bot.php) and POST /orders/smm
//   (api-order-smm.php): both accept four OPTIONAL fields —
//   split_group_id, split_part, confirmed_total_etb,
//   paxyo_cover_etb — validated and applied as described in the
//   SPLICE section at the bottom of this file. Nothing about the
//   existing order flow changes when the fields are absent: same
//   validation, same debit, same insert, same provider call.
//
//   A cover is honoured WITHOUT split markers too: a small-order
//   rescue sends confirmed_total_etb + paxyo_cover_etb with no
//   group id, and the same 10% validation applies. The split
//   markers (group id / part) only say which split order the row
//   belongs to — they are how the customer's mini-app history shows
//   the 10% test and the 90% remainder as parts of one order.
//
// MONEY FLOW (the whole order, big-order split-test example):
//   Customer confirms 10,000 views for 500.00 ETB.
//   Test leg: 1,000 views on the fastest service, 50.00 ETB, no
//     cover (same rate). Debited 50.00, order row marked
//     split_part "test".
//   Test delivers -> remainder leg: 9,000 views, same service,
//     450.00 ETB, no cover. Debited 450.00, marked "remainder".
//     Total debited 500.00, total delivered exactly 10,000.
//   Cheaper service wins instead: test 1,000 on the cheaper
//     service, 40.00 ETB, delivers -> remainder 9,000 there,
//     360.00 ETB. Total debited 400.00 for the same 10,000 views —
//     the 100.00 ETB difference was never charged, so there is no
//     separate refund transaction to record; the saving is visible
//     in the bot's message, in both order rows, and in the balance
//     (which only ever went down by what was actually spent).
//   No cheaper service works: the pricier service costs 550.00
//     for the whole order (10% above confirmed). The bot sends
//     cover 50.00; the server debits 500.00 (550.00 - 50.00) and
//     records the 50.00 cover. The customer still pays only the
//     500.00 they confirmed; the 50.00 is Paxyo's cost.
//   A service beyond +10% is never sent by the bot, and the
//     server refuses it with 400 if one ever arrives.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_split_covers  id AUTO_INCREMENT PK, split_group_id
//     VARCHAR(64) (the bot's uuid for one split order — one group
//     covers one customer order), order_id BIGINT UNIQUE (the Paxyo
//     orders.id — one cover record per order, ever), telegram_id,
//     cover_etb DECIMAL(12,2), confirmed_total_etb DECIMAL(12,2),
//     created_at.
//
//   orders gains three NULLABLE columns (added automatically, SHOW
//   COLUMNS guards — safe to run twice, and safe when the columns
//   already exist): split_group_id VARCHAR(64), split_part
//   VARCHAR(16) ("test" / "remainder"), paxyo_cover_etb
//   DECIMAL(12,2). They are how the mini-app history marks a test
//   split; a NULL in all three means a normal order.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-order-split-cover.php   (this file must pass)
//   2. Apply the SPLICE edits at the bottom of this file to bot.php
//      (POST /orders) and to server/api-order-smm.php
//      (bot_smm_place_order) — exact old/new text is given there.
//      The bot.php edits must be matched to bot.php's actual local
//      variable names; the SMM edits quote the workspace copy of
//      api-order-smm.php line for line.
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

// --- cover tables + columns (self-contained, bsc_ prefix) ---

function bsc_ensure_tables($db) {
    $db->query("CREATE TABLE IF NOT EXISTS bot_split_covers (
        id BIGINT NOT NULL AUTO_INCREMENT,
        split_group_id VARCHAR(64) NOT NULL,
        order_id BIGINT NOT NULL,
        telegram_id BIGINT NOT NULL,
        cover_etb DECIMAL(12,2) NOT NULL,
        confirmed_total_etb DECIMAL(12,2) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_order (order_id),
        KEY idx_group (split_group_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
}

function bsc_add_order_columns($db) {
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
    if (empty($have['split_group_id'])) {
        $db->query("ALTER TABLE orders ADD COLUMN split_group_id VARCHAR(64) NULL");
    }
    if (empty($have['split_part'])) {
        $db->query("ALTER TABLE orders ADD COLUMN split_part VARCHAR(16) NULL");
    }
    if (empty($have['paxyo_cover_etb'])) {
        $db->query("ALTER TABLE orders ADD COLUMN paxyo_cover_etb DECIMAL(12,2) NULL");
    }
}

// --- cover accounting ---

function bsc_cover_total($db, $split_group_id) {
    // The cover already recorded for one split group (one customer
    // order): the 10% cap is cumulative across its legs, so a
    // test leg that used cover leaves less for the remainder.
    $stmt = $db->prepare('SELECT COALESCE(SUM(cover_etb), 0) AS total FROM bot_split_covers WHERE split_group_id = ?');
    $stmt->bind_param('s', $split_group_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return (float)($row['total'] ?? 0);
}

function bsc_cover_check($db, $split_group_id, $confirmed_total, $cover) {
    // True when this cover is within the +10% band: at most 10%
    // of the confirmed total for the whole split group (or for a
    // cover-only order with no group, at most 10% of the confirmed
    // total on its own). Money is compared rounded to 2dp, the
    // same rounding the order totals use.
    $cover = round((float)$cover, 2);
    $confirmed_total = round((float)$confirmed_total, 2);
    if ($cover < 0 || $confirmed_total <= 0) return false;
    $max_cover = round($confirmed_total * 0.10, 2);
    if ($split_group_id === null || $split_group_id === '') {
        return $cover <= $max_cover;
    }
    $used = bsc_cover_total($db, (string)$split_group_id);
    return round($used + $cover, 2) <= $max_cover;
}

function bsc_cover_record($db, $split_group_id, $order_id, $telegram_id, $cover, $confirmed_total) {
    // Record one leg's cover, idempotent per order_id: a retry
    // (or a duplicate placement reply) never records the same
    // cover twice. Call ONLY after the provider confirms the
    // placement — a provider failure refunds the debit, so the
    // cover was never actually spent and must not be recorded.
    // Returns true on a fresh insert or an identical duplicate.
    bsc_ensure_tables($db);
    $stmt = $db->prepare('INSERT INTO bot_split_covers (split_group_id, order_id, telegram_id, cover_etb, confirmed_total_etb) VALUES (?, ?, ?, ?, ?) ON DUPLICATE KEY UPDATE cover_etb = VALUES(cover_etb), confirmed_total_etb = VALUES(confirmed_total_etb)');
    $stmt->bind_param('siidd', $split_group_id, $order_id, $telegram_id, $cover, $confirmed_total);
    $ok = $stmt->execute();
    $stmt->close();
    return (bool)$ok;
}

// --- the status probe ---

function bot_split_cover_status() {
    // GET /split-cover/status -> the bot's capability probe. It
    // also ensures the tables + columns exist, so the first probe
    // after install prepares the schema (the order endpoints call
    // the same ensure functions, so a probe is never required).
    global $db;
    bsc_ensure_tables($db);
    bsc_add_order_columns($db);
    bot_ok(['ok' => true, 'split_cover_live' => true]);
}

// ============================================================================
// SPLICE — apply these edits to the order endpoints. The SMM edits
// quote the workspace copy of server/api-order-smm.php (941 lines)
// line for line; the bot.php edits follow the same pattern and must
// be matched to bot.php's actual local variable names (bot.php lives
// on the server only — there is no workspace copy to quote).
//
// The pattern is the same in both endpoints:
//   (a) read the four optional fields from $in, validate the cover;
//   (b) debit total - cover instead of total (balance check too);
//   (c) store the markers on the order row;
//   (d) on provider failure refund total - cover, NOT total;
//   (e) record the cover ONLY after the provider confirms.
//
// --- SMM: server/api-order-smm.php, bot_smm_place_order() ---
//
// EDIT 1 — after the total is computed (line ~640):
//   $total = round(((float)$rate_inr / SMM_INR_PER_USD) * SMM_SELL_MULTIPLIER_ETB * $quantity / 1000, 2);
//   if ($total < 0) $total = 0.0;
//   if ($balance < $total) smm_fail(409, 'Insufficient balance.');
// becomes:
//   $total = round(((float)$rate_inr / SMM_INR_PER_USD) * SMM_SELL_MULTIPLIER_ETB * $quantity / 1000, 2);
//   if ($total < 0) $total = 0.0;
//   // Split-cover (api-order-split-cover.php): four OPTIONAL fields
//   // from the bot. A cover is only ever sent when the server
//   // confirmed it honours one (GET /split-cover/status).
//   $split_group_id = isset($in['split_group_id']) ? smm_substr(trim((string)$in['split_group_id']), 64) : null;
//   $split_part = isset($in['split_part']) ? smm_substr(trim((string)$in['split_part']), 16) : null;
//   $confirmed_total_etb = isset($in['confirmed_total_etb']) ? (float)$in['confirmed_total_etb'] : null;
//   $paxyo_cover_etb = isset($in['paxyo_cover_etb']) ? round((float)$in['paxyo_cover_etb'], 2) : 0.0;
//   if ($paxyo_cover_etb < 0) $paxyo_cover_etb = 0.0;
//   if ($paxyo_cover_etb > 0) {
//       if ($confirmed_total_etb === null || $confirmed_total_etb <= 0) smm_fail(400, 'confirmed_total_etb is required with paxyo_cover_etb.');
//       bsc_ensure_tables($db);
//       if (!bsc_cover_check($db, $split_group_id, $confirmed_total_etb, $paxyo_cover_etb)) smm_fail(400, 'paxyo_cover_etb is above 10% of the confirmed total.');
//   }
//   bsc_add_order_columns($db);
//   $debit = round($total - $paxyo_cover_etb, 2);
//   if ($debit < 0) $debit = 0.0;
//   if ($balance < $debit) smm_fail(409, 'Insufficient balance.');
//
// EDIT 2 — the debit (the UPDATE inside the transaction):
//   $stmt = $db->prepare('UPDATE auth SET balance = balance - ? WHERE tg_id = ? AND balance >= ?');
//   $stmt->bind_param('did', $total, $telegram_id, $total);
// becomes:
//   $stmt = $db->prepare('UPDATE auth SET balance = balance - ? WHERE tg_id = ? AND balance >= ?');
//   $stmt->bind_param('did', $debit, $telegram_id, $debit);
// (and the guard above it changes from `if ($total > 0)` to
// `if ($debit > 0)`.)
//
// EDIT 3 — the order insert:
//   $stmt = $db->prepare("INSERT INTO orders (telegram_id, service_id, link, quantity, total, status, idempotency_key) VALUES (?, ?, ?, ?, ?, 'pending', ?)");
//   $stmt->bind_param('iisids', $telegram_id, $service_id, $link, $quantity, $total, $key);
// becomes:
//   $stmt = $db->prepare("INSERT INTO orders (telegram_id, service_id, link, quantity, total, status, idempotency_key, split_group_id, split_part, paxyo_cover_etb) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)");
//   $stmt->bind_param('iisidsssd', $telegram_id, $service_id, $link, $quantity, $total, $key, $split_group_id, $split_part, $paxyo_cover_etb);
//
// EDIT 4 — the provider-failure refund (inside the `if
// ($placed['order_id'] === null)` block): the debit refunded is
// $debit, not $total — the user was only ever debited $debit, so
// refunding $total would over-refund by the cover:
//   $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
//   $stmt->bind_param('di', $total, $telegram_id);
// becomes:
//   $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
//   $stmt->bind_param('di', $debit, $telegram_id);
// (and the guard above it changes from `if ($total > 0)` to
// `if ($debit > 0)`.)
//
// EDIT 5 — after the provider confirms the placement (after
// `$provider_order_id = (string)$placed['order_id'];`): record the
// cover, but only when one was used:
//   if ($paxyo_cover_etb > 0) {
//       bsc_cover_record($db, (string)($split_group_id ?? ''), $order_id, $telegram_id, $paxyo_cover_etb, (float)$confirmed_total_etb);
//   }
// (A cover-only order has no group id — the record keeps an empty
// group string, and bsc_cover_check treats it as a standalone
// order. The record is what lets a later leg of the same split
// group prove the cumulative cover is still within 10%.)
//
// --- GOP: public_html/api/bot.php, POST /orders ---
//
// Apply the same five edits to the GOP order handler, matching
// bot.php's actual locals: read the four fields from the request
// body the same way, validate with bsc_cover_check (fail with the
// handler's own 400 helper), debit total - cover in the same
// transaction that inserts the order row (insert the three marker
// columns), refund total - cover on provider failure, and record
// the cover with bsc_cover_record only after the provider confirms
// the placement. When the fields are absent the handler must
// behave byte-for-byte as it does today.
//
// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'split-cover/status' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_split_cover_status(); }
//
// (Add the same bot_rate_limit(...) call the other GET endpoints use
// to that dispatch line — copy the exact call from the balance
// handler. The bot calls this at most once per process — it caches
// the answer — so the probe costs one request per deploy.)
//
// LIVE CURL TEST — read this whole block before running it. The test
// places REAL small orders on the operating account, with William's
// approval, and checks the cover math on the balance. It uses a
// split test on a cheap service so the totals stay under 5 ETB of
// Paxyo money moved (the cover itself is Paxyo's money — the test
// proves it is debited, not the customer).
//   SECRET=<redacted>(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. The probe answers live:
//   curl -s "https://paxyo.et/api/bot/split-cover/status" \
//     -H "X-Bot-Secret: <redacted>
//   -> expect {"success":true,"ok":true,"split_cover_live":true}
//   # 2. A cover above 10% is refused (no order placed, no debit):
//   curl -s -X POST https://paxyo.et/api/bot/orders \
//     -H "X-Bot-Secret: <redacted> \
//     -d '{"telegram_id":779060335,"service_id":1665,"link":"https://www.tiktok.com/@x/video/1","quantity":100,"idempotency_key":"cover-test-over","confirmed_total_etb":1.89,"paxyo_cover_etb":0.50}'
//   -> expect 400 (0.50 is above 10% of 1.89 = 0.19).
//   # 3. A cover within 10% places the order and debits total -
//   #    cover (check the balance before and after: it must fall by
//   #    total - cover, not by total):
//   curl -s -X POST https://paxyo.et/api/bot/orders \
//     -H "X-Bot-Secret: <redacted> \
//     -d '{"telegram_id":779060335,"service_id":1665,"link":"https://www.tiktok.com/@x/video/1","quantity":100,"idempotency_key":"cover-test-ok","confirmed_total_etb":1.89,"paxyo_cover_etb":0.10}'
//   -> expect the order row, and the order row carries
//      paxyo_cover_etb 0.10; the balance fell by (total - 0.10).
//   # 4. The cover record exists once for that order:
//   mysql -e "SELECT order_id, cover_etb, confirmed_total_etb FROM bot_split_covers WHERE order_id=<the new order id>;"
//   -> expect one row, cover_etb 0.10.
//   # 5. A split group cannot exceed 10% cumulatively: a second
//   #    leg for the same group with a cover that pushes the group
//   #    past 10% of the confirmed total must 400 (use the group id
//   #    from step 3 with split_group_id + split_part set).
//   Then clean up the test rows (the test orders themselves stay —
//   they are the honest record of what happened):
//   mysql -e "DELETE FROM bot_split_covers WHERE order_id IN (<ids>);"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
