<?php
// ===========================================================================
// Service reliability (cancel-cutting, item 1) for the Paxyo Bot API
// (public_html/api/bot.php). Written 16 Nov 2026 for @paxorder_bot.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/service-reliability
//     -> {"reliability": {"gop:123": {"orders": 12, "completed": 10,
//         "cancelled": 2, "failed": 0, "cancel_rate": 0.17,
//         "clean_streak": 10, "last10_orders": 10,
//         "last10_completed": 9}, "smm:7013": {...}, ...}}
//        Per (provider, service) 30-day stats from the live orders
//        table. Only services with at least one order in the window
//        are listed. `cancel_rate` is cancelled / orders — the
//        FAILED count is reported separately and is NOT in the rate
//        (a failed order is a provider ending, not a cancel; the
//        bot's exclusion rule reads cancel_rate only — see the
//        BOT-SIDE CONTRACT below). `clean_streak` is the number of
//        consecutive completed orders ending with the service's most
//        recent order in the window, capped at 10 (0 when the most
//        recent order did not complete). `last10_orders` /
//        `last10_completed` (20 Nov 2026) are the exact counts over
//        the service's 10 most recent orders in the window (fewer
//        when it has fewer) — the bot's success-rate walk reads
//        them: a service is taken only when over 60% of its last
//        10 orders delivered.
//
// THE BOT READS THESE STATS to pick services (bot.py's pick
// path): walking fastest-first by average time, a service is
// taken only when its success rate over its last 10 orders is
// over 60% (7+ of 10 delivered, from last10_completed /
// last10_orders); anything at or below 60% is skipped for the
// next-fastest, and when every candidate is skipped the bot asks
// the user instead of guessing. A service with no record at all
// reads as unknown — no evidence against it — and is taken. The
// ranking itself is a BOT-side build: this server file only
// exposes the counts. It never changes a price, a total, or
// which service is picked — the money steps stay deterministic.
//
// PROVIDER: a row in bot_smm_orders means the order went to the
// second provider ("smm"); any other order reads as "gop" (the
// first provider). The bare service ids collide between providers
// (2,790 of them), so the key is always "provider:service_id".
// When bot_smm_orders does not exist yet (the SMM file was never
// installed), every order reads as "gop" — the join is skipped.
//
// TABLE: none new. Reads only: orders (+ bot_smm_orders when it
// exists). No writes, no money moves.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-service-reliability.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file).
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient method
// to add, mirroring service_ratings in bot.py):
//   service_reliability() — GET /service-reliability. 404-tolerant
//     (endpoint not live yet -> None + warning, the bot ranks
//     exactly as today). Returns the {"reliability": {...}} map.
//   The bot caches it for one hour (the counts move slowly — one
//   order at a time) and never blocks a pick on a failed fetch.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. orders table: id, service_id (the provider's bare service
//       id), status, created_at. The code reads the row with
//       SELECT service_id, status, created_at — confirm the real
//       names with SHOW COLUMNS FROM orders and trim the lists.
//   A2. Finished statuses: 'completed', 'complete', 'success',
//       'paid' all count as completed (the same set the bot's
//       delivery watch treats as delivered). Cancelled is
//       'cancelled' or 'canceled'; failed is 'failed'. Any other
//       status counts in `orders` only (pending, processing,
//       partial, in progress, ...).
//   A3. bot_smm_orders (api-order-smm.php): order_id is the Paxyo
//       orders.id. When the table is absent the join is skipped
//       and every order reads as "gop".
//   A4. Add the same bot_rate_limit(...) call the other user
//       endpoints use to the dispatch line (copy the exact call
//       from the orders handler — the signature was not visible
//       from outside the server).
// ===========================================================================

// --- small helpers (rel_ prefix so nothing collides with bot.php) -----------

function rel_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function rel_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

// --- GET /api/bot/service-reliability ---------------------------------------
// 30-day per (provider, service) stats: orders, completed,
// cancelled, failed, cancel_rate, clean_streak. One query, ordered
// most-recent-first per service so the streak is a single pass.

