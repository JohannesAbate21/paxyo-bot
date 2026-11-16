<?php
// ===========================================================================
// Auto-pause a bad service (cancel-cutting, item 2) for the Paxyo Bot
// API (public_html/api/bot.php). Written 16 Nov 2026 for @paxorder_bot.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/service-pause   {provider, service_id, order_id?}
//     -> {"ok":true,"provider":"gop","service_id":123,
//         "cancel_count":2,"paused":false,"paused_until":null}
//        Records one provider-cancel of a service. At 3 cancels of
//        the same service within 24 hours the service is paused for
//        24 hours: {"ok":true,...,"cancel_count":3,"paused":true,
//        "paused_now":true,"paused_until":"2026-11-17 17:00:00"}.
//        `paused_now` is true ONLY on the call that starts the
//        pause — that is how the bot knows to alert William exactly
//        once per pause. A call while the service is already paused
//        returns {"paused":true,"paused_until":...} and counts
//        nothing. The same order_id twice counts once (the bot's
//        watch can see one cancelled order on two cycles).
//   GET  /api/bot/service-pauses?active=1
//     -> {"pauses":[{"provider":"gop","service_id":123,
//         "paused_until":"2026-11-17 17:00:00"}, ...]}
//        The pauses the bot must skip. Without ?active=1 it lists
//        every tracked service with its count and window, for
//        debugging — the bot only ever reads ?active=1.
//
// THE BOT records a cancel when its delivery watch sees a
// PROVIDER-cancelled order (never one the bot cancelled itself,
// never one the user asked to cancel — the bot marks those). The
// bot skips paused services in ALL picking until the pause
// expires; pauses expire on their own, there is no manual unpause
// here. The bot never pauses a service the user explicitly pinned:
// a pinned service that IS paused gets a plain "paused right now"
// line and the next best service instead of a silent switch.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_service_pauses  provider VARCHAR(16), service_id INT,
//      cancel_count INT (cancels inside the current 24h window),
//      window_started_at DATETIME (start of the current window),
//      paused_until DATETIME (NULL when not paused),
//      last_order_id BIGINT (the last order counted, so one order
//      never counts twice), updated_at TIMESTAMP,
//      PRIMARY KEY (provider, service_id).
//   One row per service. The 24h window restarts on the first
//   cancel after the old window (or after a pause) expired.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-service-pause.php    (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test rows. No money moves: pausing never touches balances,
//      orders or the provider.
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient methods
// to add, mirroring service_ratings in bot.py):
//   record_service_cancel(provider, service_id, order_id) — POST
//     /service-pause. 404-tolerant (endpoint not live yet ->
//     None + warning, the bot just does not pause anything).
//     Returns the row above; `paused_now` true means "alert
//     William once, this pause just started".
//   service_pauses() — GET /service-pauses?active=1. 404-tolerant
//     (-> {}). Returns the active pauses; the bot caches them for
//     5 minutes and skips those services in every pick.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. `provider` is the bot's slug: "gop" or "smm" only. Any
//       other value is a 400 — the bot never sends one.
//   A2. Add the same bot_rate_limit(...) call the other user
//       endpoints use to both dispatch lines (copy the exact call
//       from the orders handler — the signature was not visible
//       from outside the server).
//   A3. Pauses are per (provider, service_id): the bare ids
//       collide between providers, so a GOP pause never pauses an
//       SMM service of the same number.
// ===========================================================================

// --- small helpers (pau_ prefix so nothing collides with bot.php) -----------

