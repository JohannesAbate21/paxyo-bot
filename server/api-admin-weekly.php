<?php
// ============================================================================
// Weekly growth report for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot feature 27 — the admin bot
// /weekly shows this week vs last week, and the same report is sent
// automatically once a week, Monday 8am EAT.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/admin/weekly
//     -> {"this_week":{users, orders, completed, revenue_etb,
//         net_profit_etb, deposits_count, deposits_etb, from, to},
//         "last_week":{...same...},
//         "changes":{users_pct, orders_pct, revenue_pct, profit_pct}}
//        Weeks are EAT Monday–Sunday. "This week" is the week the
//        call falls in (Monday 00:00 EAT to next Monday 00:00 EAT);
//        "last week" is the week before it. users = auth rows created
//        in the week; orders = orders placed in the week (any status);
//        completed = orders with status 'completed' in the week;
//        revenue_etb = SUM(charge) of completed orders in the week
//        (same definition as admin-stats); net_profit_etb = revenue
//        x 220/420 (same economics as admin-stats — see A2);
//        deposits_count / deposits_etb = completed deposits in the
//        week (money in, NOT revenue). changes.*_pct is the percent
//        change from last week, rounded to a whole number, or null
//        when last week's figure is 0 (no division by zero, and no
//        invented "+infinity").
//   GET  /api/bot/admin/weekly-sent?date=YYYY-MM-DD
//     -> {"date":"2026-11-16","sent":true|false}
//        The sent marker for one Monday (the Monday's date is the
//        key). The admin bot checks this before sending, so a
//        restart after 8am Monday cannot double-send.
//   POST /api/bot/admin/weekly-sent   {date}
//     -> {"ok":true,"date":"2026-11-16","sent":true}
//        Marks a Monday as sent (idempotent — marking twice is the
//        same as marking once).
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_weekly_sent  date DATE PRIMARY KEY (the Monday), sent_at
//                    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-weekly.php       (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). The weekly-sent
//      POST marks a Monday as sent — use a PAST Monday for the test
//      (or delete the test row afterwards), never this week's Monday
//      before the real send.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use wkl_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - The weekly read is an ADMIN read (the admin bot calls it with
//     the same X-Bot-Secret). No per-user rate limit is applied here.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. orders has id, telegram_id, total, status, created_at — the
//       same columns the admin-stats endpoint assumes. created_at is
//       compared against UTC bounds (EAT Monday 00:00 = Sunday 21:00
//       UTC the day before) — same as the admin-stats endpoint's A2.
//   A2. Economics (same as api-admin-stats.php A6): the selling
//       price is provider rate x 420 ETB and the owner buys 1 USD
//       for 200 ETB, so provider cost = revenue x 200/420 and net
//       profit = revenue x 220/420. If William ever changes the 420
//       multiplier in Settings, this split must change with it — it
//       is NOT read from settings here.
//   A3. auth has tg_id and created_at — the same column the
//       admin-stats endpoint uses for new users. If auth has no
//       created_at column, users reads 0 for both weeks (never a
//       500) — the installer should confirm the column exists.
//   A4. deposits has amount, status, created_at (same as the
//       admin-stats endpoint). A 'completed' status is the paid
//       state. If the table or a column is missing, both deposit
//       figures read 0 (never a 500).
//   A5. "Completed" means status = 'completed' only (the same
//       single spelling the admin-stats endpoint uses for revenue).
// ============================================================================

// --- small helpers (wkl_ prefix so nothing collides with bot.php) -----------

function wkl_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function wkl_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function wkl_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function wkl_has_column($db, $table, $col) {
    try {
        $stmt = $db->prepare('SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ? LIMIT 1');
        $stmt->bind_param('ss', $table, $col);
        $stmt->execute();
        $found = $stmt->get_result()->fetch_assoc() !== null;
        $stmt->close();
        return $found;
    } catch (mysqli_sql_exception $e) {
        return false;
    }
}

function wkl_has_table($db, $table) {
    try {
        $stmt = $db->prepare('SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? LIMIT 1');
        $stmt->bind_param('s', $table);
        $stmt->execute();
        $found = $stmt->get_result()->fetch_assoc() !== null;
        $stmt->close();
        return $found;
    } catch (mysqli_sql_exception $e) {
        return false;
    }
}

