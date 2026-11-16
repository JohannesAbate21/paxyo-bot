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
//         "deposits_count":4,"deposits_etb":1250.00,
//         "net_profit_etb":256.62,
//         "provider_balance_usd":5.63}
//     bot_ok() adds "success":true around it, as on every other
//     endpoint; the bot reads the named keys and ignores the rest.
//     net_profit_etb is gross revenue minus provider cost:
//     the selling price is provider rate x 420 ETB and the owner
//     buys 1 USD for 200 ETB, so provider cost = revenue x
//     200/420 and net profit = revenue x 220/420. (A6 below.)
//     provider_balance_usd is the PROVIDER's live balance in USD
//     (feature 7, 15 Nov 2026 — the bot's low-provider-balance
//     watch reads it, throttled to one check per hour, and alerts
//     William below $3, again below $1). The field is OMITTED
//     when the provider cannot be reached — the stats reply stays
//     whole, and the bot's watch stays off with a log warning
//     instead of alerting on a missing number. See
//     adm_provider_balance() below (A9).
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
//   GET /api/bot/admin/stats?day=yesterday — the SAME record for
//     yesterday's EAT calendar day ONLY (date = today in EAT,
//     from = yesterday, days = 1, day = "yesterday" in the
//     response). The ?days=N windows always end today, so
//     yesterday alone needs this parameter. The admin bot's
//     morning report uses it. Any other `day` value is ignored
//     (behaves as the plain ?days=N window).
//
//   GET /api/bot/admin/morning-sent?date=YYYY-MM-DD
//     -> {"date":"2026-11-15","sent":false}
//   POST /api/bot/admin/morning-sent {"date":"2026-11-15"}
//     -> {"ok":true,"date":"2026-11-15","sent":true}
//     The once-a-day marker for the admin bot's automatic 8am
//     morning report: the bot checks GET before sending and
//     writes POST after sending, so a restart after 8am cannot
//     double-send. Table bot_morning_sent (date PK) is created
//     by this file itself. POST is idempotent (a re-mark only
//     refreshes sent_at). A missing/invalid date behaves as
//     today in EAT on GET, and is a 400 on POST.
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
//       an order is money earned). Provider cost IS subtracted
//       for net_profit_etb: the selling price is provider rate x
//       420 ETB and the owner buys 1 USD for 200 ETB, so the
//       provider cost of a completed order is its total x 200/420
//       and net profit is revenue x 220/420. The 420 multiplier
//       is editable in Paxyo Settings — if William ever changes
//       it, this 220/420 split must change with it (it is NOT
//       read from settings here; the settings table was not
//       visible from outside the server). Net profit stays an
//       admin figure — it is never shown to customers.
//   A7. EAT is UTC+3 all year (no daylight saving in Ethiopia),
//       so the UTC bounds are a fixed -3h shift. If the server
//       ever moves time zones, only adm_today_window() changes.
//   A8. bot_morning_sent holds one row per date the morning
//       report was sent (sent_date DATE PK). The admin bot is the
//       only writer; the GET/POST handlers below are the only
//       readers/writers of it.
//   A9. PROVIDER BALANCE (feature 7, 15 Nov 2026): the provider
//       balance action is action=balance on the GodOfPanel v2 API
//       (key in the query string, POST with an empty body — the
//       provider rejects a POST body with "Invalid API key").
//       Reply shape {"balance": "5.6257050", "currency": "USD"}
//       (verified 2026-11-12 in the connector doc). The call
//       prefers bot.php's godofpanel_call('balance') helper when
//       it exists (same pattern as api-order-rescue.php) and
//       falls back to a direct curl call; the key lookup mirrors
//       res_provider_key(). A failed provider call OMITS the
//       field — it never fails the stats call and never reports
//       a fake balance. TO VERIFY: confirm the helper name / key
//       constant bot.php actually uses, and check the live reply
//       carries provider_balance_usd (curl test below).
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
//   - Read-only except POST /admin/morning-sent: GET /admin/stats
//     creates no table and writes no row (only SET time_zone on
//     the session). The morning-sent handlers create the
//     bot_morning_sent table (CREATE TABLE IF NOT EXISTS) and
//     POST writes one row per date, idempotently — that is the
//     only write in this file.
//   - All money is in ETB; revenue_etb / net_profit_etb are
//     rounded to 2 decimals.
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

