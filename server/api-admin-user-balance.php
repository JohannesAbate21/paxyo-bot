<?php
// ============================================================================
// User-balance lookup + adjustment for the admin bot (18 Nov 2026).
// SERVER SIDE ONLY. Written for @atlasdeskadmin_bot (the admin chat
// bot in this repo, admin_bot.py) — William-only, allowlist from env
// ADMIN_TELEGRAM_IDS, Confirm via the `admin_confirm` callback.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/admin/users/{tg_id}/balance
//     -> {"success":true,"telegram_id":N,"username":"...",
//         "first_name":"...","balance":1234.50}
//     -> 404 {"success":false,"error":"User not found."} when the
//        Telegram id has no Paxyo user.
//   POST /api/bot/admin/users/{tg_id}/balance/adjust
//     {"delta_etb":500.00,"admin_telegram_id":779060335,
//      "confirm_token":"<hmac hex>"}
//     -> {"success":true,"ok":true,"telegram_id":N,
//         "old_balance":1234.50,"new_balance":1734.50,
//         "delta_etb":500.00}
//   A negative delta removes balance. The new balance can never go
//   below zero: the UPDATE is guarded in the database, so a change
//   that would leave it negative is refused with 409 and nothing
//   moves.
//
// INVESTIGATION (done before writing — the decision this file rests on):
//   The auth table carries tg_id, username, first_name, email and
//   balance (verified in-repo: api-deposits.php selects tg_id,
//   username, first_name, email from auth; api-order-smm.php selects
//   balance from auth where tg_id = ?; api-referrals.php updates
//   auth SET balance = balance + ? WHERE tg_id = ?). There is NO
//   phone column in auth — phone lives only in deposit records —
//   so a user can only be identified by Telegram id, never by
//   phone. This file looks users up by tg_id only, and the admin
//   bot does the same.
//   The guarded-update pattern already exists in-repo
//   (api-order-smm.php / api-referrals.php): UPDATE auth SET
//   balance = balance - ? WHERE tg_id = ? AND balance >= ?.
//   This file uses the same shape with the guard on the RESULT
//   (balance + delta >= 0), so the check and the write are one
//   atomic statement — a deposit landing between the preview and
//   the Confirm cannot push the balance below zero.
//
// ADMIN GATE — TWO LOCKS, BOTH MUST HOLD:
//   1. X-Bot-Secret (bot.php's existing check): only a holder of
//      the bot secret can reach this endpoint at all — i.e. only
//      the two bots, never a browser or a user.
//   2. confirm_token (POST only): HMAC-SHA256, keyed by the shared
//      secret, over the exact string
//      "admin-user-balance:{telegram_id}:{delta:.2f}:{admin_telegram_id}".
//      The amount is part of the token, so a token minted for +500
//      ETB cannot adjust by any other amount, and a token minted
//      for one user cannot adjust another. Only a holder of the
//      secret can mint it, and the admin bot mints it ONLY after
//      William taps Confirm (never on a single message, never
//      before the preview). The token itself is NEVER stored —
//      only its SHA-256 hash, in the audit table.
//      The delta is formatted with exactly two decimals on both
//      sides — Python f"{delta:.2f}" in admin_bot.py, PHP
//      number_format((float)$delta, 2, '.', '') here — so the two
//      HMACs agree.
//   Optional third lock (server-side allowlist): if
//   config_secret.php defines ADMIN_BOT_TELEGRAM_IDS as a
//   comma-separated list of Telegram ids, the admin_telegram_id
//   must be on it (403 if not). If the constant is NOT defined,
//   this lock is skipped and the admin bot's own allowlist
//   (ADMIN_TELEGRAM_IDS env, empty = refuses everyone) is the
//   allowlist. The HMAC is the lock that cannot be skipped:
//   without the secret nobody can mint a token.
//
// AUDIT TABLE (created automatically on first call, utf8mb4):
//   bot_admin_balance_adjustments
//                      id AUTO_INCREMENT PK, telegram_id BIGINT,
//                      admin_telegram_id BIGINT,
//                      delta_etb DECIMAL(12,2),
//                      old_balance DECIMAL(12,2),
//                      new_balance DECIMAL(12,2),
//                      confirm_token_hash CHAR(64) (SHA-256 of the
//                      token, never the token itself),
//                      status ENUM('requested','adjusted')
//                      DEFAULT 'requested', created_at.
//                      The money record is the auth.balance row
//                      itself (this file's UPDATE); this table is
//                      the WHO-ASKED record. Join them on
//                      telegram_id + created_at to audit an
//                      adjustment end to end.
//
// ADMIN-BOT SPEC — the exact contract admin_bot.py implements
// (the admin-bot build implements it, and the tests for it live
// in test_admin_bot_offline.py):
//   Trigger: William types "what is the balance of 779060335"
//     (lookup) or "add 500 ETB to 779060335" / "remove 200 ETB
//     from 779060335" (adjustment) in the admin bot. Users are
//     identified by Telegram id only.
//   Lookup: GET /admin/users/{id}/balance, reply with the user's
//     name/id and balance in ETB. Unknown user -> "There is no
//     Paxyo user with Telegram id N." Endpoint not live (404
//     without that body) -> "The balance lookup is not connected
//     yet". No preview, no Confirm — a lookup moves nothing.
//   Adjustment step 1 — preview (NO money moves, NO token
//     minted): the bot reads the user (the GET above) and shows
//     William: the user, add/remove, the amount, the current
//     balance and the new balance. A change that would leave the
//     balance below zero is refused here, before any Confirm.
//     Buttons: "✅ Confirm" (callback_data "admin_confirm") and
//     "❌ Cancel" (callback_data "admin_cancel") — the SAME
//     Confirm pattern admin_bot.py already uses for broadcasts,
//     settings, refunds and promo codes (pending entry keyed by
//     the admin's user id, cleared BEFORE executing, so a double
//     Confirm runs once).
//   Adjustment step 2 — Confirm: ONLY on the admin_confirm tap
//     (or a typed "yes" while the preview is pending) the bot
//     mints:
//       confirm_token = hmac.new(
//           BOT_API_SECRET.encode(),
//           f"admin-user-balance:{telegram_id}:{delta_etb:.2f}:{admin_telegram_id}".encode(),
//           hashlib.sha256).hexdigest()
//     (BOT_API_SECRET comes from the admin bot's Render env, never
//     hardcoded, never logged.) and POSTs
//     /admin/users/{id}/balance/adjust with the X-Bot-Secret
//     header and body:
//       {"delta_etb": <float>, "admin_telegram_id": <William's
//        Telegram id>, "confirm_token": "<hex hmac>"}
//   Adjustment step 3 — what William sees:
//     success -> "✅ Added 500.00 ETB to @name (779060335). New
//       balance: 1,734.50 ETB." (or "Removed ..." for a negative
//       delta, "from" instead of "to").
//     409 would-go-negative -> the server's reason, verbatim:
//       "That adjustment was refused — ... Nothing was changed."
//     403 confirm_token -> "Confirm token is not valid."
//       (means the admin bot minted it wrong — a bug, not a user
//       error; nothing was changed.)
//     404 -> "The balance endpoint is not connected yet —
//       nothing was changed."
//     (means the endpoint is not live on the server; the user was
//     looked up before the preview, so the user exists.)
//   Safety rules the admin-bot build must keep (same as the
//   existing admin bot): ONLY the allowlist (empty = refuses
//   everyone); EVERY adjustment needs the explicit Confirm step;
//   nothing adjusts on a single message; a double Confirm runs
//   once; the new balance never goes below zero (refused in the
//   bot before Confirm, re-checked atomically on the server).
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-user-balance.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block) to the end of bot.php.
//   3. php -l api/bot.php            (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) — the GET first
//      (read-only, safe), then ONE small adjustment on a test user
//      with William's approval, then adjust it back. Then DELETE
//      the test audit rows.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. bot_ok() RETURNS (does not exit) and adds "success":true
//       around the reply, as on every other admin endpoint
//       (api-admin-stats.php). If bot_ok actually exits, the
//       adjustment is STILL correct (it already happened in the
//       guarded UPDATE) — only the audit row stays 'requested'.
//       Verify by reading bot_ok() in bot.php at install time; if
//       it exits, mark the audit row 'adjusted' BEFORE the UPDATE
//       instead (and accept that a failed UPDATE would leave an
//       'adjusted' row with no balance change — reconcile by
//       joining auth.balance).
//   A2. BOT_API_SECRET is available on the server as the constant
//       BOT_API_SECRET (config_secret.php) or the env var of the
//       same name — the same value bot.php's X-Bot-Secret check
//       compares against, and the same value the admin bot holds in
//       Render env. If neither exists, this endpoint answers 500
//       "Admin user balance is not configured." and changes
//       nothing.
//   A3. ADMIN_BOT_TELEGRAM_IDS (optional, config_secret.php) is a
//       comma-separated list of Telegram ids. If defined and
//       non-empty it is enforced; if undefined or empty it is
//       skipped (the admin bot's own allowlist is the gate).
//       TO VERIFY: decide with William whether to define it. The
//       HMAC alone already restricts callers to secret holders.
//   A4. The auth.balance column holds a numeric balance (DECIMAL
//       in practice). The guarded UPDATE binds the delta as a
//       double, the same as the repo's other balance updates.
//   A5. No rate limit is applied here beyond bot.php's existing
//       X-Bot-Secret check (same note as api-admin-refund.php:
//       the admin bot calls this at most a few times a day).
// ============================================================================

