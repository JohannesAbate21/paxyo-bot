<?php
// ============================================================================
// Win-back audience + send recording for the Paxyo Bot API
// (public_html/api/bot.php).
// Written 15 Nov 2026 for the NEW admin chat bot (a brand-new bot,
// NOT @paxadmin_bot). The bot's /winbacks command counts the users
// who have gone quiet (no order in 14+ days), William confirms,
// and only then the BOT sends one personal message each (via
// python-telegram-bot, naming the service they usually order) and
// records the sends here, so nobody is messaged twice in 30 days.
// This file only RESOLVES the audience and RECORDS sends — it
// never sends anything itself.
//
// ENDPOINTS (behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/winbacks/audience?days=14
//     -> {"days":14,"count":3,
//         "users":[{"telegram_id":779060335,
//                   "usual_service":"TikTok Video Views",
//                   "usual_quantity":1000}, ...]}
//   POST /api/bot/winbacks/record {"telegram_ids":[779060335, ...]}
//     -> {"ok":true,"recorded":3}
//   bot_ok() adds "success":true around it, as on every other
//   endpoint; the bot reads the named keys and ignores the rest.
//
// AUDIENCE RULES:
//   * A user qualifies when they have >= 1 order AND their most
//     recent order is more than `days` ago (default 14, clamped
//     to 1..90; an invalid value behaves as 14).
//   * EXCLUDED: users with a win-back sent in the last 30 days
//     (a row in bot_winback_sends with sent_at within 30 days).
//   * EXCLUDED: users with a non-empty draft in bot_sessions —
//     they are mid-order, not quiet. draft is a JSON TEXT column:
//     NULL, '', 'null', '{}' and '[]' all count as "no draft".
//     A bot_sessions table that does not exist yet excludes nobody.
//   * usual_service / usual_quantity = the user's most-ordered
//     service (by order count) and the quantity they most recently
//     ordered of it. Best-effort: "" / null when the orders table
//     carries no service/quantity column or the user has none.
//     Nothing is ever invented — an unknown service is "".
//   * Empty audience is a correct answer: count 0, users [].
//     The bot then says "No users have gone quiet." and sends
//     nothing.
//
// RECORD RULES:
//   * INSERT ... ON DUPLICATE KEY UPDATE sent_at = NOW() —
//     recording the same user twice only refreshes the timestamp,
//     never errors, never double-counts.
//   * telegram_ids must be a list of positive integers; an empty
//     list records 0 and is not an error.
//
// AUTH: X-Bot-Secret, same as the session/confusion/stats
// endpoints. This is a BOT endpoint, called by the admin bot with
// the secret — it is NOT the human-admin session
// (admin_authenticated) and it must NOT be called from a
// user-facing page. No telegram_id is needed: the audience is
// owner-wide, not per-user.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-winbacks.php         (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block) to the end of bot.php.
//   3. php -l api/bot.php              (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). GET is
//      read-only; POST /winbacks/record writes one row per user
//      (idempotent) — test it with a throwaway telegram id and
//      delete the row afterwards (see the footer).
//
// ASSUMPTIONS — every column this file needs, and what happens when
// one is missing (each query degrades to an empty audience /
// unknown service, never a 500):
//   W1. orders has telegram_id and created_at — confirmed from the
//       local server files (api-deposits.php / HANDOVER.md).
//       created_at is compared against NOW() in MySQL server time;
//       if the server clock is not EAT, the day boundary is off
//       by the server offset (same caveat as api-admin-stats.php
//       A2 — check the live clock on install).
//   W2. orders' service/quantity columns are DISCOVERED at runtime
//       (information_schema), in the same order as
//       api-admin-stats.php: service_id, provider_service_id,
//       service, then service_name; quantity, then qty. No service
//       column -> usual_service "" (the audience still resolves).
//       TO VERIFY: SHOW COLUMNS FROM orders — if the live table
//       names the columns differently, add the name to the lists
//       in wbk_discover_orders_columns().
//   W3. The service NAME comes from a `services` table with a
//       `name` column and either provider_service_id or id to join
//       on (same as api-admin-stats.php A5). If there is no
//       `services` table, or the id matches no row, the name falls
//       back to "Service #<id>". If orders stores service_name
//       directly, that name is used as-is.
//   W4. bot_sessions has telegram_id and draft (JSON TEXT, NULL
//       when no draft) — confirmed from api-bot-sessions.php
//       (CREATE TABLE bot_sessions: telegram_id BIGINT PK,
//       history TEXT, draft TEXT NULL, lang, updated_at). The
//       draft is written by POST /sessions as json_encode of an
//       array/object, or NULL — so 'null', '{}' and '[]' are all
//       possible "empty" shapes and all count as no draft.
//   W5. bot_winback_sends is created by this file itself
//       (CREATE TABLE IF NOT EXISTS, telegram_id PK, sent_at).
//       No rate limit is applied here beyond bot.php's existing
//       X-Bot-Secret check — the admin bot calls the audience at
//       most once per /winbacks tap and records once per Confirm.
// ============================================================================

