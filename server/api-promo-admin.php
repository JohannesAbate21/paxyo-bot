<?php
// ============================================================================
// Promo code manager (admin side) for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot
// feature 25 — the admin bot /promo list and /promo off CODE.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/promo-codes
//     -> {"codes":[{code, percent, fixed_etb, active, expires_at,
//         max_uses, uses, created_at}, ...]}
//        Every promo code, active first then off, newest first.
//        `uses` is the count of redemptions so far (from
//        bot_promo_redemptions). `percent` is null for a fixed-ETB
//        code and `fixed_etb` is null for a percent code.
//   POST /api/bot/promo-codes/{CODE}/off
//     -> {"ok":true,"code":"PAXYO20","active":false}
//        Switches one code off. The code stays in the table (so
//        its redemption history is kept) — it just stops being
//        redeemable. Switching off a code that is already off (or
//        a code that does not exist) is a 404, never a silent ok.
//
// THIS FILE DOES NOT CREATE CODES. Creation is the admin bot's
// /promo create path, which calls the existing create endpoint in
// api-promo-codes.php (extended in the same round for fixed-ETB
// codes). This file only lists and switches off.
//
// TABLE: bot_promo_codes — created by api-promo-codes.php
// (code VARCHAR(32) PRIMARY KEY, percent INT, fixed_etb
// DECIMAL(10,2) NULL (added by the round-3 edit to that file),
// active TINYINT(1) DEFAULT 1, expires_at DATETIME NULL, max_uses
// INT NULL, created_at TIMESTAMP). This file creates the table too
// (same CREATE TABLE IF NOT EXISTS) so the list/off endpoints work
// even if the codes file was never installed.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-promo-admin.php          (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). The off test
//      should use a TEST code (create one first, switch it off,
//      then delete it) — never switch off a live code for a test.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use pma_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - These are ADMIN reads/writes (the admin bot calls them with
//     the same X-Bot-Secret). No per-user rate limit is applied here.
//   - The code in the URL is normalised to UPPERCASE before lookup
//     (codes are stored uppercase — the create endpoint does this).
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. bot_promo_codes has the columns api-promo-codes.php creates
//       (see the table note above), INCLUDING fixed_etb — that
//       column is added by the round-3 edit to api-promo-codes.php.
//       If the edit was not installed, this file still works: it
//       checks for the column first and reads fixed_etb as null
//       when it is missing (so a fixed code shows as percent-only
//       until the edit lands — flag it, do not guess).
//   A2. bot_promo_redemptions (telegram_id, code, deposit_id,
//       bonus_etb, UNIQUE (telegram_id, code) + UNIQUE
//       (deposit_id)) is the redemption table. When it does not
//       exist, `uses` reads 0 for every code.
// ============================================================================

// --- small helpers (pma_ prefix so nothing collides with bot.php) -----------

