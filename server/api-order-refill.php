<?php
// ============================================================================
// Refill a completed order for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot
// feature 3, refill in chat.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/orders/{id}/refill   {telegram_id}
//     -> {"ok":true,"order_id":N,"refill_id":R,
//         "provider_status":"...","duplicate":false}
//     Every confirmed refill is a fresh provider refill and is
//     recorded in bot_order_refills (one row per refill — a user
//     may refill the same order again later, after another drop).
//
// FLOW (in order):
//   1. Load the order. It must belong to telegram_id and be
//      COMPLETED (status completed / complete / success / paid /
//      done). Anything else gets an honest 409 and nothing is
//      refilled. A missing order, or an order belonging to someone
//      else, gets the same 404 (no leaking).
//   2. Refill it at the provider (GodOfPanel) — see
//      ref_provider_refill() below. The provider's own order id
//      (api_order_id) is required; without it there is nothing to
//      refill, so the endpoint refuses with 409.
//   3. If the provider says the refill ACTION itself is not
//      offered (unknown / invalid action, not supported), return
//      HTTP 501 with {"ok":false,"refill_supported":false} so the
//      bot can offer a fresh re-order instead — honestly labelled
//      as a new order, never as a refill.
//   4. If the provider refuses the refill for this order/service
//      (e.g. the service carries no refill guarantee), return 409
//      with the provider's own reason — never an invented one.
//   5. On success, record the refill in bot_order_refills. The
//      order's own status is NOT changed: it stays completed; the
//      refill is a top-up of that order, not a new order.
//
// THE SERVER NEVER PLACES A REPLACEMENT ORDER. After a 501 the
// bot re-places the order itself, as a brand-new order, through
// the existing POST /api/bot/orders endpoint. After a 409 the bot
// shows the provider's reason and places nothing.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_order_refills  id AUTO_INCREMENT PK, order_id BIGINT NOT
//                      NULL, telegram_id BIGINT NOT NULL,
//                      refill_id VARCHAR(64) (the provider's
//                      refill number), status VARCHAR(64) (the
//                      provider's word for the refill, e.g.
//                      "success"), created_at.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-order-refill.php      (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test refill row. The test refills a REAL completed test order
//      on purpose (that is the point), so use a small completed test
//      order only, with William's approval — never a real user's order.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use ref_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys. The 501 body also carries
//     "refill_supported":false, which the bot reads.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch line (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - SMM BRANCH (15 Nov 2026, api-order-smm.php): after the order
//     row is loaded, an order with a bot_smm_orders row is refilled
//     at SMM via smm_refill() instead of GodOfPanel. Same four-way
//     shape, so an SMM unsupported-action answer returns 501 with
//     refill_supported:false exactly like the GodOfPanel path.
//     Guarded by function_exists: when api-order-smm.php is not
//     installed yet, an SMM order falls through to the GodOfPanel
//     path and fails honestly with the provider's error. GodOfPanel
//     behaviour is unchanged.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL (see also the
//   "TO VERIFY" comments inside ref_provider_refill() and
//   ref_pick_order_field()):
//   A1. orders table: id, telegram_id (owner), status, service_id,
//       created_at. The code reads the row with SELECT * and picks
//       the owner / provider-id / service columns from a short
//       candidate list (primary name first), so a differently-named
//       column still works — but confirm the real names with SHOW
//       COLUMNS FROM orders and trim the lists.
//   A2. PROVIDER HELPER (biggest unknown — bot.php was not visible
//       from outside the server): this file ASSUMES bot.php defines
//       godofpanel_call(string $action, array $params): ?array,
//       returning the provider's decoded JSON reply (or null when the
//       provider could not be reached), and that POST /orders places
//       provider orders through it. If that helper exists with this
//       name and shape, ref_provider_refill() uses it. If it does NOT
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
//       keep only that one in ref_provider_key(). No key value is
//       written anywhere in this file.
//   A4. PROVIDER API (GodOfPanel v2, https://godofpanel.com/api/v2):
//       parameters go in the URL query string (key + action + order),
//       NOT in the POST body — a POST body fails with "Invalid API
//       key" (per the GodOfPanel connector doc). Refill is
//       action=refill&order=<provider order id>; the standard
//       success shape is {"refill": <provider refill id>}.
//       Refill status can be read back with action=refill_status&
//       refill=<refill id> ({"status": ..., "remains": ...}).
//       NEITHER SHAPE WAS VERIFIED LIVE against GodOfPanel — the
//       connector doc says only services/balance/add/status/cancel
//       were confirmed live, and refill is a standard action of the
//       same API family. TO VERIFY: run the live test and confirm
//       the refill reply shape; if the provider answers the refill
//       action with an "unknown action" style error, the endpoint
//       returns 501 (refill_supported:false) and the bot offers a
//       re-order instead — that path is the honest fallback, not a
//       failure to install.
//   A5. PROVIDER ORDER ID column on orders: api_order_id first,
//       then provider_order_id, provider_id. (GET /orders/{id} works
//       "by local id or provider api_order_id", so a provider id is
//       stored somewhere on the order.) If an order has NO provider
//       order id on record, the endpoint refuses with 409 — there
//       is nothing to refill at the provider.
//   A6. REFILLABLE CHECK: the provider is the authority on whether
//       a given order/service can be refilled (the provider's
//       services list carries a per-service `refill` boolean — 823
//       of 7,175 services in the 15 Nov 2026 snapshot — and its
//       refund policy confirms per-service refill guarantees).
//       This endpoint does NOT pre-check a local refill flag: it
//       asks the provider, and a provider refusal becomes the 409
//       with the provider's reason. If the server's own services
//       table carries a refill flag, the installer may add a
//       pre-check here — but the provider call stays the final word.
//   A7. auth table: tg_id + balance (same columns the deposits
//       endpoint credits — verified pattern, not an assumption).
//       No balance is touched by a refill: a refill is free to the
//       user (it tops up an order already paid for).
//   A8. No average-time / stuck check happens here: the bot calls
//       this endpoint only for an order the user asked to refill,
//       and only after its own completed-only check. Calling it for
//       a merely-slow (not completed) order is refused with 409.
// ============================================================================

