<?php
// ============================================================================
// Last-3-deposits lookup for the admin bot (19 Nov 2026).
// SERVER SIDE ONLY. Written for @atlasdeskadmin_bot (the admin chat
// bot in this repo, admin_bot.py) — William-only, allowlist from env
// ADMIN_TELEGRAM_IDS in the bot.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/admin/users/{tg_id}/deposits
//     -> {"success":true,"telegram_id":N,
//         "deposits":[
//           {"id":1219,"amount":10.00,"method":"telebirr",
//            "status":"completed",
//            "created_at":"2026-11-17 18:07:11"},
//           ... up to 3, newest first]}
//     -> 404 {"success":false,"error":"User not found."} when the
//        Telegram id has no Paxyo user. A user who exists but never
//        deposited gets {"deposits":[]} — an empty list, not a 404.
//
// INVESTIGATION (done before writing — the decision this file rests on):
//   The deposits table carries user_id (= tg_id), amount, status,
//   created_at — and NO method column (verified in-repo:
//   api-deposits.php INSERTs (user_id, amount, tx_ref,
//   reference_id, status, chapa_response, created_at) and its
//   header says the table has NO method/phone columns). The method
//   lives inside the chapa_response JSON blob, exactly as the
//   existing customer list endpoint reads it (dep_deposit_record
//   in api-deposits.php: $meta['method'] ?? null). This file reads
//   it the same way, so a deposit whose method was never recorded
//   shows method null — never a guessed method.
//   The existing customer endpoint GET /api/bot/deposits?
//   telegram_id=X&limit=5 already lists deposits, but it is the
//   customer bot's endpoint; this one is admin-scoped (a fixed
//   last-3, behind the /admin/ path) so the admin bot never has to
//   call a customer endpoint.
//
// ADMIN GATE — ONE LOCK:
//   X-Bot-Secret (bot.php's existing check): only a holder of the
//   bot secret can reach this endpoint at all — i.e. only the two
//   bots, never a browser or a user. Read-only: no token, no
//   Confirm, no audit row — a lookup moves nothing.
//
// ADMIN-BOT SPEC — the exact contract admin_bot.py implements
// (the admin-bot build implements it, and the tests for it live
// in test_admin_bot_offline.py):
//   Trigger: William types "deposit history of 779060335",
//     "last deposits @william" or "show deposits 779060335" in
//     the admin bot (Telegram id or @username — the username is
//     resolved first via server/api-admin-user-lookup.php).
//   Reply: the last 3 deposits, newest first, one line each —
//     amount, method, date, status. A deposit with no recorded
//     method shows "method not recorded". No deposits at all ->
//     "No deposits yet for @name (id)."
//   Unknown user -> "There is no Paxyo user with Telegram id N."
//     / "... with username @name." Endpoint not live (404 without
//     that body) -> "The deposit history is not connected yet".
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-user-deposits.php  (this file must pass on its own)
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
//   A2. The deposits table carries user_id, amount, status,
//       chapa_response, created_at (verified in-repo, see above).
// ============================================================================

// --- small helpers (aud_ prefix so nothing collides with bot.php) -----------

function aud_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function aud_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

// One deposit row, the same shape as the customer list endpoint
// (dep_deposit_record in api-deposits.php): the method comes from
// the chapa_response JSON blob, never from a column — the deposits
// table has no method column, so a deposit with no recorded method
// shows method null.
function aud_deposit_record($row) {
    $meta = [];
    if (!empty($row['chapa_response'])) {
        $decoded = json_decode($row['chapa_response'], true);
        if (is_array($decoded)) $meta = $decoded;
    }
    return [
        'id' => (int)$row['id'],
        'amount' => (float)$row['amount'],
        'method' => $meta['method'] ?? null,
        'status' => $row['status'],
        'created_at' => $row['created_at'],
    ];
}

// --- GET /api/bot/admin/users/{tg_id}/deposits ------------------------------
// Read-only lookup, last 3 deposits, newest first: no token, no
// Confirm, no audit row — a lookup moves nothing.

function bot_aud_user_deposits($telegram_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') aud_fail(405, 'Method not allowed.');
    if ($telegram_id <= 0) aud_fail(400, 'telegram id is required.');
    $db = aud_db();
    if ($db === null) aud_fail(500, 'Database is not available.');
    // The user must exist — a Telegram id with no auth row is a
    // 404, not an empty list (an empty list means "exists, never
    // deposited").
    $stmt = $db->prepare('SELECT tg_id FROM auth WHERE tg_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $exists = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if ($exists === null) aud_fail(404, 'User not found.');
    $stmt = $db->prepare('SELECT id, amount, status, chapa_response, created_at FROM deposits WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 3');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $res = $stmt->get_result();
    $out = [];
    while ($row = $res->fetch_assoc()) $out[] = aud_deposit_record($row);
    $stmt->close();
    bot_ok([
        'telegram_id' => (int)$telegram_id,
        'deposits' => $out,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^admin/users/(\d+)/deposits$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_aud_user_deposits((int)$m[1]); }
//
// (The balance dispatch patterns are ^admin/users/(\d+)/balance$ and
// ^admin/users/(\d+)/balance/adjust$ — distinct from /deposits, so
// order between them does not matter, but all of them must come
// before any generic admin/users handler, if one ever exists.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-admin-user-deposits.php`
// on the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST — read-only, safe:
//   SECRET=<redacted>(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. A user with deposits (William, 779060335):
//   curl -s "https://paxyo.et/api/bot/admin/users/779060335/deposits" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"telegram_id":779060335,"deposits":[...]} — at most 3, newest first
//   # 2. Unknown user:
//   curl -s "https://paxyo.et/api/bot/admin/users/1/deposits" -H "X-Bot-Secret: $SECRET"
//   -> expect HTTP 404 {"success":false,"error":"User not found."}
//   # 3. No secret at all -> the usual auth error (401/403), NOT the deposits:
//   curl -s "https://paxyo.et/api/bot/admin/users/779060335/deposits"
// ============================================================================
