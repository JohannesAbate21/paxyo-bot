<?php
// ============================================================================
// Rate-your-order for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot, ideas batch 2 —
// RATE YOUR ORDER. SERVER SIDE ONLY.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/orders/{id}/rate  {telegram_id, rating}
//     -> {"ok":true,"order_id":N,"rating":"good"}
//        rating is "good" or "bad" only. Only for COMPLETED orders
//        belonging to that telegram_id. Another user's order — or a
//        missing order — gets the SAME 404 "Order not found." (no
//        leaking whether the order exists). 409 if already rated:
//        the server enforces once, so the bot never asks twice.
//        A not-completed order gets 409 ("Order is not completed
//        yet") and is never rated.
//   GET  /api/bot/ratings/services?service_ids=1,2,3
//     -> {"ratings":{"1":{"good":12,"bad":2},"2":{"good":0,"bad":0}}}
//        Counts per service id. Unknown service ids return zero
//        counts, NEVER a 500 — the bot asks for whatever services
//        it is choosing between, and a service with no ratings yet
//        simply counts as 0/0. At most 100 ids per call.
//
// THE BOT READS THESE COUNTS to demote bad-rated services in
// future picks. The demotion itself is a BOT-side build (it lives
// in bot.py's service picking, not here): this server file only
// stores the ratings and exposes the counts. It never changes a
// price, a total, or which service is picked — the money steps
// stay deterministic.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_order_ratings  order_id BIGINT PRIMARY KEY (one rating per
//                      order, ever), telegram_id BIGINT,
//                      service_id INT NOT NULL DEFAULT 0 (the
//                      service on the order row; 0 only when the
//                      order row carries no service id), rating
//                      ENUM('good','bad'), created_at.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-order-ratings.php    (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test row. No money moves: rating never touches balances,
//      orders or the provider.
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient methods
// to add, mirroring save_session / load_session in bot.py):
//   rate_order(order_id, telegram_id, rating) — POST
//     /orders/{id}/rate. 404-tolerant (endpoint not live yet ->
//     None + warning, the bot just does not record the rating).
//     A 409 means "already rated" — the bot must not ask again.
//   service_ratings(service_ids) — GET
//     /ratings/services?service_ids=1,2,3. 404-tolerant (-> {}).
//     The bot reads the counts and demotes bad-rated services in
//     future picks (bot-side rule, separate build).
//   The bot asks for a rating ONCE, after a delivery message for a
//   completed order — and only when the server has no rating for
//   that order. (How the bot knows: it asks the server only after
//   delivery; a 409 on the POST means someone already rated it,
//   e.g. from another device, and the bot drops the ask silently.)
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. orders: id, telegram_id (owner — see A2), total, status,
//       service_id, created_at. Same columns the rescue endpoint
//       (api-order-rescue.php) assumes. The code reads the row
//       with SELECT * and picks the owner / service columns from a
//       short candidate list (primary name first), so a
//       differently-named column still works — but confirm the real
//       names with SHOW COLUMNS FROM orders and trim the lists.
//   A2. The owner column on orders: 'telegram_id' first, then
//       'user_id', then 'tg_id' (same candidate list as the rescue
//       file). GET /orders/{id} is scoped to the user, so an owner
//       column exists; confirm which name is live.
//   A3. status 'completed' is the finished state (the value the
//       orders endpoint and the mini app use — same assumption as
//       api-admin-stats.php). Other finished spellings
//       ('complete', 'success') are NOT accepted here: if the live
//       orders table writes a different word for a finished order,
//       add it to $rat_completed in bot_rat_rate().
//   A4. bot_ok() is used for success replies (it adds
//       "success":true, as on the other endpoints). Errors use
//       rat_fail() below, which returns
//       {"success":false,"error":...,"message":...} — the bot
//       reads both keys. Add the same bot_rate_limit(...) call the
//       other user endpoints use to the dispatch lines (copy the
//       exact call from the orders handler — the signature was not
//       visible from outside the server).
//   A5. No account-existence check here, unlike deposits: a rating
//       is only ever written for an order row that exists and
//       belongs to the caller, which is the check that matters.
//   A6. Ratings are NOT editable and NOT deletable through this
//       file — one rating per order, forever. If William wants a
//       user to change a rating, that needs a new endpoint (and a
//       decision), not a quiet edit.
// ============================================================================

// --- small helpers (rat_ prefix so nothing collides with bot.php) -----------

