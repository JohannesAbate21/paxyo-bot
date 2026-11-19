<?php
// ============================================================================
// Auto-refill records for the Paxyo Bot API (public_html/api/bot.php).
// Written 19 Nov 2026 for @paxorder_bot: "keep-above-target" — the bot
// tops a count (TikTok views/followers, YouTube views/subscribers,
// Telegram members) back up to a target, by itself, every hour.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/refills/status
//     -> {"refills_live":true}   (the bot probes this before ever
//        telling a user the hourly check is live; 404 means not
//        installed yet, and the bot keeps saying honestly that the
//        check is not installed)
//   POST /api/bot/refills
//     {telegram_id, service_id, provider, link, platform, metric,
//      target, service_json, idempotency_key}
//     -> {"ok":true,"id":N,"refill":{...}}   (idempotency_key is
//        UNIQUE — a retry with the same key returns the existing
//        row, never a second refill)
//   GET  /api/bot/refills?telegram_id=X[&status=active]
//     -> {"refills":[{id,telegram_id,service_id,provider,link,
//        platform,metric,target,service,spent_today,spent_date,
//        last_count,last_check,count_usage,status,created_at,
//        updated_at}]}   (no telegram_id: every user — the hourly
//        worker's list; no status: active + checking rows only;
//        status=all: everything; stalest first, so the worker
//        checks the least-recently-checked refill first)
//   POST /api/bot/refills/{id}/claim
//     -> {"ok":true} only when the row was still 'active' (or a
//        stale 'checking' row, over 30 minutes old — the claimer
//        crashed between claim and finish, see finish). This is
//        the atomic claim that makes a top-up exactly-once:
//        two overlapping worker runs cannot order twice for the
//        same refill. {"ok":false} when someone else holds it.
//   POST /api/bot/refills/{id}/finish
//     {last_count, last_check, count_usage, spent_today, spent_date}
//     -> {"ok":true}   (only a row still 'checking' can be
//        finished — this releases the claim and persists the
//        check's results, including the durable count cache)
//   POST /api/bot/refills/{id}/stop {telegram_id}
//     -> {"ok":true}   (only the row's own user can stop it;
//        only a row still 'active' or 'checking' can be stopped)
//
// WHAT THIS FILE DOES NOT DO: it never places an order and never
// touches a balance. Money flows only through the existing
// POST /orders and POST /orders/smm endpoints, which debit the
// user's balance atomically at placement. The hourly worker (Fly,
// refill_worker.py) calls those endpoints exactly like the bot
// does when auto_refill_check() says "top_up". This file only
// stores refill records.
//
// TABLE (bot_refills, created automatically on first call — see
// arf_ensure_tables; the same CREATE TABLE is in bot_refills.sql
// for running directly in phpMyAdmin). Columns map one-to-one to
// the bot-side record in register_auto_refill() (bot.py); the
// worker rebuilds that dict from a row. JSON is stored as TEXT
// (not the MySQL JSON type — the DirectAdmin server may run
// MariaDB, where JSON is only an alias). All times UTC;
// last_check is a unix timestamp because the bot compares it
// with time.time().
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-auto-refill.php   (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block) to the end of bot.php.
//   3. php -l api/bot.php          (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file), then DELETE
//      the test rows.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - Success replies carry BOTH "success":true and "ok":true: the
//     bot reads "ok" on these endpoints and "success" elsewhere.
//     Errors are {"success":false,"ok":false,"error":...,
//     "message":...} with HTTP 400 (404 only when the row is missing).
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - The dispatch lines must sit before the 404 fallback. They do
//     NOT collide with the loose two-segment orders handler (the
//     drip-feed bug, 19 Nov 2026): these paths start with "refills",
//     never "orders".
//   - The claim's 30-minute stale window matches the delayed-orders
//     file: a worker run that crashes between claim and finish
//     leaves the row 'checking', and the next run reclaims it.
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

function arf_input() {
    $raw = file_get_contents('php://input');
    if ($raw === false || $raw === '') {
        return [];
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : [];
}

function arf_ok($data) {
    // Both keys: the bot reads "ok" here and "success" elsewhere.
    $body = array_merge(['success' => true, 'ok' => true], $data);
    http_response_code(200);
    header('Content-Type: application/json');
    echo json_encode($body);
    exit;
}

function arf_fail($error, $message, $code = 400) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode([
        'success' => false, 'ok' => false,
        'error' => $error, 'message' => $message,
    ]);
    exit;
}

