<?php
// ============================================================================
// Ban / unban a user for the admin bot (19 Nov 2026).
// SERVER SIDE ONLY. Written for @atlasdeskadmin_bot (the admin chat
// bot in this repo, admin_bot.py) — William-only, allowlist from env
// ADMIN_TELEGRAM_IDS in the bot — and enforced by the customer bot
// (@paxorder_bot, bot.py), which refuses orders and deposits from
// a banned user.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/admin/users/{tg_id}/ban
//     -> {"success":true,"telegram_id":N,"username":"...",
//         "banned":false}
//     -> 404 {"success":false,"error":"User not found."} when the
//        Telegram id has no Paxyo user. A user with no ban row is
//        "banned":false — never deposited, never banned, same thing.
//   POST /api/bot/admin/users/{tg_id}/ban
//     {"action":"ban"|"unban","admin_telegram_id":779060335,
//      "confirm_token":"<hmac hex>"}
//     -> {"success":true,"ok":true,"telegram_id":N,
//         "banned":true|false}
//     Banning an already-banned user (or unbanning one who is not
//     banned) succeeds and returns the current state — the bot
//     shows the current state in its preview, so a double ban
//     should not happen, and an idempotent answer cannot hurt.
//
// INVESTIGATION (done before writing — the decision this file rests on):
//   There is currently NO ban mechanism anywhere: the only
//   "banned" hits in the repo are about social-media accounts
//   being banned and per-user banned-service preferences. So this
//   file creates the mechanism instead of extending one.
//   The ban flag lives in its OWN table (bot_banned_users), NOT
//   as a new column on auth: auth is the money/user record and
//   every admin endpoint reads it; a separate table keeps the ban
//   state (and its audit) apart from it, and an unban keeps the
//   row as history (banned=0) instead of deleting it.
//
// ADMIN GATE — TWO LOCKS, BOTH MUST HOLD:
//   1. X-Bot-Secret (bot.php's existing check): only a holder of
//      the bot secret can reach this endpoint at all — i.e. only
//      the two bots, never a browser or a user.
//   2. confirm_token (POST only): HMAC-SHA256, keyed by the shared
//      secret, over the exact string
//      "admin-user-ban:{telegram_id}:{action}:{admin_telegram_id}"
//      where action is "ban" or "unban". The action is part of
//      the token, so a token minted for a ban cannot unban, and a
//      token minted for one user cannot ban another. Only a holder
//      of the secret can mint it, and the admin bot mints it ONLY
//      after William taps Confirm (never on a single message,
//      never before the preview). The token itself is NEVER stored
//      — only its SHA-256 hash, in the ban row.
//   Optional third lock (server-side allowlist): if
//   config_secret.php defines ADMIN_BOT_TELEGRAM_IDS as a
//   comma-separated list of Telegram ids, the admin_telegram_id
//   must be on it (403 if not). If the constant is NOT defined,
//   this lock is skipped and the admin bot's own allowlist
//   (ADMIN_TELEGRAM_IDS env, empty = refuses everyone) is the
//   allowlist. The HMAC is the lock that cannot be skipped:
//   without the secret nobody can mint a token.
//
// BAN TABLE (created automatically on first call, utf8mb4):
//   bot_banned_users
//                      telegram_id BIGINT PRIMARY KEY,
//                      banned TINYINT(1) NOT NULL DEFAULT 1,
//                      admin_telegram_id BIGINT,
//                      confirm_token_hash CHAR(64) (SHA-256 of the
//                      token, never the token itself),
//                      created_at, updated_at.
//                      One row per user, ever: a ban sets
//                      banned=1, an unban sets banned=0 and keeps
//                      the row as the record of who banned whom and
//                      when. The customer bot reads it with the GET
//                      above; a missing row means "not banned".
//
// ADMIN-BOT SPEC — the exact contract admin_bot.py implements
// (the admin-bot build implements it, and the tests for it live
// in test_admin_bot_offline.py):
//   Trigger: William types "ban 779060335", "ban @william",
//     "unban 779060335" or "unban @william" in the admin bot
//     (Telegram id or @username — the username is resolved first
//     via server/api-admin-user-lookup.php).
//   Ban step 1 — preview (NO ban yet, NO token minted): the bot
//     reads the user and their current ban state and shows
//     William: the user, ban/unban, and the current state. A user
//     already in the wanted state is told so plainly and nothing
//     is previewed. Buttons: "✅ Confirm" (callback_data
//     "admin_confirm") and "❌ Cancel" (callback_data
//     "admin_cancel") — the SAME Confirm pattern admin_bot.py
//     already uses for broadcasts, settings, refunds, promo codes
//     and balance adjustments (pending entry keyed by the admin's
//     user id, cleared BEFORE executing, so a double Confirm runs
//     once).
//   Ban step 2 — Confirm: ONLY on the admin_confirm tap (or a
//     typed "yes" while the preview is pending) the bot mints:
//       confirm_token = hmac.new(
//           BOT_API_SECRET.encode(),
//           f"admin-user-ban:{telegram_id}:{action}:{admin_telegram_id}".encode(),
//           hashlib.sha256).hexdigest()
//     (BOT_API_SECRET comes from the admin bot's Render env, never
//     hardcoded, never logged.) and POSTs
//     /admin/users/{id}/ban with the X-Bot-Secret header and body:
//       {"action": "ban"|"unban", "admin_telegram_id": <William's
//        Telegram id>, "confirm_token": "<hex hmac>"}
//   Ban step 3 — what William sees:
//     success -> "✅ @name (779060335) is now banned." (or
//       "✅ @name (779060335) is unbanned.").
//     403 confirm_token -> "Confirm token is not valid."
//       (means the admin bot minted it wrong — a bug, not a user
//       error; nothing was changed.)
//     404 -> "The ban endpoint is not connected yet —
//       nothing was changed."
//     (means the endpoint is not live on the server; the user was
//       looked up before the preview, so the user exists.)
//   Safety rules the admin-bot build must keep (same as the
//   existing admin bot): ONLY the allowlist (empty = refuses
//   everyone); EVERY ban/unban needs the explicit Confirm step;
//   nothing bans on a single message; a double Confirm runs once.
//
// CUSTOMER-BOT ENFORCEMENT — the exact contract bot.py implements
// (the build implements it, and the tests for it live in
// test_bot_offline.py):
//   The customer bot reads GET /admin/users/{tg_id}/ban (same
//   X-Bot-Secret) before an order or a deposit, cached per user
//   for 5 minutes. A banned user gets one short line — "Your
//   Paxyo account is paused. Please contact support." — for any
//   order or deposit, including a Confirm tap on an order started
//   before the ban. Balance checks, order history and questions
//   still work: the ban blocks spending, not talking.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-user-ban.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block) to the end of bot.php.
//   3. php -l api/bot.php            (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) — the GET first
//      (read-only, safe), then ONE ban + unban on a test user with
//      William's approval, then check the audit row. Never ban a
//      real user as a test.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. bot_ok() RETURNS (does not exit) and adds "success":true
//       around the reply, as on every other admin endpoint
//       (api-admin-stats.php). If bot_ok actually exits, the ban
//       is STILL correct (it already happened in the upsert) —
//       only the reply is lost.
//   A2. BOT_API_SECRET is available on the server as the constant
//       BOT_API_SECRET (config_secret.php) or the env var of the
//       same name — the same value bot.php's X-Bot-Secret check
//       compares against, and the same value the admin bot holds in
//       Render env. If neither exists, the POST answers 500
//       "Admin user ban is not configured." and changes nothing.
//       (The GET needs no secret of its own — the X-Bot-Secret
//       check already gated it.)
//   A3. ADMIN_BOT_TELEGRAM_IDS (optional, config_secret.php) is a
//       comma-separated list of Telegram ids. If defined and
//       non-empty it is enforced; if undefined or empty it is
//       skipped (the admin bot's own allowlist is the gate).
//   A4. No rate limit is applied here beyond bot.php's existing
//       X-Bot-Secret check (same note as api-admin-refund.php:
//       the admin bot calls this at most a few times a day, and
//       the customer bot reads it at most once per user per
//       5 minutes).
// ============================================================================