function rat_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function rat_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function rat_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function rat_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_order_ratings (
        order_id BIGINT NOT NULL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        service_id INT NOT NULL DEFAULT 0,
        rating ENUM('good','bad') NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_rat_service (service_id),
        INDEX idx_rat_tg (telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Pick the first candidate column that exists on the row and is not
// null/empty. TO VERIFY (A1/A2): confirm the real orders column
// names with SHOW COLUMNS FROM orders and trim these lists.
function rat_pick_order_field($row, $candidates) {
    foreach ($candidates as $col) {
        if (array_key_exists($col, $row) && $row[$col] !== null && $row[$col] !== '') {
            return $row[$col];
        }
    }
    return null;
}

// --- POST /api/bot/orders/{id}/rate -----------------------------------------
// Body: {"telegram_id":N,"rating":"good"|"bad"}.
// Only a COMPLETED order belonging to telegram_id can be rated,
// and only once (order_id is the PRIMARY KEY — a second rating for
// the same order is a 409, never an overwrite).

function bot_rat_rate($order_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') rat_fail(405, 'Method not allowed.');
    $in = rat_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) rat_fail(400, 'telegram_id is required.');
    if ($order_id <= 0) rat_fail(400, 'order id is required.');
    $rating = strtolower(trim((string)($in['rating'] ?? '')));
    if ($rating !== 'good' && $rating !== 'bad') rat_fail(400, 'rating must be "good" or "bad".');

    $db = rat_db();
    if ($db === null) rat_fail(500, 'Database is not available.');
    rat_ensure_table($db);

    // Load the order and check ownership FIRST — another user's order
    // (or a missing order) gets the same 404 "Order not found." (no
    // leaking whether the order exists), before any rating state is
    // revealed. Only then is the already-rated check done.
    $stmt = $db->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) rat_fail(404, 'Order not found.');
    $owner = rat_pick_order_field($row, ['telegram_id', 'user_id', 'tg_id']);
    if ($owner === null || (int)$owner !== $telegram_id) rat_fail(404, 'Order not found.');

    // Already rated? 409 — never ask twice, never overwrite. The
    // stored rating is returned so the bot can show what was already
    // recorded.
    $stmt = $db->prepare('SELECT order_id, rating FROM bot_order_ratings WHERE order_id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $existing = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if ($existing) {
        rat_fail(409, 'Order #' . $order_id . ' was already rated "' . $existing['rating'] . '".');
    }

    $status = strtolower(trim((string)($row['status'] ?? '')));
    // TO VERIFY (A3): add any other finished-state spelling here.
    $rat_completed = ['completed'];
    if (!in_array($status, $rat_completed, true)) {
        rat_fail(409, 'Order is not completed yet, so it cannot be rated.');
    }

    $service_id = (int)(rat_pick_order_field($row, ['service_id', 'provider_service_id']) ?? 0);

    $stmt = $db->prepare('INSERT INTO bot_order_ratings (order_id, telegram_id, service_id, rating) VALUES (?, ?, ?, ?)');
    $stmt->bind_param('iiis', $order_id, $telegram_id, $service_id, $rating);
    $inserted = false;
    $duplicate = false;
    try {
        $inserted = $stmt->execute();
        if (!$inserted) $duplicate = ((int)$db->errno === 1062);
    } catch (mysqli_sql_exception $e) {
        $duplicate = ((int)$e->getCode() === 1062);
    }
    $stmt->close();
    if (!$inserted) {
        // PHP 8.1+ mysqli throws on duplicate key (1062) instead of
        // returning false — a race between two rate taps for the same
        // order must answer 409, not an empty 500 (same lesson as
        // the delayed-orders file, found live 15 Nov 2026).
        if ($duplicate) rat_fail(409, 'Order #' . $order_id . ' was already rated.');
        rat_fail(500, 'Could not save the rating.');
    }
    bot_ok(['ok' => true, 'order_id' => $order_id, 'rating' => $rating]);
}

// --- GET /api/bot/ratings/services?service_ids=1,2,3 ------------------------
// Counts per service id: {"ratings":{"1":{"good":12,"bad":2},...}}.
// Unknown ids return {"good":0,"bad":0} — never a 500. At most 100
// ids; more than that is a 400 (the bot only ever asks for the
// handful of services it is choosing between).

