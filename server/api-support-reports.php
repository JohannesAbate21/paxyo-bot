<?php
// ============================================================================
// Report-a-problem for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot, ideas batch 2 —
// REPORT A PROBLEM. SERVER SIDE ONLY.
//
// INVESTIGATION (done before writing — see the header notes):
//   How do support messages reach the admin TODAY? They do NOT —
//   there is no server endpoint or table for support messages
//   anywhere in this repo. The bot routes a support intent to the
//   contact line "You can reach our customer support by t.me/paxyo"
//   (bot.py `contact_owner` template, generic since 15 Nov 07:04
//   EAT — the bot NEVER names a person on support), and the user
//   messages William directly on Telegram. The Paxyo admin has a
//   Support Chat section (per the project record), but no local
//   file or table name for it was available in this workspace, and
//   no bot_support / support_messages table exists in any local
//   server file. So this file creates a NEW table
//   (bot_support_reports) and NEW endpoints — it wraps nothing
//   existing, because nothing existing was found. If the live admin
//   turns out to keep support chats in its own table, that table
//   and this one can be read side by side; this file does not
//   guess its name.
//   A follow-up admin page for these reports (same pattern as
//   server/admin-confused-chats.php: human-admin session gate,
//   compact table) is NOT in this file — the GET list endpoint
//   below is what the admin bot / admin panel reads.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/support-reports  {telegram_id, order_id?, message}
//     -> {"ok":true,"report_id":N,"status":"open",
//         "note":"This report does not refund your order — ... "}
//        order_id is NULLABLE — the user may report a problem
//        without an order (e.g. a deposit problem, a bot problem).
//        When order_id IS given it must belong to telegram_id, or
//        the call gets the same 404 "Order not found." as a missing
//        order (no leaking).
//   GET  /api/bot/support-reports?status=open
//     -> {"reports":[{...}, ...],"count":N}
//        For the admin (admin bot / admin panel, X-Bot-Secret).
//        Newest first, max 50 per call. status=open|handled|closed
//        (default open); status=all lists everything. Optional
//        &telegram_id=N filters to one user. Every row carries the
//        order id, the user (telegram_id + username when known)
//        and the message.
//
// THIS FLOW NEVER REFUNDS. It only reports. A report changes no
// balance, no order, no deposit and no provider state — the refund
// path is api-order-rescue.php / api-admin-refund.php, and only
// William (via the admin bot, after Confirm) can trigger it. The
// bot must NEVER tell a user that reporting a problem refunds
// them, and the POST response carries that note in plain words.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_support_reports  id AUTO_INCREMENT PK, telegram_id BIGINT,
//                        username VARCHAR(128) NULL (filled
//                        best-effort from auth at insert time, so
//                        the admin list shows a name without a
//                        join; NULL when the user has no auth row),
//                        order_id BIGINT NULL, message TEXT,
//                        status ENUM('open','handled','closed')
//                        DEFAULT 'open', created_at.
//                        Indexes on telegram_id, order_id, status.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-support-reports.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test rows. No money moves: reporting never touches balances,
//      orders, deposits or the provider.
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient methods
// to add, mirroring save_session / load_session in bot.py):
//   report_problem(telegram_id, order_id, message) — POST
//     /support-reports. 404-tolerant (endpoint not live yet ->
//     None + warning; the bot falls back to the t.me/paxyo contact
//     line, which is today's behaviour). The bot passes order_id
//     only when the user is reporting about a specific order it
//     knows (from its own history); otherwise null. The bot shows
//     the response note so the user knows this is a report, not a
//     refund.
//   The bot must NOT promise a refund, a reply time, or a named
//   person. The support-name rule still applies: no names on
//   support, only t.me/paxyo.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. orders: id, telegram_id (owner — see A2), status. Same
//       columns the rescue endpoint assumes. The ownership check
//       reads the row with SELECT * and picks the owner column from
//       a short candidate list (primary name first) — confirm the
//       real names with SHOW COLUMNS FROM orders and trim the list.
//   A2. The owner column on orders: 'telegram_id' first, then
//       'user_id', then 'tg_id' (same candidate list as the rescue
//       file).
//   A3. auth: tg_id + username (the deposits file reads username
//       from auth, so both exist — verified pattern). The username
//       lookup is best-effort: if auth has no row for the user, or
//       no username column, the report is still stored with
//       username NULL. It never fails the report.
//   A4. No account-existence check here, unlike deposits: a user
//       must be able to report a problem even when their auth row
//       does not exist yet (e.g. "I deposited but my account was
//       never created"). The telegram_id on the row is the identity.
//   A5. Status changes (open -> handled -> closed) are NOT in this
//       file — there is no PATCH endpoint. The admin marks a report
//       handled/closed from the admin panel or by direct SQL until
//       a status endpoint is built (one-line SQL in the footer).
//       The GET list defaults to open so the admin sees what still
//       needs attention.
//   A6. bot_ok() is used for success replies (it adds
//       "success":true, as on the other endpoints). Errors use
//       sup_fail() below, which returns
//       {"success":false,"error":...,"message":...} — the bot
//       reads both keys. Add the same bot_rate_limit(...) call the
//       other user endpoints use to the dispatch lines (copy the
//       exact call from the orders handler — the signature was not
//       visible from outside the server).
//   A7. Message limit is 2000 characters (same cap as the
//       confusion log's 500 is too short for a real problem
//       report). Longer input is rejected with 400, not silently
//       truncated — the user should know their message was not
//       fully stored.
// ============================================================================

