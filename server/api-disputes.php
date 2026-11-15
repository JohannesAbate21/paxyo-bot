<?php
// ============================================================================
// Disputes inbox for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot feature 15, disputes inbox —
// "I have a problem with order #1841" files a dispute into the admin
// side, and the admin bot lists the open ones (/disputes) and closes
// them ("close dispute #<id>", Confirm first).
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/disputes
//     -> {"disputes":[{id, order_id, telegram_id, username, message,
//         status, created_at}, ...],"count":N}
//        Open disputes only (status 'open'), newest first, max 50.
//        For the admin bot / admin panel. The bot-side filing is the
//        existing POST /support-reports (server/api-support-reports.php)
//        — this file only READS that same table and closes rows.
//   POST /api/bot/disputes/{id}/close
//     -> {"ok":true,"id":N,"status":"closed"}
//        Marks one open dispute closed. An already-closed dispute
//        (or a missing id) gets a 404 — the admin bot says so
//        honestly instead of confirming blind.
//
// THIS FLOW NEVER REFUNDS and never touches a balance, an order or
// the provider. Closing a dispute only changes its status so the
// admin list stops showing it. A refund, if one is owed, is a
// separate step (the admin bot's refund flow, after Confirm).
//
// TABLE: bot_support_reports — created by api-support-reports.php
// (id, telegram_id, username, order_id, message, status
// ENUM('open','handled','closed') DEFAULT 'open', created_at). This
// file creates it too (same CREATE TABLE IF NOT EXISTS) so the
// endpoints work even if the reports file was never installed —
// but the filing endpoint is the reports file, not this one.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-disputes.php              (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). No money moves:
//      listing and closing never touch balances, orders or the
//      provider. The test close should use a test dispute row, then
//      DELETE it.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use dsp_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - These are ADMIN reads/writes (the admin bot calls them with the
//     same X-Bot-Secret). No per-user rate limit is applied here —
//     the admin bot is the only caller, and the endpoints are behind
//     the secret. If bot.php applies bot_rate_limit(...) to admin
//     routes, add the same call to the dispatch lines.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. bot_support_reports has the columns api-support-reports.php
//       creates (see the table note above). If the live table has a
//       different status spelling, change DSP_OPEN_STATUS below.
//   A2. A dispute's username is filled best-effort at filing time
//       (from auth); this file never joins auth — it reads the
//       stored username as-is, NULL when unknown.
// ============================================================================

// --- small helpers (dsp_ prefix so nothing collides with bot.php) -----------

if (!defined('DSP_OPEN_STATUS')) define('DSP_OPEN_STATUS', 'open');

function dsp_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function dsp_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function dsp_ensure_table($db) {
    // Same table as api-support-reports.php — created here too so
    // the list/close endpoints work even if that file was never
    // installed. CREATE TABLE IF NOT EXISTS never overwrites.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_support_reports (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        username VARCHAR(128) NULL,
        order_id BIGINT NULL,
        message TEXT NOT NULL,
        status ENUM('open','handled','closed') NOT NULL DEFAULT 'open',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_dsp_tg (telegram_id),
        INDEX idx_dsp_order (order_id),
        INDEX idx_dsp_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

function dsp_dispute_row($row) {
    return [
        'id' => (int)$row['id'],
        'order_id' => $row['order_id'] !== null ? (int)$row['order_id'] : null,
        'telegram_id' => (int)$row['telegram_id'],
        'username' => $row['username'],
        'message' => $row['message'],
        'status' => $row['status'],
        'created_at' => $row['created_at'],
    ];
}

// --- GET /api/bot/disputes --------------------------------------------------

function bot_dsp_list() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') dsp_fail(405, 'Method not allowed.');
    $db = dsp_db();
    if ($db === null) dsp_fail(500, 'Database is not available.');
    dsp_ensure_table($db);

    $open = DSP_OPEN_STATUS;
    $stmt = $db->prepare('SELECT id, telegram_id, username, order_id, message, status, created_at FROM bot_support_reports WHERE status = ? ORDER BY id DESC LIMIT 50');
    $stmt->bind_param('s', $open);
    $stmt->execute();
    $res = $stmt->get_result();
    $disputes = [];
    while ($row = $res->fetch_assoc()) {
        $disputes[] = dsp_dispute_row($row);
    }
    $stmt->close();
    bot_ok(['disputes' => $disputes, 'count' => count($disputes)]);
}

// --- POST /api/bot/disputes/{id}/close --------------------------------------

function bot_dsp_close($dispute_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') dsp_fail(405, 'Method not allowed.');
    if ($dispute_id <= 0) dsp_fail(400, 'dispute id is required.');
    $db = dsp_db();
    if ($db === null) dsp_fail(500, 'Database is not available.');
    dsp_ensure_table($db);

    // Only an OPEN dispute closes. The UPDATE is conditional on the
    // status, so a concurrent close cannot double-close — and an
    // already-closed (or missing) id is a 404, never a silent ok.
    $open = DSP_OPEN_STATUS;
    $stmt = $db->prepare("UPDATE bot_support_reports SET status = 'closed' WHERE id = ? AND status = ?");
    $stmt->bind_param('is', $dispute_id, $open);
    $stmt->execute();
    $changed = $stmt->affected_rows;
    $stmt->close();
    if ($changed !== 1) {
        dsp_fail(404, 'Dispute not found or already closed.');
    }
    bot_ok(['ok' => true, 'id' => $dispute_id, 'status' => 'closed']);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'disputes' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_dsp_list(); }
//   if (preg_match('#^disputes/(\d+)/close$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_dsp_close((int)$m[1]); }
//
// LIVE CURL TEST — read this whole block before running it. No money
// moves: listing and closing never touch balances, orders or the
// provider. Use a test dispute row (file one from the bot, or insert
// one by SQL), then DELETE it.
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. List the open disputes:
//   curl -s "https://paxyo.et/api/bot/disputes" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"disputes":[...],"count":N}
//   # 2. Close one (use a test dispute id N):
//   curl -s -X POST https://paxyo.et/api/bot/disputes/N/close \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"ok":true,"id":N,"status":"closed"}
//   # 3. Close it AGAIN — must 404 (already closed):
//   curl -s -X POST https://paxyo.et/api/bot/disputes/N/close \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":false,"error":"Dispute not found or already closed."}
//   # 4. List again — the closed dispute must be gone from the list.
//   Then DELETE the test row:
//   mysql -e "DELETE FROM bot_support_reports WHERE id=N;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
