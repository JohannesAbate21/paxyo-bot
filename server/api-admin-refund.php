<?php
// ============================================================================
// Refund-from-the-admin-bot for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot,
// ideas batch 2 — REFUND FROM THE ADMIN BOT. SERVER SIDE ONLY.
//
// INVESTIGATION (done before writing — the decision this file rests on):
//   The admin alerts (order / deposit / refund / new-user) come from
//   the Paxyo server and are delivered by @paxadmin_bot — a
//   DIFFERENT codebase, owned by Abel, NOT in this repo. There is no
//   admin-bot code for @paxadmin_bot in ~/workspace/paxyo-bot, and
//   this file cannot add a button to it. The refund ACTION itself,
//   however, already exists: server/api-order-rescue.php implements
//   POST /orders/{id}/cancel-refund (provider cancel confirmed
//   first, then ONE atomic refund to the user's Paxyo balance,
//   duplicate-safe, never twice, never a completed order). So this
//   file is a THIN ADMIN-GATED WRAPPER around that endpoint — it
//   contains NO refund logic of its own, NO provider call, NO
//   balance UPDATE. It only proves the call came from the admin bot
//   after William's Confirm tap, records who asked for it, and
//   hands the call to bot_res_cancel_refund().
//   THE CALLBACK HANDLING LIVES IN THE ADMIN BOT'S CODE, not here.
//   Which admin bot: the NEW admin chat bot in this repo
//   (admin_bot.py — brand-new bot, William-only, allowlist from env
//   ADMIN_TELEGRAM_IDS, Confirm via the `admin_confirm` callback,
//   pending entry cleared before executing so a double Confirm runs
//   once). The handler that shows the Refund button, asks William
//   to confirm, mints the confirm_token and calls this endpoint
//   must be ADDED to admin_bot.py by the admin-bot build — this
//   file is the server half only, and admin_bot.py is NOT edited
//   here. See "ADMIN-BOT SPEC" below for the exact contract that
//   build must implement.
//   What about @paxadmin_bot (Abel's)? The one-tap refund FROM AN
//   ALERT needs the button on the alert itself, and the alerts are
//   sent by @paxadmin_bot. Until Abel adds a Refund button to
//   @paxadmin_bot (his codebase — NEEDS ABEL), or the alerts are
//   routed to the new admin bot (a server change — NEEDS A
//   DECISION), William triggers refunds in the NEW admin bot by
//   typing "refund order #N". The server endpoint works the same
//   whichever bot calls it. See OPEN QUESTIONS in the report.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/admin/orders/{id}/refund
//     {telegram_id, admin_telegram_id, confirm_token}
//     -> {"ok":true,"order_id":N,"refunded_etb":X,
//         "provider_status":"canceled","duplicate":false}
//        Exactly the cancel-refund reply (same keys, same values),
//        because the call IS the cancel-refund call. One tap
//        refunds the stuck order to the user's Paxyo balance, once,
//        with a confirm step (see ADMIN-BOT SPEC). A second call
//        for the same order returns the recorded result with
//        duplicate:true and NEVER refunds twice. A completed order
//        is refused with 409 and never refunded.
//
// ADMIN GATE — TWO LOCKS, BOTH MUST HOLD:
//   1. X-Bot-Secret (bot.php's existing check): only a holder of
//      the bot secret can reach this endpoint at all — i.e. only
//      the two bots, never a browser or a user.
//   2. confirm_token: an HMAC-SHA256, keyed by BOT_API_SECRET, over
//      the exact string "admin-refund:{order_id}:{admin_telegram_id}".
//      Only a holder of the secret can mint it, and it is bound to
//      ONE order and ONE admin id — a token minted for order 1841
//      cannot refund order 1842, and a token minted by anyone else
//      cannot refund anything. The admin bot mints it ONLY after
//      William taps Confirm (never on a single message, never
//      before the preview). The token itself is NEVER stored —
//      only its SHA-256 hash, in the audit table.
//   Optional third lock (server-side allowlist): if config_secret.php
//   defines ADMIN_BOT_TELEGRAM_IDS as a comma-separated list of
//   Telegram ids, the admin_telegram_id must be on it (403 if not).
//   If the constant is NOT defined, this lock is skipped and the
//   admin bot's own allowlist (ADMIN_TELEGRAM_IDS env, empty =
//   refuses everyone) is the allowlist. The HMAC is the lock that
//   cannot be skipped: without the secret nobody can mint a token.
//
// AUDIT TABLE (created automatically on first call, utf8mb4):
//   bot_admin_refunds  id AUTO_INCREMENT PK, order_id BIGINT,
//                      telegram_id BIGINT (the ORDER OWNER — the
//                      user who gets the refund), admin_telegram_id
//                      BIGINT (who asked for it), confirm_token_hash
//                      CHAR(64) (SHA-256 of the token, never the
//                      token itself), status ENUM('requested',
//                      'refunded','duplicate') DEFAULT 'requested',
//                      created_at. Index on order_id.
//                      The money record stays bot_order_rescues
//                      (written by the rescue endpoint); this table
//                      is the WHO-ASKED record. Join them on
//                      order_id to audit a refund end to end.
//
// ADMIN-BOT SPEC — the exact contract admin_bot.py must implement
// (NOT in this file; the admin-bot build implements it, and the
// tests for it live in test_admin_bot_offline.py):
//   Trigger: William types "refund order #N" (or "refund #N") in
//     the new admin bot. (One-tap-from-alert comes later — see the
//     investigation note above; the alert would need a Refund
//     button, which only @paxadmin_bot / Abel can add today.)
//   Step 1 — preview (NO money moves, NO token minted): the bot
//     reads the order (GET /orders/{id} — the admin bot needs the
//     owner's telegram_id from that read; the order id alone is
//     not enough, because the rescue endpoint refunds to the
//     OWNER's balance) and shows William: order id, service name,
//     quantity, total ETB, status, and the owner's telegram id.
//     Buttons: "✅ Confirm refund" (callback_data "admin_confirm")
//     and "❌ Cancel" (callback_data "admin_cancel") — the SAME
//     Confirm pattern admin_bot.py already uses for broadcasts and
//     settings (pending entry keyed by the admin's user id, cleared
//     BEFORE executing, so a double Confirm runs once).
//   Step 2 — Confirm: ONLY on the admin_confirm tap (or a typed
//     "yes" while the preview is pending) the bot mints:
//       confirm_token = HMAC-SHA256(key=BOT_API_SECRET,
//           msg="admin-refund:{order_id}:{admin_telegram_id}")
//     (Python: hmac.new(BOT_API_SECRET.encode(), msg.encode(),
//     hashlib.sha256).hexdigest(); BOT_API_SECRET comes from the
//     admin bot's Render env, never hardcoded, never logged.)
//     and POSTs /admin/orders/{id}/refund with the X-Bot-Secret
//     header and body:
//       {"telegram_id": <order owner id>,
//        "admin_telegram_id": <William's Telegram id>,
//        "confirm_token": "<hex hmac>"}
//   Step 3 — what William sees:
//     success, duplicate:false -> "✅ Refunded {refunded_etb} ETB
//       to user {telegram_id} for order #{order_id} (Paxyo balance,
//       not cash). Provider: {provider_status}."
//     success, duplicate:true  -> "Already refunded —
//       {refunded_etb} ETB for order #{order_id}. No second refund
//       was made."
//     409 already completed    -> "Order #{order_id} is already
//       completed and cannot be refunded."
//     409/502 provider refused -> the provider's reason, verbatim:
//       "No refund was made — {error}." (never invent a reason)
//     404                    -> "Order not found."
//     403 confirm_token      -> "Confirm token is not valid."
//       (means the admin bot minted it wrong — a bug, not a user
//       error; the refund did not happen.)
//   Safety rules the admin-bot build must keep (same as the
//   existing admin bot): ONLY the allowlist (empty = refuses
//   everyone); EVERY refund needs the explicit Confirm step;
//   nothing refunds on a single message; a double Confirm runs
//   once; the bot never touches a balance directly — only this
//   endpoint does, through the rescue logic. The admin bot's
//   header safety line ("never touches balances, orders, deposits
//   or refunds") must be UPDATED by that build — it is no longer
//   true once the refund handler lands.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-refund.php     (this file must pass on its own)
//   2. INSTALL api-order-rescue.php FIRST (it is the refund engine
//      — this wrapper calls bot_res_cancel_refund() from it). If it
//      is not installed, this endpoint answers 503 and refunds
//      nothing. Verify the rescue curl test passes before this one.
//   3. python3 splice script: read bot.php, INSERT THE DISPATCH LINE
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   4. php -l api/bot.php               (must pass before anything goes live)
//   5. Live curl test (see the bottom of this file) then DELETE the
//      test audit row. The test refunds a REAL test order on purpose
//      (that is the point) — use a small test order only, with
//      William's approval, never a real user's order. The refund
//      returns the full order total, so the test is net-zero on the
//      Paxyo balance (the provider cancel must succeed for the
//      refund to happen at all).
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. api-order-rescue.php is installed in the same bot.php, so
//       bot_res_cancel_refund() exists when this wrapper runs.
//       Checked with function_exists() — a missing rescue file
//       gives a plain 503, never a fatal error.
//   A2. bot_ok() RETURNS (does not exit). Evidence in-repo: the
//       sibling files put `return;` after bot_ok() calls (e.g.
//       bot_trt_load, bot_dep_status's amount-mismatch branch) —
//       dead code if bot_ok exited. This wrapper relies on it:
//       after bot_res_cancel_refund() echoes its JSON via bot_ok,
//       control returns here and the audit row is marked
//       'refunded'/'duplicate'. IF bot_ok actually exits, the
//       refund is STILL correct (it already happened inside the
//       rescue call) — only the audit row stays 'requested'.
//       Verify by reading bot_ok() in bot.php at install time; if
//       it exits, mark the audit row 'refunded' BEFORE delegating
//       instead (and accept that a failed delegation would leave a
//       'refunded' row with no rescue row — reconcile by joining
//       bot_order_rescues).
//   A3. bot_res_cancel_refund() reads telegram_id from the request
//       body (php://input) — the same body this wrapper received,
//       which the admin bot filled with the ORDER OWNER's id. The
//       wrapper reads the body first for its own checks; php://input
//       is re-readable in PHP, so the rescue call sees the same
//       body. Verify at install time that the live rescue file
//       still reads the body this way (it did when written).
//   A4. BOT_API_SECRET is available on the server as the constant
//       BOT_API_SECRET (config_secret.php) or the env var of the
//       same name — the same value bot.php's X-Bot-Secret check
//       compares against, and the same value the admin bot holds in
//       Render env. If neither exists, this endpoint answers 500
//       "Admin refund is not configured." and refunds nothing.
//       No secret value is written anywhere in this file.
//   A5. ADMIN_BOT_TELEGRAM_IDS (optional, config_secret.php) is a
//       comma-separated list of Telegram ids. If defined and
//       non-empty it is enforced; if undefined or empty it is
//       skipped (the admin bot's own allowlist is the gate).
//       TO VERIFY: decide with William whether to define it. The
//       HMAC alone already restricts callers to secret holders.
//   A6. The rescue endpoint's own guarantees carry over unchanged:
//       provider cancel confirmed first, atomic refund, duplicate
//       safe, never a completed order, full stored order total
//       (see api-order-rescue.php A1–A9 — especially A7, the
//       full-total vs partial-delivery tension with the Paxyo
//       Terms, which William should confirm before going live).
//   A7. No rate limit is applied here beyond bot.php's existing
//       X-Bot-Secret check (same note as api-admin-stats.php: the
//       admin bot calls this at most a few times a day; a
//       per-telegram_id limit does not fit an admin call). If
//       bot.php's bot_rate_limit() supports a secret-only call,
//       add it to the dispatch line; otherwise leave it off and
//       note it here.
// ============================================================================