// Yesterday's EAT calendar day ONLY, as a window the same shape
// as adm_window() returns: `date` is today in EAT, `from` is
// yesterday, `days` is 1, and the UTC bounds cover
// [yesterday 00:00 EAT, today 00:00 EAT). Used by
// GET /admin/stats?day=yesterday for the morning report.
function adm_day_window() {
    $tz = new DateTimeZone('Africa/Addis_Ababa');
    $now = new DateTime('now', $tz);
    $start_eat = new DateTime($now->format('Y-m-d') . ' 00:00:00', $tz);
    $start_eat->modify('-1 day');
    $end_eat = new DateTime($now->format('Y-m-d') . ' 00:00:00', $tz);
    $utc = new DateTimeZone('UTC');
    $start_eat->setTimezone($utc);
    $end_eat->setTimezone($utc);
    return [
        'date' => $now->format('Y-m-d'),
        'from' => (clone $start_eat)->setTimezone($tz)->format('Y-m-d'),
        'days' => 1,
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

// --- provider balance (feature 7, 15 Nov 2026) -------------------------
// The bot's low-provider-balance watch reads provider_balance_usd
// from GET /admin/stats. The provider balance action is
// action=balance on the GodOfPanel v2 API (key in the query
// string, POST with an empty body — the same call style as
// api-order-rescue.php); the reply is {"balance": "5.6257050",
// "currency": "USD"} (verified 2026-11-12 in the connector doc).
// If the provider cannot be reached, the key is missing, or the
// reply has no numeric balance, adm_provider_balance() returns
// null and the field is OMITTED from the stats reply — the stats
// call must never break because the provider is unreachable.

function adm_provider_key() {
    // TO VERIFY (same as api-order-rescue.php A3): keep only the
    // constant bot.php actually uses for the provider key when
    // placing orders; delete the rest.
    foreach (['GODOPANEL_API_KEY', 'GOD_OF_PANEL_API_KEY', 'PROVIDER_API_KEY', 'PANEL_API_KEY'] as $name) {
        if (defined($name) && constant($name) !== '') return (string)constant($name);
    }
    $env = getenv('GODOFPANEL_API_KEY');
    if ($env !== false && $env !== '') return $env;
    return null;
}

function adm_provider_base() {
    if (defined('GODOPANEL_API_URL') && GODOPANEL_API_URL !== '') return rtrim(GODOPANEL_API_URL, '/');
    $env = getenv('GODOFPANEL_API_URL');
    if ($env !== false && $env !== '') return rtrim($env, '/');
    return 'https://godofpanel.com/api/v2';
}

// One raw provider call. Params go in the URL query string (the
// provider rejects a POST body with "Invalid API key"). Returns the
// decoded JSON reply as an array, or null when the provider could
// not be reached / did not answer JSON.
function adm_provider_raw($action, $params) {
    $key = adm_provider_key();
    if ($key === null) return null;
    $query = array_merge(['key' => $key, 'action' => $action], $params);
    $url = adm_provider_base() . '?' . http_build_query($query);
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => '',
        CURLOPT_TIMEOUT => 30,
    ]);
    $raw = curl_exec($ch);
    curl_close($ch);
    if (!is_string($raw) || $raw === '') return null;
    $res = json_decode($raw, true);
    return is_array($res) ? $res : null;
}

// The provider's current balance in USD (float), or null when it
// cannot be read. Uses bot.php's godofpanel_call('balance')
// helper when it exists, else the direct call above. Never throws.
function adm_provider_balance() {
    // TO VERIFY (same as api-order-rescue.php A2): if bot.php's
    // helper exists, use it here too.
    if (function_exists('godofpanel_call')) {
        try {
            $res = godofpanel_call('balance', []);
        } catch (Throwable $e) {
            $res = null;
        }
        if (is_array($res) && isset($res['balance']) && is_numeric($res['balance'])) {
            return (float)$res['balance'];
        }
        // Helper existed but gave nothing usable — fall through to
        // the direct call below rather than guessing.
    }
    $res = adm_provider_raw('balance', []);
    if ($res === null || !isset($res['balance']) || !is_numeric($res['balance'])) return null;
    return (float)$res['balance'];
}

// --- second-provider balance (cancel-cutting, item 12, 16 Nov 2026) --------
// The SMM panel's balance, converted to USD (float), or null when it
// cannot be read. The panel bills in INR, so the reply is
// {"balance": "73.85", "currency": "INR"}; the conversion uses a
// fixed approximate rate (95 INR per USD — the panel's own rate
// drifts a few rupees either way, and the guard only needs to know
// whether the balance is nearly empty, so an approximate figure is
// enough; never use this figure for money, only for the $3/$1
// low-balance thresholds the bot already uses). Reads through
// smm_provider_raw() from api-order-smm.php when that file is
// installed (guarded by function_exists — when it is not installed
// the field is simply omitted, exactly like provider_balance_usd
// when its provider cannot be reached). Never throws.
function adm_smm_balance_usd() {
    if (!function_exists('smm_provider_raw')) return null;
    try {
        $res = smm_provider_raw('balance', []);
    } catch (Throwable $e) {
        return null;
    }
    if (!is_array($res) || !isset($res['balance']) || !is_numeric($res['balance'])) return null;
    $balance_inr = (float)$res['balance'];
    // Only convert when the reply is INR (or carries no currency
    // — the panel bills in INR); a USD reply is already dollars.
    $currency = strtoupper(trim((string)($res['currency'] ?? 'INR')));
    if ($currency === 'USD') return round($balance_inr, 2);
    if ($currency !== 'INR') return null;
    return round($balance_inr / 95.0, 2);
}

