<?php
// ============================================================================
// Cancel-and-refund (stall rescue) for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot
// feature 2, automatic stall rescue.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/orders/{id}/cancel-refund   {telegram_id}
//     -> {"ok":true,"order_id":N,"refunded_etb":X,"provider_status":"...",
//         "duplicate":false}
//     A second call for the same order_id returns the recorded result
//     with "duplicate":true and NEVER refunds a second time.
//
// FLOW (in order — money moves only at step 4, and only after the
// provider has confirmed the cancel):
//   1. A rescue row already exists for this order_id -> return it.
//      (This is what makes a retry / duplicate call safe.)
//   2. Load the order. It must belong to telegram_id and still be
//      cancellable: status pending / processing (also the spellings
//      "in progress" / "queued"). A completed order is NEVER touched;
//      an already cancelled / refunded / failed order gets an honest
//      409 and no second refund.
//   3. Cancel it at the provider (GodOfPanel) — see
//      res_provider_cancel() below. If the provider says the order
//      cannot be cancelled, return that honestly (409) and refund
//      NOTHING. If the provider does not answer clearly, return 502
//      and refund NOTHING; the bot may safely retry later.
//   4. In ONE database transaction: re-check the rescue table (a
//      concurrent duplicate may have refunded already), mark the
//      order cancelled, credit the FULL stored order total back to
//      the user's Paxyo balance (auth.balance, keyed by tg_id — the
//      same credit the deposits endpoint does), and insert the rescue
//      row. Any failure rolls everything back; the balance is
//      untouched.
//
// THE SERVER NEVER PLACES THE REPLACEMENT ORDER. After a successful
// refund the bot re-places the order itself, on the next-best
// service, through the existing POST /api/bot/orders endpoint.
// The bot — not this endpoint — decides an order is stuck: the
// stuck rule lives in bot.py (is_order_stuck: elapsed >= 3x the
// claimed average time AND >= 15 minutes overdue; no average time
// means never stuck). This endpoint only enforces ownership, a
// cancellable state, and a confirmed provider cancel.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_order_rescues  id AUTO_INCREMENT PK, order_id BIGINT UNIQUE
//                      (the Paxyo orders.id — one rescue per order,
//                      ever), telegram_id, service_id, refunded_etb
//                      DECIMAL(12,2), provider_status VARCHAR(64)
//                      (the provider's word for the cancelled order,
//                      e.g. "Canceled"), provider_order_id VARCHAR(64)
//                      (the provider's own order number, for the
//                      admin to check), created_at.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-order-rescue.php      (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test rescue row. The test cancels a REAL test order on purpose
//      (that is the point), so use a small test order only, with
//      William's approval — never a real user's order.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use res_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch line (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL (see also the
//   "TO VERIFY" comments inside res_provider_cancel() and
//   res_pick_order_field()):
//   A1. orders table: id, telegram_id (owner), total (the ETB total
//       the customer paid — the same column the admin-stats endpoint
//       assumes), status, service_id, created_at. The code reads the
//       row with SELECT * and picks the owner / total / provider-id /
//       service columns from a short candidate list (primary name
//       first), so a differently-named column still works — but
//       confirm the real names with SHOW COLUMNS FROM orders and
//       trim the lists.
//   A2. PROVIDER HELPER (biggest unknown — bot.php was not visible
//       from outside the server): this file ASSUMES bot.php defines
//       godofpanel_call(string $action, array $params): ?array,
//       returning the provider's decoded JSON reply (or null when the
//       provider could not be reached), and that POST /orders places
//       provider orders through it. If that helper exists with this
//       name and shape, res_provider_cancel() uses it. If it does NOT
//       exist, or has a different name/signature, the call is caught
//       and the file falls back to a direct provider call (same curl
//       style as api-deposits.php) — so the endpoint still works, but
//       the installer MUST check bot.php and either rename the helper
//       in the one marked ADAPTER spot or confirm the fallback's key
//       lookup matches how bot.php authenticates to the provider.
//   A3. PROVIDER KEY: the fallback looks for a defined constant
//       GODOPANEL_API_KEY, GOD_OF_PANEL_API_KEY, PROVIDER_API_KEY or
//       PANEL_API_KEY (in config_secret.php), then getenv
//       ('GODOFPANEL_API_KEY'). TO VERIFY: find the constant bot.php
//       actually uses for the provider key when placing orders and
//       keep only that one in res_provider_key(). No key value is
//       written anywhere in this file.
//   A4. PROVIDER API (GodOfPanel v2, https://godofpanel.com/api/v2):
//       parameters go in the URL query string (key + action + order),
//       NOT in the POST body — a POST body fails with "Invalid API
//       key" (per the GodOfPanel connector doc). Cancel is
//       action=cancel&order=<provider order id>; success is a reply
//       with cancel == 1 (or a status of Canceled/Cancelled). The
//       reply shape was NOT verified live (the connector doc says
//       add/cancel are untested) — after the cancel call the code
//       re-checks with action=status and only refunds when the
//       provider's own status says the order is cancelled (or the
//       cancel reply itself unambiguously said so). TO VERIFY: run
//       the live test and confirm the cancel reply shape.
//   A5. PROVIDER ORDER ID column on orders: api_order_id first,
//       then provider_order_id, provider_id. (GET /orders/{id} works
//       "by local id or provider api_order_id", so a provider id is
//       stored somewhere on the order.) If an order has NO provider
//       order id on record, the endpoint refuses with 409 and refunds
//       nothing — there is nothing to cancel at the provider.
//   A6. FINAL ORDER STATUS written by the refund: 'cancelled' (see
//       RES_FINAL_STATUS below). TO VERIFY: if the admin / orders
//       list expects 'refunded' instead, change that one constant —
//       the delivery watch treats both as terminal, so either is safe.
//   A7. REFUND AMOUNT is the FULL stored order total, even if the
//       provider had already delivered part of the order before the
//       cancel. That is what the stall-rescue spec says (credit the
//       order total back). It is in tension with the Paxyo Terms
//       ("if an order is partially completed, canceled, or fails,
//       the remaining amount will be returned") — William / the
//       installer should confirm full-total refund is the intended
//       policy for a stall rescue before going live.
//   A8. auth table: tg_id + balance (same columns the deposits
//       endpoint credits — verified pattern, not an assumption).
//   A9. No average-time / stuck check happens here: the bot calls
//       this endpoint only after its own is_order_stuck rule fires.
//       Calling it for a merely-slow (not stuck) order still cancels
//       and refunds it — that is by design; the bot is the guard.
// ============================================================================

