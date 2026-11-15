<?php
// ============================================================================
// Targeted-broadcast audience for the Paxyo Bot API
// (public_html/api/bot.php).
// Written 15 Nov 2026 for the NEW admin chat bot (a brand-new bot,
// NOT @paxadmin_bot). The bot asks "send this to users who never
// deposited", shows the count + the exact message, William confirms,
// and only then the BOT sends (it holds ADMIN_BOT_TOKEN and sends
// via python-telegram-bot). This endpoint only RESOLVES the
// audience — it never sends anything and never writes a row.
//
// THE AUDIENCE CONTRACT (authoritative — the admin-panel
// targeted-broadcasts feature reuses this same endpoint, so the
// shape is the contract, not a one-off):
//   GET /api/bot/broadcasts/audience?segment=<segment>&service_id=<id>
//     -> {"segment":"never_deposited","service_id":null,
//         "count":42,
//         "telegram_ids":[779060335, ...]}
//   bot_ok() adds "success":true around it, as on every other
//   endpoint; the bot reads the named keys and ignores the rest.
//
// SEGMENTS:
//   all             — every user in auth (every tg_id).
//   never_deposited — users with NO completed deposit.
//   deposited       — users with at least one completed deposit.
//   service         — users who ordered a given service at least
//                     once. Requires service_id (a provider service
//                     id, e.g. 6139). A user who ordered it twice
//                     counts ONCE; a user who never ordered it is
//                     never included.
//
// RULES:
//   * telegram_ids are DISTINCT — a user appears at most once,
//     whatever the segment. The bot additionally dedupes before
//     sending, but the server is the authority.
//   * Only COMPLETED deposits count as "deposited" (a pending or
//     failed deposit is not a deposit). A completed order counts
//     for the service segment whatever its status (placed is
//     enough — the user bought it).
//   * Empty audience is a correct answer: count 0, telegram_ids [].
//     The bot then says nobody matches and sends nothing.
//   * Unknown segment -> 400. service segment without a valid
//     service_id -> 400. Nothing here is ever a 500 for bad input.
//
// AUTH: X-Bot-Secret, same as the session/confusion/stats
// endpoints. This is a BOT endpoint, called by the admin bot with
// the secret — it is NOT the human-admin session
// (admin_authenticated) and it must NOT be called from a
// user-facing page. No telegram_id is needed: the audience is
// owner-wide, not per-user.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-broadcasts.php  (this file must pass on its own)
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
// one is missing (each query degrades to an empty audience, never
// a 500, except a missing orders service column on the service
// segment, which is a 400 with a plain message):
//   B1. auth has tg_id — confirmed from the local server files
//       (api-deposits.php selects tg_id from auth). tg_id IS the
//       Telegram id, and it is what the bot sends messages to.
//   B2. deposits has user_id, status, created_at — user_id IS the
//       telegram id (confirmed: api-deposits.php binds the
//       telegram_id into deposits.user_id on INSERT). status
//       'completed' is the paid state (the value the deposit
//       recheck writes). A deposit row with no matching auth row
//       still counts for the `deposited` segment (its user_id is a
//       real Telegram id); it is simply not in `all` until an auth
//       row exists.
//   B3. orders has telegram_id and a service column — the service
//       column is DISCOVERED at runtime (information_schema), in
//       the same order as api-admin-stats.php: service_id,
//       provider_service_id, service, then service_name. The id
//       the bot sends is a provider service id (the number users
//       see, e.g. 6139), so the match is against whichever id
//       column exists; a service_name column matches by name.
//       - No service column at all: the service segment answers
//         400 ("orders carry no service column"), the other three
//         segments are unaffected.
//       TO VERIFY: SHOW COLUMNS FROM orders — if the live table
//       names the service column differently, add the name to the
//       list in brd_discover_service_column().
//   B4. No rate limit is applied here beyond bot.php's existing
//       X-Bot-Secret check. The admin bot calls this at most once
//       per broadcast preview (and once per confirm, if it
//       re-resolves) — a handful of calls a day. Add the same
//       bot_rate_limit(...) call the other endpoints use to the
//       dispatch line if the installer wants one (copy the exact
//       call from the orders handler).
//   B5. Very large audiences come back as one JSON array. Paxyo
//       has a few thousand users at most today, so this is fine;
//       if the audience ever grows past ~50,000 ids, page it
//       (limit/offset) instead of growing this response.
// ============================================================================

// --- small helpers (brd_ prefix so nothing collides with bot.php) -----------

function brd_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function brd_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

