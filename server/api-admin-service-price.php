<?php
// ============================================================================
// Service price overrides for the admin bot (19 Nov 2026).
// SERVER SIDE ONLY. Written for @atlasdeskadmin_bot (the admin chat
// bot in this repo, admin_bot.py) — William-only, allowlist from env
// ADMIN_TELEGRAM_IDS in the bot — and read by the customer bot
// (@paxorder_bot, bot.py), which applies the overrides to the
// catalogue it fetches from /services.
//
// WHAT IT ADDS (behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/admin/service-price-overrides
//     -> {"success":true,
//         "overrides":[
//           {"provider":"gop","service_id":6139,
//            "combined_id":"gop:6139","price_etb":50.00,
//            "updated_at":"2026-11-19 07:00:00"},
//           ...]}
//     An empty list means no overrides are set — the normal prices
//     apply everywhere.
//   POST /api/bot/admin/service-price/set
//     {"provider":"gop","service_id":6139,"price_etb":50.00,
//      "admin_telegram_id":779060335,"confirm_token":"<hmac hex>"}
//     -> {"success":true,"ok":true,"provider":"gop",
//         "service_id":6139,"combined_id":"gop:6139",
//         "price_etb":50.00}
//   POST /api/bot/admin/service-price/clear
//     {"provider":"gop","service_id":6139,
//      "admin_telegram_id":779060335,"confirm_token":"<hmac hex>"}
//     -> {"success":true,"ok":true,"provider":"gop",
//         "service_id":6139,"combined_id":"gop:6139",
//         "cleared":true|false}
//     Clearing an override that was never set succeeds and returns
//     cleared:false — the normal price was already in effect.
//
// INVESTIGATION (done before writing — the decision this file rests on):
//   There is currently NO price-override mechanism anywhere: sell
//   prices are computed from provider rates (GodOfPanel x420, SMM
//   x400) and the bot fetches the catalogue via GET /services from
//   the live bot.php router, which is NOT in the repo (only the
//   api-*.php endpoint files are). So this file does NOT touch
//   the live /services handler: the override lives in its OWN
//   table, and the customer bot applies it in-memory to the
//   catalogue it fetches (see the CUSTOMER-BOT note below).
//   A bare service id alone never identifies a service — 2,790
//   bare ids collide between the two providers — so the override
//   is keyed by (provider, service_id), and the combined id
//   ("gop:6139" / "smm:6139") is what the customer bot matches on.
//   The admin bot resolves a bare id to a provider from the live
//   catalogue first (GET /services, GOP only) and asks William
//   when it cannot tell; an explicit "gop service 6139" / "smm
//   service 6139" in the command skips the question.
//   Amounts are ETB per 1000 — the unit the bot quotes. An
//   override can never make a price zero or negative: the bot
//   refuses those before Confirm, and this file refuses them
//   again with 400.
//
// ADMIN GATE — TWO LOCKS, BOTH MUST HOLD:
//   1. X-Bot-Secret (bot.php's existing check): only a holder of
//      the bot secret can reach this endpoint at all — i.e. only
//      the two bots, never a browser or a user.
//   2. confirm_token (POST only): HMAC-SHA256, keyed by the shared
//      secret, over the exact string
//      "admin-service-price:set:{provider}:{service_id}:{price:.2f}:{admin_telegram_id}"
//      for a set, and
//      "admin-service-price:clear:{provider}:{service_id}:{admin_telegram_id}"
//      for a clear. The provider, id and price are part of the
//      token, so a token minted for one service or price cannot
//      change another. Only a holder of the secret can mint it,
//      and the admin bot mints it ONLY after William taps Confirm
//      (never on a single message, never before the preview). The
//      token itself is NEVER stored — only its SHA-256 hash, in
//      the override row.
//   Optional third lock (server-side allowlist): if
//   config_secret.php defines ADMIN_BOT_TELEGRAM_IDS as a
//   comma-separated list of Telegram ids, the admin_telegram_id
//   must be on it (403 if not). If the constant is NOT defined,
//   this lock is skipped and the admin bot's own allowlist
//   (ADMIN_TELEGRAM_IDS env, empty = refuses everyone) is the
//   allowlist. The HMAC is the lock that cannot be skipped:
//   without the secret nobody can mint a token.
//
// OVERRIDE TABLE (created automatically on first call, utf8mb4):
//   service_price_overrides
//                      provider VARCHAR(8) NOT NULL,
//                      service_id INT NOT NULL,
//                      price_etb DECIMAL(12,2) NOT NULL,
//                      admin_telegram_id BIGINT,
//                      confirm_token_hash CHAR(64) (SHA-256 of the
//                      token, never the token itself),
//                      created_at, updated_at,
//                      PRIMARY KEY (provider, service_id).
//                      One row per service, ever: setting an
//                      override that is already there replaces its
//                      price (and records the latest token hash);
//                      clearing deletes the row, so the normal
//                      price applies again at once.
//
// ADMIN-BOT SPEC — the exact contract admin_bot.py implements
// (the admin-bot build implements it, and the tests for it live
// in test_admin_bot_offline.py):
//   Trigger: William types "set price of service 6139 to 50 ETB",
//     "edit price 6139 50", "clear price of service 6139" or
//     "show price of service 6139" in the admin bot. An explicit
//     provider word works too: "set price of smm service 6139
//     to 50 ETB".
//   Set / clear step 1 — preview (NO price moves, NO token
//     minted): the bot resolves the provider, reads the current
//     price (catalogue price, or the override when one is set)
//     and shows William: the service, the current price and the
//     new price (or "clear the override"). A zero or negative
//     price is refused here, before any Confirm, as is clearing
//     a service that has no override. Buttons: "✅ Confirm"
//     (callback_data "admin_confirm") and "❌ Cancel"
//     (callback_data "admin_cancel") — the SAME Confirm pattern
//     admin_bot.py already uses (pending entry keyed by the
//     admin's user id, cleared BEFORE executing, so a double
//     Confirm runs once).
//   Set / clear step 2 — Confirm: ONLY on the admin_confirm tap
//     (or a typed "yes" while the preview is pending) the bot
//     mints:
//       confirm_token = hmac.new(
//           BOT_API_SECRET.encode(),
//           f"admin-service-price:set:{provider}:{service_id}:{price_etb:.2f}:{admin_telegram_id}".encode(),
//           hashlib.sha256).hexdigest()
//     (or the ":clear:" message for a clear; BOT_API_SECRET comes
//     from the admin bot's Render env, never hardcoded, never
//     logged.) and POSTs /admin/service-price/set (or /clear)
//     with the X-Bot-Secret header.
//   Set / clear step 3 — what William sees:
//     success -> "✅ Price of service gop:6139 set to 50.00 ETB
//       per 1000." (or "✅ Price override cleared for service
//       gop:6139 — it now uses the normal price.").
//     403 confirm_token -> "Confirm token is not valid."
//       (means the admin bot minted it wrong — a bug, not a user
//       error; nothing was changed.)
//     404 -> "The price endpoint is not connected yet —
//       nothing was changed."
//     (means the endpoint is not live on the server.)
//   Show: no preview, no Confirm — a read. "Service gop:6139:
//     50.00 ETB per 1000 (override)." or "... (normal price)."
//   Safety rules the admin-bot build must keep (same as the
//   existing admin bot): ONLY the allowlist (empty = refuses
//   everyone); EVERY set/clear needs the explicit Confirm step;
//   nothing changes on a single message; a double Confirm runs
//   once; a price is never zero or negative (refused in the bot
//   before Confirm, re-checked on the server).
//
// CUSTOMER-BOT NOTE — the exact contract bot.py implements
// (the build implements it, and the tests for it live in
// test_bot_offline.py):
//   The customer bot reads GET /admin/service-price-overrides
//   (same X-Bot-Secret) whenever it refreshes the catalogue, and
//   applies each override in-memory to the merged list before
//   caching it: a service whose combined_id matches an override
//   gets rate_etb_per_1000 = the override price. Quoted prices,
//   order totals and the fastest/cheapest picks all read the
//   overridden price, because they all read the catalogue. An
//   override for a service that is not in the catalogue matches
//   nothing and changes nothing. The catalogue cache is 10
//   minutes, so a new or cleared override shows up within
//   10 minutes. The endpoint answering 404 (not live yet) means
//   "no overrides" — the normal prices apply.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-service-price.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block) to the end of bot.php.
//   3. php -l api/bot.php            (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) — the GET first
//      (read-only, safe), then ONE set + clear on a test service
//      with William's approval, then check the table. Never set a
//      real override as a test without his say-so.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. bot_ok() RETURNS (does not exit) and adds "success":true
//       around the reply, as on every other admin endpoint
//       (api-admin-stats.php).
//   A2. BOT_API_SECRET is available on the server as the constant
//       BOT_API_SECRET (config_secret.php) or the env var of the
//       same name — the same value bot.php's X-Bot-Secret check
//       compares against, and the same value the admin bot holds in
//       Render env. If neither exists, the POSTs answer 500
//       "Admin service price is not configured." and change
//       nothing. (The GET needs no secret of its own — the
//       X-Bot-Secret check already gated it.)
//   A3. ADMIN_BOT_TELEGRAM_IDS (optional, config_secret.php) is a
//       comma-separated list of Telegram ids. If defined and
//       non-empty it is enforced; if undefined or empty it is
//       skipped (the admin bot's own allowlist is the gate).
//   A4. No rate limit is applied here beyond bot.php's existing
//       X-Bot-Secret check (same note as api-admin-refund.php:
//       the admin bot calls this at most a few times a day, and
//       the customer bot reads it at most once per catalogue
//       refresh, every 10 minutes).
// ============================================================================