// --- GET /api/bot/admin/stats ------------------------------------------------

function bot_admin_stats() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') adm_fail(405, 'Method not allowed.');

    $db = adm_db();
    if ($db === null) adm_fail(500, 'Database is not available.');

    // ?days=N — the last N calendar days in EAT, today included.
    // Default 1 (today). Clamped to 1..90 inside adm_window().
    // ?day=yesterday — yesterday's EAT calendar day only (the
    // morning report). Any other `day` value is ignored.
    $days = 1;
    if (isset($_GET['days']) && is_numeric($_GET['days'])) {
        $days = (int)$_GET['days'];
    }
    $day = strtolower(trim((string)($_GET['day'] ?? '')));
    if ($day === 'yesterday') {
        $win = adm_day_window();
    } else {
        $win = adm_window($days);
    }
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

    // Net profit: revenue minus provider cost. The selling price
    // is provider rate x 420 ETB and the owner buys 1 USD for
    // 200 ETB, so provider cost = revenue x 200/420 and net
    // profit = revenue x 220/420 (see A6). If William ever
    // changes the 420 multiplier in Settings, this split must
    // change with it — it is NOT read from settings here.

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

    $out = [
        'date' => $date,
        'from' => $win['from'],
        'days' => $win['days'],
        'orders' => $orders,
        'completed' => $completed,
        'revenue_etb' => round($revenue, 2),
        'net_profit_etb' => round($revenue * 220 / 420, 2),
        'new_users' => $new_users,
        'top_service' => $top_service,
        'top_quantity' => $top_quantity,
        'deposits_count' => $deposits_count,
        'deposits_etb' => round($deposits_etb, 2),
    ];
    // Provider balance in USD (feature 7, 15 Nov 2026): read live
    // from the provider on every stats call — the bot throttles
    // its checks to one per hour, so this costs at most one
    // provider call per hour. When the provider cannot be reached
    // the field is OMITTED (never a fake 0, never a 500): the
    // bot's watch then stays off with a log warning.
    $provider_balance = adm_provider_balance();
    if ($provider_balance !== null) {
        $out['provider_balance_usd'] = round($provider_balance, 2);
    }
    // Second provider (cancel-cutting, item 12, 16 Nov 2026): the
    // bot's balance guard reads smm_balance_usd the same way it
    // reads provider_balance_usd (same $3/$1 thresholds, same
    // alert). Omitted when the SMM file is not installed or the
    // panel cannot be reached — the guard then reads SMM as
    // healthy rather than blocking orders on a missing number.
    $smm_balance = adm_smm_balance_usd();
    if ($smm_balance !== null) {
        $out['smm_balance_usd'] = round($smm_balance, 2);
    }
    if ($day === 'yesterday') {
        $out['day'] = 'yesterday';
    }
    bot_ok($out);
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

// --- morning-sent marker (bot_morning_sent) ----------------------------------

function adm_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function adm_ensure_morning_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_morning_sent (
        sent_date DATE NOT NULL PRIMARY KEY,
        sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Is $value a real YYYY-MM-DD date? Returns the string, or null.
function adm_valid_date($value) {
    $value = trim((string)$value);
    if (!preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $value, $m)) return null;
    if (!checkdate((int)$m[2], (int)$m[3], (int)$m[1])) return null;
    return $value;
}

// Today's date in EAT (YYYY-MM-DD).
function adm_today_eat() {
    $tz = new DateTimeZone('Africa/Addis_Ababa');
    return (new DateTime('now', $tz))->format('Y-m-d');
}

// --- GET /api/bot/admin/morning-sent ------------------------------------------

function bot_morning_sent_get() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') adm_fail(405, 'Method not allowed.');

    $db = adm_db();
    if ($db === null) adm_fail(500, 'Database is not available.');

    // ?date=YYYY-MM-DD; missing/invalid behaves as today in EAT.
    $date = adm_valid_date($_GET['date'] ?? '') ?? adm_today_eat();
    adm_ensure_morning_table($db);

    $sent = false;
    try {
        $stmt = $db->prepare('SELECT 1 FROM bot_morning_sent WHERE sent_date = ? LIMIT 1');
        $stmt->bind_param('s', $date);
        $stmt->execute();
        $sent = $stmt->get_result()->fetch_assoc() !== null;
        $stmt->close();
    } catch (mysqli_sql_exception $e) { /* degrade: not sent */ }

    bot_ok(['date' => $date, 'sent' => $sent]);
}