// --- small helpers (sup_ prefix so nothing collides with bot.php) -----------

function sup_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function sup_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function sup_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function sup_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_support_reports (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        username VARCHAR(128) NULL,
        order_id BIGINT NULL,
        message TEXT NOT NULL,
        status ENUM('open','handled','closed') NOT NULL DEFAULT 'open',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_sup_tg (telegram_id),
        INDEX idx_sup_order (order_id),
        INDEX idx_sup_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Pick the first candidate column that exists on the row and is not
// null/empty. TO VERIFY (A1/A2): confirm the real orders column
// names with SHOW COLUMNS FROM orders and trim this list.
function sup_pick_order_field($row, $candidates) {
    foreach ($candidates as $col) {
        if (array_key_exists($col, $row) && $row[$col] !== null && $row[$col] !== '') {
            return $row[$col];
        }
    }
    return null;
}

// Best-effort username for the admin list. Never throws, never
// fails the report — NULL when the user has no auth row.
function sup_username_for($db, $telegram_id) {
    try {
        $stmt = $db->prepare('SELECT username FROM auth WHERE tg_id = ? LIMIT 1');
        $stmt->bind_param('i', $telegram_id);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_assoc();
        $stmt->close();
        if ($row && (string)($row['username'] ?? '') !== '') return (string)$row['username'];
    } catch (mysqli_sql_exception $e) {
        // No username column, no auth table — the report still goes
        // in with username NULL (see A3).
    }
    return null;
}

function sup_report_row($row) {
    return [
        'id' => (int)$row['id'],
        'telegram_id' => (int)$row['telegram_id'],
        'username' => $row['username'],
        'order_id' => $row['order_id'] === null ? null : (int)$row['order_id'],
        'message' => $row['message'],
        'status' => $row['status'],
        'created_at' => $row['created_at'],
    ];
}

// --- POST /api/bot/support-reports ------------------------------------------
// Body: {"telegram_id":N,"order_id":N|null,"message":"..."}. This
// only RECORDS the problem. It NEVER refunds — see the header.

function bot_sup_create() {
    $in = sup_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) sup_fail(400, 'telegram_id is required.');
    $message = trim((string)($in['message'] ?? ''));
    if ($message === '') sup_fail(400, 'message is required.');
    if (function_exists('mb_strlen') ? mb_strlen($message, 'UTF-8') > 2000 : strlen($message) > 2000) {
        sup_fail(400, 'message is too long (max 2000 characters).');
    }
    $order_id = null;
    if (isset($in['order_id']) && $in['order_id'] !== null && trim((string)$in['order_id']) !== '') {
        if (!is_int($in['order_id']) && !(is_string($in['order_id']) && preg_match('/^\d+$/', (string)$in['order_id']))) {
            sup_fail(400, 'order_id must be a number or null.');
        }
        $order_id = (int)$in['order_id'];
        if ($order_id <= 0) sup_fail(400, 'order_id must be a number or null.');
    }

    $db = sup_db();
    if ($db === null) sup_fail(500, 'Database is not available.');
    sup_ensure_table($db);

    // When an order is named, it must belong to this user — same
    // 404 as a missing order, no leaking.
    if ($order_id !== null) {
        $stmt = $db->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
        $stmt->bind_param('i', $order_id);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_assoc();
        $stmt->close();
        if (!$row) sup_fail(404, 'Order not found.');
        $owner = sup_pick_order_field($row, ['telegram_id', 'user_id', 'tg_id']);
        if ($owner === null || (int)$owner !== $telegram_id) sup_fail(404, 'Order not found.');
    }

    $username = sup_username_for($db, $telegram_id);
    $stmt = $db->prepare('INSERT INTO bot_support_reports (telegram_id, username, order_id, message) VALUES (?, ?, ?, ?)');
    $stmt->bind_param('isis', $telegram_id, $username, $order_id, $message);
    if (!$stmt->execute()) {
        $stmt->close();
        sup_fail(500, 'Could not save the report.');
    }
    $report_id = $db->insert_id;
    $stmt->close();
    bot_ok([
        'ok' => true,
        'report_id' => (int)$report_id,
        'status' => 'open',
        'note' => 'Report received. This does not refund your order — support will look into it.',
    ]);
}