function bot_rel_service_reliability() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') rel_fail(405, 'Method not allowed.');

    $db = rel_db();
    if ($db === null) rel_fail(500, 'Database is not available.');

    // Does the SMM orders table exist? When it does, a row there
    // marks the order as the second provider's.
    $has_smm = false;
    try {
        $chk = $db->query("SHOW TABLES LIKE 'bot_smm_orders'");
        if ($chk) {
            $has_smm = ($chk->num_rows > 0);
            $chk->close();
        }
    } catch (mysqli_sql_exception $e) {
        $has_smm = false;
    }

    if ($has_smm) {
        $sql = "SELECT o.service_id, o.status, o.created_at, "
            . "CASE WHEN s.order_id IS NOT NULL THEN 'smm' ELSE 'gop' END AS provider "
            . "FROM orders o LEFT JOIN bot_smm_orders s ON s.order_id = o.id "
            . "WHERE o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
            . "ORDER BY provider, o.service_id, o.created_at DESC";
    } else {
        $sql = "SELECT o.service_id, o.status, o.created_at, 'gop' AS provider "
            . "FROM orders o "
            . "WHERE o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
            . "ORDER BY provider, o.service_id, o.created_at DESC";
    }
    try {
        $res = $db->query($sql);
    } catch (mysqli_sql_exception $e) {
        rel_fail(500, 'Could not read order history.');
    }
    if ($res === false) rel_fail(500, 'Could not read order history.');

    $completed_words = ['completed', 'complete', 'success', 'paid'];
    $cancelled_words = ['cancelled', 'canceled'];
    $out = [];
    while ($row = $res->fetch_assoc()) {
        $sid = (int)($row['service_id'] ?? 0);
        if ($sid <= 0) continue;
        $provider = ((string)($row['provider'] ?? '') === 'smm') ? 'smm' : 'gop';
        $key = $provider . ':' . $sid;
        if (!isset($out[$key])) {
            $out[$key] = [
                'orders' => 0, 'completed' => 0, 'cancelled' => 0,
                'failed' => 0, 'cancel_rate' => 0.0, 'clean_streak' => 0,
                'last10_orders' => 0, 'last10_completed' => 0,
                '_streak_open' => true,
            ];
        }
        $rec = &$out[$key];
        $rec['orders']++;
        $status = strtolower(trim((string)($row['status'] ?? '')));
        // Last-10 window (20 Nov 2026): rows arrive newest-first
        // per service, so the first 10 rows ARE the last 10
        // orders. The bot's success-rate walk reads these exact
        // counts (over 60% of the last 10 must have delivered).
        if ($rec['last10_orders'] < 10) {
            $rec['last10_orders']++;
            if (in_array($status, $completed_words, true)) {
                $rec['last10_completed']++;
            }
        }
        if (in_array($status, $completed_words, true)) {
            $rec['completed']++;
            // The streak counts leading completed orders from the
            // most recent one down (rows arrive newest-first); the
            // first non-completed status closes it for this service.
            if ($rec['_streak_open'] && $rec['clean_streak'] < 10) {
                $rec['clean_streak']++;
            }
        } else {
            $rec['_streak_open'] = false;
            if (in_array($status, $cancelled_words, true)) {
                $rec['cancelled']++;
            } elseif ($status === 'failed') {
                $rec['failed']++;
            }
        }
        unset($rec);
    }
    $res->close();

    foreach ($out as $key => $rec) {
        $orders = (int)$rec['orders'];
        $out[$key]['cancel_rate'] = $orders > 0
            ? round((int)$rec['cancelled'] / $orders, 4)
            : 0.0;
        unset($out[$key]['_streak_open']);
    }
    bot_ok(['reliability' => $out]);
}

// ===========================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'service-reliability' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_rel_service_reliability(); }
//   (Add the same bot_rate_limit(...) call the other user endpoints
//    use to that dispatch line — copy the exact call from the orders
//    handler; the signature was not visible from outside the server.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-service-reliability.php`
// on the server (step 1 of the install) and `php -l api/bot.php`
// after splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (read-only, no money moves):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/service-reliability" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"reliability":{...}} with one entry per
//      (provider, service) that has orders in the last 30 days, each
//      carrying orders/completed/cancelled/failed/cancel_rate/
//      clean_streak/last10_orders/last10_completed. A service with
//      no orders in 30 days is absent (the bot reads that as
//      unknown/neutral, never penalised). NOTE: this file must be
//      re-installed on the server (splice into bot.php) for the
//      last10_* fields to appear — until then the bot's walk reads
//      the clean streak (7+ takes) and the 30-day rate instead.
//   Sanity: pick one service id with known history and check the
//   counts against:
//     mysql -e "SELECT status, COUNT(*) FROM orders WHERE service_id=N
//       AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY status;"
// ===========================================================================