// --- small helpers (ref_ prefix so nothing collides with bot.php) -----------

function ref_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function ref_fail($code, $msg, $extra = []) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(array_merge(
        ['success' => false, 'ok' => false, 'error' => $msg, 'message' => $msg],
        $extra
    ));
    exit;
}

function ref_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function ref_substr($text, $len) {
    // mb_substr keeps emoji intact when truncating; plain substr is
    // the fallback if mbstring is ever missing on the server.
    if (function_exists('mb_substr')) return mb_substr($text, 0, $len, 'UTF-8');
    return substr($text, 0, $len);
}

function ref_ensure_tables($db) {
    // utf8mb4, like the other bot tables. set_charset is idempotent —
    // harmless if bot.php already did it.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_order_refills (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        order_id BIGINT NOT NULL,
        telegram_id BIGINT NOT NULL,
        refill_id VARCHAR(64) NULL,
        status VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_bot_order_refills_order (order_id),
        INDEX idx_bot_order_refills_tg (telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Pick the first candidate column that exists on the row and is not
// null/empty. TO VERIFY (A1/A5): confirm the real orders column names
// with SHOW COLUMNS FROM orders and trim these lists. Primary name
// first in each list (telegram_id / api_order_id / service_id match
// the sibling cancel-refund endpoint's assumptions).
function ref_pick_order_field($row, $candidates) {
    foreach ($candidates as $col) {
        if (array_key_exists($col, $row) && $row[$col] !== null && $row[$col] !== '') {
            return $row[$col];
        }
    }
    return null;
}

// --- provider calls (ADAPTER — see A2/A3/A4; one spot to fix) ---------------

function ref_provider_key() {
    // VERIFIED 16 Nov 2026: bot.php uses GOP_API_KEY (config_secret.php
    // line 18, loaded via db.php); checked first, the rest are fallbacks.
    foreach (['GOP_API_KEY', 'GODOPANEL_API_KEY', 'GOD_OF_PANEL_API_KEY', 'PROVIDER_API_KEY', 'PANEL_API_KEY'] as $name) {
        if (defined($name) && constant($name) !== '') return (string)constant($name);
    }
    $env = getenv('GODOFPANEL_API_KEY');
    if ($env !== false && $env !== '') return $env;
    return null;
}

function ref_provider_base() {
    if (defined('GOP_API_URL') && GOP_API_URL !== '') return rtrim(GOP_API_URL, '/');
    if (defined('GODOPANEL_API_URL') && GODOPANEL_API_URL !== '') return rtrim(GODOPANEL_API_URL, '/');
    $env = getenv('GODOFPANEL_API_URL');
    if ($env !== false && $env !== '') return rtrim($env, '/');
    return 'https://godofpanel.com/api/v2';
}

// One raw provider call. Params go in the URL query string (the
// provider rejects a POST body with "Invalid API key"). Returns the
// decoded JSON reply as an array, or null when the provider could
// not be reached / did not answer JSON.
function ref_provider_raw($action, $params) {
    $key = ref_provider_key();
    if ($key === null) return null;
    $query = array_merge(['key' => $key, 'action' => $action], $params);
    $url = ref_provider_base() . '?' . http_build_query($query);
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
// offered? (Unknown / invalid action, not supported.) That is the
// 501 case: the bot offers a re-order instead. Any other provider
// error is a refusal for this order/service (409).
function ref_error_is_unsupported_action($error) {
    $low = strtolower(trim((string)$error));
    if ($low === '') return false;
    return (bool)preg_match(
        '/unknown action|invalid action|action.*not (supported|available|found)|not support|does not support|unsupported action|incorrect request/',
        $low
    );
}

// Refill one order at the provider.
// Returns ['refill_id' => string|null, 'status' => string,
//          'unsupported' => bool, 'refused' => bool,
//          'error' => string|null].
//   refill_id set   -> the provider accepted the refill.
//   unsupported     -> the provider does not offer the refill
//                      action at all (501 to the bot).
//   refused         -> the provider refused this order/service
//                      (409 to the bot, with the provider's reason).
//   otherwise       -> ambiguous (provider unreachable, reply not
//                      understood): the bot is told the refill
//                      could not be started (502), and may retry.
function ref_provider_refill($provider_order_id) {
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
            $res = godofpanel_call('refill', ['order' => $provider_order_id]);
        } catch (Throwable $e) {
            $res = null;
        }
    }
    if ($res === null && !$used_helper) {
        if (ref_provider_key() === null) {
            return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => false, 'error' => 'Provider is not configured.'];
        }
        $res = ref_provider_raw('refill', ['order' => $provider_order_id]);
    }
    if ($res === null) {
        return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => false, 'error' => 'Provider did not answer. No refill was made.'];
    }

    // An explicit provider error: either the action is not offered
    // at all (501) or this order/service cannot be refilled (409).
    // Never invent a reason — return the provider's own words.
    if (isset($res['error']) && $res['error'] !== '') {
        $msg = (string)$res['error'];
        if (ref_error_is_unsupported_action($msg)) {
            return ['refill_id' => null, 'status' => '', 'unsupported' => true, 'refused' => false, 'error' => $msg];
        }
        return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => true, 'error' => $msg];
    }

    // Refill accepted? The standard success shape is
    // {"refill": <provider refill id>} (TO VERIFY, A4).
    if (isset($res['refill']) && $res['refill'] !== '' && $res['refill'] !== null) {
        $status = isset($res['status']) ? strtolower(trim((string)$res['status'])) : 'success';
        return ['refill_id' => (string)$res['refill'], 'status' => $status, 'unsupported' => false, 'refused' => false, 'error' => null];
    }

    // Reply arrived but said neither yes nor error — do not guess.
    return ['refill_id' => null, 'status' => '', 'unsupported' => false, 'refused' => false, 'error' => 'Provider reply was not understood. No refill was made.'];
}