// --- small helpers (asp_ prefix so nothing collides with bot.php) -----------

function asp_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function asp_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function asp_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function asp_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS service_price_overrides (
        provider VARCHAR(8) NOT NULL,
        service_id INT NOT NULL,
        price_etb DECIMAL(12,2) NOT NULL,
        admin_telegram_id BIGINT NULL,
        confirm_token_hash CHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (provider, service_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// The secret both sides share. Same value bot.php's X-Bot-Secret
// check uses, and the admin bot holds in Render env. Never logged,
// never returned. TO VERIFY (A2).
function asp_bot_secret() {
    if (defined('BOT_API_SECRET') && BOT_API_SECRET !== '') return (string)BOT_API_SECRET;
    $env = getenv('BOT_API_SECRET');
    if ($env !== false && $env !== '') return $env;
    return null;
}

// The messages the HMAC is computed over. Both sides must use these
// exact strings — the admin bot builds them the same way (see the
// ADMIN-BOT SPEC in the header). The provider, id and price are
// part of the token, so a token minted for one service or price
// cannot change another. Prices are formatted with exactly two
// decimals on both sides — Python f"{price:.2f}" in admin_bot.py,
// PHP number_format((float)$price, 2, '.', '') here — so the two
// HMACs agree.
function asp_token_message_set($provider, $service_id, $price_etb, $admin_telegram_id) {
    return 'admin-service-price:set:' . $provider . ':' . (int)$service_id . ':' . number_format((float)$price_etb, 2, '.', '') . ':' . (int)$admin_telegram_id;
}

function asp_token_message_clear($provider, $service_id, $admin_telegram_id) {
    return 'admin-service-price:clear:' . $provider . ':' . (int)$service_id . ':' . (int)$admin_telegram_id;
}

function asp_check_admin_allowlist($admin_telegram_id) {
    if (defined('ADMIN_BOT_TELEGRAM_IDS') && trim((string)ADMIN_BOT_TELEGRAM_IDS) !== '') {
        $allowed = [];
        foreach (explode(',', (string)ADMIN_BOT_TELEGRAM_IDS) as $part) {
            $part = trim($part);
            if (preg_match('/^\d+$/', $part)) $allowed[(int)$part] = true;
        }
        if (!isset($allowed[$admin_telegram_id])) {
            asp_fail(403, 'Admin is not allowed to change service prices.');
        }
    }
}

// A provider word is only "gop" or "smm" — anything else is a 400,
// never a silent default: a bare id that collides between the two
// providers must never be guessed.
function asp_check_provider($provider) {
    if ($provider !== 'gop' && $provider !== 'smm') {
        asp_fail(400, 'provider must be "gop" or "smm".');
    }
    return $provider;
}

function asp_override_record($row) {
    return [
        'provider' => $row['provider'],
        'service_id' => (int)$row['service_id'],
        'combined_id' => $row['provider'] . ':' . (int)$row['service_id'],
        'price_etb' => (float)$row['price_etb'],
        'updated_at' => $row['updated_at'],
    ];
}

// --- GET /api/bot/admin/service-price-overrides -----------------------------
// Read-only: no token, no Confirm — a read moves nothing. An empty
// list means no overrides are set anywhere.

function bot_asp_price_overrides() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') asp_fail(405, 'Method not allowed.');
    $db = asp_db();
    if ($db === null) asp_fail(500, 'Database is not available.');
    asp_ensure_table($db);
    $res = $db->query('SELECT provider, service_id, price_etb, updated_at FROM service_price_overrides ORDER BY provider, service_id');
    $out = [];
    while ($row = $res->fetch_assoc()) $out[] = asp_override_record($row);
    bot_ok(['overrides' => $out]);
}

// --- POST /api/bot/admin/service-price/set ----------------------------------
// Body: {"provider","service_id","price_etb","admin_telegram_id",
//        "confirm_token"}. One upsert: setting an override that is
// already there replaces its price.

function bot_asp_price_set() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') asp_fail(405, 'Method not allowed.');
    $in = asp_json_body();
    $provider = isset($in['provider']) ? strtolower(trim((string)$in['provider'])) : '';
    asp_check_provider($provider);
    $service_id = (int)($in['service_id'] ?? 0);
    if ($service_id <= 0) asp_fail(400, 'service_id is required.');
    if (!isset($in['price_etb']) || !is_numeric($in['price_etb'])) {
        asp_fail(400, 'price_etb is required.');
    }
    $price = (float)$in['price_etb'];
    // A price is never zero or negative — refused here as well as
    // in the bot before Confirm, so a forged call cannot zero a
    // service out.
    if (!is_finite($price) || $price <= 0) {
        asp_fail(400, 'price_etb must be more than 0.');
    }
    $admin_telegram_id = (int)($in['admin_telegram_id'] ?? 0);
    if ($admin_telegram_id <= 0) asp_fail(400, 'admin_telegram_id is required.');
    $confirm_token = isset($in['confirm_token']) ? (string)$in['confirm_token'] : '';
    if ($confirm_token === '') {
        asp_fail(400, 'confirm_token is required.');
    }

    $secret = asp_bot_secret();
    if ($secret === null) asp_fail(500, 'Admin service price is not configured.');

    // Lock 2 — the confirm token. hash_equals, not == (timing-safe).
    $expected = hash_hmac('sha256', asp_token_message_set($provider, $service_id, $price, $admin_telegram_id), $secret);
    if (!hash_equals($expected, $confirm_token)) {
        asp_fail(403, 'Confirm token is not valid.');
    }

    // Optional lock 3 — server-side allowlist (A3). Skipped when
    // the constant is not defined or empty.
    asp_check_admin_allowlist($admin_telegram_id);

    $db = asp_db();
    if ($db === null) asp_fail(500, 'Database is not available.');
    asp_ensure_table($db);

    $token_hash = hash('sha256', $confirm_token);
    $stmt = $db->prepare('INSERT INTO service_price_overrides (provider, service_id, price_etb, admin_telegram_id, confirm_token_hash) VALUES (?, ?, ?, ?, ?) ON DUPLICATE KEY UPDATE price_etb = VALUES(price_etb), admin_telegram_id = VALUES(admin_telegram_id), confirm_token_hash = VALUES(confirm_token_hash)');
    $stmt->bind_param('sidds', $provider, $service_id, $price, $admin_telegram_id, $token_hash);
    if (!$stmt->execute()) {
        $stmt->close();
        asp_fail(500, 'Could not save the price override. Nothing was changed.');
    }
    $stmt->close();
    bot_ok([
        'ok' => true,
        'provider' => $provider,
        'service_id' => $service_id,
        'combined_id' => $provider . ':' . $service_id,
        'price_etb' => $price,
    ]);
}