// --- small helpers (aban_ prefix so nothing collides with bot.php) ----------

function aban_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function aban_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function aban_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function aban_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_banned_users (
        telegram_id BIGINT NOT NULL PRIMARY KEY,
        banned TINYINT(1) NOT NULL DEFAULT 1,
        admin_telegram_id BIGINT NULL,
        confirm_token_hash CHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_aban_admin (admin_telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// The secret both sides share. Same value bot.php's X-Bot-Secret
// check uses, and the admin bot holds in Render env. Never logged,
// never returned. TO VERIFY (A2).
function aban_bot_secret() {
    if (defined('BOT_API_SECRET') && BOT_API_SECRET !== '') return (string)BOT_API_SECRET;
    $env = getenv('BOT_API_SECRET');
    if ($env !== false && $env !== '') return $env;
    return null;
}

// The message the HMAC is computed over. Both sides must use this
// exact string — the admin bot builds it the same way (see the
// ADMIN-BOT SPEC in the header). The action ("ban" / "unban") is
// part of the token, so a token minted for a ban cannot unban.
function aban_token_message($telegram_id, $action, $admin_telegram_id) {
    return 'admin-user-ban:' . (int)$telegram_id . ':' . $action . ':' . (int)$admin_telegram_id;
}

function aban_check_admin_allowlist($admin_telegram_id) {
    if (defined('ADMIN_BOT_TELEGRAM_IDS') && trim((string)ADMIN_BOT_TELEGRAM_IDS) !== '') {
        $allowed = [];
        foreach (explode(',', (string)ADMIN_BOT_TELEGRAM_IDS) as $part) {
            $part = trim($part);
            if (preg_match('/^\d+$/', $part)) $allowed[(int)$part] = true;
        }
        if (!isset($allowed[$admin_telegram_id])) {
            aban_fail(403, 'Admin is not allowed to ban users.');
        }
    }
}

// The ban row for a user, or null when the user was never banned
// (a missing row means "not banned", never an error).
function aban_ban_row($db, $telegram_id) {
    $stmt = $db->prepare('SELECT telegram_id, banned, admin_telegram_id, created_at, updated_at FROM bot_banned_users WHERE telegram_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// --- GET /api/bot/admin/users/{tg_id}/ban -----------------------------------
// Read-only: no token, no Confirm, no audit row — a lookup moves
// nothing. 404 only when the Telegram id has no Paxyo user at all.

function bot_aban_user_ban($telegram_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') aban_fail(405, 'Method not allowed.');
    if ($telegram_id <= 0) aban_fail(400, 'telegram id is required.');
    $db = aban_db();
    if ($db === null) aban_fail(500, 'Database is not available.');
    $stmt = $db->prepare('SELECT tg_id, username FROM auth WHERE tg_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $user = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if ($user === null) aban_fail(404, 'User not found.');
    aban_ensure_table($db);
    $row = aban_ban_row($db, $telegram_id);
    bot_ok([
        'telegram_id' => (int)$telegram_id,
        'username' => $user['username'],
        'banned' => $row !== null && (int)$row['banned'] === 1,
    ]);
}

// --- POST /api/bot/admin/users/{tg_id}/ban ----------------------------------
// Body: {"action":"ban"|"unban","admin_telegram_id":<William>,
//        "confirm_token":"<hmac hex>"}. One upsert: a ban sets
// banned=1, an unban sets banned=0 and keeps the row as history.

function bot_aban_user_ban_set($telegram_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') aban_fail(405, 'Method not allowed.');
    $in = aban_json_body();
    if ($telegram_id <= 0) aban_fail(400, 'telegram id is required.');
    $admin_telegram_id = (int)($in['admin_telegram_id'] ?? 0);
    if ($admin_telegram_id <= 0) aban_fail(400, 'admin_telegram_id is required.');
    $action = isset($in['action']) ? (string)$in['action'] : '';
    if ($action !== 'ban' && $action !== 'unban') {
        aban_fail(400, 'action must be "ban" or "unban".');
    }
    $confirm_token = isset($in['confirm_token']) ? (string)$in['confirm_token'] : '';
    if ($confirm_token === '') {
        aban_fail(400, 'confirm_token is required.');
    }

    $secret = aban_bot_secret();
    if ($secret === null) aban_fail(500, 'Admin user ban is not configured.');

    // Lock 2 — the confirm token. hash_equals, not == (timing-safe).
    $expected = hash_hmac('sha256', aban_token_message($telegram_id, $action, $admin_telegram_id), $secret);
    if (!hash_equals($expected, $confirm_token)) {
        aban_fail(403, 'Confirm token is not valid.');
    }

    // Optional lock 3 — server-side allowlist (A3). Skipped when
    // the constant is not defined or empty.
    aban_check_admin_allowlist($admin_telegram_id);

    $db = aban_db();
    if ($db === null) aban_fail(500, 'Database is not available.');
    aban_ensure_table($db);

    // The user must exist — the bot looked them up before the
    // preview, so a missing user here means something changed.
    $stmt = $db->prepare('SELECT tg_id FROM auth WHERE tg_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $exists = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if ($exists === null) aban_fail(404, 'User not found.');

    $banned = $action === 'ban' ? 1 : 0;
    $token_hash = hash('sha256', $confirm_token);
    // One row per user, ever: INSERT a new row, or UPDATE the one
    // that is there (the token hash and admin record the latest
    // change; the row itself is the history).
    $stmt = $db->prepare('INSERT INTO bot_banned_users (telegram_id, banned, admin_telegram_id, confirm_token_hash) VALUES (?, ?, ?, ?) ON DUPLICATE KEY UPDATE banned = VALUES(banned), admin_telegram_id = VALUES(admin_telegram_id), confirm_token_hash = VALUES(confirm_token_hash)');
    $stmt->bind_param('iiis', $telegram_id, $banned, $admin_telegram_id, $token_hash);
    if (!$stmt->execute()) {
        $stmt->close();
        aban_fail(500, 'Could not record the ban. Nothing was changed.');
    }
    $stmt->close();
    bot_ok([
        'ok' => true,
        'telegram_id' => (int)$telegram_id,
        'banned' => $banned === 1,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^admin/users/(\d+)/ban$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_aban_user_ban((int)$m[1]); }
//   if (preg_match('#^admin/users/(\d+)/ban$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_aban_user_ban_set((int)$m[1]); }
//
// (The balance / deposits dispatch patterns are distinct
// (/balance, /balance/adjust, /deposits), so order between them
// does not matter, but all of them must come before any generic
// admin/users handler, if one ever exists.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-admin-user-ban.php`
// on the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST — read this whole block before running it. Test the
// GET first (read-only, safe), then ONE ban + unban on a test user
// with William's approval. Never ban a real user as a test.
//   SECRET=<redacted>(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. Ban state (read-only):
//   curl -s "https://paxyo.et/api/bot/admin/users/779060335/ban" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"telegram_id":779060335,"banned":false}
//   # 2. Unknown user:
//   curl -s "https://paxyo.et/api/bot/admin/users/1/ban" -H "X-Bot-Secret: $SECRET"
//   -> expect HTTP 404 {"success":false,"error":"User not found."}
//   # 3. No secret at all -> the usual auth error (401/403), NOT the ban:
//   curl -s "https://paxyo.et/api/bot/admin/users/779060335/ban"
//   # 4. Ban a TEST user (then unban them back right away):
//   TOKEN=$(php -r 'echo hash_hmac("sha256", "admin-user-ban:<tg_id>:ban:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/users/<tg_id>/ban \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"action\":\"ban\",\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect {"success":true,"ok":true,"banned":true}
//   # 5. Same token again with the other action must fail 403:
//   curl -s -X POST https://paxyo.et/api/bot/admin/users/<tg_id>/ban \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"action\":\"unban\",\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect {"success":false,"error":"Confirm token is not valid."}
//   # 6. Unban the test user back (fresh token):
//   TOKEN2=$(php -r 'echo hash_hmac("sha256", "admin-user-ban:<tg_id>:unban:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/users/<tg_id>/ban \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"action\":\"unban\",\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN2\"}"
//   -> expect {"success":true,"ok":true,"banned":false}
//   # 7. Check the audit row, then DELETE the test row:
//   mysql -e "SELECT telegram_id, banned, admin_telegram_id FROM bot_banned_users WHERE telegram_id=<tg_id>;"
//   mysql -e "DELETE FROM bot_banned_users WHERE telegram_id=<tg_id>;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