// --- small helpers (wbk_ prefix so nothing collides with bot.php) -----------

function wbk_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function wbk_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function wbk_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

// Does table $table have column $col? (information_schema read; if
// the check itself fails, answer "no" — the caller degrades.)
function wbk_has_column($db, $table, $col) {
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
function wbk_has_table($db, $table) {
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

function wbk_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_winback_sends (
        telegram_id BIGINT NOT NULL PRIMARY KEY,
        sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_wbk_sent (sent_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Discover which service/quantity columns orders actually has.
// Returns ['service' => col-or-null, 'service_is_name' => bool,
//          'quantity' => col-or-null]. First match wins, in the
// order listed in W2.
function wbk_discover_orders_columns($db) {
    $service = null;
    $service_is_name = false;
    foreach (['service_id', 'provider_service_id', 'service'] as $col) {
        if (wbk_has_column($db, 'orders', $col)) { $service = $col; break; }
    }
    if ($service === null && wbk_has_column($db, 'orders', 'service_name')) {
        $service = 'service_name';
        $service_is_name = true;
    }
    $quantity = null;
    foreach (['quantity', 'qty'] as $col) {
        if (wbk_has_column($db, 'orders', $col)) { $quantity = $col; break; }
    }
    return ['service' => $service, 'service_is_name' => $service_is_name, 'quantity' => $quantity];
}

// Resolve a service id to its display name via the services table.
// Falls back to "Service #<id>" when the table or the row is missing.
function wbk_service_name($db, $service_id) {
    $service_id = (int)$service_id;
    if ($service_id <= 0) return null;
    if (wbk_has_table($db, 'services') && wbk_has_column($db, 'services', 'name')) {
        $join_col = null;
        foreach (['provider_service_id', 'id'] as $col) {
            if (wbk_has_column($db, 'services', $col)) { $join_col = $col; break; }
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

// The user's most-ordered service and the quantity they most
// recently ordered of it. Returns ['service' => string-or-'',
// 'quantity' => int-or-null]. Best-effort: "" / null when the
// columns are missing or the user has no usable order.
function wbk_usual_service($db, $telegram_id, $cols) {
    $out = ['service' => '', 'quantity' => null];
    if ($cols['service'] === null) return $out;
    $svc = $cols['service'];
    try {
        // Most-ordered service for this user (by order count).
        $stmt = $db->prepare(
            'SELECT `' . $svc . '` AS svc, COUNT(*) AS n FROM orders '
            . 'WHERE telegram_id = ? AND `' . $svc . '` IS NOT NULL AND `' . $svc . "` <> '' "
            . 'GROUP BY `' . $svc . '` ORDER BY n DESC LIMIT 1'
        );
        $stmt->bind_param('i', $telegram_id);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_assoc();
        $stmt->close();
        if (!$row) return $out;
        $top = $row['svc'];
        if ($cols['service_is_name']) {
            $out['service'] = (string)$top;
        } else {
            $out['service'] = wbk_service_name($db, $top);
        }
        // Quantity most recently ordered of that service.
        if ($cols['quantity'] !== null) {
            $qty = $cols['quantity'];
            $stmt = $db->prepare(
                'SELECT `' . $qty . '` AS q FROM orders '
                . 'WHERE telegram_id = ? AND `' . $svc . '` = ? '
                . 'ORDER BY created_at DESC LIMIT 1'
            );
            $stmt->bind_param('is', $telegram_id, $top);
            $stmt->execute();
            $qrow = $stmt->get_result()->fetch_assoc();
            $stmt->close();
            if ($qrow && $qrow['q'] !== null) $out['quantity'] = (int)$qrow['q'];
        }
    } catch (mysqli_sql_exception $e) { /* degrade: "" / null */ }
    return $out;
}

// --- GET /api/bot/winbacks/audience ------------------------------------------

function bot_winbacks_audience() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') wbk_fail(405, 'Method not allowed.');

    $db = wbk_db();
    if ($db === null) wbk_fail(500, 'Database is not available.');

    // ?days=N — the most recent order must be more than N days
    // ago. Default 14, clamped to 1..90.
    $days = 14;
    if (isset($_GET['days']) && is_numeric($_GET['days'])) {
        $days = (int)$_GET['days'];
    }
    if ($days < 1) $days = 1;
    if ($days > 90) $days = 90;

    wbk_ensure_table($db);

    $users = [];
    try {
        // Users with >= 1 order whose MOST RECENT order is older
        // than $days. GROUP BY + HAVING MAX(created_at) is the
        // whole rule in one query (>= 1 order is implied: a user
        // with no orders has no group at all).
        $sql =
            'SELECT telegram_id FROM orders '
            . 'WHERE telegram_id IS NOT NULL '
            . 'GROUP BY telegram_id '
            . 'HAVING MAX(created_at) < DATE_SUB(NOW(), INTERVAL ? DAY)';
        $stmt = $db->prepare($sql);
        $stmt->bind_param('i', $days);
        $stmt->execute();
        $res = $stmt->get_result();
        $ids = [];
        while ($row = $res->fetch_row()) {
            if ($row[0] === null) continue;
            $id = (int)$row[0];
            if ($id > 0) $ids[] = $id;
        }
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        $ids = [];
    }

    $cols = wbk_discover_orders_columns($db);
    foreach ($ids as $tid) {
        // Exclude: win-back sent in the last 30 days.
        $recent = false;
        try {
            $stmt = $db->prepare(
                'SELECT 1 FROM bot_winback_sends WHERE telegram_id = ? '
                . 'AND sent_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) LIMIT 1'
            );
            $stmt->bind_param('i', $tid);
            $stmt->execute();
            $recent = $stmt->get_result()->fetch_assoc() !== null;
            $stmt->close();
        } catch (mysqli_sql_exception $e) { /* keep the user in */ }
        if ($recent) continue;

        // Exclude: a non-empty draft in bot_sessions — the user
        // is mid-order, not quiet. NULL / '' / 'null' / '{}' /
        // '[]' all count as "no draft" (see W4).
        if (wbk_has_table($db, 'bot_sessions') && wbk_has_column($db, 'bot_sessions', 'draft')) {
            $has_draft = false;
            try {
                $stmt = $db->prepare('SELECT draft FROM bot_sessions WHERE telegram_id = ? LIMIT 1');
                $stmt->bind_param('i', $tid);
                $stmt->execute();
                $srow = $stmt->get_result()->fetch_assoc();
                $stmt->close();
                if ($srow) {
                    $draft = $srow['draft'];
                    if ($draft !== null) {
                        $trimmed = trim((string)$draft);
                        if ($trimmed !== '' && $trimmed !== 'null' && $trimmed !== '{}' && $trimmed !== '[]') {
                            $has_draft = true;
                        }
                    }
                }
            } catch (mysqli_sql_exception $e) { /* keep the user in */ }
            if ($has_draft) continue;
        }

        $usual = wbk_usual_service($db, $tid, $cols);
        $users[] = [
            'telegram_id' => $tid,
            'usual_service' => $usual['service'],
            'usual_quantity' => $usual['quantity'],
        ];
    }

    bot_ok([
        'days' => $days,
        'count' => count($users),
        'users' => $users,
    ]);
}

// --- POST /api/bot/winbacks/record --------------------------------------------

function bot_winbacks_record() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') wbk_fail(405, 'Method not allowed.');

    $db = wbk_db();
    if ($db === null) wbk_fail(500, 'Database is not available.');

    $in = wbk_json_body();
    $ids = $in['telegram_ids'] ?? null;
    if (!is_array($ids)) wbk_fail(400, 'telegram_ids must be a list.');
    $clean = [];
    foreach ($ids as $raw) {
        $id = (int)$raw;
        if ($id > 0) $clean[] = $id;
    }
    $clean = array_values(array_unique($clean));

    wbk_ensure_table($db);

    // Idempotent: a re-record only refreshes sent_at.
    $recorded = 0;
    try {
        $stmt = $db->prepare(
            'INSERT INTO bot_winback_sends (telegram_id) VALUES (?) '
            . 'ON DUPLICATE KEY UPDATE sent_at = NOW()'
        );
        foreach ($clean as $tid) {
            $stmt->bind_param('i', $tid);
            if ($stmt->execute()) $recorded++;
        }
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        wbk_fail(500, 'Could not record the win-back sends.');
    }

    bot_ok(['ok' => true, 'recorded' => $recorded]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'winbacks/audience' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_winbacks_audience(); }
//   if ($bp === 'winbacks/record' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_winbacks_record(); }
//
// LIVE CURL TEST (GET is read-only — no money moves, no rows are
// written, and NOTHING is sent to any user by this endpoint):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/winbacks/audience?days=14" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"days":14,"count":N,
//      "users":[{"telegram_id":...,"usual_service":"...",
//      "usual_quantity":N}, ...]} — count = number of users whose
//      most recent order is older than 14 days, minus anyone
//      messaged in the last 30 days or with a draft in progress.
//      Cross-check: SELECT telegram_id, MAX(created_at) FROM orders
//      GROUP BY telegram_id HAVING MAX(created_at) <
//      DATE_SUB(NOW(), INTERVAL 14 DAY) must list the same ids
//      before the 30-day / draft exclusions.
//   curl -s "https://paxyo.et/api/bot/winbacks/audience?days=abc" -H "X-Bot-Secret: $SECRET"
//   -> expect days 14 (invalid behaves as the default).
//   curl -s "https://paxyo.et/api/bot/winbacks/audience" -H "X-Bot-Secret: $SECRET"
//   -> same as days=14.
//   Without the header (or with a wrong secret) the request must be
//   refused by bot.php's existing X-Bot-Secret check, before this
//   code runs:
//   curl -s "https://paxyo.et/api/bot/winbacks/audience?days=14"
//   -> expect the usual auth error (401/403), NOT the audience.
//   POST /winbacks/record writes one row per id (idempotent —
//   test with a throwaway id, then delete the row):
//   curl -s -X POST "https://paxyo.et/api/bot/winbacks/record" -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" -d '{"telegram_ids":[123456789]}'
//   -> expect {"success":true,"ok":true,"recorded":1}.
//   curl -s -X POST "https://paxyo.et/api/bot/winbacks/record" -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" -d '{"telegram_ids":[123456789]}'
//   -> expect recorded 1 again (idempotent, no error).
//   mysql -e "SELECT * FROM bot_winback_sends WHERE telegram_id=123456789;"
//   -> one row; then DELETE FROM bot_winback_sends WHERE telegram_id=123456789;
//   curl -s -X POST "https://paxyo.et/api/bot/winbacks/record" -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" -d '{"telegram_ids":[]}'
//   -> expect {"success":true,"ok":true,"recorded":0}.
//   curl -s -X POST "https://paxyo.et/api/bot/winbacks/record" -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" -d '{}'
//   -> expect HTTP 400 (telegram_ids must be a list).
// ============================================================================