function wkl_ensure_tables($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_weekly_sent (
        date DATE NOT NULL PRIMARY KEY,
        sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Run a scalar query (one row, one value) and return the value, or
// $default when the query fails or returns nothing. Never throws.
function wkl_scalar($db, $sql, $types, $params, $default) {
    try {
        $stmt = $db->prepare($sql);
        if ($types !== '' && $params !== []) $stmt->bind_param($types, ...$params);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_row();
        $stmt->close();
        if ($row === null || $row[0] === null) return $default;
        return $row[0];
    } catch (mysqli_sql_exception $e) {
        return $default;
    }
}

// This week + last week as UTC bounds, from EAT Monday–Sunday.
// Returns ['this' => ['from' => Y-m-d, 'to' => Y-m-d,
// 'start_utc' => ..., 'end_utc' => ...], 'last' => [...same...]].
// EAT = UTC+3, no DST: Monday 00:00 EAT = Sunday 21:00 UTC.
function wkl_weeks() {
    $tz = new DateTimeZone('Africa/Addis_Ababa');
    $now = new DateTime('now', $tz);
    $monday = new DateTime($now->format('Y-m-d') . ' 00:00:00', $tz);
    $monday->modify('-' . ((int)$now->format('N') - 1) . ' days');
    $next_monday = clone $monday;
    $next_monday->modify('+7 days');
    $last_monday = clone $monday;
    $last_monday->modify('-7 days');
    $last_sunday = clone $monday;
    $last_sunday->modify('-1 day');
    $utc = new DateTimeZone('UTC');
    $to_utc = function ($dt) use ($utc, $tz) {
        $c = clone $dt;
        $c->setTimezone($utc);
        return $c->format('Y-m-d H:i:s');
    };
    return [
        'this' => [
            'from' => $monday->format('Y-m-d'),
            'to' => (clone $next_monday)->modify('-1 day')->format('Y-m-d'),
            'start_utc' => $to_utc($monday),
            'end_utc' => $to_utc($next_monday),
        ],
        'last' => [
            'from' => $last_monday->format('Y-m-d'),
            'to' => $last_sunday->format('Y-m-d'),
            'start_utc' => $to_utc($last_monday),
            'end_utc' => $to_utc($monday),
        ],
    ];
}

function wkl_week_figures($db, $win) {
    $start = $win['start_utc'];
    $end = $win['end_utc'];
    $orders = (int)wkl_scalar(
        $db,
        'SELECT COUNT(*) FROM orders WHERE created_at >= ? AND created_at < ?',
        'ss', [$start, $end], 0
    );
    $completed = (int)wkl_scalar(
        $db,
        "SELECT COUNT(*) FROM orders WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
        'ss', [$start, $end], 0
    );
    $revenue = (float)wkl_scalar(
        $db,
        "SELECT COALESCE(SUM(charge), 0) FROM orders WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
        'ss', [$start, $end], 0
    );
    $users = 0;
    if (wkl_has_column($db, 'auth', 'created_at')) {
        $users = (int)wkl_scalar(
            $db,
            'SELECT COUNT(*) FROM auth WHERE created_at >= ? AND created_at < ?',
            'ss', [$start, $end], 0
        );
    }
    $deposits_count = 0;
    $deposits_etb = 0.0;
    if (
        wkl_has_table($db, 'deposits')
        && wkl_has_column($db, 'deposits', 'amount')
        && wkl_has_column($db, 'deposits', 'status')
        && wkl_has_column($db, 'deposits', 'created_at')
    ) {
        $deposits_count = (int)wkl_scalar(
            $db,
            "SELECT COUNT(*) FROM deposits WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
            'ss', [$start, $end], 0
        );
        $deposits_etb = (float)wkl_scalar(
            $db,
            "SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
            'ss', [$start, $end], 0
        );
    }
    return [
        'users' => $users,
        'orders' => $orders,
        'completed' => $completed,
        'revenue_etb' => round($revenue, 2),
        // Same economics as admin-stats (A2).
        'net_profit_etb' => round($revenue * 220 / 420, 2),
        'deposits_count' => $deposits_count,
        'deposits_etb' => round($deposits_etb, 2),
        'from' => $win['from'],
        'to' => $win['to'],
    ];
}

function wkl_pct_change($this_value, $last_value) {
    $this_value = (float)$this_value;
    $last_value = (float)$last_value;
    if ($last_value == 0) return null;
    return (int)round(100 * ($this_value - $last_value) / $last_value);
}

// --- GET /api/bot/admin/weekly ----------------------------------------------

function bot_wkl_weekly() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') wkl_fail(405, 'Method not allowed.');
    $db = wkl_db();
    if ($db === null) wkl_fail(500, 'Database is not available.');
    try { $db->query("SET time_zone = '+00:00'"); } catch (mysqli_sql_exception $e) { /* keep going */ }

    $weeks = wkl_weeks();
    $this_week = wkl_week_figures($db, $weeks['this']);
    $last_week = wkl_week_figures($db, $weeks['last']);
    bot_ok([
        'this_week' => $this_week,
        'last_week' => $last_week,
        'changes' => [
            'users_pct' => wkl_pct_change($this_week['users'], $last_week['users']),
            'orders_pct' => wkl_pct_change($this_week['orders'], $last_week['orders']),
            'revenue_etb_pct' => wkl_pct_change($this_week['revenue_etb'], $last_week['revenue_etb']),
            'net_profit_etb_pct' => wkl_pct_change($this_week['net_profit_etb'], $last_week['net_profit_etb']),
        ],
    ]);
}

// --- GET / POST /api/bot/admin/weekly-sent ----------------------------------

function bot_wkl_weekly_sent() {
    $method = $_SERVER['REQUEST_METHOD'];
    if ($method === 'GET') {
        $date = $_GET['date'] ?? '';
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) wkl_fail(400, 'date must be YYYY-MM-DD.');
        $db = wkl_db();
        if ($db === null) wkl_fail(500, 'Database is not available.');
        wkl_ensure_tables($db);
        $sent = (bool)wkl_scalar(
            $db,
            'SELECT 1 FROM bot_weekly_sent WHERE date = ? LIMIT 1',
            's', [$date], false
        );
        bot_ok(['date' => $date, 'sent' => $sent]);
        return;
    }
    if ($method === 'POST') {
        $in = wkl_json_body();
        $date = $in['date'] ?? '';
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) wkl_fail(400, 'date must be YYYY-MM-DD.');
        $db = wkl_db();
        if ($db === null) wkl_fail(500, 'Database is not available.');
        wkl_ensure_tables($db);
        try {
            $stmt = $db->prepare('INSERT IGNORE INTO bot_weekly_sent (date) VALUES (?)');
            $stmt->bind_param('s', $date);
            $stmt->execute();
            $stmt->close();
        } catch (mysqli_sql_exception $e) {
            wkl_fail(500, 'Could not mark the week as sent.');
        }
        bot_ok(['ok' => true, 'date' => $date, 'sent' => true]);
        return;
    }
    wkl_fail(405, 'Method not allowed.');
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/weekly' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_wkl_weekly(); }
//   if ($bp === 'admin/weekly-sent' && in_array($_SERVER['REQUEST_METHOD'], ['GET', 'POST'], true)) { bot_wkl_weekly_sent(); }
//
// LIVE CURL TEST — read this whole block before running it. The
// weekly-sent POST marks a Monday as sent — use a PAST Monday for
// the test (or delete the test row afterwards), never this week's
// Monday before the real send.
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. The report (read-only):
//   curl -s "https://paxyo.et/api/bot/admin/weekly" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"this_week":{...},"last_week":{...},
//      "changes":{...}}. Cross-check one figure against the admin
//      panel: this_week.orders must equal the orders placed since
//      Monday 00:00 EAT, and this_week.revenue_etb must equal the
//      SUM(charge) of this week's completed orders.
//   # 2. The sent marker for a PAST Monday (e.g. 2026-11-09):
//   curl -s "https://paxyo.et/api/bot/admin/weekly-sent?date=2026-11-09" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"date":"2026-11-09","sent":false}
//   curl -s -X POST https://paxyo.et/api/bot/admin/weekly-sent \
//     -H "X-Bot-Secret: $S" \
//     -d '{"date":"2026-11-09"}'
//   -> expect {"success":true,"ok":true,"date":"2026-11-09","sent":true}
//   curl -s "https://paxyo.et/api/bot/admin/weekly-sent?date=2026-11-09" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"date":"2026-11-09","sent":true}
//   Then DELETE the test row:
//   mysql -e "DELETE FROM bot_weekly_sent WHERE date='2026-11-09';"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
