<?php
// ============================================================================
// SMM Social Media orders for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot:
// the second SMM provider (smmsocialmedia.in) wired into the bot
// alongside GodOfPanel. The bot (built separately) calls POST
// /orders/smm and GET /orders/{id}/smm-status; the cancel / rescue /
// refill / partial-refund endpoints branch to the smm_* helpers in
// this file when the order is an SMM order (see smm_is_smm_order()).
//
// *** INSTALLER — READ THIS FIRST: SMM_API_KEY ***
//   This file NEVER contains a provider key. The SMM key must be
//   added to public_html/config_secret.php on paxyo.et BEFORE this
//   file is installed, as a constant named SMM_API_KEY (the same
//   key the SMM Social Media panel shows on its account page — NOT
//   the login password). smm_provider_key() reads that constant
//   first, then getenv('SMM_API_KEY'), and returns null when
//   neither is set — every provider call then fails honestly with
//   "Provider is not configured." / a 502, and no order is ever
//   placed or charged. The installer adds the constant; this file
//   does not have the key and must never be given it in chat.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/orders/smm
//     {telegram_id, service_id (SMM bare int), link, quantity,
//      idempotency_key}
//     -> {"ok":true,"order":{"id":N,"status":"pending","total":X,
//         "provider":"smmsocialmedia"},"duplicate":false}
//     A retry with the same idempotency_key returns the earlier
//     order with "duplicate":true and NO second charge, exactly
//     like POST /orders.
//   GET  /api/bot/orders/{id}/smm-status?telegram_id=
//     -> {"ok":true,"order_id":N,"status":"...","remains":R|null,
//         "order":{"id":N,"status":"..."}}
//     Only for SMM orders (a row in bot_smm_orders). A non-SMM
//     order gets a 404 here — the generic GET /orders/{id} owns
//     non-SMM orders.
//
// FLOW — POST /orders/smm (in order; money moves only at step 4,
//   and only after the live price has been computed server-side):
//   1. Validate telegram_id / service_id / link / quantity /
//      idempotency_key (400s). Quantity must be a multiple of 10
//      (bot-side rule, same as POST /orders).
//   2. The account must exist in auth (tg_id + balance, same
//      columns the deposits/refund files use). No account -> 404.
//   3. Fetch the LIVE SMM services list and validate the service
//      exists and the quantity is within its min/max. A service
//      the live list does not carry, or a quantity outside min/max,
//      is a 400 — never a guessed price.
//   4. Compute the total SERVER-SIDE from the live SMM rate:
//      total = rate_inr_per_1000 / 94.263 * 400 * quantity / 1000,
//      rounded to 2 decimals. A client-sent total is NEVER trusted
//      (the endpoint does not even read one). Balance check: short
//      -> 409 "Insufficient balance." and nothing is charged.
//   5. In ONE database transaction: debit the balance AND insert
//      the order row (status 'pending') with the idempotency_key
//      UNIQUE guard. A duplicate key rolls back and returns the
//      existing order with duplicate:true — no second charge.
//   6. Call SMM add. On success, record the provider order id on
//      the orders row (api_order_id first, then provider_order_id,
//      provider_id — whichever column exists) and insert the
//      bot_smm_orders row. On provider failure, refund the debit
//      and mark the order 'failed' in ONE transaction, then answer
//      502 with the provider's own reason — never an invented one.
//
// FLOW — GET /orders/{id}/smm-status:
//   1. Load the order; a missing order, or one belonging to
//      someone else, gets the same 404 (no leaking). An order with
//      no bot_smm_orders row gets a 404 too (not an SMM order).
//   2. Read the live SMM status. When the provider's status word
//      differs from the stored orders.status, UPDATE the stored
//      status to the provider's word (lowercased), so the generic
//      read path and the order list agree with the provider.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_smm_orders  order_id BIGINT PRIMARY KEY (the Paxyo
//                   orders.id — one row per SMM order, ever),
//                   provider VARCHAR(32) NOT NULL DEFAULT
//                   'smmsocialmedia', provider_order_id VARCHAR(64)
//                   (the provider's own order number),
//                   provider_service_id INT (the SMM bare service
//                   id), created_at.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   0. Add SMM_API_KEY to public_html/config_secret.php FIRST
//      (see the *** note above). Without it every provider call
//      fails honestly and no SMM order can be placed.
//   1. php -l api-order-smm.php       (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php. Install the branch edits in
//      api-order-cancel.php, api-order-rescue.php,
//      api-order-refill.php, api-order-partial-refund.php and
//      api-delayed-orders.php in the same splice round (each file's
//      own footer says what changed).
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then cancel the
//      test order (which refunds it in full) and DELETE the test
//      bot_smm_orders row. The test places a REAL order at SMM on
//      purpose (that is the point), so use a small test order only,
//      under the 5 ETB test cap, with William's approval, on the
//      operating account — never a real user's order.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use smm_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - SMM prices are provider USD rate x400 ETB. GodOfPanel stays
//     x420 — do NOT touch that; the two multipliers live in
//     different files on purpose.
//   - A total that rounds to 0.00 ETB (the cheapest SMM services at
//     the smallest quantities) is a free order: no debit is made
//     and no refund is needed on provider failure. The bot should
//     still prefer quantities whose total is at least 0.01 ETB, so
//     the order is a real paid order in the finance figures.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL (see also the
//   "TO VERIFY" comments inside the helpers):
//   A1. orders table: id, telegram_id (owner), service_id, link,
//       quantity, total, status, created_at, idempotency_key UNIQUE
//       (the HANDOVER confirms idempotency_key is a UNIQUE column
//       on orders — POST /orders relies on it), plus a provider
//       order id in api_order_id (then provider_order_id,
//       provider_id). The code reads the row with SELECT * and picks
//       the owner / total / provider-id / service columns from a
//       short candidate list (primary name first), so a
//       differently-named column still works — but confirm the real
//       names with SHOW COLUMNS FROM orders and trim the lists.
//   A2. auth table: tg_id + balance (same columns the deposits
//       endpoint credits — verified pattern, not an assumption).
//   A3. PROVIDER KEY: smm_provider_key() reads ONLY the constant
//       SMM_API_KEY (config_secret.php), then getenv('SMM_API_KEY').
//       TO VERIFY: confirm config_secret.php on paxyo.et defines
//       SMM_API_KEY with the SMM panel key before install; if the
//       server already has a differently-named SMM constant, rename
//       it here in the one marked spot. No key value is written
//       anywhere in this file.
//   A4. PROVIDER API (SMM Social Media v2,
//       https://smmsocialmedia.in/api/v2): parameters go in the URL
//       query string (key + action + ...), NOT in the POST body —
//       the POST body is EMPTY, exactly like GodOfPanel (a POST body
//       fails with "Invalid API key" on that panel family; the SMM
//       connector doc confirms the same query-string placement for
//       this panel). Actions: services / balance / add / status /
//       cancel / refill. TO VERIFY LIVE: add / cancel / refill /
//       status were NEVER called against this panel (the connector
//       doc confirms only balance + services live — balance
//       73.8506480 INR, 3,301 services, 15 Nov 2026). The reply
//       shapes below are the standard SMM-panel shapes and are
//       parsed defensively (order id accepted as "order" /
//       "order_id" / "id"; a missing "remains" is null, never
//       invented). Run the live test and confirm each shape; if a
//       shape differs, fix the one marked parse spot, not the flow.
//   A5. SERVICES LIST shape (VERIFIED live 15 Nov 2026, 3,301
//       services): a JSON list of {"service":N,"name":...,
//       "type":...,"rate":"58.00" (INR per 1,000, a STRING),
//       "min":N,"max":N,"dripfeed":bool,"refill":bool,"cancel":bool}.
//       The price math uses "rate" (INR per 1,000). There is NO
//       average-time field on this panel either.
//   A6. RATES: SMM_INR_PER_USD = 94.263 is William's rate (the SMM
//       connector doc and the merged catalogue both use it), and
//       SMM_SELL_MULTIPLIER_ETB = 400 is the SMM sell multiplier.
//       If William changes either rate, change the one constant
//       below — the price formula itself never changes.
//   A7. STATUS WORDS: the provider's status words are taken as
//       given and lowercased before storing (pending / processing /
//       in progress / partial / completed / canceled / ...). The
//       exact spellings this panel uses were NOT verified live —
//       the live status test confirms them. The generic read path
//       and the order list must treat the stored word the same way
//       they treat a GodOfPanel word.
//   A8. bot_ok() / bot_rate_limit(): assumed to exist in bot.php,
//       same as the sibling endpoint files. bot_ok() adds
//       "success":true to the reply.
// ============================================================================

