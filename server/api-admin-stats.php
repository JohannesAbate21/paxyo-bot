<?php
// ============================================================================
// Daily digest stats for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot, feature 4 (confused-chats
// admin + working daily digest). Server side of the bot's /digest
// command: PaxyoClient.admin_stats() in bot.py calls GET
// /admin/stats and build_digest_text() formats the record it gets
// back. Until this endpoint is live, /digest answers honestly that
// the digest is not connected yet.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/admin/stats
//     -> {"date":"2026-11-15","orders":12,"completed":9,
//         "revenue_etb":486.20,"new_users":3,
//         "top_service":"TikTok Video Views","top_quantity":5400,
//         "days":1,"from":"2026-11-15",
//         "deposits_count":4,"deposits_etb":1250.00}
//     bot_ok() adds "success":true around it, as on every other
//     endpoint; the bot reads the named keys and ignores the rest.
//
//   GET /api/bot/admin/stats?days=7 — same record for the last 7
//     calendar days in EAT (today included). `days` is clamped to
//     1..90; an invalid value behaves as 1. `date` is always today
//     in EAT and `from` is the first day of the window, so the bot
//     can label the range. `deposits_count` / `deposits_etb` are
//     the COMPLETED deposits in the window (count and total ETB);
//     a deposit is money in, not revenue, so it is reported
//     separately from revenue_etb and never added to it.
//
// WINDOW DECISION — TODAY (not last 24h), in Africa/Addis_Ababa:
//   * date         = today's date in EAT (YYYY-MM-DD).
//   * orders       = orders PLACED today (created_at inside today
//                    EAT), any status.
//   * completed    = orders with status 'completed' created today.
//   * revenue_etb  = SUM(total) of the completed orders today.
//   * new_users    = auth rows created today.
//   * top_service  = name of the most-ordered service today, and
//                    top_quantity = total quantity ordered of it
//                    today (SUM of the quantity column when one
//                    exists, else the count of orders for it —
//                    see ASSUMPTIONS below).
//   "Today" was chosen over "last 24h" because the digest is a
//   once-a-day morning message for William ("today so far"), and
//   because a calendar day lines up with the admin dashboard's
//   "Today" timeframe. The bot displays whatever `date` the server
//   returns, so the window is the server's call — this file is it.
//
// AUTH: X-Bot-Secret, same as the session/confusion endpoints.
// This is a BOT endpoint, called by @paxorder_bot with the secret —
// it is NOT the human-admin session (admin_authenticated) and it
// must NOT be called from a user-facing page. No telegram_id is
// needed: the digest is owner-wide, not per-user.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-stats.php      (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINE
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php              (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). Read-only GET —
//      no money moves, no rows are written.
//
// ASSUMPTIONS — every column this file needs, and what happens when
// one is missing (each query degrades to zero/empty, never a 500):
//   A1. orders has id, telegram_id, total, status, created_at —
//       confirmed from the local server files (api-deposits.php /
//       HANDOVER.md). status 'completed' is the finished state
//       (the value the orders endpoint and the mini app use).
//   A2. orders.created_at is stored in UTC (TIMESTAMP column, as
//       bot_confusions.created_at is) OR the server clock is EAT.
//       The code sets the MySQL session time zone to +00:00 and
//       compares created_at against UTC bounds computed from the
//       EAT day (00:00 EAT = 21:00 UTC the day before). TO VERIFY
//       on install: SHOW COLUMNS FROM orders — if created_at is a
//       DATETIME stored in server-local time (not UTC), the day
//       boundary will be off by the server offset; switch the
//       comparison to DATE(created_at) = CURDATE() with the
//       session time zone set to +03:00 instead.
//   A3. auth has tg_id and created_at — created_at is the column
//       the local files list; if auth has no created_at column,
//       new_users reads 0 (the query is skipped, nothing errors).
//       TO VERIFY: SHOW COLUMNS FROM auth.
//   A4. orders does NOT list a service/quantity column in the
//       local files, so the top-service query DISCOVERS them at
//       runtime (information_schema): it looks for a service
//       column (service_id, provider_service_id, service, then
//       service_name) and a quantity column (quantity, then qty).
//       - service_id + quantity: top service by SUM(quantity).
//       - service_id, no quantity: top service by COUNT(*) of
//         orders, and top_quantity is that order count (NOT units
//         — the digest then means "most orders", flagged here so
//         nobody misreads it as units).
//       - service_name only: top service by COUNT(*), quantity
//         falls back to the order count as above.
//       - no service column at all: top_service null,
//         top_quantity 0 (the digest simply omits the top line).
//       TO VERIFY: SHOW COLUMNS FROM orders — if the live table
//       names the columns differently, add the name to the lists
//       in adm_discover_orders_columns().
//   A5. The service NAME comes from a `services` table with a
//       `name` column and either provider_service_id or id to join
//       on (the services endpoint returns id, provider_service_id,
//       name, so a table shaped like that is expected). If there
//       is no `services` table, or the id does not match a row,
//       top_service falls back to "Service #<id>" so the digest
//       still shows something useful. TO VERIFY: SHOW TABLES LIKE
//       'services' and SHOW COLUMNS FROM services on install.
//   A6. Revenue is the SUM of orders.total for completed orders
//       only — deposits are NOT revenue (a deposit is money in,
//       an order is money earned). Provider cost is NOT subtracted
//       here; the digest shows gross revenue, as build_digest_text
//       expects. Net profit stays an admin-dashboard figure.
//   A7. EAT is UTC+3 all year (no daylight saving in Ethiopia),
//       so the UTC bounds are a fixed -3h shift. If the server
//       ever moves time zones, only adm_today_window() changes.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for the success reply (it adds
//     "success":true, as on the other endpoints). Errors use
//     adm_fail() below, which returns {"success":false,
//     "error":...,"message":...} — the bot reads both keys.
//     A 404 from this endpoint means "not live yet" to the bot
//     (admin_stats() returns None); a 500 raises, so every
//     per-figure query is wrapped and degrades instead of dying.
//   - Add the same bot_rate_limit(...) call the other endpoints
//     use to the dispatch line (copy the exact call from the
//     orders handler — the signature was not visible from
//     outside the server). This endpoint is called at most a few
//     times a day (one /digest tap), so a per-telegram_id limit
//     does not fit — rate-limit it as a secret-only endpoint, or
//     leave the limit off and note it here.
//   - Read-only: no table is created, no row is written. The
//     only writes are SET time_zone on the session.
//   - All money is in ETB; revenue_etb is rounded to 2 decimals.
// ============================================================================

