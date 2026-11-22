<?php
// ============================================================================
// Total user count + biggest balances for the admin bot (22 Nov 2026).
// William asked the admin bot "How many users i do have" and it
// answered "Today: 0 new users" — the stats endpoint only reports
// NEW users in a window, never the total. He then asked "Who has
// most biggest balance" and the bot said it cannot list users in
// chat, because no endpoint returns balances ranked. These two
// endpoints answer both questions in chat.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/admin/users-count
//     -> {"total_users": 42}
//     The number of rows in auth, i.e. every Paxyo user who ever
//     started the customer bot. No window, no date: the total is
//     the total. (The stats endpoint's new_users is still the
//     per-window figure — this endpoint is the overall one.)
//
//   GET /api/bot/admin/top-balances?limit=5
//     -> {"users": [{"telegram_id": 779060335, "username": "Paxyo",
//         "first_name": "William", "balance": 1234.50}, ...],
//         "limit": 5}
//     The users with the largest Paxyo balances, highest first.
//     limit defaults to 5 and is clamped to 1..10; a non-numeric
//     limit behaves as 5. A user with no username shows as
//     first_name + Telegram id on the bot side. Balances are in
//     ETB, rounded to 2 decimals. The list is the admin's own
//     data, shown only in the allowlisted admin chat — never in
//     the customer bot.
//
// WHY A SEPARATE FILE: api-admin-stats.php is already spliced
// into the live bot.php. Adding these endpoints to it would mean
// removing the old spliced copy first, and a bad removal (two
// copies of bot_admin_stats in one file) is a fatal error the
// linter does not catch. A new file installs by the plain
// first-install flow below and never touches the live stats code.
//
// AUTH: X-Bot-Secret, same as the session/confusion endpoints.
// This is a BOT endpoint, called by @atlasdeskadmin_bot with the
// secret — it is NOT the human-admin session
// (admin_authenticated) and it must NOT be called from a
// user-facing page. No telegram_id is needed: both figures are
// owner-wide, not per-user.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. Fetch this file (curl from GitHub raw, never open GitHub
//      in a browser) and php -l api-admin-users.php (must pass).
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404
//      fallback, then append this file's code WITHOUT its first
//      line (the "<?php" opening tag — bot.php is already inside
//      one PHP block) to the end of bot.php.
//   3. php -l api/bot.php              (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). Read-only
//      GETs — no money moves, no rows are written.
//
// ASSUMPTIONS — every column this file needs, and what happens
// when one is missing (each query degrades to zero/empty, never
// a 500):
//   A1. auth has tg_id, username, first_name, balance — confirmed
//       from the local server files (api-deposits.php selects
//       tg_id, balance from auth; api-admin-user-balance.php
//       returns first_name and balance for one tg_id). COUNT(*)
//       needs no column at all, so the total reads even if a
//       column is missing; the top-balances query needs all
//       four, and degrades to an empty list when the SELECT
//       fails (a NULL balance reads as 0.00, a NULL username or
//       first_name reads as "").
//   A2. No table is created and no row is written: both GETs are
//       pure reads.
//   A3. All money is in ETB; balances are rounded to 2 decimals.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for the success reply (it adds
//     "success":true, as on the other endpoints). Errors use
//     aus_fail() below, which returns {"success":false,
//     "error":...,"message":...} — the bot reads both keys.
//     A 404 from either endpoint means "not live yet" to the bot
//     (admin_users_count() / admin_top_balances() return None);
//     a 500 raises, so every query is wrapped and degrades
//     instead of dying.
//   - The helper prefix is aus_ (admin users). Every spliced
//     file in bot.php must use its own prefix — aus_ is unused
//     (checked 22 Nov 2026 against all server/*.php).
// ============================================================================

// --- small helpers (aus_ prefix so nothing collides with bot.php) -----------

function aus_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function aus_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

// Run a scalar query (one row, one value) and return the value, or
// $default when the query fails or returns nothing. Never throws.
function aus_scalar($db, $sql, $default) {
    try {
        $stmt = $db->prepare($sql);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_row();
        $stmt->close();
        if ($row === null || $row === false || $row[0] === null) return $default;
        return $row[0];
    } catch (mysqli_sql_exception $e) {
        return $default;
    }
}

// --- GET /api/bot/admin/users-count ------------------------------------------

function bot_admin_users_count() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') aus_fail(405, 'Method not allowed.');

    $db = aus_db();
    if ($db === null) aus_fail(500, 'Database is not available.');

    // Every row in auth is a Paxyo user (see A1). COUNT(*) needs
    // no column, so this reads even on a table missing created_at.
    $total = (int)aus_scalar($db, 'SELECT COUNT(*) FROM auth', 0);

    bot_ok(['total_users' => $total]);
}

// --- GET /api/bot/admin/top-balances -----------------------------------------

function bot_admin_top_balances() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') aus_fail(405, 'Method not allowed.');

    $db = aus_db();
    if ($db === null) aus_fail(500, 'Database is not available.');

    // ?limit=N — default 5, clamped to 1..10; non-numeric behaves as 5.
    $limit = 5;
    if (isset($_GET['limit']) && is_numeric($_GET['limit'])) {
        $limit = (int)$_GET['limit'];
    }
    if ($limit < 1) $limit = 1;
    if ($limit > 10) $limit = 10;

    $users = [];
    try {
        $stmt = $db->prepare(
            'SELECT tg_id, username, first_name, balance FROM auth '
            . 'ORDER BY balance DESC, tg_id ASC LIMIT ?'
        );
        $stmt->bind_param('i', $limit);
        $stmt->execute();
        $res = $stmt->get_result();
        while ($row = $res->fetch_assoc()) {
            $users[] = [
                'telegram_id' => (int)$row['tg_id'],
                'username' => (string)($row['username'] ?? ''),
                'first_name' => (string)($row['first_name'] ?? ''),
                'balance' => round((float)($row['balance'] ?? 0), 2),
            ];
        }
        $stmt->close();
    } catch (mysqli_sql_exception $e) { /* degrade: empty list */ }

    bot_ok(['users' => $users, 'limit' => $limit]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/users-count' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_admin_users_count(); }
//   if ($bp === 'admin/top-balances' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_admin_top_balances(); }
//
// LIVE CURL TEST (both GETs are read-only — no money moves, no
// rows are written):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/admin/users-count" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"total_users":N} with N the number of
//      rows in auth (cross-check: SELECT COUNT(*) FROM auth; — the
//      two must match; a 0 here with users in the table means the
//      query failed, not that there are no users).
//   curl -s "https://paxyo.et/api/bot/admin/top-balances" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"users":[...],"limit":5} with the
//      users ordered by balance descending; the first row's balance
//      must equal SELECT MAX(balance) FROM auth; (cross-check with
//      SELECT tg_id, username, first_name, balance FROM auth
//      ORDER BY balance DESC LIMIT 5; — same rows, same order).
//   curl -s "https://paxyo.et/api/bot/admin/top-balances?limit=2" -H "X-Bot-Secret: $SECRET"
//   -> expect exactly 2 users and "limit":2. limit=0, limit=abc
//      and limit=999 behave as limit=1 / limit=5 / limit=10.
//   Without the header (or with a wrong secret) the request must
//   be refused by bot.php's existing X-Bot-Secret check, before
//   this code runs:
//   curl -s "https://paxyo.et/api/bot/admin/users-count"
//   -> expect the usual auth error (401/403), NOT the count.
//   No test rows to delete: both GETs write nothing.
// ============================================================================