// SMM branch (api-order-smm.php): refill an SMM order at SMM,
// with the same four-way return shape as ref_provider_refill().
// When the SMM file is not installed yet, smm_refill() does not
// exist and the call falls back to the GodOfPanel path, which fails
// honestly with the provider's error — never silently. An SMM
// unsupported-action answer returns 501 with refill_supported:false
// through the same code path as the GodOfPanel one below.
function ref_provider_refill_smm($provider_order_id) {
    if (!function_exists('smm_refill')) return ref_provider_refill($provider_order_id);
    return smm_refill($provider_order_id);
}

// --- POST /api/bot/orders/{id}/refill ---------------------------------------

function bot_ref_refill($order_id) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') ref_fail(405, 'Method not allowed.');
    $in = ref_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) ref_fail(400, 'telegram_id is required.');
    if ($order_id <= 0) ref_fail(400, 'order id is required.');

    $db = ref_db();
    if ($db === null) ref_fail(500, 'Database is not available.');
    ref_ensure_tables($db);

    // 1. Load the order and check ownership + completed state. A
    //    different telegram_id asking for the same order gets the
    //    same 404 as a missing order (no leaking).
    $stmt = $db->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) ref_fail(404, 'Order not found.');
    $owner = ref_pick_order_field($row, ['telegram_id', 'user_id', 'tg_id']);
    if ($owner === null || (int)$owner !== $telegram_id) ref_fail(404, 'Order not found.');

    $status = strtolower(trim((string)($row['status'] ?? '')));
    $completed = ['completed', 'complete', 'success', 'paid', 'done'];
    if (!in_array($status, $completed, true)) {
        ref_fail(409, 'Only completed orders can be refilled (this order is ' . ($status !== '' ? $status : 'in an unknown state') . ').');
    }

    $service_id = (int)(ref_pick_order_field($row, ['service_id', 'provider_service_id']) ?? 0);

    // The provider's own order number — without it there is nothing
    // to refill at the provider, so refuse rather than guess.
    $provider_order_id = ref_pick_order_field($row, ['api_order_id', 'provider_order_id', 'provider_id']);
    if ($provider_order_id === null) {
        ref_fail(409, 'Order has no provider order id on record, so it cannot be refilled at the provider.');
    }
    $provider_order_id = (string)$provider_order_id;

    // SMM branch (api-order-smm.php): an SMM order is refilled at
    // SMM, not GodOfPanel. Guarded by function_exists — when the SMM
    // file is not installed yet, smm_is_smm_order() does not exist,
    // $is_smm is false, and the order falls through to the GodOfPanel
    // path below, which fails honestly with the provider's error.
    $is_smm = function_exists('smm_is_smm_order') && smm_is_smm_order($db, $order_id);

    // 2. Refill at the provider. No row is recorded on any failure
    //    path below.
    $refill = $is_smm
        ? ref_provider_refill_smm($provider_order_id)
        : ref_provider_refill($provider_order_id);
    if ($refill['refill_id'] === null) {
        if (!empty($refill['unsupported'])) {
            ref_fail(501, 'Provider does not offer refills.', ['refill_supported' => false]);
        }
        if (!empty($refill['refused'])) {
            ref_fail(409, 'Provider refused the refill: ' . ref_substr((string)($refill['error'] ?? 'refill not available for this order'), 200));
        }
        ref_fail(502, $refill['error'] ?? 'Provider did not confirm the refill. No refill was made.');
    }
    $refill_id = $refill['refill_id'];
    $provider_status = $refill['status'] !== '' ? ref_substr($refill['status'], 64) : 'success';

    // 3. Record the refill. A failure here never claims the refill
    //    did not happen at the provider — it only means the record
    //    was not kept, so the bot is told plainly (500) instead of
    //    being given a success with no record.
    $stmt = $db->prepare('INSERT INTO bot_order_refills (order_id, telegram_id, refill_id, status) VALUES (?, ?, ?, ?)');
    $stmt->bind_param('iiss', $order_id, $telegram_id, $refill_id, $provider_status);
    $inserted = false;
    try {
        $inserted = $stmt->execute();
    } catch (mysqli_sql_exception $e) {
        $inserted = false;
    }
    $stmt->close();
    if (!$inserted) {
        ref_fail(500, 'Refill was accepted by the provider (refill ' . ref_substr($refill_id, 64) . ') but could not be recorded. Please contact support with the refill number.');
    }

    bot_ok([
        'ok' => true,
        'order_id' => $order_id,
        'refill_id' => $refill_id,
        'provider_status' => $provider_status,
        'duplicate' => false,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if (preg_match('#^orders/(\d+)/refill$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_ref_refill((int)$m[1]); }
//
// (Add the same bot_rate_limit(...) call the other user endpoints use
// to that dispatch line — copy the exact call from the orders
// handler; the signature was not visible from outside the server.)
//
// LIVE CURL TEST — read this whole block before running it. The test
// REFILLS a real completed order at the provider on purpose (that is
// the point), so it must use a SMALL COMPLETED TEST order placed for
// this test, with William's approval, on the operating account —
// NEVER a real user's order. A refill tops the order up for free
// (no balance is touched), so the test is net-zero on the Paxyo
// balance.
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. Confirm the test order N is completed:
//   curl -s "https://paxyo.et/api/bot/orders/N?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect the order with status "completed".
//   # 2. Refill it:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/refill \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true,"order_id":N,
//      "refill_id":"<provider refill id>","provider_status":"success",
//      "duplicate":false}
//   # 3. Check the refill was recorded:
//   mysql -e "SELECT * FROM bot_order_refills WHERE order_id=N;"
//   # 4. Wrong owner must get a 404 (no leaking whether the order
//   #    exists):
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/refill \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":1}'
//   -> expect {"success":false,"error":"Order not found."}
//   # 5. A pending order must refuse with 409 (use a known pending
//   #    order id — this call touches nothing):
//   curl -s -X POST https://paxyo.et/api/bot/orders/<pending-id>/refill \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":false,"error":"Only completed orders ..."}.
//   # 6. If the provider answers the refill action as unknown /
//   #    not supported, expect HTTP 501 with
//   #    {"success":false,"ok":false,"refill_supported":false,...}
//   #    — that is the honest fallback path, and the bot will offer
//   #    a re-order instead. Do NOT treat a 501 as a failed install.
//   Then DELETE the test refill row and confirm it is gone (the
//   completed test order row itself stays, status 'completed'):
//   mysql -e "DELETE FROM bot_order_refills WHERE order_id=N AND telegram_id=779060335; SELECT COUNT(*) FROM bot_order_refills WHERE order_id=N;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