// --- small helpers (adm_ prefix so nothing collides with bot.php) -----------

function adm_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function adm_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

// Today's window in EAT, returned as UTC bounds for created_at.
// EAT = UTC+3, no DST: today 00:00 EAT = yesterday 21:00 UTC,
// tomorrow 00:00 EAT = today 21:00 UTC.
function adm_today_window() {
    return adm_window(1);
}

// Window of the last $days calendar days in EAT, today included.
// $days is clamped to 1..90. `date` is today in EAT, `from` is the
// first day of the window, and the UTC bounds cover [from 00:00
// EAT, tomorrow 00:00 EAT).
function adm_window($days) {
    $days = (int)$days;
    if ($days < 1) $days = 1;
    if ($days > 90) $days = 90;
    $tz = new DateTimeZone('Africa/Addis_Ababa');
    $now = new DateTime('now', $tz);
    $start_eat = new DateTime($now->format('Y-m-d') . ' 00:00:00', $tz);
    if ($days > 1) $start_eat->modify('-' . ($days - 1) . ' days');
    $end_eat = new DateTime($now->format('Y-m-d') . ' 00:00:00', $tz);
    $end_eat->modify('+1 day');
    $utc = new DateTimeZone('UTC');
    $start_eat->setTimezone($utc);
    $end_eat->setTimezone($utc);
    return [
        'date' => $now->format('Y-m-d'),
        'from' => (clone $start_eat)->setTimezone($tz)->format('Y-m-d'),
        'days' => $days,
        'start_utc' => $start_eat->format('Y-m-d H:i:s'),
        'end_utc' => $end_eat->format('Y-m-d H:i:s'),
    ];
}