function bot_rat_service_counts() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') rat_fail(405, 'Method not allowed.');
    $raw = trim((string)($_GET['service_ids'] ?? ''));
    if ($raw === '') rat_fail(400, 'service_ids is required, e.g. ?service_ids=1,2,3.');
    $ids = [];
    foreach (explode(',', $raw) as $part) {
        $part = trim($part);
        if ($part === '') continue;
        if (!preg_match('/^\d+$/', $part)) rat_fail(400, 'service_ids must be a comma-separated list of service ids.');
        $id = (int)$part;
        if ($id > 0) $ids[$id] = $id;
    }
    if (!$ids) rat_fail(400, 'service_ids is required, e.g. ?service_ids=1,2,3.');
    if (count($ids) > 100) rat_fail(400, 'At most 100 service ids per call.');

    $db = rat_db();
    if ($db === null) rat_fail(500, 'Database is not available.');
    rat_ensure_table($db);

    // Every requested id starts at 0/0 — an unknown service id
    // (or one with no ratings yet) stays 0/0 instead of erroring.
    $out = [];
    foreach ($ids as $id) $out[(string)$id] = ['good' => 0, 'bad' => 0];

    $placeholders = implode(',', array_fill(0, count($ids), '?'));
    $types = str_repeat('i', count($ids));
    $params = array_values($ids);
    try {
        $stmt = $db->prepare(
            "SELECT service_id, rating, COUNT(*) AS n FROM bot_order_ratings "
            . "WHERE service_id IN ($placeholders) GROUP BY service_id, rating"
        );
        $stmt->bind_param($types, ...$params);
        $stmt->execute();
        $res = $stmt->get_result();
        while ($r = $res->fetch_assoc()) {
            $sid = (string)$r['service_id'];
            if (!isset($out[$sid])) continue;
            if ($r['rating'] === 'good') $out[$sid]['good'] = (int)$r['n'];
            if ($r['rating'] === 'bad') $out[$sid]['bad'] = (int)$r['n'];
        }
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        // A counts read must never 500 the bot's service pick — on
        // any database error, answer the zero counts instead.
        $out = [];
        foreach ($ids as $id) $out[(string)$id] = ['good' => 0, 'bad' => 0];
    }
    bot_ok(['ratings' => $out]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^orders/(\d+)/rate$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_rat_rate((int)$m[1]); }
//   if ($bp === 'ratings/services' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_rat_service_counts(); }
//   (Add the same bot_rate_limit(...) call the other user endpoints
//    use to both dispatch lines — copy the exact call from the orders
//    handler; the signature was not visible from outside the server.
//    NOTE: the orders/{id}/rate pattern must be checked BEFORE the
//    generic orders/{id} handler in bot.php, or the rate call will
//    be swallowed by the order-status read.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-order-ratings.php`
// on the server (step 1 of the install) and `php -l api/bot.php`
// after splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account,
// and a KNOWN COMPLETED test order id C — e.g. an old completed test
// order. No money moves: rating never touches balances, orders or
// the provider):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. counts for a service with no ratings yet -> zeros, not 500:
//   curl -s "https://paxyo.et/api/bot/ratings/services?service_ids=1665,999999" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ratings":{"1665":{"good":0,"bad":0},
//      "999999":{"good":0,"bad":0}}}
//   # 2. rate completed order C "good":
//   curl -s -X POST https://paxyo.et/api/bot/orders/C/rate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"rating":"good"}'
//   -> expect {"success":true,"ok":true,"order_id":C,"rating":"good"}
//   # 3. counts now show it:
//   curl -s "https://paxyo.et/api/bot/ratings/services?service_ids=<service id of C>" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect that service id with "good":1,"bad":0.
//   # 4. rate the SAME order again -> 409, nothing changed:
//   curl -s -X POST https://paxyo.et/api/bot/orders/C/rate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"rating":"bad"}'
//   -> expect {"success":false,"error":"Order #C was already rated \"good\"."}.
//   # 5. wrong owner -> 404, same message as a missing order
//   #    (use a different completed order id, or C with telegram_id 1
//   #    — but C is already rated, so step 4's 409 would answer first;
//   #    use another completed order id C2 for this check):
//   curl -s -X POST https://paxyo.et/api/bot/orders/C2/rate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":1,"rating":"good"}'
//   -> expect {"success":false,"error":"Order not found."}
//   # 6. a PENDING order id P -> 409, never rated:
//   curl -s -X POST https://paxyo.et/api/bot/orders/P/rate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"rating":"good"}'
//   -> expect {"success":false,"error":"Order is not completed yet, ..."}.
//   # 7. bad rating value -> 400:
//   curl -s -X POST https://paxyo.et/api/bot/orders/C/rate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"rating":"meh"}'
//   -> expect {"success":false,"error":"rating must be \"good\" or \"bad\"."}.
//   # 8. more than 100 ids -> 400:
//   curl -s "https://paxyo.et/api/bot/ratings/services?service_ids=$(seq -s, 1 101)" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":false,"error":"At most 100 service ids per call."}.
//   Then DELETE the test row and confirm it is gone:
//   mysql -e "DELETE FROM bot_order_ratings WHERE order_id=C; SELECT COUNT(*) FROM bot_order_ratings WHERE order_id=C;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