// --- constants (one place to change the rates — see A6) ----------------------

// William's rate: 94.263 INR per 1 USD (SMM panel currency is INR).
if (!defined('SMM_INR_PER_USD')) define('SMM_INR_PER_USD', 94.263);
// SMM services sell at provider USD rate x400 ETB. GodOfPanel stays
// x420 — that multiplier lives in the GodOfPanel code, not here.
if (!defined('SMM_SELL_MULTIPLIER_ETB')) define('SMM_SELL_MULTIPLIER_ETB', 400);

// --- small helpers (smm_ prefix so nothing collides with bot.php) -----------

function smm_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function smm_fail($code, $msg, $extra = []) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(array_merge(
        ['success' => false, 'ok' => false, 'error' => $msg, 'message' => $msg],
        $extra
    ));
    exit;
}

function smm_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function smm_substr($text, $len) {
    // mb_substr keeps emoji intact when truncating; plain substr is
    // the fallback if mbstring is ever missing on the server.
    if (function_exists('mb_substr')) return mb_substr($text, 0, $len, 'UTF-8');
    return substr($text, 0, $len);
}

function smm_ensure_tables($db) {
    // utf8mb4, like the other bot tables. set_charset is idempotent —
    // harmless if bot.php already did it.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_smm_orders (
        order_id BIGINT NOT NULL PRIMARY KEY,
        provider VARCHAR(32) NOT NULL DEFAULT 'smmsocialmedia',
        provider_order_id VARCHAR(64) NULL,
        provider_service_id INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_bot_smm_orders_provider (provider_order_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Pick the first candidate column that exists on the row and is not
// null/empty. TO VERIFY (A1): confirm the real orders column names
// with SHOW COLUMNS FROM orders and trim these lists. Primary name
// first in each list.
function smm_pick_order_field($row, $candidates) {
    foreach ($candidates as $col) {
        if (array_key_exists($col, $row) && $row[$col] !== null && $row[$col] !== '') {
            return $row[$col];
        }
    }
    return null;
}

function smm_order_reply($row) {
    return [
        'id' => (int)$row['id'],
        'status' => (string)($row['status'] ?? 'pending'),
        'total' => (float)($row['total'] ?? 0),
        'provider' => 'smmsocialmedia',
    ];
}

function smm_order_by_key($db, $key) {
    $stmt = $db->prepare('SELECT * FROM orders WHERE idempotency_key = ? LIMIT 1');
    $stmt->bind_param('s', $key);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// --- provider calls (ADAPTER — see A3/A4; one spot to fix) ------------------

function smm_provider_key() {
    // TO VERIFY (A3): SMM_API_KEY must be defined in
    // public_html/config_secret.php on paxyo.et BEFORE install.
    // Never write a key value here, in chat, or in any file.
    if (defined('SMM_API_KEY') && constant('SMM_API_KEY') !== '') return (string)constant('SMM_API_KEY');
    $env = getenv('SMM_API_KEY');
    if ($env !== false && $env !== '') return $env;
    return null;
}

function smm_provider_base() {
    if (defined('SMM_API_URL') && SMM_API_URL !== '') return rtrim(SMM_API_URL, '/');
    $env = getenv('SMM_API_URL');
    if ($env !== false && $env !== '') return rtrim($env, '/');
    return 'https://smmsocialmedia.in/api/v2';
}

// One raw provider call. Params go in the URL query string (the
// provider rejects a POST body with "Invalid API key"). The POST
// body is EMPTY. Returns the decoded JSON reply as an array, or
// null when the provider could not be reached / did not answer JSON.
function smm_provider_raw($action, $params) {
    $key = smm_provider_key();
    if ($key === null) return null;
    $query = array_merge(['key' => $key, 'action' => $action], $params);
    $url = smm_provider_base() . '?' . http_build_query($query);
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

// Does a provider error say the refill ACTION itself is not
// offered? (Unknown / invalid action, not supported.) Same regex
// idea as ref_error_is_unsupported_action() in api-order-refill.php.
function smm_error_is_unsupported_action($error) {
    $low = strtolower(trim((string)$error));
    if ($low === '') return false;
    return (bool)preg_match(
        '/unknown action|invalid action|action.*not (supported|available|found)|not support|does not support|unsupported action|incorrect request/',
        $low
    );
}

// --- SMM services list (live, for validation + server-side pricing) ---------

// Returns the live services list as an array, or null when the
// provider could not be reached / did not answer with a list.
// TO VERIFY (A5): the list shape was verified live 15 Nov 2026.
function smm_services() {
    $res = smm_provider_raw('services', []);
    if ($res === null) return null;
    if (isset($res['error'])) return null;
    // A list reply is a JSON array; an assoc reply is not a list.
    if (array_keys($res) !== range(0, count($res) - 1)) return null;
    return $res;
}

// Find one service in the live list by its bare SMM id. The list
// carries the id in "service" (also accepts "id" defensively).
// Returns the service row array, or null.
function smm_find_service($services, $service_id) {
    if (!is_array($services)) return null;
    foreach ($services as $svc) {
        if (!is_array($svc)) continue;
        $id = (int)($svc['service'] ?? $svc['id'] ?? 0);
        if ($id === $service_id) return $svc;
    }
    return null;
}

// --- SMM provider actions ---------------------------------------------------

// Place an order at SMM.
// Returns ['order_id' => string|null, 'error' => string|null].
//   order_id set -> the provider accepted the order.
//   otherwise    -> the provider refused / did not answer; 'error'
//                   carries the provider's own words (never invented).
// TO VERIFY (A4): the add shape {"order": <id>} was never called
// live against this panel. The id is accepted as "order" /
// "order_id" / "id", defensively.
function smm_place($service_id, $link, $quantity) {
    if (smm_provider_key() === null) {
        return ['order_id' => null, 'error' => 'Provider is not configured.'];
    }
    $res = smm_provider_raw('add', ['service' => $service_id, 'link' => $link, 'quantity' => $quantity]);
    if ($res === null) {
        return ['order_id' => null, 'error' => 'Provider did not answer. No order was placed.'];
    }
    if (isset($res['error']) && $res['error'] !== '') {
        return ['order_id' => null, 'error' => (string)$res['error']];
    }
    foreach (['order', 'order_id', 'id'] as $key) {
        if (isset($res[$key]) && $res[$key] !== '' && $res[$key] !== null && is_numeric($res[$key])) {
            return ['order_id' => (string)$res[$key], 'error' => null];
        }
    }
    return ['order_id' => null, 'error' => 'Provider reply was not understood. No order was placed.'];
}

// Read the live SMM status for one provider order id.
// Returns ['status' => lowercased status string|null,
//          'remains' => int|null, 'error' => string|null], or null
// when the provider could not be reached at all. A missing
// "remains" is null, never invented.
// TO VERIFY (A4/A7): the status shape {"status": "...", "charge":
// "...", "currency": "...", "remains": N} was never called live
// against this panel; confirm the field names and the status
// spellings with the live test.
function smm_order_status($provider_order_id) {
    if (smm_provider_key() === null) {
        return ['status' => null, 'remains' => null, 'error' => 'Provider is not configured.'];
    }
    $res = smm_provider_raw('status', ['order' => $provider_order_id]);
    if ($res === null) return null;
    if (isset($res['error']) && $res['error'] !== '') {
        return ['status' => null, 'remains' => null, 'error' => (string)$res['error']];
    }
    if (!isset($res['status'])) {
        return ['status' => null, 'remains' => null, 'error' => 'Provider reply was not understood.'];
    }
    $remains = null;
    foreach (['remains', 'remain', 'remaining', 'undelivered'] as $key) {
        if (isset($res[$key]) && is_numeric($res[$key])) {
            $remains = (int)$res[$key];
            break;
        }
    }
    return [
        'status' => strtolower(trim((string)$res['status'])),
        'remains' => $remains,
        'error' => null,
    ];
}

// Cancel one order at SMM and confirm it is cancelled. Same return
// shape as can_provider_cancel() / res_provider_cancel(), so the
// cancel and rescue endpoints can call this in place of their
// GodOfPanel cancel.
// Returns ['confirmed' => bool, 'provider_status' => string|null,
//          'not_cancellable' => bool, 'error' => string|null].
//   confirmed=true  -> the provider cancelled it; refund is safe.
//   not_cancellable -> the provider explicitly refused: refund NOTHING.
//   otherwise       -> ambiguous: refund NOTHING; the bot may retry.
// TO VERIFY (A4): the cancel shape (cancel == 1, or a status of
// Canceled/Cancelled) was never called live against this panel —
// the code re-checks with action=status and only confirms when
// the provider's own status says cancelled (or the cancel reply
// itself unambiguously said so).
function smm_cancel($provider_order_id) {
    if (smm_provider_key() === null) {
        return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => false, 'error' => 'Provider is not configured.'];
    }
    $res = smm_provider_raw('cancel', ['order' => $provider_order_id]);
    if ($res === null) {
        // Cancel reply never arrived. A failed change may still have
        // gone through — check the provider's own status first.
        $st = smm_order_status($provider_order_id);
        if (is_array($st) && ($st['status'] === 'canceled' || $st['status'] === 'cancelled')) {
            return ['confirmed' => true, 'provider_status' => $st['status'], 'not_cancellable' => false, 'error' => null];
        }
        if (is_array($st) && $st['status'] !== null) {
            return ['confirmed' => false, 'provider_status' => $st['status'], 'not_cancellable' => false, 'error' => 'Provider did not confirm the cancel (provider status: ' . $st['status'] . '). No refund was made.'];
        }
        return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => false, 'error' => 'Provider did not answer. No refund was made.'];
    }

    // An explicit provider error: the order cannot be cancelled.
    // Never refund on this path, and never invent a reason.
    if (isset($res['error']) && $res['error'] !== '') {
        return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => true, 'error' => 'Provider refused the cancel: ' . smm_substr((string)$res['error'], 200)];
    }

    // Cancel accepted? The standard success shape is cancel == 1
    // (TO VERIFY, A4).
    $cancel_flag = $res['cancel'] ?? null;
    $status_word = isset($res['status']) ? strtolower(trim((string)$res['status'])) : '';
    if ($cancel_flag === 1 || $cancel_flag === '1' || $cancel_flag === true || $cancel_flag === 'true'
        || $status_word === 'canceled' || $status_word === 'cancelled') {
        // The cancel reply said yes — still confirm with the
        // provider's own status read, so a lying / stale reply can
        // never trigger a refund for a live order.
        $st = smm_order_status($provider_order_id);
        if (is_array($st) && ($st['status'] === 'canceled' || $st['status'] === 'cancelled')) {
            return ['confirmed' => true, 'provider_status' => $st['status'], 'not_cancellable' => false, 'error' => null];
        }
        if (is_array($st) && $st['status'] !== null) {
            return ['confirmed' => false, 'provider_status' => $st['status'], 'not_cancellable' => false, 'error' => 'Provider said the cancel went through but still reports status: ' . $st['status'] . '. No refund was made.'];
        }
        // Status read failed but the cancel reply itself was an
        // unambiguous yes — accept it (the re-check is a safety net,
        // not a veto, when the provider already said cancelled).
        return ['confirmed' => true, 'provider_status' => ($status_word !== '' ? $status_word : 'canceled'), 'not_cancellable' => false, 'error' => null];
    }

    // Reply arrived but said neither yes nor error — do not guess.
    $st = smm_order_status($provider_order_id);
    if (is_array($st) && ($st['status'] === 'canceled' || $st['status'] === 'cancelled')) {
        return ['confirmed' => true, 'provider_status' => $st['status'], 'not_cancellable' => false, 'error' => null];
    }
    if (is_array($st) && $st['status'] !== null) {
        return ['confirmed' => false, 'provider_status' => $st['status'], 'not_cancellable' => false, 'error' => 'Provider did not cancel the order (provider status: ' . $st['status'] . '). No refund was made.'];
    }
    return ['confirmed' => false, 'provider_status' => null, 'not_cancellable' => false, 'error' => 'Provider reply was not understood. No refund was made.'];
}

// Refill one order at SMM. Same four-way return shape as
// ref_provider_refill() in api-order-refill.php, so that endpoint
// can call this in place of its GodOfPanel refill.
// Returns ['refill_id' => string|null, 'status' => string,
//          'unsupported' => bool, 'refused' => bool,
//          'error' => string|null].
//   refill_id set   -> the provider accepted the refill.
//   unsupported     -> the provider does not offer the refill
//                      action at all (501 to the bot).
//   refused         -> the provider refused this order/service
//                      (409 to the bot, with the provider's reason).
//   otherwise       -> ambiguous: the bot is told the refill
//                      could not be started (502), and may retry.
// TO VERIFY (A4): the refill shape {"refill": <id>} was never
// called live against this panel.
function smm_refill($provider_order_id) {
    if (smm_provider_key() === null) {
        return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => false, 'error' => 'Provider is not configured.'];
    }
    $res = smm_provider_raw('refill', ['order' => $provider_order_id]);
    if ($res === null) {
        return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => false, 'error' => 'Provider did not answer. No refill was made.'];
    }
    if (isset($res['error']) && $res['error'] !== '') {
        $msg = (string)$res['error'];
        if (smm_error_is_unsupported_action($msg)) {
            return ['refill_id' => null, 'status' => '', 'unsupported' => true, 'refused' => false, 'error' => $msg];
        }
        return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => true, 'error' => $msg];
    }
    if (isset($res['refill']) && $res['refill'] !== '' && $res['refill'] !== null) {
        $status = isset($res['status']) ? strtolower(trim((string)$res['status'])) : 'success';
        return ['refill_id' => (string)$res['refill'], 'status' => $status, 'unsupported' => false, 'refused' => false, 'error' => null];
    }
    return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => false, 'error' => 'Provider reply was not understood. No refill was made.'];
}