// --- GET /api/bot/support-reports -------------------------------------------
// For the admin (admin bot / admin panel, X-Bot-Secret). Newest
// first, max 50. ?status=open (default) | handled | closed | all.
// Optional &telegram_id=N filters to one user.

function bot_sup_list() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') sup_fail(405, 'Method not allowed.');
    $status = strtolower(trim((string)($_GET['status'] ?? 'open')));
    if (!in_array($status, ['open', 'handled', 'closed', 'all'], true)) {
        sup_fail(400, 'status must be open, handled, closed or all.');
    }
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    $limit = (int)($_GET['limit'] ?? 50);
    if ($limit < 1) $limit = 50;
    if ($limit > 50) $limit = 50;

    $db = sup_db();
    if ($db === null) sup_fail(500, 'Database is not available.');
    sup_ensure_table($db);

    $where = [];
    $types = '';
    $params = [];
    if ($status !== 'all') {
        $where[] = 'status = ?';
        $types .= 's';
        $params[] = $status;
    }
    if ($telegram_id > 0) {
        $where[] = 'telegram_id = ?';
        $types .= 'i';
        $params[] = $telegram_id;
    }
    $where_sql = $where ? (' WHERE ' . implode(' AND ', $where)) : '';
    $params[] = $limit;
    $types .= 'i';

    $reports = [];
    try {
        $stmt = $db->prepare(
            'SELECT id, telegram_id, username, order_id, message, status, created_at '
            . 'FROM bot_support_reports' . $where_sql . ' ORDER BY id DESC LIMIT ?'
        );
        $stmt->bind_param($types, ...$params);
        $stmt->execute();
        $res = $stmt->get_result();
        while ($row = $res->fetch_assoc()) $reports[] = sup_report_row($row);
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        sup_fail(500, 'Could not list the reports.');
    }
    bot_ok(['reports' => $reports, 'count' => count($reports)]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'support-reports' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_sup_create(); }
//   if ($bp === 'support-reports' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_sup_list(); }
//   (Add the same bot_rate_limit(...) call the other user endpoints
//    use to both dispatch lines — copy the exact call from the orders
//    handler; the signature was not visible from outside the server.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-support-reports.php`
// on the server (step 1 of the install) and `php -l api/bot.php`
// after splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account,
// and a KNOWN order id C belonging to it. No money moves: reporting
// never touches balances, orders, deposits or the provider):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. report WITHOUT an order:
//   curl -s -X POST https://paxyo.et/api/bot/support-reports \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"message":"Test report — no order. Please ignore."}'
//   -> expect {"success":true,"ok":true,"report_id":N,"status":"open",
//      "note":"Report received. This does not refund your order — ... "}
//   # 2. report WITH order C:
//   curl -s -X POST https://paxyo.et/api/bot/support-reports \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"order_id":C,"message":"Test report — order C. Please ignore."}'
//   -> expect {"success":true,"ok":true,"report_id":M,"status":"open",...}
//   # 3. list open reports -> both test rows, newest first, each with
//   #    order id, user and message:
//   curl -s "https://paxyo.et/api/bot/support-reports?status=open" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"reports":[{...,"telegram_id":779060335,
//      "order_id":C,"message":"Test report — order C. ..."}, {...,
//      "order_id":null,...}],"count":N}
//   # 4. filter by telegram_id:
//   curl -s "https://paxyo.et/api/bot/support-reports?status=open&telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect the same two rows (and no other user's rows).
//   # 5. someone else's order id -> 404, same message as missing:
//   curl -s -X POST https://paxyo.et/api/bot/support-reports \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":1,"order_id":C,"message":"x"}'
//   -> expect {"success":false,"error":"Order not found."}
//   # 6. empty message -> 400, nothing stored:
//   curl -s -X POST https://paxyo.et/api/bot/support-reports \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"message":"   "}'
//   -> expect {"success":false,"error":"message is required."}
//   # 7. bad status filter -> 400:
//   curl -s "https://paxyo.et/api/bot/support-reports?status=bogus" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":false,"error":"status must be open, handled, closed or all."}
//   Then DELETE the test rows and confirm they are gone:
//   mysql -e "DELETE FROM bot_support_reports WHERE telegram_id=779060335 AND message LIKE 'Test report%'; SELECT COUNT(*) FROM bot_support_reports WHERE telegram_id=779060335 AND message LIKE 'Test report%';"
//   (use the same MySQL credentials db.php uses; never print them.)
//   Marking a report handled/closed (no endpoint yet — see A5):
//   mysql -e "UPDATE bot_support_reports SET status='handled' WHERE id=N;"
// ============================================================================