// --- small helpers (aub_ prefix so nothing collides with bot.php) -----------

function aub_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function aub_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function aub_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function aub_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_admin_balance_adjustments (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        admin_telegram_id BIGINT NOT NULL,
        delta_etb DECIMAL(12,2) NOT NULL,
        old_balance DECIMAL(12,2) NULL,
        new_balance DECIMAL(12,2) NULL,
        confirm_token_hash CHAR(64) NOT NULL,
        status ENUM('requested','adjusted') NOT NULL DEFAULT 'requested',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_aub_user (telegram_id),
        INDEX idx_aub_admin (admin_telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// The secret both sides share. Same value bot.php's X-Bot-Secret
// check uses, and the admin bot holds in Render env. Never logged,
// never returned. TO VERIFY (A2).
function aub_bot_secret() {
    if (defined('BOT_API_SECRET') && BOT_API_SECRET !== '') return (string)BOT_API_SECRET;
    $env = getenv('BOT_API_SECRET');
    if ($env !== false && $env !== '') return $env;
    return null;
}

// The message the HMAC is computed over. Both sides must use this
// exact string — the admin bot builds it the same way (see the
// ADMIN-BOT SPEC in the header). The delta is formatted with
// exactly two decimals, matching Python f"{delta:.2f}".
function aub_token_message($telegram_id, $delta_etb, $admin_telegram_id) {
    return 'admin-user-balance:' . (int)$telegram_id . ':' . number_format((float)$delta_etb, 2, '.', '') . ':' . (int)$admin_telegram_id;
}

function aub_mark_audit($db, $audit_id, $status, $old_balance = null, $new_balance = null) {
    $stmt = $db->prepare("UPDATE bot_admin_balance_adjustments SET status = ?, old_balance = ?, new_balance = ? WHERE id = ?");
    $stmt->bind_param('sddi', $status, $old_balance, $new_balance, $audit_id);
    $stmt->execute();
    $stmt->close();
}

function aub_check_admin_allowlist($admin_telegram_id) {
    if (defined('ADMIN_BOT_TELEGRAM_IDS') && trim((string)ADMIN_BOT_TELEGRAM_IDS) !== '') {
        $allowed = [];
        foreach (explode(',', (string)ADMIN_BOT_TELEGRAM_IDS) as $part) {
            $part = trim($part);
            if (preg_match('/^\d+$/', $part)) $allowed[(int)$part] = true;
        }
        if (!isset($allowed[$admin_telegram_id])) {
            aub_fail(403, 'Admin is not allowed to adjust balances.');
        }
    }
}

// One user row from auth: tg_id, username, first_name, balance —
// or null when the Telegram id has no Paxyo user.
function aub_user_row($db, $telegram_id) {
    $stmt = $db->prepare('SELECT tg_id, username, first_name, balance FROM auth WHERE tg_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// --- GET /api/bot/admin/users/{tg_id}/balance -------------------------------
// Read-only lookup: no token, no Confirm, no audit row — a lookup
// moves nothing.

function bot_aub_user_balance($telegram_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') aub_fail(405, 'Method not allowed.');
    if ($telegram_id <= 0) aub_fail(400, 'telegram id is required.');
    $db = aub_db();
    if ($db === null) aub_fail(500, 'Database is not available.');
    $row = aub_user_row($db, $telegram_id);
    if ($row === null) aub_fail(404, 'User not found.');
    bot_ok([
        'telegram_id' => (int)$row['tg_id'],
        'username' => $row['username'],
        'first_name' => $row['first_name'],
        'balance' => (float)$row['balance'],
    ]);
}

// --- POST /api/bot/admin/users/{tg_id}/balance/adjust -----------------------
// Body: {"delta_etb":<float>,"admin_telegram_id":<William>,
//        "confirm_token":"<hmac hex>"}. The guarded UPDATE is the
// money move: one atomic statement, never below zero.

function bot_aub_user_balance_adjust($telegram_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') aub_fail(405, 'Method not allowed.');
    $in = aub_json_body();
    if ($telegram_id <= 0) aub_fail(400, 'telegram id is required.');
    $admin_telegram_id = (int)($in['admin_telegram_id'] ?? 0);
    if ($admin_telegram_id <= 0) aub_fail(400, 'admin_telegram_id is required.');
    if (!isset($in['delta_etb']) || !is_numeric($in['delta_etb'])) {
        aub_fail(400, 'delta_etb is required.');
    }
    $delta = (float)$in['delta_etb'];
    if (!is_finite($delta) || $delta == 0.0) {
        aub_fail(400, 'delta_etb must be a non-zero amount.');
    }
$confirm_token=<redacted>
if ($confirm_token=<redacted>
        aub_fail(400, 'confirm_token is required.');
    }

    $secret = aub_bot_secret();
    if ($secret === null) aub_fail(500, 'Admin user balance is not configured.');

    // Lock 2 — the confirm token. hash_equals, not == (timing-safe).
    $expected = hash_hmac('sha256', aub_token_message($telegram_id, $delta, $admin_telegram_id), $secret);
    if (!hash_equals($expected, $confirm_token)) {
        aub_fail(403, 'Confirm token is not valid.');
    }

    // Optional lock 3 — server-side allowlist (A3). Skipped when
    // the constant is not defined or empty.
    aub_check_admin_allowlist($admin_telegram_id);

    $db = aub_db();
    if ($db === null) aub_fail(500, 'Database is not available.');
    aub_ensure_table($db);

    // The user must exist — the bot looked them up before the
    // preview, so a missing user here means something changed.
    $row = aub_user_row($db, $telegram_id);
    if ($row === null) aub_fail(404, 'User not found.');
    $old_balance = (float)$row['balance'];

    // Audit FIRST: who asked, for whom, by how much, with which
    // token (hash only — never the token). Status 'requested'
    // until the UPDATE succeeds (see A1 for the bot_ok() caveat).
    $token_hash = hash('sha256', $confirm_token);
    $audit_id = 0;
    $stmt = $db->prepare('INSERT INTO bot_admin_balance_adjustments (telegram_id, admin_telegram_id, delta_etb, old_balance, confirm_token_hash) VALUES (?, ?, ?, ?, ?)');
    $stmt->bind_param('iidds', $telegram_id, $admin_telegram_id, $delta, $old_balance, $token_hash);
    if ($stmt->execute()) $audit_id = $db->insert_id;
    $stmt->close();
    // An audit-write failure must not block the adjustment itself
    // — the money record is the auth.balance row. The audit is
    // best-effort from here on.

    // The money move: one atomic guarded UPDATE. The guard
    // (balance + delta >= 0) is checked by the database in the
    // same statement as the write, so nothing can slip between
    // the check and the write.
    $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ? AND balance + ? >= 0');
    $stmt->bind_param('did', $delta, $telegram_id, $delta);
    $stmt->execute();
    $affected = $stmt->affected_rows;
    $stmt->close();
    if ($affected !== 1) {
        // No row updated: the guard refused (the balance moved
        // between the preview and the Confirm) or the user row
        // vanished. Re-read to say which — never guess.
        $again = aub_user_row($db, $telegram_id);
        if ($again === null) aub_fail(404, 'User not found.');
        aub_fail(409, 'That adjustment would leave the balance below zero — nothing was changed.');
    }

    $new_balance = $old_balance + $delta;
    if ($audit_id > 0) {
        aub_mark_audit($db, $audit_id, 'adjusted', $old_balance, $new_balance);
    }
    bot_ok([
        'ok' => true,
        'telegram_id' => (int)$telegram_id,
        'old_balance' => $old_balance,
        'new_balance' => $new_balance,
        'delta_etb' => $delta,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^admin/users/(\d+)/balance$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_aub_user_balance((int)$m[1]); }
//   if (preg_match('#^admin/users/(\d+)/balance/adjust$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_aub_user_balance_adjust((int)$m[1]); }
//
// (The adjust pattern must be checked BEFORE the plain balance
// pattern would match it — the two patterns are distinct
// (/balance vs /balance/adjust), so order between them does not
// matter, but both must come before any generic admin/users
// handler, if one ever exists.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-admin-user-balance.php`
// on the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST — read this whole block before running it. Test the
// GET first (read-only, safe), then ONE small adjustment on a test
// user with William's approval, then adjust it back the same way.
// Never test on a real user's balance.
//   SECRET=<redacted>(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. Lookup (read-only):
//   curl -s "https://paxyo.et/api/bot/admin/users/779060335/balance" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"telegram_id":779060335,"balance":<number>}
//   # 2. Unknown user:
//   curl -s "https://paxyo.et/api/bot/admin/users/1/balance" -H "X-Bot-Secret: $SECRET"
//   -> expect HTTP 404 {"success":false,"error":"User not found."}
//   # 3. No secret at all -> the usual auth error (401/403), NOT the balance:
//   curl -s "https://paxyo.et/api/bot/admin/users/779060335/balance"
//   # 4. Adjustment (+10 ETB on a test user, then -10 back):
//   TOKEN=$(php -r 'echo hash_hmac("sha256", "admin-user-balance:<tg_id>:10.00:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/users/<tg_id>/balance/adjust \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"delta_etb\":10.00,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect {"success":true,"ok":true,"new_balance":<old+10>}
//   # 5. Same token again with a different amount must fail 403:
//   curl -s -X POST https://paxyo.et/api/bot/admin/users/<tg_id>/balance/adjust \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"delta_etb\":20.00,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect {"success":false,"error":"Confirm token is not valid."}
//   # 6. A removal bigger than the balance must fail 409, nothing changed:
//   BIG=<the test user's whole balance + 100, as a number>
//   TOKEN2=$(php -r 'echo hash_hmac("sha256", "admin-user-balance:<tg_id>:-$BIG.00:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/users/<tg_id>/balance/adjust \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"delta_etb\":-$BIG,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN2\"}"
//   -> expect HTTP 409 {"success":false,"error":"That adjustment would leave the balance below zero — nothing was changed."}
//   # 7. Adjust the +10 back (-10 with a fresh token), then check the
//   #    audit rows and DELETE the test rows:
//   mysql -e "SELECT telegram_id, admin_telegram_id, delta_etb, old_balance, new_balance, status FROM bot_admin_balance_adjustments WHERE telegram_id=<tg_id> AND admin_telegram_id=779060335;"
//   mysql -e "DELETE FROM bot_admin_balance_adjustments WHERE telegram_id=<tg_id> AND admin_telegram_id=779060335;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