// --- which provider owns an order? (called by the other files) -----------

// The bot_smm_orders row for a Paxyo order id, or null when the
// order is not an SMM order (or the table does not exist yet — an
// SMM order can only exist after this file is installed, so a
// missing table honestly means "not SMM"). Never throws: the
// cancel / rescue / refill / partial-refund branches call this
// guarded by function_exists, and must keep working when this file
// is not installed yet.
function smm_order_provider($db, $order_id) {
    if ($db === null || $order_id <= 0) return null;
    try {
        $stmt = $db->prepare('SELECT order_id, provider, provider_order_id, provider_service_id, created_at FROM bot_smm_orders WHERE order_id = ? LIMIT 1');
        if ($stmt === false) return null;
        $stmt->bind_param('i', $order_id);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_assoc();
        $stmt->close();
        return $row ?: null;
    } catch (Throwable $e) {
        return null;
    }
}

function smm_is_smm_order($db, $order_id) {
    return smm_order_provider($db, $order_id) !== null;
}

// Record the provider order id on the orders row. Tries the
// candidate columns in order (api_order_id first) and stops at the
// first that works — the same tolerant pattern as the siblings.
// Returns true when one of them was written.
function smm_set_provider_order_id($db, $order_id, $provider_order_id) {
    foreach (['api_order_id', 'provider_order_id', 'provider_id'] as $col) {
        try {
            $stmt = $db->prepare('UPDATE orders SET ' . $col . ' = ? WHERE id = ?');
            if ($stmt === false) continue;
            $stmt->bind_param('si', $provider_order_id, $order_id);
            $ok = $stmt->execute();
            $stmt->close();
            if ($ok) return true;
        } catch (mysqli_sql_exception $e) {
            continue;
        } catch (Throwable $e) {
            continue;
        }
    }
    return false;
}