// --- POST /api/bot/admin/service-price/clear --------------------------------
// Body: {"provider","service_id","admin_telegram_id",
//        "confirm_token"}. Deletes the override row, so the normal
// price applies again. Clearing an override that was never set
// succeeds with cleared:false.

function bot_asp_price_clear() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') asp_fail(405, 'Method not allowed.');
    $in = asp_json_body();
    $provider = isset($in['provider']) ? strtolower(trim((string)$in['provider'])) : '';
    asp_check_provider($provider);
    $service_id = (int)($in['service_id'] ?? 0);
    if ($service_id <= 0) asp_fail(400, 'service_id is required.');
    $admin_telegram_id = (int)($in['admin_telegram_id'] ?? 0);
    if ($admin_telegram_id <= 0) asp_fail(400, 'admin_telegram_id is required.');
    $confirm_token = isset($in['confirm_token']) ? (string)$in['confirm_token'] : '';
    if ($confirm_token === '') {
        asp_fail(400, 'confirm_token is required.');
    }

    $secret = asp_bot_secret();
    if ($secret === null) asp_fail(500, 'Admin service price is not configured.');

    // Lock 2 — the confirm token. hash_equals, not == (timing-safe).
    $expected = hash_hmac('sha256', asp_token_message_clear($provider, $service_id, $admin_telegram_id), $secret);
    if (!hash_equals($expected, $confirm_token)) {
        asp_fail(403, 'Confirm token is not valid.');
    }

    // Optional lock 3 — server-side allowlist (A3). Skipped when
    // the constant is not defined or empty.
    asp_check_admin_allowlist($admin_telegram_id);

    $db = asp_db();
    if ($db === null) asp_fail(500, 'Database is not available.');
    asp_ensure_table($db);

    $stmt = $db->prepare('DELETE FROM service_price_overrides WHERE provider = ? AND service_id = ?');
    $stmt->bind_param('si', $provider, $service_id);
    $stmt->execute();
    $cleared = $stmt->affected_rows === 1;
    $stmt->close();
    bot_ok([
        'ok' => true,
        'provider' => $provider,
        'service_id' => $service_id,
        'combined_id' => $provider . ':' . $service_id,
        'cleared' => $cleared,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/service-price-overrides' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_asp_price_overrides(); }
//   if ($bp === 'admin/service-price/set' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_asp_price_set(); }
//   if ($bp === 'admin/service-price/clear' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_asp_price_clear(); }
//
// (Exact-path matches, so they cannot collide with the
// admin/users/... patterns — but all of them must come before any
// generic admin handler, if one ever exists.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-admin-service-price.php`
// on the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST — read this whole block before running it. Test the
// GET first (read-only, safe), then ONE set + clear on a test service
// with William's approval. Never set a real override as a test
// without his say-so.
//   SECRET=<redacted>(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. Overrides list (read-only):
//   curl -s "https://paxyo.et/api/bot/admin/service-price-overrides" -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"overrides":[...]}
//   # 2. No secret at all -> the usual auth error (401/403), NOT the list:
//   curl -s "https://paxyo.et/api/bot/admin/service-price-overrides"
//   # 3. Set an override on a TEST service id (use one that is not sold):
//   TOKEN=$(php -r 'echo hash_hmac("sha256", "admin-service-price:set:gop:999999:50.00:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/service-price/set \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"provider\":\"gop\",\"service_id\":999999,\"price_etb\":50.00,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect {"success":true,"ok":true,"combined_id":"gop:999999","price_etb":50}
//   # 4. Same token again with a different price must fail 403:
//   curl -s -X POST https://paxyo.et/api/bot/admin/service-price/set \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"provider\":\"gop\",\"service_id\":999999,\"price_etb\":60.00,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN\"}"
//   -> expect {"success":false,"error":"Confirm token is not valid."}
//   # 5. A zero price must fail 400, nothing changed:
//   TOKEN0=$(php -r 'echo hash_hmac("sha256", "admin-service-price:set:gop:999999:0.00:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/service-price/set \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"provider\":\"gop\",\"service_id\":999999,\"price_etb\":0,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKEN0\"}"
//   -> expect HTTP 400 {"success":false,"error":"price_etb must be more than 0."}
//   # 6. Clear the test override back (fresh token):
//   TOKENC=$(php -r 'echo hash_hmac("sha256", "admin-service-price:clear:gop:999999:779060335", $argv[1]);' "$SECRET")
//   curl -s -X POST https://paxyo.et/api/bot/admin/service-price/clear \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"provider\":\"gop\",\"service_id\":999999,\"admin_telegram_id\":779060335,\"confirm_token\":\"$TOKENC\"}"
//   -> expect {"success":true,"ok":true,"cleared":true}
//   # 7. Check the table is empty again, then DELETE any test row left:
//   mysql -e "SELECT provider, service_id, price_etb FROM service_price_overrides;"
//   mysql -e "DELETE FROM service_price_overrides WHERE service_id=999999;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