function pau_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function pau_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function pau_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function pau_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_service_pauses (
        provider VARCHAR(16) NOT NULL,
        service_id INT NOT NULL,
        cancel_count INT NOT NULL DEFAULT 0,
        window_started_at DATETIME NULL,
        paused_until DATETIME NULL,
        last_order_id BIGINT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (provider, service_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// One row of bot_service_pauses as the bot reads it.
function pau_row_reply($row) {
    return [
        'ok' => true,
        'provider' => (string)$row['provider'],
        'service_id' => (int)$row['service_id'],
        'cancel_count' => (int)$row['cancel_count'],
        'paused' => $row['paused_until'] !== null
            && strtotime((string)$row['paused_until']) > time(),
        'paused_until' => $row['paused_until'] !== null
            ? (string)$row['paused_until'] : null,
    ];
}

// --- POST /api/bot/service-pause --------------------------------------------
// Body: {"provider":"gop"|"smm","service_id":123,"order_id":456?}.
// Records one provider-cancel. At 3 cancels in 24h the service is
// paused for 24h; `paused_now` is true only on the call that starts
// the pause, so the bot alerts William exactly once per pause.

function bot_pau_record_cancel() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') pau_fail(405, 'Method not allowed.');
    $in = pau_json_body();
    $provider = strtolower(trim((string)($in['provider'] ?? '')));
    if ($provider !== 'gop' && $provider !== 'smm') {
        pau_fail(400, 'provider must be "gop" or "smm".');
    }
    $service_id = (int)($in['service_id'] ?? 0);
    if ($service_id <= 0) pau_fail(400, 'service_id is required.');
    $order_id = (int)($in['order_id'] ?? 0);
    if ($order_id <= 0) $order_id = null;

    $db = pau_db();
    if ($db === null) pau_fail(500, 'Database is not available.');
    pau_ensure_table($db);

    // The row must exist before it can be locked: INSERT ... ON
    // DUPLICATE KEY UPDATE is a no-op for an existing row.
    $stmt = $db->prepare('INSERT INTO bot_service_pauses (provider, service_id, cancel_count) VALUES (?, ?, 0) ON DUPLICATE KEY UPDATE provider = provider');
    $stmt->bind_param('si', $provider, $service_id);
    $stmt->execute();
    $stmt->close();

    $db->begin_transaction();
    $stmt = $db->prepare('SELECT provider, service_id, cancel_count, window_started_at, paused_until, last_order_id FROM bot_service_pauses WHERE provider = ? AND service_id = ? FOR UPDATE');
    $stmt->bind_param('si', $provider, $service_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) {
        $db->rollback();
        pau_fail(500, 'Could not load the pause row.');
    }

    $now = time();
    $paused_until = $row['paused_until'] !== null
        ? strtotime((string)$row['paused_until']) : null;
    // Already paused: count nothing, report the pause as-is.
    if ($paused_until !== null && $paused_until > $now) {
        $db->commit();
        bot_ok(pau_row_reply($row));
        return;
    }
    // The same order twice counts once: the watch can see one
    // cancelled order on two cycles (a failed rescue keeps it
    // watched), and a retry must not manufacture a pause.
    if ($order_id !== null && (int)($row['last_order_id'] ?? 0) === $order_id) {
        $db->commit();
        bot_ok(pau_row_reply($row));
        return;
    }
    $window_started = $row['window_started_at'] !== null
        ? strtotime((string)$row['window_started_at']) : null;
    $count = (int)$row['cancel_count'];
    // A fresh window: no window yet, the old one is over 24h old,
    // or a pause just expired.
    if (
        $window_started === null
        || ($now - $window_started) >= 24 * 3600
        || $paused_until !== null
    ) {
        $count = 1;
        $window_started = $now;
    } else {
        $count++;
    }
    $paused_now = false;
    $new_paused_until = null;
    if ($count >= 3) {
        $paused_now = true;
        $new_paused_until = date('Y-m-d H:i:s', $now + 24 * 3600);
    }
    $stmt = $db->prepare('UPDATE bot_service_pauses SET cancel_count = ?, window_started_at = ?, paused_until = ?, last_order_id = ? WHERE provider = ? AND service_id = ?');
    $window_sql = date('Y-m-d H:i:s', $window_started);
    $stmt->bind_param(
        'issisi', $count, $window_sql, $new_paused_until, $order_id,
        $provider, $service_id
    );
    $stmt->execute();
    $stmt->close();
    $db->commit();

    $reply = pau_row_reply([
        'provider' => $provider,
        'service_id' => $service_id,
        'cancel_count' => $count,
        'paused_until' => $new_paused_until,
    ]);
    $reply['paused_now'] = $paused_now;
    bot_ok($reply);
}

// --- GET /api/bot/service-pauses --------------------------------------------
// ?active=1 lists only pauses still in force (what the bot reads);
// without it, every tracked service with its count and window.

function bot_pau_list() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') pau_fail(405, 'Method not allowed.');
    $db = pau_db();
    if ($db === null) pau_fail(500, 'Database is not available.');
    pau_ensure_table($db);

    $active_only = (($_GET['active'] ?? '') === '1');
    $sql = 'SELECT provider, service_id, cancel_count, window_started_at, paused_until FROM bot_service_pauses';
    if ($active_only) {
        $sql .= ' WHERE paused_until IS NOT NULL AND paused_until > NOW()';
    }
    $sql .= ' ORDER BY provider, service_id';
    try {
        $res = $db->query($sql);
    } catch (mysqli_sql_exception $e) {
        pau_fail(500, 'Could not read pauses.');
    }
    if ($res === false) pau_fail(500, 'Could not read pauses.');
    $pauses = [];
    while ($row = $res->fetch_assoc()) {
        $pauses[] = [
            'provider' => (string)$row['provider'],
            'service_id' => (int)$row['service_id'],
            'cancel_count' => (int)$row['cancel_count'],
            'window_started_at' => $row['window_started_at'] !== null
                ? (string)$row['window_started_at'] : null,
            'paused_until' => $row['paused_until'] !== null
                ? (string)$row['paused_until'] : null,
        ];
    }
    $res->close();
    bot_ok(['pauses' => $pauses]);
}