// Does table $table have column $col? (information_schema read; if
// the check itself fails, answer "no" — the caller degrades.)
function brd_has_column($db, $table, $col) {
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
function brd_has_table($db, $table) {
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

// Which service column does orders have, if any? Returns
// ['column' => col-or-null, 'is_name' => bool]. First match wins.
function brd_discover_service_column($db) {
    foreach (['service_id', 'provider_service_id', 'service'] as $col) {
        if (brd_has_column($db, 'orders', $col)) {
            return ['column' => $col, 'is_name' => false];
        }
    }
    if (brd_has_column($db, 'orders', 'service_name')) {
        return ['column' => 'service_name', 'is_name' => true];
    }
    return ['column' => null, 'is_name' => false];
}

// Run a query returning one integer column per row; returns the
// values as a list of ints (empty list when the query fails or
// returns nothing). Never throws.
function brd_id_list($db, $sql, $types, $params) {
    $out = [];
    try {
        $stmt = $db->prepare($sql);
        if ($types !== '' && $params) $stmt->bind_param($types, ...$params);
        $stmt->execute();
        $res = $stmt->get_result();
        while ($row = $res->fetch_row()) {
            if ($row[0] === null) continue;
            $id = (int)$row[0];
            if ($id > 0) $out[] = $id;
        }
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        return [];
    }
    // DISTINCT is in the SQL; this is a belt-and-braces dedupe so
    // the contract (a user appears at most once) holds even if a
    // query is ever edited without it.
    return array_values(array_unique($out));
}

// --- GET /api/bot/broadcasts/audience ----------------------------------------

function bot_broadcasts_audience() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') brd_fail(405, 'Method not allowed.');

    $db = brd_db();
    if ($db === null) brd_fail(500, 'Database is not available.');

    $segment = strtolower(trim((string)($_GET['segment'] ?? '')));
    $valid = ['all', 'never_deposited', 'deposited', 'service'];
    if (!in_array($segment, $valid, true)) {
        brd_fail(400, 'segment must be all, never_deposited, deposited or service.');
    }

    $service_id = null;
    if ($segment === 'service') {
        $raw = $_GET['service_id'] ?? '';
        if (!is_numeric($raw) || (int)$raw <= 0) {
            brd_fail(400, 'service_id is required for the service segment.');
        }
        $service_id = (int)$raw;
    }

    try { $db->query("SET time_zone = '+00:00'"); } catch (mysqli_sql_exception $e) { /* keep going */ }

    $ids = [];
    if ($segment === 'all') {
        // Every user in auth. tg_id IS the Telegram id.
        $ids = brd_id_list($db, 'SELECT DISTINCT tg_id FROM auth WHERE tg_id IS NOT NULL', '', []);
    } elseif ($segment === 'deposited') {
        // At least one completed deposit. deposits.user_id IS the
        // telegram id (see B2).
        if (brd_has_table($db, 'deposits') && brd_has_column($db, 'deposits', 'user_id') && brd_has_column($db, 'deposits', 'status')) {
            $ids = brd_id_list($db, "SELECT DISTINCT user_id FROM deposits WHERE status = 'completed' AND user_id IS NOT NULL", '', []);
        }
    } elseif ($segment === 'never_deposited') {
        // In auth, with NO completed deposit. NOT EXISTS (not
        // NOT IN) so a NULL user_id in deposits can never wipe
        // the whole list.
        if (brd_has_table($db, 'deposits') && brd_has_column($db, 'deposits', 'user_id') && brd_has_column($db, 'deposits', 'status')) {
            $ids = brd_id_list(
                $db,
                "SELECT DISTINCT a.tg_id FROM auth a WHERE a.tg_id IS NOT NULL "
                . "AND NOT EXISTS (SELECT 1 FROM deposits d WHERE d.user_id = a.tg_id AND d.status = 'completed')",
                '', []
            );
        } else {
            // No deposits table at all: nobody has deposited.
            $ids = brd_id_list($db, 'SELECT DISTINCT tg_id FROM auth WHERE tg_id IS NOT NULL', '', []);
        }
    } else { // service
        $disc = brd_discover_service_column($db);
        if ($disc['column'] === null) {
            brd_fail(400, 'orders carry no service column, so the service audience cannot be resolved.');
        }
        $col = $disc['column'];
        if ($disc['is_name']) {
            // service_name column: match by name. The bot sends a
            // numeric id, so a name match only happens when the
            // stored name IS that number; anything else is 400.
            brd_fail(400, 'orders store the service name, not an id, so the service audience cannot be resolved by service_id.');
        } else {
            $ids = brd_id_list(
                $db,
                'SELECT DISTINCT telegram_id FROM orders WHERE `' . $col . '` = ? AND telegram_id IS NOT NULL',
                'i', [$service_id]
            );
        }
    }

    bot_ok([
        'segment' => $segment,
        'service_id' => $service_id,
        'count' => count($ids),
        'telegram_ids' => $ids,
    ]);
}

// ============================================================================
// DISPATCH — insert this line in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'broadcasts/audience' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_broadcasts_audience(); }
//
// LIVE CURL TEST (read-only GET — no money moves, no rows written,
// and NOTHING is sent to any user by this endpoint):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=all" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"segment":"all","service_id":null,
//      "count":N,"telegram_ids":[...]} — count = number of auth rows.
//   curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=never_deposited" -H "X-Bot-Secret: $SECRET"
//   curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=deposited" -H "X-Bot-Secret: $SECRET"
//   -> never_deposited count + deposited count = all count (every
//      auth user either has a completed deposit or does not).
//   curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=service&service_id=6139" -H "X-Bot-Secret: $SECRET"
//   -> expect only users who ordered service 6139, each id once.
//      Cross-check: SELECT COUNT(DISTINCT telegram_id) FROM orders
//      WHERE service_id = 6139 (or the live service column) must
//      equal "count".
//   curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=bogus" -H "X-Bot-Secret: $SECRET"
//   -> expect HTTP 400, success:false.
//   curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=service" -H "X-Bot-Secret: $SECRET"
//   -> expect HTTP 400 (service_id is required).
//   Without the header (or with a wrong secret) the request must be
//   refused by bot.php's existing X-Bot-Secret check, before this
//   code runs:
//   curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=all"
//   -> expect the usual auth error (401/403), NOT the audience.
//   No test rows to delete: this endpoint writes nothing.
// ============================================================================