// --- POST /api/bot/orders/smm ----------------------------------------------

function bot_smm_place_order() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') smm_fail(405, 'Method not allowed.');
    $in = smm_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) smm_fail(400, 'telegram_id is required.');
    $service_id = (int)($in['service_id'] ?? 0);
    if ($service_id <= 0) smm_fail(400, 'service_id is required.');
    $link = smm_substr(trim((string)($in['link'] ?? '')), 500);
    if ($link === '') smm_fail(400, 'link is required.');
    $quantity = (int)($in['quantity'] ?? 0);
    if ($quantity <= 0) smm_fail(400, 'quantity must be positive.');
    if ($quantity % 10 !== 0) smm_fail(400, 'quantity must be a multiple of 10.');
    $key = smm_substr(trim((string)($in['idempotency_key'] ?? '')), 64);
    if ($key === '') smm_fail(400, 'idempotency_key is required.');

    $db = smm_db();
    if ($db === null) smm_fail(500, 'Database is not available.');
    smm_ensure_tables($db);

    // Duplicate idempotency key, checked up front: a retried Confirm
    // returns the earlier order, never a second charge. (The UNIQUE
    // guard in the transaction below is the real protection against
    // two calls racing each other; this check is the fast path.)
    $existing = smm_order_by_key($db, $key);
    if ($existing !== null) {
        $owner = smm_pick_order_field($existing, ['telegram_id', 'user_id', 'tg_id']);
        if ($owner === null || (int)$owner !== $telegram_id) {
            smm_fail(409, 'idempotency_key is already in use.');
        }
        bot_ok(array_merge(['ok' => true, 'order' => smm_order_reply($existing)], ['duplicate' => true]));
        return;
    }

    // 2. The account must exist in auth (tg_id + balance). No
    //    account -> 404; the bot creates the account on /start, so
    //    a missing row means the user never started the bot.
    $stmt = $db->prepare('SELECT balance FROM auth WHERE tg_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $auth = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$auth) smm_fail(404, 'Account not found.');
    $balance = (float)($auth['balance'] ?? 0);

    // 3. Validate against the LIVE SMM services list. The list is
    //    the authority on whether the service exists and on min/max.
    $services = smm_services();
    if ($services === null) {
        smm_fail(502, 'Provider did not answer. The service could not be checked. No charge was made.');
    }
    $svc = smm_find_service($services, $service_id);
    if ($svc === null) smm_fail(400, 'Service not found.');
    $rate_inr = $svc['rate'] ?? $svc['rate_inr'] ?? null;
    if ($rate_inr === null || !is_numeric($rate_inr) || (float)$rate_inr < 0) {
        smm_fail(502, 'Provider did not give a usable rate for this service. No charge was made.');
    }
    $min = (int)($svc['min'] ?? 0);
    $max = (int)($svc['max'] ?? 0);
    if (($min > 0 && $quantity < $min) || ($max > 0 && $quantity > $max)) {
        smm_fail(400, 'quantity must be between ' . $min . ' and ' . $max . ' for this service.');
    }

    // 4. Server-side total. rate is INR per 1,000; / 94.263 is USD
    //    per 1,000; x400 is ETB per 1,000; x quantity / 1000 is the
    //    ETB total. Never trust a client-sent total.
    $total = round(((float)$rate_inr / SMM_INR_PER_USD) * SMM_SELL_MULTIPLIER_ETB * $quantity / 1000, 2);
    if ($total < 0) $total = 0.0;
    if ($balance < $total) smm_fail(409, 'Insufficient balance.');

    // 5. ONE transaction: debit the balance AND insert the order
    //    row (status 'pending') with the idempotency_key UNIQUE
    //    guard. Any failure rolls both back; the balance is untouched.
    $db->begin_transaction();
    if ($total > 0) {
        // The balance >= total guard makes the debit itself the
        // race check: a concurrent order that spent the balance
        // first leaves affected_rows 0 here.
        $stmt = $db->prepare('UPDATE auth SET balance = balance - ? WHERE tg_id = ? AND balance >= ?');
        $stmt->bind_param('did', $total, $telegram_id, $total);
        $stmt->execute();
        $debited = $stmt->affected_rows;
        $stmt->close();
        if ($debited !== 1) {
            $db->rollback();
            smm_fail(409, 'Insufficient balance.');
        }
    }
    // TO VERIFY (A1): the orders columns used here — telegram_id,
    // service_id, link, quantity, total, status, idempotency_key —
    // match POST /orders (HANDOVER confirms idempotency_key is a
    // UNIQUE column on orders).
    $stmt = $db->prepare("INSERT INTO orders (telegram_id, service_id, link, quantity, total, status, idempotency_key) VALUES (?, ?, ?, ?, ?, 'pending', ?)");
    $stmt->bind_param('iisids', $telegram_id, $service_id, $link, $quantity, $total, $key);
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
            $again = smm_order_by_key($db, $key);
            if ($again !== null) {
                $owner = smm_pick_order_field($again, ['telegram_id', 'user_id', 'tg_id']);
                if ($owner !== null && (int)$owner === $telegram_id) {
                    bot_ok(array_merge(['ok' => true, 'order' => smm_order_reply($again)], ['duplicate' => true]));
                    return;
                }
            }
            smm_fail(409, 'idempotency_key is already in use.');
        }
        smm_fail(500, 'Could not record the order. No charge was made.');
    }
    $order_id = (int)$db->insert_id;
    $db->commit();

    // 6. Place it at SMM. The debit + order row are already committed;
    //    a provider failure below refunds the debit and marks the
    //    order 'failed' — it never leaves a charged-but-unplaced order.
    $placed = smm_place($service_id, $link, $quantity);
    if ($placed['order_id'] === null) {
        $reason = $placed['error'] ?? 'Provider did not answer.';
        $db->begin_transaction();
        if ($total > 0) {
            $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
            $stmt->bind_param('di', $total, $telegram_id);
            $stmt->execute();
            $refunded = $stmt->affected_rows;
            $stmt->close();
            if ($refunded !== 1) {
                $db->rollback();
                smm_fail(500, 'Provider refused the order (' . smm_substr($reason, 200) . ') and the refund could not be recorded. Please contact support with order id ' . $order_id . '.');
            }
        }
        $stmt = $db->prepare("UPDATE orders SET status = 'failed' WHERE id = ? AND status = 'pending'");
        $stmt->bind_param('i', $order_id);
        $stmt->execute();
        $stmt->close();
        $db->commit();
        // The provider's own reason, never an invented one. A
        // provider that did not answer at all is a 502.
        if (stripos($reason, 'did not answer') !== false || stripos($reason, 'not configured') !== false) {
            smm_fail(502, $reason . ' No charge was made.');
        }
        smm_fail(502, 'Provider refused the order: ' . smm_substr($reason, 200) . ' No charge was made.');
    }
    $provider_order_id = (string)$placed['order_id'];

    // Record the provider order id on the orders row (first column
    // that exists wins) and the SMM mapping row. If the mapping
    // insert fails the order is still placed and paid for — the
    // provider id on the orders row keeps it findable, so this
    // never turns a placed order into a failure reply.
    smm_set_provider_order_id($db, $order_id, $provider_order_id);
    try {
        $provider_name = 'smmsocialmedia';
        $stmt = $db->prepare('INSERT INTO bot_smm_orders (order_id, provider, provider_order_id, provider_service_id) VALUES (?, ?, ?, ?)');
        $stmt->bind_param('issi', $order_id, $provider_name, $provider_order_id, $service_id);
        $stmt->execute();
        $stmt->close();
    } catch (Throwable $e) {
        // Best-effort only (see above) — do not fail the reply.
    }

    bot_ok([
        'ok' => true,
        'order' => ['id' => $order_id, 'status' => 'pending', 'total' => $total, 'provider' => 'smmsocialmedia'],
        'duplicate' => false,
    ]);
}