// ===========================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'service-pause' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_pau_record_cancel(); }
//   if ($bp === 'service-pauses' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_pau_list(); }
//   (Add the same bot_rate_limit(...) call the other user endpoints
//    use to both dispatch lines — copy the exact call from the orders
//    handler; the signature was not visible from outside the server.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-service-pause.php`
// on the server (step 1 of the install) and `php -l api/bot.php`
// after splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (no money moves; then DELETE the test rows):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. list active pauses (empty at first):
//   curl -s "https://paxyo.et/api/bot/service-pauses?active=1" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"pauses":[]}
//   # 2. record 3 cancels of a TEST service id (use a service with
//   #    no real orders, e.g. 999001, provider gop, order ids 1,2,3):
//   for i in 1 2 3; do curl -s -X POST https://paxyo.et/api/bot/service-pause \
//     -H "X-Bot-Secret: $SECRET" \
//     -d "{\"provider\":\"gop\",\"service_id\":999001,\"order_id\":$i}"; echo; done
//   -> expect cancel_count 1, 2, then 3 with "paused":true and
//      "paused_now":true only on the third call, paused_until ~24h out.
//   # 3. the same order again counts nothing:
//   curl -s -X POST https://paxyo.et/api/bot/service-pause \
//     -H "X-Bot-Secret: $SECRET" \
//     -d '{"provider":"gop","service_id":999001,"order_id":3}'
//   -> expect cancel_count still 3, "paused":true, no "paused_now".
//   # 4. list shows it:
//   curl -s "https://paxyo.et/api/bot/service-pauses?active=1" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect one pause, provider gop, service_id 999001.
//   # 5. a bad provider is a 400:
//   curl -s -X POST https://paxyo.et/api/bot/service-pause \
//     -H "X-Bot-Secret: $SECRET" \
//     -d '{"provider":"other","service_id":1}'
//   -> expect {"success":false,"error":"provider must be \"gop\" or \"smm\"."}.
//   Then DELETE the test row:
//   mysql -e "DELETE FROM bot_service_pauses WHERE service_id=999001;"
// ===========================================================================