// Does table $table have column $col? (information_schema read; if
// the check itself fails, answer "no" — the caller degrades.)
function adm_has_column($db, $table, $col) {
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

// Does table $table exist at all?
function adm_has_table($db, $table) {
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

// Discover which service/quantity columns orders actually has.
// Returns ['service' => col-or-null, 'service_is_name' => bool,
//          'quantity' => col-or-null]. First match wins, in the
// order listed in A4.
function adm_discover_orders_columns($db) {
    $service = null;
    $service_is_name = false;
    foreach (['service_id', 'provider_service_id', 'service'] as $col) {
        if (adm_has_column($db, 'orders', $col)) { $service = $col; break; }
    }
    if ($service === null && adm_has_column($db, 'orders', 'service_name')) {
        $service = 'service_name';
        $service_is_name = true;
    }
    $quantity = null;
    foreach (['quantity', 'qty'] as $col) {
        if (adm_has_column($db, 'orders', $col)) { $quantity = $col; break; }
    }
    return ['service' => $service, 'service_is_name' => $service_is_name, 'quantity' => $quantity];
}

// Run a scalar query (one row, one value) and return the value, or
// $default when the query fails or returns nothing. Never throws.
function adm_scalar($db, $sql, $types, $params, $default) {
    try {
        $stmt = $db->prepare($sql);
        if ($types !== '' && $params) $stmt->bind_param($types, ...$params);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_row();
        $stmt->close();
        if ($row === null || $row === false || $row[0] === null) return $default;
        return $row[0];
    } catch (mysqli_sql_exception $e) {
        return $default;
    }
}

// --- GET /api/bot/admin/stats ------------------------------------------------

function bot_admin_stats() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') adm_fail(405, 'Method not allowed.');

    $db = adm_db();
    if ($db === null) adm_fail(500, 'Database is not available.');

    // ?days=N — the last N calendar days in EAT, today included.
    // Default 1 (today). Clamped to 1..90 inside adm_window().
    $days = 1;
    if (isset($_GET['days']) && is_numeric($_GET['days'])) {
        $days = (int)$_GET['days'];
    }
    $win = adm_window($days);
    $date = $win['date'];
    $start = $win['start_utc'];
    $end = $win['end_utc'];

    // Session time zone UTC so the UTC bounds compare literally
    // against TIMESTAMP columns (stored UTC, converted per session)
    // and against DATETIME columns stored in UTC. See A2.
    try { $db->query("SET time_zone = '+00:00'"); } catch (mysqli_sql_exception $e) { /* keep going — bounds still apply */ }

    // Orders placed today (any status).
    $orders = (int)adm_scalar(
        $db,
        'SELECT COUNT(*) FROM orders WHERE created_at >= ? AND created_at < ?',
        'ss', [$start, $end], 0
    );

    // Completed today.
    $completed = (int)adm_scalar(
        $db,
        "SELECT COUNT(*) FROM orders WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
        'ss', [$start, $end], 0
    );

    // Gross revenue today: sum of totals of completed orders only.
    $revenue = (float)adm_scalar(
        $db,
        "SELECT COALESCE(SUM(total), 0) FROM orders WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
        'ss', [$start, $end], 0
    );

    // New users today (auth rows created today). If auth has no
    // created_at column, this reads 0 — see A3.
    $new_users = 0;
    if (adm_has_column($db, 'auth', 'created_at')) {
        $new_users = (int)adm_scalar(
            $db,
            'SELECT COUNT(*) FROM auth WHERE created_at >= ? AND created_at < ?',
            'ss', [$start, $end], 0
        );
    }

    // Most-ordered service today (see A4/A5 for the fallbacks).
    $top_service = null;
    $top_quantity = 0;
    $cols = adm_discover_orders_columns($db);
    if ($cols['service'] !== null) {
        $svc = $cols['service'];
        if ($cols['service_is_name']) {
            // The name is stored on the order itself.
            $measure = $cols['quantity'] !== null
                ? 'SUM(`' . $cols['quantity'] . '`)'
                : 'COUNT(*)';
            try {
                $stmt = $db->prepare(
                    'SELECT `' . $svc . '` AS svc, ' . $measure . ' AS q FROM orders '
                    . 'WHERE created_at >= ? AND created_at < ? AND `' . $svc . '` IS NOT NULL AND `' . $svc . "` <> '' "
                    . 'GROUP BY `' . $svc . '` ORDER BY q DESC LIMIT 1'
                );
                $stmt->bind_param('ss', $start, $end);
                $stmt->execute();
                $row = $stmt->get_result()->fetch_assoc();
                $stmt->close();
                if ($row) {
                    $top_service = (string)$row['svc'];
                    $top_quantity = (int)$row['q'];
                }
            } catch (mysqli_sql_exception $e) { /* degrade: no top line */ }
        } else {
            // A service id: aggregate, then resolve the name.
            $measure = $cols['quantity'] !== null
                ? 'SUM(`' . $cols['quantity'] . '`)'
                : 'COUNT(*)';
            try {
                $stmt = $db->prepare(
                    'SELECT `' . $svc . '` AS svc, ' . $measure . ' AS q FROM orders '
                    . 'WHERE created_at >= ? AND created_at < ? AND `' . $svc . '` IS NOT NULL '
                    . 'GROUP BY `' . $svc . '` ORDER BY q DESC LIMIT 1'
                );
                $stmt->bind_param('ss', $start, $end);
                $stmt->execute();
                $row = $stmt->get_result()->fetch_assoc();
                $stmt->close();
                if ($row) {
                    $top_quantity = (int)$row['q'];
                    $top_service = adm_service_name($db, $row['svc']);
                }
            } catch (mysqli_sql_exception $e) { /* degrade: no top line */ }
        }
    }

    // Completed deposits in the window (count + total ETB).
    // A deposit is money in, NOT revenue — reported separately
    // and never added to revenue_etb. The deposits table is
    // confirmed to have user_id (= telegram id, see
    // api-deposits.php), amount, status and created_at; a
    // 'completed' status is the paid state. If the table or a
    // column is missing, both figures read 0 (never a 500).
    $deposits_count = 0;
    $deposits_etb = 0.0;
    if (
        adm_has_table($db, 'deposits')
        && adm_has_column($db, 'deposits', 'amount')
        && adm_has_column($db, 'deposits', 'status')
        && adm_has_column($db, 'deposits', 'created_at')
    ) {
        $deposits_count = (int)adm_scalar(
            $db,
            "SELECT COUNT(*) FROM deposits WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
            'ss', [$start, $end], 0
        );
        $deposits_etb = (float)adm_scalar(
            $db,
            "SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE status = 'completed' AND created_at >= ? AND created_at < ?",
            'ss', [$start, $end], 0
        );
    }

    bot_ok([
        'date' => $date,
        'from' => $win['from'],
        'days' => $win['days'],
        'orders' => $orders,
        'completed' => $completed,
        'revenue_etb' => round($revenue, 2),
        'new_users' => $new_users,
        'top_service' => $top_service,
        'top_quantity' => $top_quantity,
        'deposits_count' => $deposits_count,
        'deposits_etb' => round($deposits_etb, 2),
    ]);
}

// Resolve a service id to its display name via the services table.
// Falls back to "Service #<id>" when the table or the row is missing.
function adm_service_name($db, $service_id) {
    $service_id = (int)$service_id;
    if ($service_id <= 0) return null;
    if (adm_has_table($db, 'services') && adm_has_column($db, 'services', 'name')) {
        $join_col = null;
        foreach (['provider_service_id', 'id'] as $col) {
            if (adm_has_column($db, 'services', $col)) { $join_col = $col; break; }
        }
        if ($join_col !== null) {
            try {
                $stmt = $db->prepare('SELECT name FROM services WHERE `' . $join_col . '` = ? LIMIT 1');
                $stmt->bind_param('i', $service_id);
                $stmt->execute();
                $row = $stmt->get_result()->fetch_assoc();
                $stmt->close();
                if ($row && (string)$row['name'] !== '') return (string)$row['name'];
            } catch (mysqli_sql_exception $e) { /* fall through */ }
        }
    }
    return 'Service #' . $service_id;
}

// ============================================================================
// DISPATCH — insert this line in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/stats' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_admin_stats(); }
//
// LIVE CURL TEST (read-only GET — no money moves, no rows written):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/admin/stats" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"date":"YYYY-MM-DD","from":"YYYY-MM-DD",
//      "days":1,"orders":N,"completed":N,"revenue_etb":N.NN,
//      "new_users":N,"top_service":"..."|null,"top_quantity":N,
//      "deposits_count":N,"deposits_etb":N.NN}
//      with "date" = today's date in EAT. On a quiet day every count
//      may legitimately be 0 and top_service null — that is a correct
//      answer, not an error.
//   curl -s "https://paxyo.et/api/bot/admin/stats?days=7" -H "X-Bot-Secret: $SECRET"
//   -> same shape with "days":7 and "from" = 6 days ago in EAT;
//      the counts cover the whole 7-day window. days=0, days=abc
//      and days=999 behave as days=1 / days=1 / days=90.
//   Without the header (or with a wrong secret) the request must be
//   refused by bot.php's existing X-Bot-Secret check, before this
//   code runs:
//   curl -s "https://paxyo.et/api/bot/admin/stats"
//   -> expect the usual auth error (401/403), NOT the stats.
//   No test rows to delete: this endpoint writes nothing.
// ============================================================================