function arf_ensure_tables() {
    $db = arf_db();
    if ($db === null) {
        arf_fail('db_unavailable', 'Database is not available.', 500);
    }
    $sql = "CREATE TABLE IF NOT EXISTS `bot_refills` (
      `id` bigint unsigned NOT NULL AUTO_INCREMENT,
      `telegram_id` bigint NOT NULL,
      `service_id` int DEFAULT NULL,
      `provider` varchar(8) NOT NULL DEFAULT 'gop',
      `link` varchar(500) NOT NULL,
      `platform` varchar(32) NOT NULL DEFAULT '',
      `metric` varchar(32) NOT NULL DEFAULT '',
      `target` int NOT NULL,
      `service_json` text NOT NULL,
      `spent_today` decimal(12,2) NOT NULL DEFAULT 0.00,
      `spent_date` date DEFAULT NULL,
      `last_count` int DEFAULT NULL,
      `last_check` bigint DEFAULT NULL,
      `count_usage` text NULL,
      `status` enum('active','checking','stopped') NOT NULL DEFAULT 'active',
      `idempotency_key` varchar(64) DEFAULT NULL,
      `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
      `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_refill_idem` (`idempotency_key`),
      KEY `idx_refills_user` (`telegram_id`, `status`),
      KEY `idx_refills_active` (`status`, `updated_at`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4";
    if (!$db->query($sql)) {
        arf_fail('db_error', 'Could not create the refills table.', 500);
    }
}

// The five platform+metric pairs the count chain can actually check
// (COUNT_CHAIN in bot.py). The bot already refuses anything else at
// setup; the server refuses it too, so a bad row can never sit in
// the table waiting for a worker that cannot check it.
function arf_supported_combo($platform, $metric) {
    $ok = [
        'tiktok' => ['views', 'followers'],
        'youtube' => ['views', 'subscribers'],
        'telegram' => ['members'],
    ];
    return isset($ok[$platform]) && in_array($metric, $ok[$platform], true);
}

function arf_decode_json($text, $fallback) {
    if ($text === null || $text === '') {
        return $fallback;
    }
    $decoded = json_decode($text, true);
    return is_array($decoded) ? $decoded : $fallback;
}

// One DB row -> the bot-side refill record shape (the dict
// auto_refill_check() takes). The worker rebuilds exactly this.
function arf_row_to_record($row) {
    return [
        'id' => (int)$row['id'],
        'telegram_id' => (int)$row['telegram_id'],
        'service_id' => $row['service_id'] !== null ? (int)$row['service_id'] : null,
        'provider' => $row['provider'],
        'link' => $row['link'],
        'platform' => $row['platform'],
        'metric' => $row['metric'],
        'target' => (int)$row['target'],
        'service' => arf_decode_json($row['service_json'], []),
        'spent_today' => (float)$row['spent_today'],
        'spent_date' => $row['spent_date'],
        'last_count' => $row['last_count'] !== null ? (int)$row['last_count'] : null,
        'last_check' => $row['last_check'] !== null ? (int)$row['last_check'] : null,
        'count_usage' => arf_decode_json($row['count_usage'], []),
        'status' => $row['status'],
        'created_at' => $row['created_at'],
        'updated_at' => $row['updated_at'],
    ];
}

function arf_fetch_row($db, $id) {
    $stmt = $db->prepare('SELECT * FROM bot_refills WHERE id = ?');
    $stmt->bind_param('i', $id);
    $stmt->execute();
    $res = $stmt->get_result();
    $row = $res ? $res->fetch_assoc() : null;
    $stmt->close();
    return $row ?: null;
}

// --- endpoints -------------------------------------------------------------

function arf_status() {
    // The bot's probe (GET /refills/status): a tiny reply, no DB hit.
    arf_ok(['refills_live' => true]);
}

function arf_create() {
    arf_ensure_tables();
    $db = arf_db();
    $in = arf_input();
    $telegram_id = isset($in['telegram_id']) ? (int)$in['telegram_id'] : 0;
    $service_id = isset($in['service_id']) ? (int)$in['service_id'] : 0;
    $provider = strtolower(trim($in['provider'] ?? 'gop'));
    $link = trim($in['link'] ?? '');
    $platform = strtolower(trim($in['platform'] ?? ''));
    $metric = strtolower(trim($in['metric'] ?? ''));
    $target = isset($in['target']) ? (int)$in['target'] : 0;
    $service = $in['service_json'] ?? $in['service'] ?? null;
    if (is_string($service)) {
        $service = arf_decode_json($service, null);
    }
    $idem = trim($in['idempotency_key'] ?? '');
    if ($telegram_id <= 0) {
        arf_fail('bad_telegram_id', 'telegram_id is required.');
    }
    if ($service_id <= 0) {
        arf_fail('bad_service_id', 'service_id is required.');
    }
    if ($provider !== 'gop' && $provider !== 'smm') {
        arf_fail('bad_provider', "provider must be 'gop' or 'smm'.");
    }
    if ($link === '' || strlen($link) > 500) {
        arf_fail('bad_link', 'link is required (max 500 characters).');
    }
    if (!arf_supported_combo($platform, $metric)) {
        arf_fail('unsupported_metric', 'This platform and metric cannot be counted yet.');
    }
    if ($target <= 0) {
        arf_fail('bad_target', 'target must be a count above zero.');
    }
    if (!is_array($service) || !isset($service['service'])
        || !isset($service['rate_etb_per_1000'])) {
        arf_fail('bad_service', 'service_json must carry the service id and rate.');
    }
    if ($idem === '') {
        $idem = 'refill-' . bin2hex(random_bytes(8));
    }
    // Idempotent create: a retry with the same key returns the
    // existing row, never a second refill.
    $stmt = $db->prepare('SELECT * FROM bot_refills WHERE idempotency_key = ?');
    $stmt->bind_param('s', $idem);
    $stmt->execute();
    $res = $stmt->get_result();
    $existing = $res ? $res->fetch_assoc() : null;
    $stmt->close();
    if ($existing) {
        arf_ok(['id' => (int)$existing['id'], 'duplicate' => true,
                'refill' => arf_row_to_record($existing)]);
    }
    $service_json = json_encode($service);
    $stmt = $db->prepare(
        'INSERT INTO bot_refills (telegram_id, service_id, provider, link, ' .
        'platform, metric, target, service_json, idempotency_key) ' .
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
    );
    $stmt->bind_param('iissssiss', $telegram_id, $service_id, $provider, $link,
        $platform, $metric, $target, $service_json, $idem);
    if (!$stmt->execute()) {
        // 1062: a concurrent create with the same key won the race —
        // return its row instead of failing.
        if ($db->errno === 1062) {
            $stmt->close();
            $stmt = $db->prepare('SELECT * FROM bot_refills WHERE idempotency_key = ?');
            $stmt->bind_param('s', $idem);
            $stmt->execute();
            $res = $stmt->get_result();
            $row = $res ? $res->fetch_assoc() : null;
            $stmt->close();
            if ($row) {
                arf_ok(['id' => (int)$row['id'], 'duplicate' => true,
                        'refill' => arf_row_to_record($row)]);
            }
        }
        $stmt->close();
        arf_fail('db_error', 'Could not save the refill.', 500);
    }
    $id = (int)$db->insert_id;
    $stmt->close();
    $row = arf_fetch_row($db, $id);
    arf_ok(['id' => $id, 'refill' => arf_row_to_record($row)]);
}

function arf_list() {
    arf_ensure_tables();
    $db = arf_db();
    $telegram_id = isset($_GET['telegram_id']) ? (int)$_GET['telegram_id'] : 0;
    $status = strtolower(trim($_GET['status'] ?? ''));
    $where = [];
    $types = '';
    $params = [];
    if ($telegram_id > 0) {
        $where[] = 'telegram_id = ?';
        $types .= 'i';
        $params[] = $telegram_id;
    }
    if ($status === 'all') {
        // No status filter: everything, including stopped rows.
    } elseif ($status !== '') {
        if (!in_array($status, ['active', 'checking', 'stopped'], true)) {
            arf_fail('bad_status', "status must be 'active', 'checking', 'stopped' or 'all'.");
        }
        $where[] = 'status = ?';
        $types .= 's';
        $params[] = $status;
    } else {
        // Default: rows the worker still cares about.
        $where[] = "status IN ('active','checking')";
    }
    $sql = 'SELECT * FROM bot_refills';
    if ($where) {
        $sql .= ' WHERE ' . implode(' AND ', $where);
    }
    // Stalest first: the worker checks the least-recently-checked
    // refill first, spreading checks across the hour.
    $sql .= ' ORDER BY updated_at ASC LIMIT 100';
    $stmt = $db->prepare($sql);
    if ($params) {
        $stmt->bind_param($types, ...$params);
    }
    $stmt->execute();
    $res = $stmt->get_result();
    $out = [];
    while ($res && ($row = $res->fetch_assoc())) {
        $out[] = arf_row_to_record($row);
    }
    $stmt->close();
    arf_ok(['refills' => $out]);
}

function arf_claim($id) {
    arf_ensure_tables();
    $db = arf_db();
    // Atomic claim: only an 'active' row, or a 'checking' row whose
    // claimer went stale over 30 minutes ago, can be claimed.
    $stmt = $db->prepare(
        "UPDATE bot_refills SET status = 'checking', updated_at = NOW() " .
        'WHERE id = ? AND (status = \'active\' OR ' .
        "(status = 'checking' AND updated_at < DATE_SUB(NOW(), INTERVAL 30 MINUTE)))"
    );
    $stmt->bind_param('i', $id);
    $stmt->execute();
    $claimed = $stmt->affected_rows === 1;
    $stmt->close();
    arf_ok(['claimed' => $claimed]);
}

function arf_finish($id) {
    arf_ensure_tables();
    $db = arf_db();
    $in = arf_input();
    // Only a row still 'checking' can be finished: this releases
    // the claim and persists the check's results in one step.
    $last_count = isset($in['last_count']) && $in['last_count'] !== null
        ? (int)$in['last_count'] : null;
    $last_check = isset($in['last_check']) && $in['last_check'] !== null
        ? (int)$in['last_check'] : null;
    $usage = $in['count_usage'] ?? [];
    if (!is_array($usage)) {
        $usage = [];
    }
    $count_usage = json_encode($usage);
    $spent_today = isset($in['spent_today']) ? (float)$in['spent_today'] : 0.0;
    $spent_date = isset($in['spent_date']) && $in['spent_date'] !== null
        ? substr(trim($in['spent_date']), 0, 10) : null;
    if ($spent_date === '') {
        $spent_date = null;
    }
    if ($spent_today < 0) {
        $spent_today = 0.0;
    }
    $stmt = $db->prepare(
        'UPDATE bot_refills SET status = \'active\', last_count = ?, ' .
        'last_check = ?, count_usage = ?, spent_today = ?, spent_date = ?, ' .
        "updated_at = NOW() WHERE id = ? AND status = 'checking'"
    );
    $stmt->bind_param('iisdsi', $last_count, $last_check, $count_usage,
        $spent_today, $spent_date, $id);
    $stmt->execute();
    $finished = $stmt->affected_rows === 1;
    $stmt->close();
    if (!$finished) {
        arf_fail('not_checking', 'This refill is not claimed by a worker run.', 409);
    }
    arf_ok(['finished' => true]);
}

function arf_stop($id) {
    arf_ensure_tables();
    $db = arf_db();
    $in = arf_input();
    $telegram_id = isset($in['telegram_id']) ? (int)$in['telegram_id'] : 0;
    if ($telegram_id <= 0) {
        arf_fail('bad_telegram_id', 'telegram_id is required.');
    }
    // Only the row's own user can stop it.
    $stmt = $db->prepare(
        "UPDATE bot_refills SET status = 'stopped', updated_at = NOW() " .
        "WHERE id = ? AND telegram_id = ? AND status IN ('active','checking')"
    );
    $stmt->bind_param('ii', $id, $telegram_id);
    $stmt->execute();
    $stopped = $stmt->affected_rows === 1;
    $stmt->close();
    if (!$stopped) {
        arf_fail('not_stoppable', 'This refill is already stopped or is not yours.', 409);
    }
    arf_ok(['stopped' => true]);
}

// --- DISPATCH LINES ---------------------------------------------------------
// Insert these into bot.php BEFORE the 404 fallback (and copy the
// bot_rate_limit(...) call the other user endpoints use from the
// orders handler — its signature was not visible from outside the
// server). The bot.php router dispatches on $bp from
// $_GET['bot_path']; these paths start with "refills", so they
// cannot collide with the loose two-segment orders handler.
//   if ($bp === 'refills/status' && $_SERVER['REQUEST_METHOD'] === 'GET') { arf_status(); }
//   if ($bp === 'refills' && $_SERVER['REQUEST_METHOD'] === 'POST') { arf_create(); }
//   if ($bp === 'refills' && $_SERVER['REQUEST_METHOD'] === 'GET') { arf_list(); }
//   if (preg_match('#^refills/(\d+)/(claim|finish|stop)$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') {
//       $arf_id = (int)$m[1];
//       if ($m[2] === 'claim') { arf_claim($arf_id); }
//       if ($m[2] === 'finish') { arf_finish($arf_id); }
//       if ($m[2] === 'stop') { arf_stop($arf_id); }
//   }
//
// LIVE CURL TEST (after install; X-Bot-Secret is the same secret the
// bot uses — read it from the server's own config, never paste it
// into chat):
//   curl -s https://paxyo.et/api/bot/refills/status -H "X-Bot-Secret: <secret>"
//     -> {"success":true,"ok":true,"refills_live":true}
//   Then create one test refill, list it, claim it, finish it, stop
//   it — and DELETE the test row from bot_refills afterwards.