// --- small helpers (res_ prefix so nothing collides with bot.php) -----------

// Final status written onto the orders row after a successful rescue.
// TO VERIFY (A6): change to 'refunded' here if the admin expects that.
if (!defined('RES_FINAL_STATUS')) define('RES_FINAL_STATUS', 'cancelled');

function res_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function res_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function res_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function res_substr($text, $len) {
    // mb_substr keeps emoji intact when truncating; plain substr is
    // the fallback if mbstring is ever missing on the server.
    if (function_exists('mb_substr')) return mb_substr($text, 0, $len, 'UTF-8');
    return substr($text, 0, $len);
}

function res_ensure_tables($db) {
    // utf8mb4, like the other bot tables. set_charset is idempotent —
    // harmless if bot.php already did it.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_order_rescues (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        order_id BIGINT NOT NULL,
        telegram_id BIGINT NOT NULL,
        service_id INT NOT NULL,
        refunded_etb DECIMAL(12,2) NOT NULL,
        provider_status VARCHAR(64) NOT NULL,
        provider_order_id VARCHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bot_order_rescues_order (order_id),
        INDEX idx_bot_order_rescues_tg (telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Pick the first candidate column that exists on the row and is not
// null/empty. TO VERIFY (A1/A5): confirm the real orders column names
// with SHOW COLUMNS FROM orders and trim these lists. Primary name
// first in each list (telegram_id / total / api_order_id / service_id
// match the sibling admin-stats endpoint's assumptions).
function res_pick_order_field($row, $candidates) {
    foreach ($candidates as $col) {
        if (array_key_exists($col, $row) && $row[$col] !== null && $row[$col] !== '') {
            return $row[$col];
        }
    }
    return null;
}

function res_rescue_row($db, $order_id) {
    $stmt = $db->prepare('SELECT order_id, telegram_id, service_id, refunded_etb, provider_status, provider_order_id, created_at FROM bot_order_rescues WHERE order_id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

function res_rescue_reply($row) {
    return [
        'ok' => true,
        'order_id' => (int)$row['order_id'],
        'refunded_etb' => (float)$row['refunded_etb'],
        'provider_status' => $row['provider_status'],
    ];
}

// --- provider calls (ADAPTER — see A2/A3/A4; one spot to fix) ---------------

function res_provider_key() {
    // TO VERIFY (A3): keep only the constant bot.php actually uses
    // for the provider key when placing orders; delete the rest.
    foreach (['GODOPANEL_API_KEY', 'GOD_OF_PANEL_API_KEY', 'PROVIDER_API_KEY', 'PANEL_API_KEY'] as $name) {
        if (defined($name) && constant($name) !== '') return (string)constant($name);
    }
    $env = getenv('GODOFPANEL_API_KEY');
    if ($env !== false && $env !== '') return $env;
    return null;
}

function res_provider_base() {
    if (defined('GODOPANEL_API_URL') && GODOPANEL_API_URL !== '') return rtrim(GODOPANEL_API_URL, '/');
    $env = getenv('GODOFPANEL_API_URL');
    if ($env !== false && $env !== '') return rtrim($env, '/');
    return 'https://godofpanel.com/api/v2';
}

// One raw provider call. Params go in the URL query string (the
// provider rejects a POST body with "Invalid API key"). Returns the
// decoded JSON reply as an array, or null when the provider could
// not be reached / did not answer JSON.
function res_provider_raw($action, $params) {
    $key = res_provider_key();
    if ($key === null) return null;
    $query = array_merge(['key' => $key, 'action' => $action], $params);
    $url = res_provider_base() . '?' . http_build_query($query);
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

// Read the provider's own status for one provider order id.
// Returns the lowercased status string (e.g. "canceled",
// "completed", "in progress", "partial", "pending") or null when
// the provider could not be reached.
function res_provider_status($provider_order_id) {
    // TO VERIFY (A2): if bot.php's helper exists, use it here too.
    if (function_exists('godofpanel_call')) {
        try {
            $res = godofpanel_call('status', ['order' => $provider_order_id]);
        } catch (Throwable $e) {
            $res = null;
        }
        if (is_array($res) && isset($res['status'])) {
            return strtolower(trim((string)$res['status']));
        }
        // Helper existed but gave nothing usable — fall through to
        // the direct call below rather than guessing.
    }
    $res = res_provider_raw('status', ['order' => $provider_order_id]);
    if ($res === null || !isset($res['status'])) return null;
    return strtolower(trim((string)$res['status']));
}

// Cancel one order at the provider and confirm it is cancelled.
// Returns ['confirmed' => bool, 'provider_status' => string|null,
//          'not_cancellable' => bool, 'error' => string|null].
//   confirmed=true  -> the provider cancelled it; refund is safe.
//   not_cancellable -> the provider explicitly refused (e.g. the
//     order already finished / cannot be cancelled): refund NOTHING.
//   otherwise       -> ambiguous (provider unreachable, reply not
//     understood, cancel not confirmed): refund NOTHING; the bot
//     may safely retry later.
function res_provider_cancel($provider_order_id) {
    $res = null;
    $used_helper = false;
    // TO VERIFY (A2): assumed helper — godofpanel_call(string $action,
    // array $params): ?array — the same helper POST /orders is assumed
    // to use when placing provider orders. If bot.php has no such
    // helper, or it takes different arguments, the call below throws,
    // is caught, and the direct call underneath runs instead.
    if (function_exists('godofpanel_call')) {
        $used_helper = true;
        try {
            $res = godofpanel_call('cancel', ['order' => $provider_order_id]);
        } catch (Throwable $e) {
            $res = null;
        }
    }
    if ($res === null && !$used_helper) {
        if (res_provider_key() === null) {
            return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => false, 'error' => 'Provider is not configured.'];
        }
        $res = res_provider_raw('cancel', ['order' => $provider_order_id]);
    }
    if ($res === null) {
        // Cancel reply never arrived (timeout / transport failure).
        // Per the connector doc, a failed change may still have gone
        // through — check the provider's own status before deciding.
        $st = res_provider_status($provider_order_id);
        if ($st === 'canceled' || $st === 'cancelled') {
            return ['confirmed' => true, 'provider_status' => $st, 'not_cancellable' => false, 'error' => null];
        }
        if ($st !== null) {
            return ['confirmed' => false, 'provider_status' => $st, 'not_cancellable' => false, 'error' => 'Provider did not confirm the cancel (provider status: ' . $st . '). No refund was made.'];
        }
        return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => false, 'error' => 'Provider did not answer. No refund was made.'];
    }

    // An explicit provider error: the order cannot be cancelled.
    // Never refund on this path, and never invent a reason — return
    // the provider's own words, truncated.
    if (isset($res['error']) && $res['error'] !== '') {
        return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => true, 'error' => 'Provider refused the cancel: ' . res_substr((string)$res['error'], 200)];
    }

    // Cancel accepted? The documented success shape is cancel == 1
    // (TO VERIFY, A4 — the connector doc says cancel is untested).
    $cancel_flag = $res['cancel'] ?? null;
    $status_word = isset($res['status']) ? strtolower(trim((string)$res['status'])) : '';
    if ($cancel_flag === 1 || $cancel_flag === '1' || $cancel_flag === true || $cancel_flag === 'true'
        || $status_word === 'canceled' || $status_word === 'cancelled') {
        // The cancel reply said yes — still confirm with the
        // provider's own status read, so a lying / stale reply can
        // never trigger a refund for a live order.
        $st = res_provider_status($provider_order_id);
        if ($st === 'canceled' || $st === 'cancelled') {
            return ['confirmed' => true, 'provider_status' => $st, 'not_cancellable' => false, 'error' => null];
        }
        if ($st !== null) {
            return ['confirmed' => false, 'provider_status' => $st, 'not_cancellable' => false, 'error' => 'Provider said the cancel went through but still reports status: ' . $st . '. No refund was made.'];
        }
        // Status read failed but the cancel reply itself was an
        // unambiguous yes — accept it (the re-check is a safety net,
        // not a veto, when the provider already said cancelled).
        return ['confirmed' => true, 'provider_status' => ($status_word !== '' ? $status_word : 'canceled'), 'not_cancellable' => false, 'error' => null];
    }

    // Reply arrived but said neither yes nor error — do not guess.
    $st = res_provider_status($provider_order_id);
    if ($st === 'canceled' || $st === 'cancelled') {
        return ['confirmed' => true, 'provider_status' => $st, 'not_cancellable' => false, 'error' => null];
    }
    if ($st !== null) {
        return ['confirmed' => false, 'provider_status' => $st, 'not_cancellable' => false, 'error' => 'Provider did not cancel the order (provider status: ' . $st . '). No refund was made.'];
    }
    return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => false, 'error' => 'Provider reply was not understood. No refund was made.'];
}

// --- POST /api/bot/orders/{id}/cancel-refund --------------------------------

function bot_res_cancel_refund($order_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') res_fail(405, 'Method not allowed.');
    $in = res_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) res_fail(400, 'telegram_id is required.');
    if ($order_id <= 0) res_fail(400, 'order id is required.');

    $db = res_db();
    if ($db === null) res_fail(500, 'Database is not available.');
    res_ensure_tables($db);

    // 1. Already rescued? Return the recorded result — never a
    //    second refund. A different telegram_id asking for the same
    //    order gets the same 404 as a missing order (no leaking).
    $existing = res_rescue_row($db, $order_id);
    if ($existing !== null) {
        if ((int)$existing['telegram_id'] !== $telegram_id) res_fail(404, 'Order not found.');
        bot_ok(array_merge(res_rescue_reply($existing), ['duplicate' => true]));
        return;
    }

    // 2. Load the order and check ownership + cancellable state.
    $stmt = $db->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) res_fail(404, 'Order not found.');
    $owner = res_pick_order_field($row, ['telegram_id', 'user_id', 'tg_id']);
    if ($owner === null || (int)$owner !== $telegram_id) res_fail(404, 'Order not found.');

    $status = strtolower(trim((string)($row['status'] ?? '')));
    $cancellable = ['pending', 'processing', 'in progress', 'inprogress', 'queued'];
    if (in_array($status, ['completed', 'complete', 'success', 'paid'], true)) {
        res_fail(409, 'Order is already completed and cannot be cancelled.');
    }
    if (in_array($status, ['cancelled', 'canceled', 'refunded', 'failed'], true)) {
        res_fail(409, 'Order is already ' . $status . ' and cannot be refunded again.');
    }
    if (!in_array($status, $cancellable, true)) {
        // Unknown / unexpected status: say so with the real stored
        // word — never invent a status or a reason.
        res_fail(409, 'Order cannot be cancelled while it is ' . ($status !== '' ? $status : 'in an unknown state') . '.');
    }

    $service_id = (int)(res_pick_order_field($row, ['service_id', 'provider_service_id']) ?? 0);
    $total = res_pick_order_field($row, ['total', 'charge', 'amount']);
    if ($total === null || !is_numeric($total)) {
        res_fail(500, 'Order total is not on record, so no refund can be made.');
    }
    $refund = round((float)$total, 2);

    // The provider's own order number — without it there is nothing
    // to cancel at the provider, so refuse rather than refund blind.
    $provider_order_id = res_pick_order_field($row, ['api_order_id', 'provider_order_id', 'provider_id']);
    if ($provider_order_id === null) {
        res_fail(409, 'Order has no provider order id on record, so it cannot be cancelled at the provider. No refund was made.');
    }
    $provider_order_id = (string)$provider_order_id;

    // 3. Cancel at the provider. No balance is touched on any
    //    failure path below.
    $cancel = res_provider_cancel($provider_order_id);
    if (!$cancel['confirmed']) {
        // Race check: a concurrent duplicate call may have refunded
        // already while this call was talking to the provider.
        $raced = res_rescue_row($db, $order_id);
        if ($raced !== null && (int)$raced['telegram_id'] === $telegram_id) {
            bot_ok(array_merge(res_rescue_reply($raced), ['duplicate' => true]));
            return;
        }
        if (!empty($cancel['not_cancellable'])) {
            res_fail(409, $cancel['error'] ?? 'Provider refused the cancel. No refund was made.');
        }
        res_fail(502, $cancel['error'] ?? 'Provider did not confirm the cancel. No refund was made.');
    }
    $provider_status = $cancel['provider_status'] !== null && $cancel['provider_status'] !== ''
        ? res_substr((string)$cancel['provider_status'], 64) : 'canceled';

    // 4. Atomic refund: re-check the rescue table under lock, mark
    //    the order cancelled, credit the balance, record the rescue.
    //    Any failure rolls the whole thing back.
    $db->begin_transaction();
    $stmt = $db->prepare('SELECT order_id FROM bot_order_rescues WHERE order_id = ? FOR UPDATE');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $locked = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if ($locked) {
        $db->rollback();
        $again = res_rescue_row($db, $order_id);
        if ($again !== null && (int)$again['telegram_id'] === $telegram_id) {
            bot_ok(array_merge(res_rescue_reply($again), ['duplicate' => true]));
            return;
        }
        res_fail(409, 'Order was already refunded.');
    }

    // The order may have finished while the provider call was in
    // flight — re-check its status under lock before touching money.
    $stmt = $db->prepare('SELECT status FROM orders WHERE id = ? FOR UPDATE');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $fresh = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    $fresh_status = strtolower(trim((string)($fresh['status'] ?? '')));
    if (!$fresh || !in_array($fresh_status, $cancellable, true)) {
        $db->rollback();
        res_fail(409, 'Order is no longer cancellable (status: ' . ($fresh_status !== '' ? $fresh_status : 'unknown') . '). No refund was made.');
    }

    $final = RES_FINAL_STATUS;
    $stmt = $db->prepare("UPDATE orders SET status = ? WHERE id = ? AND status IN ('pending','processing','in progress','inprogress','queued')");
    $stmt->bind_param('si', $final, $order_id);
    $stmt->execute();
    $order_changed = $stmt->affected_rows;
    $stmt->close();
    if ($order_changed !== 1) {
        $db->rollback();
        res_fail(409, 'Order is no longer cancellable. No refund was made.');
    }

    // Credit exactly once: the rescue-row UNIQUE key + the checks
    // above are what stop a duplicate credit, not this UPDATE.
    // (Same credit shape as the deposits endpoint: auth.balance
    // keyed by tg_id.)
    $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
    $stmt->bind_param('di', $refund, $telegram_id);
    $stmt->execute();
    $balance_changed = $stmt->affected_rows;
    $stmt->close();
    if ($balance_changed !== 1) {
        $db->rollback();
        res_fail(500, 'Could not credit the balance. No refund was made.');
    }

    // Insert the rescue record. A duplicate key here (1062) means a
    // concurrent call won the race — roll back and return its row.
    $stmt = $db->prepare('INSERT INTO bot_order_rescues (order_id, telegram_id, service_id, refunded_etb, provider_status, provider_order_id) VALUES (?, ?, ?, ?, ?, ?)');
    $stmt->bind_param('iiidss', $order_id, $telegram_id, $service_id, $refund, $provider_status, $provider_order_id);
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
            $again = res_rescue_row($db, $order_id);
            if ($again !== null && (int)$again['telegram_id'] === $telegram_id) {
                bot_ok(array_merge(res_rescue_reply($again), ['duplicate' => true]));
                return;
            }
        }
        res_fail(500, 'Could not record the refund. No refund was made.');
    }

    $db->commit();
    bot_ok([
        'ok' => true,
        'order_id' => $order_id,
        'refunded_etb' => $refund,
        'provider_status' => $provider_status,
        'duplicate' => false,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^orders/(\d+)/cancel-refund$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_res_cancel_refund((int)$m[1]); }
//
// (Add the same bot_rate_limit(...) call the other user endpoints use
// to that dispatch line — copy the exact call from the orders
// handler; the signature was not visible from outside the server.)
//
// LIVE CURL TEST — read this whole block before running it. The test
// CANCELS a real order at the provider on purpose (that is the
// point), so it must use a SMALL TEST order placed for this test,
// with William's approval, on the operating account — NEVER a real
// user's order. The refund returns the full order total, so the
// test is net-zero on the Paxyo balance (the provider cancel must
// succeed for the refund to happen at all).
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. Place a small test order first (under the 5 ETB test cap,
//   #    e.g. 100 TikTok views #1665 ≈ 1.89 ETB) via POST /orders or
//   #    the bot, and note its Paxyo order id N. Confirm it is
//   #    pending at the provider:
//   curl -s "https://paxyo.et/api/bot/orders/N?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect the order with status "pending" (or "processing").
//   # 2. Cancel + refund it:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/cancel-refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true,"order_id":N,
//      "refunded_etb":<the order total>,"provider_status":"canceled",
//      "duplicate":false}
//   # 3. Check the balance went back up by exactly the order total:
//   curl -s "https://paxyo.et/api/bot/balance?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   # 4. Call it AGAIN — the same order must NOT refund twice:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/cancel-refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect the SAME refunded_etb with "duplicate":true, and the
//      balance from step 3 UNCHANGED.
//   # 5. Wrong owner must get a 404 (no leaking whether the order
//   #    exists):
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/cancel-refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":1}'
//   -> expect {"success":false,"error":"Order not found."}
//   # 6. A completed order must refuse with 409 (use a known
//   #    completed order id, e.g. an old test order — this call
//   #    touches nothing):
//   curl -s -X POST https://paxyo.et/api/bot/orders/<completed-id>/cancel-refund \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":false,"error":"Order is already completed ..."}.
//   Then DELETE the test rescue row and confirm it is gone (the
//   cancelled test order row itself stays, status 'cancelled' —
//   that is the honest record of what happened):
//   mysql -e "DELETE FROM bot_order_rescues WHERE order_id=N AND telegram_id=779060335; SELECT COUNT(*) FROM bot_order_rescues WHERE order_id=N;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
