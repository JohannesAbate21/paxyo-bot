<?php
// ============================================================================
// One-time delayed orders for the Paxyo Bot API (public_html/api/bot.php).
// Written 14 Nov 2026 for @paxorder_bot: "order 10k views to this link
// after 3 hrs" places ONCE at that time, even if the user is asleep
// or offline, and messages them afterwards.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/delayed-orders
//     {telegram_id, service_id, link, quantity, total, run_at,
//      idempotency_key}
//     -> {"ok":true,"id":N,"delayed_order":{...}}   (run_at is UTC
//        "YYYY-MM-DD HH:MM:SS"; idempotency_key is unique — a retry
//        with the same key returns the existing row, never a second
//        scheduled order)
//   GET  /api/bot/delayed-orders?telegram_id=X[&status=scheduled]
//     -> {"delayed_orders":[{id,telegram_id,service_id,link,quantity,
//        total,run_at,status,idempotency_key,order_id,reason,
//        created_at}]}  soonest first
//   POST /api/bot/delayed-orders/{id}/cancel {telegram_id}
//     -> {"ok":true}   (only a row still 'scheduled' can be cancelled)
//   GET  /api/bot/delayed-orders/due
//     -> {"delayed_orders":[...]}   scheduled rows whose run_at is
//        now or past, PLUS rows stuck 'placing' for over 30 minutes
//        (the claimer crashed between claim and place — see claim)
//   POST /api/bot/delayed-orders/{id}/claim {telegram_id}
//     -> {"ok":true} only when the row was still 'scheduled' (or a
//        stale 'placing' row) — the atomic claim that makes placement
//        exactly-once. {"ok":false} when someone else already
//        claimed it.
//   POST /api/bot/delayed-orders/{id}/finish
//     {telegram_id, status:"placed"|"failed", order_id?, reason?}
//     -> {"ok":true}   (only a row still 'placing' can be finished)
//
// TABLES (created automatically on first call, utf8mb4 so emoji in
// links survive):
//   delayed_orders  id AUTO_INCREMENT PK, telegram_id, service_id,
//                   link VARCHAR(500), quantity, total DECIMAL(12,2),
//                   run_at DATETIME (UTC), status ENUM(scheduled,
//                   placing, placed, failed, cancelled),
//                   idempotency_key VARCHAR(64) UNIQUE,
//                   order_id VARCHAR(64) NULL, reason VARCHAR(255)
//                   NULL, created_at, updated_at (ON UPDATE — the
//                   claim timestamp for the stale-claim recovery)
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-delayed-orders.php    (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test rows.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use del_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - NO account-existence check here, unlike deposits: a scheduled
//     order must be storable even for a brand-new user whose auth row
//     does not exist yet. Orphan rows are tiny and keyed by
//     telegram_id, so this cannot grow out of control.
//   - The bot checks the balance at placement time and marks the row
//     'failed' (reason "insufficient balance") when it is short —
//     the server never places an order itself and never touches a
//     balance. All money steps stay in the bot's deterministic code.
//   - Exact timing needs an always-on server: on free Render the bot
//     sleeps ~15 minutes idle, so a due order may run late, on the
//     next wake. The due endpoint and the claim are built so a late
//     run still places exactly once.
// ============================================================================

// --- small helpers (del_ prefix so nothing collides with bot.php) -----------

function del_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function del_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function del_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function del_substr($text, $len) {
    // mb_substr keeps emoji intact when truncating; plain substr is
    // the fallback if mbstring is ever missing on the server.
    if (function_exists('mb_substr')) return mb_substr($text, 0, $len, 'UTF-8');
    return substr($text, 0, $len);
}

function del_ensure_tables($db) {
    // utf8mb4 so emoji in links survive.
    // set_charset is idempotent — harmless if bot.php already did it.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS delayed_orders (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        service_id INT NOT NULL,
        link VARCHAR(500) NOT NULL,
        quantity INT NOT NULL,
        total DECIMAL(12,2) NOT NULL,
        run_at DATETIME NOT NULL,
        status ENUM('scheduled','placing','placed','failed','cancelled') NOT NULL DEFAULT 'scheduled',
        idempotency_key VARCHAR(64) NOT NULL,
        order_id VARCHAR(64) NULL,
        reason VARCHAR(255) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_delayed_idem (idempotency_key),
        INDEX idx_delayed_tg (telegram_id),
        INDEX idx_delayed_run (status, run_at),
        INDEX idx_delayed_updated (status, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

function del_row($row) {
    return [
        'id' => (int)$row['id'],
        'telegram_id' => (int)$row['telegram_id'],
        'service_id' => (int)$row['service_id'],
        'link' => $row['link'],
        'quantity' => (int)$row['quantity'],
        'total' => (float)$row['total'],
        'run_at' => $row['run_at'],
        'status' => $row['status'],
        'idempotency_key' => $row['idempotency_key'],
        'order_id' => $row['order_id'],
        'reason' => $row['reason'],
        'created_at' => $row['created_at'],
    ];
}

function del_load_row($db, $id, $telegram_id) {
    $stmt = $db->prepare('SELECT * FROM delayed_orders WHERE id = ? AND telegram_id = ? LIMIT 1');
    $stmt->bind_param('ii', $id, $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// --- POST /api/bot/delayed-orders -------------------------------------------

function bot_del_create() {
    $in = del_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) del_fail(400, 'telegram_id is required.');
    $service_id = (int)($in['service_id'] ?? 0);
    if ($service_id <= 0) del_fail(400, 'service_id is required.');
    $link = del_substr(trim((string)($in['link'] ?? '')), 500);
    if ($link === '') del_fail(400, 'link is required.');
    $quantity = (int)($in['quantity'] ?? 0);
    if ($quantity <= 0) del_fail(400, 'quantity must be positive.');
    $total = (float)($in['total'] ?? 0);
    if ($total < 0) del_fail(400, 'total must not be negative.');
    $run_at = trim((string)($in['run_at'] ?? ''));
    if (!preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $run_at)
        || strtotime($run_at) === false) {
        del_fail(400, 'run_at must be "YYYY-MM-DD HH:MM:SS" (UTC).');
    }
    $key = del_substr(trim((string)($in['idempotency_key'] ?? '')), 64);
    if ($key === '') del_fail(400, 'idempotency_key is required.');

    $db = del_db();
    if ($db === null) del_fail(500, 'Database is not available.');
    del_ensure_tables($db);

    $stmt = $db->prepare('INSERT INTO delayed_orders (telegram_id, service_id, link, quantity, total, run_at, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?)');
    $stmt->bind_param('iisidss', $telegram_id, $service_id, $link, $quantity, $total, $run_at, $key);
    if (!$stmt->execute()) {
        // Duplicate idempotency key: the same order was already
        // scheduled (a retried Confirm) — return the existing row
        // instead of failing or double-scheduling.
        if ($db->errno === 1062) {
            $stmt->close();
            $stmt2 = $db->prepare('SELECT * FROM delayed_orders WHERE idempotency_key = ? LIMIT 1');
            $stmt2->bind_param('s', $key);
            $stmt2->execute();
            $row = $stmt2->get_result()->fetch_assoc();
            $stmt2->close();
            if ($row) {
                bot_ok(['ok' => true, 'id' => (int)$row['id'], 'delayed_order' => del_row($row)]);
                return;
            }
        }
        $stmt->close();
        del_fail(500, 'Could not schedule the order.');
    }
    $id = $db->insert_id;
    $stmt->close();
    $row = del_load_row($db, $id, $telegram_id);
    bot_ok(['ok' => true, 'id' => $id, 'delayed_order' => $row ? del_row($row) : null]);
}

// --- GET /api/bot/delayed-orders?telegram_id=X[&status=...] ------------------

function bot_del_list() {
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) del_fail(400, 'telegram_id is required.');
    $status = strtolower(trim((string)($_GET['status'] ?? 'scheduled')));
    $allowed = ['scheduled', 'placing', 'placed', 'failed', 'cancelled'];
    if (!in_array($status, $allowed, true)) del_fail(400, 'status is not valid.');

    $db = del_db();
    if ($db === null) del_fail(500, 'Database is not available.');
    del_ensure_tables($db);

    $stmt = $db->prepare('SELECT * FROM delayed_orders WHERE telegram_id = ? AND status = ? ORDER BY run_at ASC LIMIT 100');
    $stmt->bind_param('is', $telegram_id, $status);
    $stmt->execute();
    $res = $stmt->get_result();
    $out = [];
    while ($row = $res->fetch_assoc()) {
        $out[] = del_row($row);
    }
    $stmt->close();
    bot_ok(['delayed_orders' => $out]);
}

// --- GET /api/bot/delayed-orders/due ----------------------------------------
// Scheduled rows whose run_at is now or past, PLUS rows stuck
// 'placing' for over 30 minutes (the claimer crashed between claim
// and place). The claim below still guards against a double
// placement, so a stale claim delays the order instead of losing it.

function bot_del_due() {
    $db = del_db();
    if ($db === null) del_fail(500, 'Database is not available.');
    del_ensure_tables($db);

    $res = $db->query("SELECT * FROM delayed_orders WHERE (status = 'scheduled' AND run_at <= UTC_TIMESTAMP()) OR (status = 'placing' AND updated_at < UTC_TIMESTAMP() - INTERVAL 30 MINUTE) ORDER BY run_at ASC LIMIT 100");
    $out = [];
    while ($row = $res->fetch_assoc()) {
        $out[] = del_row($row);
    }
    bot_ok(['delayed_orders' => $out]);
}

// --- POST /api/bot/delayed-orders/{id}/cancel|claim|finish -------------------

function bot_del_action($id, $action) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') del_fail(405, 'Method not allowed.');
    $in = del_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) del_fail(400, 'telegram_id is required.');
    if ($id <= 0) del_fail(400, 'id is required.');

    $db = del_db();
    if ($db === null) del_fail(500, 'Database is not available.');
    del_ensure_tables($db);

    if ($action === 'cancel') {
        // Only a row still 'scheduled' can be cancelled.
        $stmt = $db->prepare("UPDATE delayed_orders SET status = 'cancelled' WHERE id = ? AND telegram_id = ? AND status = 'scheduled'");
        $stmt->bind_param('ii', $id, $telegram_id);
        $stmt->execute();
        $changed = $stmt->affected_rows;
        $stmt->close();
        if ($changed === 1) {
            bot_ok(['ok' => true]);
            return;
        }
        if (del_load_row($db, $id, $telegram_id) === null) del_fail(404, 'Delayed order not found.');
        del_fail(409, 'Delayed order is no longer scheduled.');
    }

    if ($action === 'claim') {
        // The atomic claim: only a row still 'scheduled' (or a stale
        // 'placing' row, see /due) is claimed. Two claimers racing
        // each other: exactly one UPDATE matches.
        $stmt = $db->prepare("UPDATE delayed_orders SET status = 'placing' WHERE id = ? AND telegram_id = ? AND (status = 'scheduled' OR (status = 'placing' AND updated_at < UTC_TIMESTAMP() - INTERVAL 30 MINUTE))");
        $stmt->bind_param('ii', $id, $telegram_id);
        $stmt->execute();
        $changed = $stmt->affected_rows;
        $stmt->close();
        if ($changed === 1) {
            bot_ok(['ok' => true]);
            return;
        }
        if (del_load_row($db, $id, $telegram_id) === null) del_fail(404, 'Delayed order not found.');
        bot_ok(['ok' => false]);
        return;
    }

    if ($action === 'finish') {
        $status = strtolower(trim((string)($in['status'] ?? '')));
        if (!in_array($status, ['placed', 'failed'], true)) del_fail(400, 'status must be "placed" or "failed".');
        $order_id = null;
        if (isset($in['order_id']) && $in['order_id'] !== '') {
            $order_id = del_substr((string)$in['order_id'], 64);
        }
        $reason = null;
        if (isset($in['reason']) && $in['reason'] !== '') {
            $reason = del_substr((string)$in['reason'], 255);
        }
        // Only a row still 'placing' can be finished.
        $stmt = $db->prepare('UPDATE delayed_orders SET status = ?, order_id = ?, reason = ? WHERE id = ? AND telegram_id = ? AND status = ?');
        $placing = 'placing';
        $stmt->bind_param('sssiis', $status, $order_id, $reason, $id, $telegram_id, $placing);
        $stmt->execute();
        $changed = $stmt->affected_rows;
        $stmt->close();
        if ($changed === 1) {
            bot_ok(['ok' => true]);
            return;
        }
        if (del_load_row($db, $id, $telegram_id) === null) del_fail(404, 'Delayed order not found.');
        del_fail(409, 'Delayed order is not being placed.');
    }

    del_fail(404, 'Unknown delayed-orders action.');
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'delayed-orders' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_del_create(); }
//   if ($bp === 'delayed-orders' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_del_list(); }
//   if ($bp === 'delayed-orders/due' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_del_due(); }
//   if (preg_match('#^delayed-orders/(\d+)/(cancel|claim|finish)$#', $bp, $m)) { bot_del_action((int)$m[1], $m[2]); }
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account —
// no money moves, these endpoints never touch balances or orders):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. create a test order due in 2 minutes (run_at is UTC):
//   RUN_AT=$(date -u -d '+2 minutes' '+%Y-%m-%d %H:%M:%S')
//   curl -s -X POST https://paxyo.et/api/bot/delayed-orders \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d "{\"telegram_id\":779060335,\"service_id\":1665,\"link\":\"https://www.tiktok.com/@paxyo/video/1\",\"quantity\":100,\"total\":1.89,\"run_at\":\"$RUN_AT\",\"idempotency_key\":\"test-delay-1\"}"
//   -> expect {"success":true,"ok":true,"id":N,"delayed_order":{...,"status":"scheduled",...}}
//   # 2. same key again -> the SAME id, no second row:
//   curl -s -X POST https://paxyo.et/api/bot/delayed-orders \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d "{\"telegram_id\":779060335,\"service_id\":1665,\"link\":\"https://www.tiktok.com/@paxyo/video/1\",\"quantity\":100,\"total\":1.89,\"run_at\":\"$RUN_AT\",\"idempotency_key\":\"test-delay-1\"}"
//   -> expect the same "id":N as step 1.
//   # 3. list it:
//   curl -s "https://paxyo.et/api/bot/delayed-orders?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect the row in "delayed_orders".
//   # 4. cancel it (id N from step 1):
//   curl -s -X POST https://paxyo.et/api/bot/delayed-orders/N/cancel \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true}
//   # 5. claim the cancelled row -> ok:false (no longer scheduled):
//   curl -s -X POST https://paxyo.et/api/bot/delayed-orders/N/claim \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":false}
//   # 6. due (nothing due — the test row is cancelled):
//   curl -s "https://paxyo.et/api/bot/delayed-orders/due" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"delayed_orders":[]}
//   Then DELETE the test row and confirm it is gone:
//   mysql -e "DELETE FROM delayed_orders WHERE telegram_id=779060335; SELECT COUNT(*) FROM delayed_orders WHERE telegram_id=779060335;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
