<?php
// ============================================================================
// Username -> user lookup for the admin bot (19 Nov 2026).
// SERVER SIDE ONLY. Written for @atlasdeskadmin_bot (the admin chat
// bot in this repo, admin_bot.py) — William-only, allowlist from env
// ADMIN_TELEGRAM_IDS in the bot.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/admin/users/lookup?username={name}
//     -> {"success":true,"telegram_id":N,"username":"...",
//         "first_name":"...","balance":1234.50}
//     -> 404 {"success":false,"error":"User not found."} when no
//        Paxyo user has that username.
//   The username is matched EXACTLY against the auth.username
//   column (a leading @ is stripped first). A phone number can
//   never look a user up — the auth table has no phone column
//   (phone lives only in deposit records) — so username and
//   Telegram id are the only two ways to name a user, and this
//   endpoint is the username half. The balance half is
//   server/api-admin-user-balance.php (GET by Telegram id).
//
// WHY A SEPARATE ENDPOINT (and not a change to the balance file):
//   The balance endpoint is already pushed (commit aae8a75) and
//   its install is pending; changing it now would move the file
//   under the install. A lookup is also used by four bot intents
//   (balance check, balance adjust, deposit history, ban/unban),
//   so it earns its own small file, the same one-endpoint-per-file
//   shape as the other admin endpoints.
//
// ADMIN GATE — ONE LOCK:
//   X-Bot-Secret (bot.php's existing check): only a holder of the
//   bot secret can reach this endpoint at all — i.e. only the two
//   bots, never a browser or a user. Read-only: no token, no
//   Confirm, no audit row — a lookup moves nothing.
//
// USERNAME RULES (same as Telegram's own):
//   5-32 characters, letters / digits / underscore, starts with a
//   letter. Anything else is refused with 400 before any query.
//   MySQL's default collation compares varchar case-insensitively,
//   so "William" and "william" match the same row — the reply
//   returns the username exactly as stored, so the bot always
//   shows the stored spelling.
//
// ADMIN-BOT SPEC — the exact contract admin_bot.py implements
// (the admin-bot build implements it, and the tests for it live
// in test_admin_bot_offline.py):
//   Trigger: William types a user-targeted command with a
//     @username instead of a Telegram id, e.g. "balance of
//     @william", "add 500 ETB to @william", "deposit history of
//     @william", "ban @william". The bot resolves the name here
//     first, then runs the command against the Telegram id it
//     gets back.
//   Unknown username -> "There is no Paxyo user with username
//     @name." Endpoint not live (404 without that body) -> "The
//     user lookup is not connected yet".
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-user-lookup.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block) to the end of bot.php.
//   3. php -l api/bot.php            (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) — read-only, safe.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. bot_ok() RETURNS (does not exit) and adds "success":true
//       around the reply, as on every other admin endpoint
//       (api-admin-stats.php).
//   A2. The auth table carries tg_id, username, first_name,
//       balance (verified in-repo: api-deposits.php selects tg_id,
//       username, first_name, email from auth).
// ============================================================================

// --- small helpers (aul_ prefix so nothing collides with bot.php) -----------

function aul_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function aul_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

// One user row from auth by username, or null when no Paxyo user
// has that username. The match is exact on the username column
// (case-insensitive under MySQL's default collation); a leading @
// is stripped before the query.
function aul_user_row_by_username($db, $username) {
    $stmt = $db->prepare('SELECT tg_id, username, first_name, balance FROM auth WHERE username = ? LIMIT 1');
    $stmt->bind_param('s', $username);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// --- GET /api/bot/admin/users/lookup?username={name} ------------------------
// Read-only lookup: no token, no Confirm, no audit row — a lookup
// moves nothing.

function bot_aul_user_lookup() {
    $username = isset($_GET['username']) ? trim((string)$_GET['username']) : '';
    // A leading @ is not part of the name ("@william" -> "william").
    if (strlen($username) > 0 && $username[0] === '@') {
        $username = substr($username, 1);
    }
    if ($username === '') aul_fail(400, 'username is required.');
    // Telegram's own username rules: 5-32 chars, letters / digits
    // / underscore, starts with a letter. Anything else is refused
    // before any query — it cannot be a username.
    if (!preg_match('/^[A-Za-z][A-Za-z0-9_]{4,31}$/', $username)) {
        aul_fail(400, 'username does not look like a Telegram username.');
    }
    $db = aul_db();
    if ($db === null) aul_fail(500, 'Database is not available.');
    $row = aul_user_row_by_username($db, $username);
    if ($row === null) aul_fail(404, 'User not found.');
    bot_ok([
        'telegram_id' => (int)$row['tg_id'],
        'username' => $row['username'],
        'first_name' => $row['first_name'],
        'balance' => (float)$row['balance'],
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/users/lookup' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_aul_user_lookup(); }
//
// (The balance dispatch patterns are ^admin/users/(\d+)/... —
// "lookup" is not numeric, so this line cannot collide with them,
// but it must still come before any generic admin/users handler,
// if one ever exists.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-admin-user-lookup.php`
// on the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST — read-only, safe:
//   SECRET=<redacted>(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. Known username (use a real one from the auth table):
//   curl -s "https://paxyo.et/api/bot/admin/users/lookup?username=william" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"telegram_id":<number>,"username":"william","balance":<number>}
//   # 2. Same, with a leading @:
//   curl -s "https://paxyo.et/api/bot/admin/users/lookup?username=%40william" -H "X-Bot-Secret: $SECRET"
//   -> expect the same record
//   # 3. Unknown username:
//   curl -s "https://paxyo.et/api/bot/admin/users/lookup?username=nobodyhere123" -H "X-Bot-Secret: $SECRET"
//   -> expect HTTP 404 {"success":false,"error":"User not found."}
//   # 4. Bad username (too short / bad characters):
//   curl -s "https://paxyo.et/api/bot/admin/users/lookup?username=ab" -H "X-Bot-Secret: $SECRET"
//   -> expect HTTP 400
//   # 5. No secret at all -> the usual auth error (401/403), NOT the user:
//   curl -s "https://paxyo.et/api/bot/admin/users/lookup?username=william"
// ============================================================================