function pma_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function pma_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function pma_has_column($db, $table, $col) {
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

function pma_has_table($db, $table) {
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

function pma_ensure_table($db) {
    // Same table as api-promo-codes.php (plus the fixed_etb column
    // the round-3 edit adds there). CREATE TABLE IF NOT EXISTS
    // never overwrites an existing table; the ALTER below adds the
    // column when the table exists without it.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_promo_codes (
        code VARCHAR(32) NOT NULL PRIMARY KEY,
        percent INT NULL,
        fixed_etb DECIMAL(10,2) NULL,
        active TINYINT(1) NOT NULL DEFAULT 1,
        expires_at DATETIME NULL,
        max_uses INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    if (!pma_has_column($db, 'bot_promo_codes', 'fixed_etb')) {
        $db->query('ALTER TABLE bot_promo_codes ADD COLUMN fixed_etb DECIMAL(10,2) NULL AFTER percent');
    }
    if (!pma_has_column($db, 'bot_promo_codes', 'percent')) {
        $db->query('ALTER TABLE bot_promo_codes ADD COLUMN percent INT NULL AFTER code');
    }
}

// --- GET /api/bot/promo-codes ------------------------------------------------

function bot_pma_list() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') pma_fail(405, 'Method not allowed.');
    $db = pma_db();
    if ($db === null) pma_fail(500, 'Database is not available.');
    pma_ensure_table($db);

    $has_fixed = pma_has_column($db, 'bot_promo_codes', 'fixed_etb');
    $fixed_expr = $has_fixed ? 'fixed_etb' : 'NULL AS fixed_etb';
    $has_uses = pma_has_table($db, 'bot_promo_redemptions');
    $uses_expr = $has_uses
        ? '(SELECT COUNT(*) FROM bot_promo_redemptions r WHERE r.code = c.code)'
        : '0';
    try {
        $res = $db->query(
            "SELECT c.code, c.percent, $fixed_expr, c.active, c.expires_at, c.max_uses, $uses_expr AS uses, c.created_at "
            . 'FROM bot_promo_codes c ORDER BY c.active DESC, c.created_at DESC'
        );
    } catch (mysqli_sql_exception $e) {
        pma_fail(500, 'Could not read the promo codes table.');
    }
    if ($res === false) pma_fail(500, 'Could not read the promo codes table.');
    $codes = [];
    while ($row = $res->fetch_assoc()) {
        $codes[] = [
            'code' => (string)$row['code'],
            'percent' => $row['percent'] !== null ? (int)$row['percent'] : null,
            'fixed_etb' => $row['fixed_etb'] !== null ? (float)$row['fixed_etb'] : null,
            'active' => (bool)$row['active'],
            'expires_at' => $row['expires_at'],
            'max_uses' => $row['max_uses'] !== null ? (int)$row['max_uses'] : null,
            'uses' => (int)$row['uses'],
            'created_at' => $row['created_at'],
        ];
    }
    bot_ok(['codes' => $codes]);
}

// --- POST /api/bot/promo-codes/{CODE}/off -----------------------------------

function bot_pma_off($code) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') pma_fail(405, 'Method not allowed.');
    $code = strtoupper(trim((string)$code));
    if ($code === '' || !preg_match('/^[A-Z0-9]{4,20}$/', $code)) {
        pma_fail(400, 'A promo code is required.');
    }
    $db = pma_db();
    if ($db === null) pma_fail(500, 'Database is not available.');
    pma_ensure_table($db);

    // Only an ACTIVE code switches off. The UPDATE is conditional
    // on active = 1, so switching off an already-off (or missing)
    // code is a 404, never a silent ok.
    try {
        $stmt = $db->prepare('UPDATE bot_promo_codes SET active = 0 WHERE code = ? AND active = 1');
        $stmt->bind_param('s', $code);
        $stmt->execute();
        $changed = $stmt->affected_rows;
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        pma_fail(500, 'Could not switch the code off.');
    }
    if ($changed !== 1) {
        pma_fail(404, 'Promo code not found or already off.');
    }
    bot_ok(['ok' => true, 'code' => $code, 'active' => false]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'promo-codes' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_pma_list(); }
//   if (preg_match('#^promo-codes/([A-Za-z0-9]+)/off$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_pma_off($m[1]); }
//
// LIVE CURL TEST — read this whole block before running it. The off
// test must use a TEST code — create one first, switch it off, then
// delete it. Never switch off a live code for a test.
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. List the codes:
//   curl -s "https://paxyo.et/api/bot/promo-codes" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"codes":[...]}
//   # 2. Create a TEST code (via the admin bot /promo create, or the
//   #    create endpoint in api-promo-codes.php), then switch it off:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/TESTCODE/off \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"ok":true,"code":"TESTCODE","active":false}
//   # 3. Switch it off AGAIN — must 404 (already off):
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/TESTCODE/off \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":false,"error":"Promo code not found or already off."}
//   # 4. List again — TESTCODE must show active:false.
//   Then DELETE the test code:
//   mysql -e "DELETE FROM bot_promo_codes WHERE code='TESTCODE';"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