// --- POST /api/bot/admin/morning-sent -----------------------------------------

function bot_morning_sent_mark() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') adm_fail(405, 'Method not allowed.');

    $db = adm_db();
    if ($db === null) adm_fail(500, 'Database is not available.');

    $in = adm_json_body();
    $date = adm_valid_date($in['date'] ?? '');
    if ($date === null) adm_fail(400, 'date must be YYYY-MM-DD.');

    adm_ensure_morning_table($db);

    // Idempotent: a re-mark only refreshes sent_at.
    try {
        $stmt = $db->prepare(
            'INSERT INTO bot_morning_sent (sent_date) VALUES (?) '
            . 'ON DUPLICATE KEY UPDATE sent_at = NOW()'
        );
        $stmt->bind_param('s', $date);
        if (!$stmt->execute()) {
            $stmt->close();
            adm_fail(500, 'Could not mark the morning report as sent.');
        }
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        adm_fail(500, 'Could not mark the morning report as sent.');
    }

    bot_ok(['ok' => true, 'date' => $date, 'sent' => true]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/stats' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_admin_stats(); }
//   if ($bp === 'admin/morning-sent' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_morning_sent_get(); }
//   if ($bp === 'admin/morning-sent' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_morning_sent_mark(); }
//
// LIVE CURL TEST (GET /admin/stats is read-only — no money moves,
// no rows are written):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/admin/stats" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"date":"YYYY-MM-DD","from":"YYYY-MM-DD",
//      "days":1,"orders":N,"completed":N,"revenue_etb":N.NN,
//      "net_profit_etb":N.NN,
//      "new_users":N,"top_service":"..."|null,"top_quantity":N,
//      "deposits_count":N,"deposits_etb":N.NN,
//      "provider_balance_usd":N.NN}
//      with "date" = today's date in EAT. On a quiet day every count
//      may legitimately be 0 and top_service null — that is a correct
//      answer, not an error. net_profit_etb must equal
//      revenue_etb x 220/420 (e.g. revenue 420.00 -> net 220.00).
//      provider_balance_usd is present when the provider answers
//      (compare it with the provider panel's own balance figure);
//      when the provider is unreachable the field is OMITTED and
//      every other figure is still there — that is correct too,
//      not an error.
//   curl -s "https://paxyo.et/api/bot/admin/stats?days=7" -H "X-Bot-Secret: $SECRET"
//   -> same shape with "days":7 and "from" = 6 days ago in EAT;
//      the counts cover the whole 7-day window. days=0, days=abc
//      and days=999 behave as days=1 / days=1 / days=90.
//   curl -s "https://paxyo.et/api/bot/admin/stats?day=yesterday" -H "X-Bot-Secret: $SECRET"
//   -> same shape with "days":1, "day":"yesterday", "from" =
//      yesterday in EAT and "date" = today in EAT; the counts
//      cover yesterday only. Cross-check: the orders count must
//      equal SELECT COUNT(*) FROM orders WHERE created_at >=
//      <yesterday 00:00 EAT in UTC> AND created_at < <today
//      00:00 EAT in UTC>.
//   curl -s "https://paxyo.et/api/bot/admin/stats?day=bogus" -H "X-Bot-Secret: $SECRET"
//   -> behaves as the plain ?days=1 window (no "day" key).
//   Without the header (or with a wrong secret) the request must be
//   refused by bot.php's existing X-Bot-Secret check, before this
//   code runs:
//   curl -s "https://paxyo.et/api/bot/admin/stats"
//   -> expect the usual auth error (401/403), NOT the stats.
//   No test rows to delete for the stats GETs: they write nothing.
//   Morning-sent marker (writes one row per date, idempotent —
//   test with a past date, then delete the row):
//   curl -s "https://paxyo.et/api/bot/admin/morning-sent?date=2026-01-01" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"date":"2026-01-01","sent":false}.
//   curl -s -X POST "https://paxyo.et/api/bot/admin/morning-sent" -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" -d '{"date":"2026-01-01"}'
//   -> expect {"success":true,"ok":true,"date":"2026-01-01","sent":true}.
//   curl -s "https://paxyo.et/api/bot/admin/morning-sent?date=2026-01-01" -H "X-Bot-Secret: $SECRET"
//   -> expect sent true now.
//   curl -s -X POST "https://paxyo.et/api/bot/admin/morning-sent" -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" -d '{"date":"2026-01-01"}'
//   -> expect sent true again (idempotent, no error).
//   mysql -e "DELETE FROM bot_morning_sent WHERE sent_date='2026-01-01';"
//   curl -s -X POST "https://paxyo.et/api/bot/admin/morning-sent" -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" -d '{"date":"not-a-date"}'
//   -> expect HTTP 400 (date must be YYYY-MM-DD).
// ============================================================================