// --- GET /api/bot/orders/{id}/smm-status ------------------------------------

function bot_smm_order_status($order_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') smm_fail(405, 'Method not allowed.');
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) smm_fail(400, 'telegram_id is required.');
    if ($order_id <= 0) smm_fail(400, 'order id is required.');

    $db = smm_db();
    if ($db === null) smm_fail(500, 'Database is not available.');
    smm_ensure_tables($db);

    // Load the order and check ownership. A different telegram_id
    // asking for the same order gets the same 404 as a missing
    // order (no leaking).
    $stmt = $db->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) smm_fail(404, 'Order not found.');
    $owner = smm_pick_order_field($row, ['telegram_id', 'user_id', 'tg_id']);
    if ($owner === null || (int)$owner !== $telegram_id) smm_fail(404, 'Order not found.');

    // Only SMM orders live here. A non-SMM order gets a 404 — the
    // generic GET /orders/{id} owns non-SMM orders.
    $smm_row = smm_order_provider($db, $order_id);
    if ($smm_row === null) smm_fail(404, 'Order not found.');
    $provider_order_id = $smm_row['provider_order_id'] ?? null;
    if ($provider_order_id === null || $provider_order_id === '') {
        $provider_order_id = smm_pick_order_field($row, ['api_order_id', 'provider_order_id', 'provider_id']);
    }
    if ($provider_order_id === null || (string)$provider_order_id === '') {
        smm_fail(409, 'Order has no provider order id on record, so its status cannot be checked at the provider.');
    }
    $provider_order_id = (string)$provider_order_id;

    // Read the live SMM status.
    $live = smm_order_status($provider_order_id);
    if ($live === null) {
        smm_fail(502, 'Provider did not answer.');
    }
    if (!empty($live['error'])) {
        smm_fail(502, 'Provider refused the status check: ' . smm_substr((string)$live['error'], 200));
    }
    $live_status = $live['status'] !== null ? $live['status'] : '';
    $stored_status = strtolower(trim((string)($row['status'] ?? '')));

    // When the provider's word differs from the stored status,
    // UPDATE the stored status to the provider's word (lowercased),
    // so the generic read path and the order list agree.
    if ($live_status !== '' && $live_status !== $stored_status) {
        $stmt = $db->prepare('UPDATE orders SET status = ? WHERE id = ?');
        $stmt->bind_param('si', $live_status, $order_id);
        $stmt->execute();
        $stmt->close();
        $stored_status = $live_status;
    }

    bot_ok([
        'ok' => true,
        'order_id' => $order_id,
        'status' => $stored_status,
        'remains' => $live['remains'],
        'order' => ['id' => $order_id, 'status' => $stored_status],
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'orders/smm' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_smm_place_order(); }
//   if (preg_match('#^orders/(\d+)/smm-status$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_smm_order_status((int)$m[1]); }
//
// (Add the same bot_rate_limit(...) call the other user endpoints use
// to both dispatch lines — copy the exact call from the orders
// handler; the signature was not visible from outside the server.
// The 'orders/smm' line must sit BEFORE any generic 'orders/...'
// pattern that could match it, if bot.php has one.)
//
// BOT.PHP PATCH SNIPPET — generic GET /orders/{id} and GET /orders
// list (anchors TO VERIFY: bot.php itself was not in this workspace,
// so the exact variable names — $row, $db, the provider-order-id
// column, the reply array — must be checked against the live file
// and adjusted to match; the BRANCH LOGIC below is the contract):
//
//   // --- SMM branch (api-order-smm.php) — after loading the order
//   // row (and after the ownership check) in GET /orders/{id}:
//   if (function_exists('smm_is_smm_order') && smm_is_smm_order($db, (int)$row['id'])) {
//       // Use the SMM status read INSTEAD of the GodOfPanel one.
//       $smm_row = smm_order_provider($db, (int)$row['id']);
//       $smm_provider_id = $smm_row['provider_order_id'] ?? null;
//       if ($smm_provider_id !== null && $smm_provider_id !== '') {
//           $smm_live = smm_order_status((string)$smm_provider_id);
//           if (is_array($smm_live) && !empty($smm_live['status'])) {
//               $row['status'] = $smm_live['status'];
//               // + UPDATE orders SET status = <provider word> WHERE id = ?
//               //   when it differs from the stored status (same rule
//               //   as bot_smm_order_status() above).
//           }
//       }
//       $row['provider'] = 'smmsocialmedia';
//       $row['combined_id'] = 'smm:' . (int)$row['service_id'];
//   }
//
//   // --- SMM branch — per row in the GET /orders list handler:
//   if (function_exists('smm_is_smm_order') && smm_is_smm_order($db, (int)$row['id'])) {
//       $row['provider'] = 'smmsocialmedia';
//       $row['combined_id'] = 'smm:' . (int)$row['service_id'];
//       // (List rows do NOT get a live provider status read — the
//       //  list uses the stored orders.status, which the smm-status
//       //  endpoint and the delivery watch keep in sync.)
//   }
//
// LIVE CURL TEST — read this whole block before running it. The test
// PLACES A REAL ORDER at SMM on purpose (that is the point), so it
// must use a SMALL TEST order, under the 5 ETB test cap, with
// William's approval, on the operating account telegram_id
// 779060335 — NEVER a real user's order. The test order is
// cancelled afterwards, which refunds it in full, so the test is
// net-zero on the Paxyo balance (the provider cancel must succeed
// for the refund to happen at all).
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 0. Read the balance, and RE-CHECK THE LIVE SMM RATE FIRST
//   #    (rates move — the numbers below are the 15 Nov 2026
//   #    snapshot, not a promise):
//   curl -s "https://paxyo.et/api/bot/balance?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   #    Snapshot: SMM #7013 Instagram Views, rate 0.074 INR/1000,
//   #    min 100 max 500000 -> qty 100 total =
//   #    0.074 / 94.263 * 400 * 100 / 1000 = 0.03 ETB.
//   # 1. Place the test order (use a REAL Instagram post link
//   #    William owns, not the placeholder below):
//   curl -s -X POST https://paxyo.et/api/bot/orders/smm \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"service_id":7013,"link":"https://www.instagram.com/p/paxyo-test/","quantity":100,"idempotency_key":"test-smm-1"}'
//   -> expect {"success":true,"ok":true,"order":{"id":N,
//      "status":"pending","total":0.03,
//      "provider":"smmsocialmedia"},"duplicate":false}
//      (total follows the LIVE rate — recompute it from step 0 if
//      the rate moved; the server's total is the authority.)
//   # 2. Live status (order id N from step 1):
//   curl -s "https://paxyo.et/api/bot/orders/N/smm-status?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"order_id":N,
//      "status":"<provider word, e.g. pending>","remains":<n or null>,
//      "order":{"id":N,"status":"<same word>"}}
//      TO VERIFY: the provider status word and whether "remains"
//      is present. If the shape differs, fix smm_order_status().
//   # 3. Same idempotency key again -> the SAME order, no second
//   #    charge (balance from step 0, minus the one order total):
//   curl -s -X POST https://paxyo.et/api/bot/orders/smm \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"service_id":7013,"link":"https://www.instagram.com/p/paxyo-test/","quantity":100,"idempotency_key":"test-smm-1"}'
//   -> expect the same "id":N with "duplicate":true.
//   # 4. Wrong owner must get a 404 (no leaking whether the order
//   #    exists):
//   curl -s "https://paxyo.et/api/bot/orders/N/smm-status?telegram_id=1" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":false,"error":"Order not found."}
//   # 5. Insufficient balance must refuse with 409 and charge
//   #    nothing (read the balance in step 0 first, then pick a
//   #    quantity whose server-side total exceeds it — snapshot:
//   #    SMM #2016 YouTube views, rate 235.857 INR/1000, min 1000,
//   #    qty 2000 total = 235.857 / 94.263 * 400 * 2000 / 1000
//   #    = 2001.70 ETB, above the ~1,075 ETB operating balance):
//   curl -s -X POST https://paxyo.et/api/bot/orders/smm \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"service_id":2016,"link":"https://www.youtube.com/watch?v=paxyo-test","quantity":2000,"idempotency_key":"test-smm-2"}'
//   -> expect HTTP 409 {"success":false,
//      "error":"Insufficient balance."}
//      and the balance UNCHANGED.
//   # 6. A bad service id must refuse with 400 (touches nothing):
//   curl -s -X POST https://paxyo.et/api/bot/orders/smm \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"service_id":999999999,"link":"https://www.instagram.com/p/paxyo-test/","quantity":100,"idempotency_key":"test-smm-3"}'
//   -> expect HTTP 400 {"success":false,"error":"Service not found."}
//   # 7. A non-SMM order must 404 on the SMM status endpoint (use a
//   #    known GodOfPanel order id — this call touches nothing):
//   curl -s "https://paxyo.et/api/bot/orders/<gop-order-id>/smm-status?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":false,"error":"Order not found."}
//   Then CANCEL the test order (refunds it in full — the SMM branch
//   in api-order-cancel.php handles it) and DELETE the test SMM row:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/cancel \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   mysql -e "DELETE FROM bot_smm_orders WHERE order_id=N; SELECT COUNT(*) FROM bot_smm_orders WHERE order_id=N;"
//   (use the same MySQL credentials db.php uses; never print them.
//   The cancelled test order row itself stays, status 'cancelled' —
//   that is the honest record of what happened.)
// ============================================================================
