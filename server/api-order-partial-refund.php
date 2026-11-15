<?php
// ============================================================================
// Partial-order refund for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot feature 13, partial order
// handling — when the provider delivers less than ordered, the bot
// tells the user honestly what arrived vs what was ordered and
// refunds the undelivered part to their Paxyo balance automatically.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/orders/{id}/partial-refund   {telegram_id}
//     -> {"ok":true,"order_id":N,"delivered":700,"remains":300,
//         "refunded_etb":12.60,"provider_status":"partial",
//         "duplicate":false}
//     A second call for the same order_id returns the recorded result
//     with "duplicate":true and NEVER refunds a second time.
//
// FLOW (in order — money moves only at step 4, and only after the
// provider's own status says the order is partial):
//   1. A partial row already exists for this order_id -> return it.
//      (This is what makes a retry / duplicate call safe.)
//   2. Load the order. It must belong to telegram_id. The stored
//      status may be anything except completed / cancelled /
//      refunded / failed — the provider's status is the authority
//      on partial, not the local row. A completed order is NEVER
//      touched; an already cancelled / refunded / failed order gets
//      an honest 409 and no second refund.
//   3. Read the provider's status (action=status). Only a provider
//      status of "partial" proceeds. Anything else gets an honest
//      409 ("This order was not partial.") and refunds NOTHING. A
//      provider that cannot be reached gets a 502 and refunds
//      NOTHING; the bot may safely retry later.
//   4. The refund is the undelivered part, priced pro-rata from
//      the stored order: refund = remains x total / quantity,
//      rounded to 2dp. The figures (delivered, remains) are the
//      PROVIDER's own numbers from the status reply, never computed
//      locally. When the provider gives no remains count, the call
//      refuses with 409 — a refund must never be guessed.
//      In ONE database transaction: re-check the partial table (a
//      concurrent duplicate may have refunded already), credit the
//      refund to the user's Paxyo balance (auth.balance, keyed by
//      tg_id — the same credit the deposits endpoint does), and
//      insert the partial row. The order's own status is left
//      EXACTLY as it is ("partial") — this endpoint never marks an
//      order completed or cancelled; the delivery watch decides
//      what happens next. Any failure rolls everything back; the
//      balance is untouched.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_order_partials  id AUTO_INCREMENT PK, order_id BIGINT UNIQUE
//                      (the Paxyo orders.id — one partial refund per
//                      order, ever), telegram_id, service_id,
//                      delivered INT (what the provider delivered),
//                      remains INT (what it did not),
//                      refunded_etb DECIMAL(12,2),
//                      provider_status VARCHAR(64) (the provider's
//                      word, e.g. "Partial"), provider_order_id
//                      VARCHAR(64), created_at.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-order-partial-refund.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test partial row. The test refunds a REAL partial order on
//      purpose (that is the point), so use a small test order only,
//      with William's approval — never a real user's order.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use par_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch line (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - SMM BRANCH (15 Nov 2026, api-order-smm.php): after the order
//     row is loaded, an order with a bot_smm_orders row has its
//     status + remains read at SMM via smm_order_status() instead of
//     GodOfPanel. Refund math is unchanged (pro-rata on the stored
//     total and quantity; delivered falls back to quantity -
//     remains, as it does for GodOfPanel when delivered is missing).
//     Guarded by function_exists: when api-order-smm.php is not
//     installed yet, an SMM order falls through to the GodOfPanel
//     read and fails honestly. GodOfPanel behaviour is unchanged.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. orders table: id, telegram_id (owner), total (the ETB total
//       the customer paid), quantity, status, service_id, created_at,
//       plus a provider order id in api_order_id (then
//       provider_order_id, provider_id). The code reads the row with
//       SELECT * and picks the owner / total / quantity / provider-id
//       / service columns from a short candidate list (primary name
//       first) — confirm the real names with SHOW COLUMNS FROM orders
//       and trim the lists. quantity is REQUIRED here: without it
//       the pro-rata refund cannot be computed, and the call refuses
//       with 500 rather than guessing.
//   A2. PROVIDER STATUS REPLY: action=status returns the order's
//       status plus, for a partial order, "remains" (the undelivered
//       count) and usually "start_count" / "charge". This file reads
//       remains from the reply (candidates: remains, remain,
//       remaining, undelivered) and delivered from the reply when
//       present (candidates: delivered, start_count is NOT delivered
//       — it is the count before the order started; do not use it).
//       When the reply has remains but no delivered count, delivered
//       is quantity - remains. TO VERIFY: run the live test against
//       a genuinely partial order and confirm the reply carries
//       remains. If the provider's partial reply has NO remains
//       field, this endpoint will always 409 — that is by design
//       (never guess a refund), and the installer must then decide
//       the fallback (e.g. ask the provider, or use the order's own
//       progress read).
//   A3. PROVIDER HELPER: same assumption as the rescue/cancel files
//       — bot.php is assumed to define godofpanel_call(string
//       $action, array $params): ?array. If it does NOT exist, the
//       file falls back to a direct provider call (same curl style
//       as api-deposits.php). TO VERIFY: check bot.php and either
//       rename the helper in the one marked ADAPTER spot or confirm
//       the fallback's key lookup matches how bot.php authenticates
//       to the provider.
//   A4. PROVIDER KEY: the fallback looks for a defined constant
//       GODOPANEL_API_KEY, GOD_OF_PANEL_API_KEY, PROVIDER_API_KEY or
//       PANEL_API_KEY (in config_secret.php), then getenv
//       ('GODOFPANEL_API_KEY'). TO VERIFY: find the constant bot.php
//       actually uses for the provider key when placing orders and
//       keep only that one in par_provider_key(). No key value is
//       written anywhere in this file.
//   A5. PROVIDER API: parameters go in the URL query string (key +
//       action + order), NOT in the POST body.
//   A6. The refund is pro-rata on the STORED total and quantity:
//       remains x total / quantity. If the provider's per-unit price
//       changed since the order was placed, the stored total is
//       still the authority — the customer paid that total, and the
//       undelivered part of it is what comes back.
//   A7. auth table: tg_id + balance (same columns the deposits
//       endpoint credits — verified pattern, not an assumption).
// ============================================================================