// --- small helpers (arf_ prefix so nothing collides with bot.php) -----------

function arf_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function arf_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function arf_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function arf_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_admin_refunds (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        order_id BIGINT NOT NULL,
        telegram_id BIGINT NOT NULL,
        admin_telegram_id BIGINT NOT NULL,
        confirm_token_hash CHAR(64) NOT NULL,
        status ENUM('requested','refunded','duplicate') NOT NULL DEFAULT 'requested',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_arf_order (order_id),
        INDEX idx_arf_admin (admin_telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// The secret both sides share. Same value bot.php's X-Bot-Secret
// check uses, and the admin bot holds in Render env. Never logged,
// never returned. TO VERIFY (A4).
function arf_bot_secret() {
    if (defined('BOT_API_SECRET') && BOT_API_SECRET !== '') return (string)BOT_API_SECRET;
    $env = getenv('BOT_API_SECRET');
    if ($env !== false && $env !== '') return $env;
    return null;
}

// The message the HMAC is computed over. Both sides must use this
// exact string — the admin bot builds it the same way (see the
// ADMIN-BOT SPEC in the header).
function arf_token_message($order_id, $admin_telegram_id) {
    return 'admin-refund:' . (int)$order_id . ':' . (int)$admin_telegram_id;
}

function arf_mark_audit($db, $audit_id, $status) {
    $stmt = $db->prepare("UPDATE bot_admin_refunds SET status = ? WHERE id = ?");
    $stmt->bind_param('si', $status, $audit_id);
    $stmt->execute();
    $stmt->close();
}

// --- POST /api/bot/admin/orders/{id}/refund ---------------------------------
// Body: {"telegram_id":<order owner>,"admin_telegram_id":<William>,
//        "confirm_token":"<hmac hex>"}. Thin wrapper: gate, audit,
// delegate to bot_res_cancel_refund() (api-order-rescue.php). This
// function contains NO refund logic of its own.

function bot_arf_admin_refund($order_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') arf_fail(405, 'Method not allowed.');
    $in = arf_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) arf_fail(400, 'telegram_id is required.');
    if ($order_id <= 0) arf_fail(400, 'order id is required.');
    $admin_telegram_id = (int)($in['admin_telegram_id'] ?? 0);
    if ($admin_telegram_id <= 0) arf_fail(400, 'admin_telegram_id is required.');
    $confirm_token = strtolower(trim((string)($in['confirm_token'] ?? '')));
    if ($confirm_token === '' || !preg_match('/^[0-9a-f]{64}$/', $confirm_token)) {
        arf_fail(400, 'confirm_token is required.');
    }

    $secret = arf_bot_secret();
    if ($secret === null) arf_fail(500, 'Admin refund is not configured.');

    // Lock 2 — the confirm token. hash_equals, not == (timing-safe).
    $expected = hash_hmac('sha256', arf_token_message($order_id, $admin_telegram_id), $secret);
    if (!hash_equals($expected, $confirm_token)) {
        arf_fail(403, 'Confirm token is not valid.');
    }

    // Optional lock 3 — server-side allowlist (A5). Skipped when
    // the constant is not defined or empty.
    if (defined('ADMIN_BOT_TELEGRAM_IDS') && trim((string)ADMIN_BOT_TELEGRAM_IDS) !== '') {
        $allowed = [];
        foreach (explode(',', (string)ADMIN_BOT_TELEGRAM_IDS) as $part) {
            $part = trim($part);
            if (preg_match('/^\d+$/', $part)) $allowed[(int)$part] = true;
        }
        if (!isset($allowed[$admin_telegram_id])) {
            arf_fail(403, 'Admin is not allowed to refund orders.');
        }
    }

    $db = arf_db();
    if ($db === null) arf_fail(500, 'Database is not available.');
    arf_ensure_table($db);

    // The rescue engine must be installed — this wrapper refunds
    // nothing on its own (A1).
    if (!function_exists('bot_res_cancel_refund')) {
        arf_fail(503, 'Cancel-refund endpoint is not installed yet. Install api-order-rescue.php first.');
    }

    // Audit FIRST: who asked, for which order, with which token
    // (hash only — never the token). Status 'requested' until the
    // delegation returns (see A2 for the bot_ok() caveat).
    $token_hash = hash('sha256', $confirm_token);
    $audit_id = 0;
    $stmt = $db->prepare('INSERT INTO bot_admin_refunds (order_id, telegram_id, admin_telegram_id, confirm_token_hash) VALUES (?, ?, ?, ?)');
    $stmt->bind_param('iiis', $order_id, $telegram_id, $admin_telegram_id, $token_hash);
    if ($stmt->execute()) $audit_id = $db->insert_id;
    $stmt->close();
    // An audit-write failure must not block the refund itself — the
    // money record (bot_order_rescues) is written by the rescue
    // call. The audit is best-effort from here on.
    $had_rescue_before = false;
    if ($audit_id > 0) {
        try {
            $stmt = $db->prepare('SELECT order_id FROM bot_order_rescues WHERE order_id = ? LIMIT 1');
            $stmt->bind_param('i', $order_id);
            $stmt->execute();
            $had_rescue_before = $stmt->get_result()->fetch_assoc() !== null;
            $stmt->close();
        } catch (mysqli_sql_exception $e) {
            $had_rescue_before = false;
        }
    }

    // Delegate. The rescue function reads telegram_id from the same
    // request body (A3), checks ownership + cancellable state,
    // confirms the provider cancel, and refunds atomically. On any
    // failure it answers with res_fail() (which exits) — the audit
    // row stays 'requested' and no money moved. On success it
    // echoes its JSON via bot_ok() and RETURNS (A2), and the audit
    // row is marked below. The reply the admin bot gets is the
    // rescue reply itself (ok, order_id, refunded_etb,
    // provider_status, duplicate).
    bot_res_cancel_refund($order_id);

    // Reached only when bot_ok() returned (A2): the refund happened
    // (fresh or duplicate — the rescue row existed before the call
    // exactly when this was a duplicate).
    if ($audit_id > 0) {
        arf_mark_audit($db, $audit_id, $had_rescue_before ? 'duplicate' : 'refunded');
    }
}

// ============================================================================
// DISPATCH — insert this line in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^admin/orders/(\d+)/refund$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_arf_admin_refund((int)$m[1]); }
//
// (See A7 on rate limiting. The admin/orders/{id}/refund pattern
//  must be checked BEFORE any generic admin/orders handler, if one
//  ever exists.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-admin-refund.php` on
// the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 4) — both must pass before anything goes live.
//
// LIVE CURL TEST — read this whole block before running it. The test
// REFUNDS a real order at the provider on purpose (that is the
// point), so it must use a SMALL TEST order placed for this test,
// with William's approval, on the operating account — NEVER a real
// user's order. The refund returns the full order total, so the test
// is net-zero on the Paxyo balance (the provider cancel must succeed
// for the refund to happen at all). The admin bot is NOT needed for
// this test: the token is minted here with the same HMAC the admin
// bot will use (the test proves the server verifies it).
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # Mint the token for test order N, admin id = William's Telegram
//   # id W (use the operating account id 779060335 as the admin id
//   # for this test — the allowlist constant is not defined, so any
//   # id mints a valid token; the point is the HMAC check):
//   TOKEN=$(php -r 'echo hash_hmac("sha256", "admin-refund:N:779060335", $argv[1]);' "$SECRET")
//   # 1. Place a small test order first (under the 5 ETB test cap,
//   #    e.g. 100 TikTok views #1665 ≈ 1.89 ETB) via POST /orders or
//   #    the bot, and note its Paxyo order id N. Confirm it is
//   #    pending at the provider:
//   curl -s "https://paxyo.et/api/bot/orders/N?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect the order with status "pending" (or "processing").
//   # 2. Refund it through the admin wrapper:
//   curl -s -X POST https://paxyo.et/api/bot/admin/orders/N/refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d "{\"telegram_id\":779060335,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect {"success":true,"ok":true,"order_id":N,
//      "refunded_etb":<the order total>,"provider_status":"canceled",
//      "duplicate":false}
//   # 3. Check the balance went back up by exactly the order total:
//   curl -s "https://paxyo.et/api/bot/balance?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   # 4. Call it AGAIN with the SAME token — the same order must NOT
//   #    refund twice (the token is per order+admin, so it stays
//   #    valid; the RESCUE layer is what blocks the second refund):
//   curl -s -X POST https://paxyo.et/api/bot/admin/orders/N/refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d "{\"telegram_id\":779060335,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect the SAME refunded_etb with "duplicate":true, and the
//      balance from step 3 UNCHANGED.
//   # 5. A token minted for a DIFFERENT order must fail 403:
//   WRONG=$(php -r 'echo hash_hmac("sha256", "admin-refund:999999:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/orders/N/refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d "{\"telegram_id\":779060335,\"admin_telegram_id\":779060335,\"confirm_token\":\"$WRONG\"}"
//   -> expect {"success":false,"error":"Confirm token is not valid."}
//   # 6. No token at all -> 400:
//   curl -s -X POST https://paxyo.et/api/bot/admin/orders/N/refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"admin_telegram_id":779060335}'
//   -> expect {"success":false,"error":"confirm_token is required."}
//   # 7. A completed order must refuse with 409 (use a known
//   #    completed order id, e.g. an old test order — mint its token
//   #    the same way; this call touches nothing):
//   TOKEN2=$(php -r 'echo hash_hmac("sha256", "admin-refund:<completed-id>:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/orders/<completed-id>/refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d "{\"telegram_id\":779060335,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN2\"}"
//   -> expect {"success":false,"error":"Order is already completed ..."}.
//   # 8. Audit row: who asked for it, token hash only, status marked:
//   mysql -e "SELECT order_id, telegram_id, admin_telegram_id, status, LEFT(confirm_token_hash, 12) FROM bot_admin_refunds WHERE order_id=N;"
//   -> expect two rows (steps 2 and 4), both admin 779060335,
//      statuses 'refunded' then 'duplicate'. (If both say
//      'requested', bot_ok() exits in the live bot.php — see A2:
//      the refunds themselves are still correct; join
//      bot_order_rescues to confirm.)
//   Then DELETE the test audit rows and confirm they are gone (the
//   cancelled test order row itself stays, status 'cancelled', and
//   the bot_order_rescues row stays — those are the honest records
//   of what happened; only this wrapper's audit rows are test rows):
//   mysql -e "DELETE FROM bot_admin_refunds WHERE order_id=N AND admin_telegram_id=779060335; SELECT COUNT(*) FROM bot_admin_refunds WHERE order_id=N;"
//   (use the same MySQL credentials db.php uses; never print them.)
//   ADMIN-BOT PYTHON (for the admin-bot build — mint the token only
//   AFTER William taps Confirm):
//       import hashlib, hmac
//       msg = f"admin-refund:{order_id}:{admin_telegram_id}"
//       confirm_token = hmac.new(
//           BOT_API_SECRET.encode(), msg.encode(),
//           hashlib.sha256).hexdigest()
// ============================================================================