// --- small helpers (par_ prefix so nothing collides with bot.php) -----------

function par_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function par_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function par_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function par_substr($text, $len) {
    if (function_exists('mb_substr')) return mb_substr($text, 0, $len, 'UTF-8');
    return substr($text, 0, $len);
}

function par_ensure_tables($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_order_partials (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        order_id BIGINT NOT NULL,
        telegram_id BIGINT NOT NULL,
        service_id INT NOT NULL,
        delivered INT NOT NULL,
        remains INT NOT NULL,
        refunded_etb DECIMAL(12,2) NOT NULL,
        provider_status VARCHAR(64) NOT NULL,
        provider_order_id VARCHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bot_order_partials_order (order_id),
        INDEX idx_bot_order_partials_tg (telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Pick the first candidate column that exists on the row and is not
// null/empty. Primary name first in each list.
function par_pick_order_field($row, $candidates) {
    foreach ($candidates as $col) {
        if (array_key_exists($col, $row) && $row[$col] !== null && $row[$col] !== '') {
            return $row[$col];
        }
    }
    return null;
}

function par_partial_row($db, $order_id) {
    $stmt = $db->prepare('SELECT order_id, telegram_id, service_id, delivered, remains, refunded_etb, provider_status, provider_order_id, created_at FROM bot_order_partials WHERE order_id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

function par_partial_reply($row) {
    return [
        'ok' => true,
        'order_id' => (int)$row['order_id'],
        'delivered' => (int)$row['delivered'],
        'remains' => (int)$row['remains'],
        'refunded_etb' => (float)$row['refunded_etb'],
        'provider_status' => $row['provider_status'],
    ];
}

// --- provider calls (ADAPTER — see A3/A4/A5; one spot to fix) ---------------

function par_provider_key() {
    foreach (['GODOPANEL_API_KEY', 'GOD_OF_PANEL_API_KEY', 'PROVIDER_API_KEY', 'PANEL_API_KEY'] as $name) {
        if (defined($name) && constant($name) !== '') return (string)constant($name);
    }
    $env = getenv('GODOFPANEL_API_KEY');
    if ($env !== false && $env !== '') return $env;
    return null;
}

function par_provider_base() {
    if (defined('GODOPANEL_API_URL') && GODOPANEL_API_URL !== '') return rtrim(GODOPANEL_API_URL, '/');
    $env = getenv('GODOFPANEL_API_URL');
    if ($env !== false && $env !== '') return rtrim($env, '/');
    return 'https://godofpanel.com/api/v2';
}

// One raw provider call. Params go in the URL query string (the
// provider rejects a POST body with "Invalid API key"). Returns the
// decoded JSON reply as an array, or null when the provider could
// not be reached / did not answer JSON.
function par_provider_raw($action, $params) {
    $key = par_provider_key();
    if ($key === null) return null;
    $query = array_merge(['key' => $key, 'action' => $action], $params);
    $url = par_provider_base() . '?' . http_build_query($query);
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => '',
        CURLOPT_TIMEOUT => 30,
    ]);
    $raw = curl_exec($ch);
    curl_close($ch);
    if (!is_string($raw) || $raw === '') return null;
    $res = json_decode($raw, true);
    return is_array($res) ? $res : null;
}

// Read the provider's full status reply for one provider order id.
// Returns ['status' => lowercased status string, 'remains' => int|null,
//          'delivered' => int|null] or null when the provider could
// not be reached. TO VERIFY (A2): the remains/delivered field names.
function par_provider_status_full($provider_order_id) {
    $res = null;
    // TO VERIFY (A3): if bot.php's helper exists, use it here too.
    if (function_exists('godofpanel_call')) {
        try {
            $res = godofpanel_call('status', ['order' => $provider_order_id]);
        } catch (Throwable $e) {
            $res = null;
        }
    }
    if ($res === null) {
        $res = par_provider_raw('status', ['order' => $provider_order_id]);
    }
    if ($res === null || !isset($res['status'])) return null;
    $remains = null;
    foreach (['remains', 'remain', 'remaining', 'undelivered'] as $key) {
        if (isset($res[$key]) && is_numeric($res[$key])) {
            $remains = (int)$res[$key];
            break;
        }
    }
    $delivered = null;
    foreach (['delivered', 'completed_count', 'done'] as $key) {
        if (isset($res[$key]) && is_numeric($res[$key])) {
            $delivered = (int)$res[$key];
            break;
        }
    }
    return [
        'status' => strtolower(trim((string)$res['status'])),
        'remains' => $remains,
        'delivered' => $delivered,
    ];
}

// SMM branch (api-order-smm.php): read an SMM order's status +
// remains at SMM, with the same return shape as
// par_provider_status_full() (delivered is always null for SMM —
// the status reply carries no delivered count, so the handler's
// quantity - remains fallback applies, exactly as for GodOfPanel
// when delivered is missing). When the SMM file is not installed
// yet, smm_order_status() does not exist and the call falls back
// to the GodOfPanel read, which fails honestly with the provider's
// error — never silently.
function par_provider_status_smm($provider_order_id) {
    if (!function_exists('smm_order_status')) return par_provider_status_full($provider_order_id);
    $live = smm_order_status($provider_order_id);
    if ($live === null) return null;
    if (!empty($live['error'])) return null;
    return [
        'status' => $live['status'] !== null ? $live['status'] : '',
        'remains' => $live['remains'],
        'delivered' => null,
    ];
}

// --- POST /api/bot/orders/{id}/partial-refund -------------------------------

function bot_par_partial_refund($order_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') par_fail(405, 'Method not allowed.');
    $in = par_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) par_fail(400, 'telegram_id is required.');
    if ($order_id <= 0) par_fail(400, 'order id is required.');

    $db = par_db();
    if ($db === null) par_fail(500, 'Database is not available.');
    par_ensure_tables($db);

    // 1. Already partially refunded? Return the recorded result —
    //    never a second refund. A different telegram_id asking for
    //    the same order gets the same 404 as a missing order.
    $existing = par_partial_row($db, $order_id);
    if ($existing !== null) {
        if ((int)$existing['telegram_id'] !== $telegram_id) par_fail(404, 'Order not found.');
        bot_ok(array_merge(par_partial_reply($existing), ['duplicate' => true]));
        return;
    }

    // 2. Load the order and check ownership. The stored status is
    //    NOT the authority on partial — the provider's is — but a
    //    finished order is never touched.
    $stmt = $db->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) par_fail(404, 'Order not found.');
    $owner = par_pick_order_field($row, ['telegram_id', 'user_id', 'tg_id']);
    if ($owner === null || (int)$owner !== $telegram_id) par_fail(404, 'Order not found.');

    $status = strtolower(trim((string)($row['status'] ?? '')));
    if (in_array($status, ['completed', 'complete', 'success', 'paid', 'cancelled', 'canceled', 'refunded', 'failed'], true)) {
        par_fail(409, 'Order is already ' . $status . ' and cannot be partially refunded.');
    }

    $service_id = (int)(par_pick_order_field($row, ['service_id', 'provider_service_id']) ?? 0);
    $total = par_pick_order_field($row, ['total', 'charge', 'amount']);
    if ($total === null || !is_numeric($total)) {
        par_fail(500, 'Order total is not on record, so no refund can be made.');
    }
    $quantity = par_pick_order_field($row, ['quantity', 'qty']);
    if ($quantity === null || !is_numeric($quantity) || (int)$quantity <= 0) {
        par_fail(500, 'Order quantity is not on record, so the undelivered part cannot be priced.');
    }
    $quantity = (int)$quantity;

    // The provider's own order number — without it there is nothing
    // to check at the provider, so refuse rather than refund blind.
    $provider_order_id = par_pick_order_field($row, ['api_order_id', 'provider_order_id', 'provider_id']);
    if ($provider_order_id === null) {
        par_fail(409, 'Order has no provider order id on record, so its delivery cannot be checked at the provider. No refund was made.');
    }
    $provider_order_id = (string)$provider_order_id;

    // SMM branch (api-order-smm.php): an SMM order's status +
    // remains are read at SMM, not GodOfPanel. Guarded by
    // function_exists — when the SMM file is not installed yet,
    // smm_is_smm_order() does not exist, $is_smm is false, and the
    // order falls through to the GodOfPanel read below, which fails
    // honestly with the provider's error. Refund math is unchanged.
    $is_smm = function_exists('smm_is_smm_order') && smm_is_smm_order($db, $order_id);

    // 3. The provider's status is the authority. Only "partial"
    //    proceeds; anything else is an honest 409, and an
    //    unreachable provider is a 502 (the bot may retry later).
    $provider = $is_smm
        ? par_provider_status_smm($provider_order_id)
        : par_provider_status_full($provider_order_id);
    if ($provider === null) {
        par_fail(502, 'Provider did not answer. No refund was made.');
    }
    if ($provider['status'] !== 'partial') {
        par_fail(409, 'This order was not partial (provider status: ' . $provider['status'] . '). No refund was made.');
    }
    if ($provider['remains'] === null || $provider['remains'] < 0) {
        par_fail(409, 'The provider did not report how much is undelivered, so no refund can be calculated. No refund was made.');
    }
    $remains = $provider['remains'];
    if ($remains === 0) {
        par_fail(409, 'This order was not partial — nothing is undelivered. No refund was made.');
    }
    if ($remains > $quantity) {
        // The provider claims more undelivered than was ordered:
        // cap at the ordered quantity rather than refunding more
        // than the customer paid. The recorded remains keeps the
        // provider's number; the refund is capped.
        $remains_for_refund = $quantity;
    } else {
        $remains_for_refund = $remains;
    }
    $delivered = $provider['delivered'];
    if ($delivered === null) {
        $delivered = $quantity - $remains;
        if ($delivered < 0) $delivered = 0;
    }
    $provider_status = par_substr($provider['status'], 64);

    // 4. Pro-rata refund, in ONE transaction: re-check the partial
    //    table under lock, credit the balance, record the partial.
    //    The order's own status is left as it is ("partial").
    $refund = round($remains_for_refund * ((float)$total / $quantity), 2);
    if ($refund <= 0) {
        par_fail(409, 'The undelivered part is worth nothing, so no refund can be made.');
    }

    $db->begin_transaction();
    $stmt = $db->prepare('SELECT order_id FROM bot_order_partials WHERE order_id = ? FOR UPDATE');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $locked = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if ($locked) {
        $db->rollback();
        $again = par_partial_row($db, $order_id);
        if ($again !== null && (int)$again['telegram_id'] === $telegram_id) {
            bot_ok(array_merge(par_partial_reply($again), ['duplicate' => true]));
            return;
        }
        par_fail(409, 'Order was already partially refunded.');
    }

    // Credit exactly once: the partial-row UNIQUE key + the check
    // above are what stop a duplicate credit, not this UPDATE.
    $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
    $stmt->bind_param('di', $refund, $telegram_id);
    $stmt->execute();
    $balance_changed = $stmt->affected_rows;
    $stmt->close();
    if ($balance_changed !== 1) {
        $db->rollback();
        par_fail(500, 'Could not credit the balance. No refund was made.');
    }

    // Insert the partial record. A duplicate key here (1062) means a
    // concurrent call won the race — roll back and return its row.
    $stmt = $db->prepare('INSERT INTO bot_order_partials (order_id, telegram_id, service_id, delivered, remains, refunded_etb, provider_status, provider_order_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    $stmt->bind_param('iiiidsss', $order_id, $telegram_id, $service_id, $delivered, $remains, $refund, $provider_status, $provider_order_id);
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
        $db->rollback();
        if ($duplicate) {
            $again = par_partial_row($db, $order_id);
            if ($again !== null && (int)$again['telegram_id'] === $telegram_id) {
                bot_ok(array_merge(par_partial_reply($again), ['duplicate' => true]));
                return;
            }
        }
        par_fail(500, 'Could not record the refund. No refund was made.');
    }

    $db->commit();
    bot_ok([
        'ok' => true,
        'order_id' => $order_id,
        'delivered' => $delivered,
        'remains' => $remains,
        'refunded_etb' => $refund,
        'provider_status' => $provider_status,
        'duplicate' => false,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^orders/(\d+)/partial-refund$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_par_partial_refund((int)$m[1]); }
//
// (Add the same bot_rate_limit(...) call the other user endpoints use
// to that dispatch line — copy the exact call from the orders
// handler; the signature was not visible from outside the server.)
//
// LIVE CURL TEST — read this whole block before running it. The test
// refunds a REAL partial order on purpose (that is the point), so it
// must use a genuinely partial test order (placed for this test,
// with William's approval, on the operating account) — NEVER a real
// user's order. First confirm the order IS partial at the provider:
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/orders/N?telegram_id=779060335" \
//     -H "X-Bot-Secret: $S"
//   -> expect the order with status "partial".
//   # Refund the undelivered part:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/partial-refund \
//     -H "X-Bot-Secret: $S" \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true,"order_id":N,"delivered":<n>,
//      "remains":<m>,"refunded_etb":<m x total / quantity>,
//      "provider_status":"partial","duplicate":false}
//   # Check the balance went up by exactly refunded_etb, and the
//   # order status is STILL "partial" (this endpoint never marks it
//   # completed or cancelled):
//   curl -s "https://paxyo.et/api/bot/balance?telegram_id=779060335" \
//     -H "X-Bot-Secret: $S"
//   # Call it AGAIN — the same order must NOT refund twice:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/partial-refund \
//     -H "X-Bot-Secret: $S" \
//     -d '{"telegram_id":779060335}'
//   -> expect the SAME refunded_etb with "duplicate":true, and the
//      balance from the step above UNCHANGED.
//   # A non-partial order must refuse with 409 (use a known
//   # completed order id — this call touches nothing):
//   curl -s -X POST https://paxyo.et/api/bot/orders/<completed-id>/partial-refund \
//     -H "X-Bot-Secret: $S" \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":false,"error":"This order was not partial ..."}.
//   Then DELETE the test partial row and confirm it is gone:
//   mysql -e "DELETE FROM bot_order_partials WHERE order_id=N AND telegram_id=779060335; SELECT COUNT(*) FROM bot_order_partials WHERE order_id=N;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
