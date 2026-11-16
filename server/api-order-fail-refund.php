<?php
// ============================================================================
// Fail-refund (failed-order rescue) for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot:
// William's cross-provider fallback (18:46 EAT) — when an order
// FAILS at the provider, the bot refunds it and re-places it on the
// next-fastest service, even on the other provider.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/orders/{id}/fail-refund   {telegram_id}
//     -> {"ok":true,"order_id":N,"refunded_etb":X,
//         "provider_status":"failed","duplicate":false}
//     A second call for the same order_id returns the recorded result
//     with "duplicate":true and NEVER refunds a second time.
//
// FLOW (in order — money moves only at step 4, and only after the
// provider's OWN live status says the order ended failed):
//   1. A fail-refund row already exists for this order_id -> return
//      it. (This is what makes a retry / duplicate call safe.)
//   2. Load the order. It must belong to telegram_id. A completed
//      order is NEVER touched; an already refunded order, or a
//      cancelled order that a cancel path already refunded (a row
//      in bot_order_rescues / bot_order_cancels), gets an honest
//      409 and no second refund. A stored 'cancelled' with NO such
//      row is a PROVIDER-cancelled order, never refunded — it may
//      proceed (cancel-cutting, 16 Nov 2026). A stored status of
//      "failed" is NOT refused here — the live provider word below
//      is authoritative, and the stored word may be stale.
//   3. Read the provider's LIVE status for the provider order id
//      (GodOfPanel via godofpanel_call() with a direct-call
//      fallback; SMM via smm_order_status(), guarded by
//      function_exists — when api-order-smm.php is not installed
//      yet an SMM order falls through to the GodOfPanel path and
//      fails honestly). Refund ONLY when the live word is failed /
//      canceled / cancelled — the provider already ended the order,
//      so NO provider cancel call is made (unlike the stall-rescue
//      endpoint, which cancels a live order first). Any other live
//      word (pending / processing / completed / partial / ...) gets
//      an honest 409 and NO refund — the order may still complete,
//      and the bot keeps watching it. If the provider cannot be
//      reached at all, 502 and NO refund; the bot retries later.
//   4. In ONE database transaction: re-check the fail-refund table
//      (a concurrent duplicate may have refunded already), mark
//      the order refunded, credit the FULL stored order total back
//      to the user's Paxyo balance (auth.balance, keyed by tg_id —
//      the same credit the deposits endpoint does), and insert the
//      fail-refund row. Any failure rolls everything back; the
//      balance is untouched.
//
// THE SERVER NEVER PLACES THE REPLACEMENT ORDER. After a successful
// refund the bot re-places the order itself, on the next-best
// service (across providers), through the existing POST /orders
// (GodOfPanel) or POST /orders/smm endpoints. The bot — not this
// endpoint — decides an order failed: the failed rule lives in
// bot.py (the delivery watch reads the provider status each cycle;
// "failed" triggers the failed-rescue attempt). This endpoint only
// enforces ownership, a failed live provider status, and a
// once-ever refund.
//
// WHY "failed" ONLY — never "canceled"/"cancelled" from the BOT's
// side: the bot only calls this endpoint when the WATCH saw the
// provider word "failed" (or, since the cancel-cutting build of
// 16 Nov 2026, "cancelled"/"canceled" from the PROVIDER — see the
// note below). A user-cancelled order (round-3 cancel feature) is
// refunded by the cancel endpoint instead, and re-placing it would
// undo the user's own cancel. A "refunded" order is already
// refunded. The live-word check here is the second guard: even if
// the watch was wrong, a provider word of "completed" or
// "processing" refuses the refund.
//
// CANCEL-CUTTING (16 Nov 2026): a PROVIDER-cancelled order IS
// refundable here now — but ONLY when no refund was already paid
// for it. The stored status of a bot-cancelled order (stall
// rescue, auto-cancel) is also 'cancelled', and its refund lives
// in bot_order_rescues; a user-cancelled order's refund lives in
// bot_order_cancels. So a stored 'cancelled'/'canceled' is
// refunded here only when NEITHER table has a row for this order
// (frf_has_refund_row below); when either has one the order was
// already refunded and this call 409s, exactly as before. The
// live-word check (failed / canceled / cancelled) still runs
// after this, so a stored 'cancelled' whose provider word is
// anything else still refuses.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_order_fail_refunds  id AUTO_INCREMENT PK, order_id BIGINT
//      UNIQUE (the Paxyo orders.id — one fail-refund per order,
//      ever), telegram_id, service_id, refunded_etb DECIMAL(12,2),
//      provider_status VARCHAR(64) (the provider's word for the
//      failed order, e.g. "failed"), provider_order_id VARCHAR(64)
//      (the provider's own order number, for the admin to check),
//      created_at.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-order-fail-refund.php   (this file must pass)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH
//      LINES (see the bottom of this file) before the 404 fallback,
//      then append this file's code WITHOUT its first line (the
//      "<?php" opening tag — bot.php is already inside one PHP
//      block) to the end of bot.php.
//   3. php -l api/bot.php                (must pass before live)
//   4. Live curl test (see the bottom of this file) then DELETE
//      the test fail-refund row. The test refunds a REAL test order
//      that failed at the provider on purpose (that is the point),
//      so use a small test order only, with William's approval —
//      never a real user's order.
//
// NOTES FOR THE INSTALLER (check these against the live files):
//   - This file is SELF-CONTAINED: it defines its own frf_*
//     helpers and uses only bot_ok() (the standard success reply
//     every endpoint uses) plus the global $db handle from bot.php.
//     It does NOT depend on the stall-rescue file's helpers.
//   - Add the same bot_rate_limit(...) call the other user
//     endpoints use to the dispatch line (copy the exact call from
//     the orders handler — the signature was not visible from
//     outside the server).
//   - SMM BRANCH: after the order row is loaded, an order with a
//     bot_smm_orders row reads its live status from SMM via
//     smm_order_status() instead of GodOfPanel — that one
//     delegation covers the provider touch. Guarded by
//     function_exists: when api-order-smm.php is not installed yet,
//     an SMM order falls through to the GodOfPanel path and fails
//     honestly with the provider's error. GodOfPanel behaviour is
//     unchanged.
//   - The refund is the FULL stored order total (the same policy
//     as the stall rescue). The Terms' "remaining amount" wording
//     vs full-total refund is an open question for William — see
//     the stall-rescue file's header (A7); settle it before
//     go-live if the policy changes, and change it in both files.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. orders table: id, telegram_id (owner), total (the ETB total
//       the customer paid), status, service_id, created_at. The
//       code reads the row with SELECT * and picks the owner /
//       total / provider-id / service columns from a short
//       candidate list (primary name first), so a differently-named
//       column still works — but confirm the real names with SHOW
//       COLUMNS FROM orders and trim the lists.
//   A2. PROVIDER HELPER (biggest unknown — bot.php was not visible
//       from outside the server): this file ASSUMES bot.php defines
//       godofpanel_call(string $action, array $params): ?array,
//       returning the provider's decoded JSON reply (or null when
//       the provider could not be reached), and that POST /orders
//       places provider orders through it. If that helper exists
//       with this name and shape, frf_gop_status() uses it. If it
//       does NOT exist, or has a different name/signature, the call
//       is caught and the file falls back to a direct provider call
//       (same curl style as api-deposits.php) — so the endpoint
//       still works, but the installer MUST check bot.php and
//       either rename the helper in the one marked ADAPTER spot or
//       confirm the fallback's key lookup matches how bot.php
//       authenticates to the provider.
//   A3. PROVIDER KEY: the fallback looks for a defined constant
//       GODOPANEL_API_KEY, GOD_OF_PANEL_API_KEY, PROVIDER_API_KEY
//       or PANEL_API_KEY (in config_secret.php), then getenv
//       ('GODOFPANEL_API_KEY'). TO VERIFY: find the constant
//       bot.php actually uses for the provider key when placing
//       orders and keep only that one in frf_gop_key(). No key value
//       is written anywhere in this file.
//   A4. PROVIDER API (GodOfPanel v2, https://godofpanel.com/api/v2):
//       parameters go in the URL query string (key + action +
//       order), NOT in the POST body — a POST body fails with
//       "Invalid API key" (per the GodOfPanel connector doc).
//       Status is action=status&order=<provider order id>; the
//       reply carries a "status" string. The exact status spellings
//       were NOT verified live — after the live test, confirm the
//       spellings this panel returns (pending / processing / in
//       progress / partial / completed / failed / canceled).
//   A5. PROVIDER ORDER ID column on orders: api_order_id first,
//       then provider_order_id, provider_id. (GET /orders/{id}
//       works "by local id or provider api_order_id", so a provider
//       id is expected on the row.)
//   A6. SMM status words: smm_order_status() (api-order-smm.php)
//       lowercases the SMM panel's status word; the exact
//       spellings SMM returns are unverified until the live test.
//       The fail-refund check accepts failed / canceled /
//       cancelled — if SMM spells a failed order differently,
//       add that spelling to FRF_FAILED_WORDS below.
//   A7. The bot's fail_refund() client treats 404 as "endpoint
//       not live yet" (returns None) and raises on every other
//       error, so a 409/502 here must carry a clear error string.
// ============================================================================

// The live provider words that mean "the provider ended this order
// with no delivery, so a refund is safe". Anything else refuses.
const FRF_FAILED_WORDS = ['failed', 'canceled', 'cancelled'];
// Stored statuses a fail-refund must never touch.
const FRF_FINAL_WORDS = ['completed', 'complete', 'success', 'paid',
    'cancelled', 'canceled', 'refunded'];
// Stored statuses the order may be in when the refund lands. The
// stored word is usually "failed" itself — that MUST be in the list,
// or the UPDATE below would affect 0 rows and the refund would fail.
const FRF_REFUNDABLE_WORDS = ['pending', 'processing', 'in progress',
    'inprogress', 'queued', 'failed'];

function frf_fail($code, $message) {
    http_response_code((int)$code);
    header('Content-Type: application/json');
    echo json_encode([
        'success' => false, 'error' => $message, 'message' => $message,
    ]);
    exit;
}

function frf_ensure_tables($db) {
    $db->query("CREATE TABLE IF NOT EXISTS bot_order_fail_refunds (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        order_id BIGINT NOT NULL,
        telegram_id BIGINT NOT NULL,
        service_id INT NOT NULL DEFAULT 0,
        refunded_etb DECIMAL(12,2) NOT NULL DEFAULT 0.00,
        provider_status VARCHAR(64) NOT NULL DEFAULT '',
        provider_order_id VARCHAR(64) NOT NULL DEFAULT '',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_order (order_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
}

function frf_row($db, $order_id) {
    $stmt = $db->prepare('SELECT order_id, telegram_id, service_id, refunded_etb, provider_status, provider_order_id, created_at FROM bot_order_fail_refunds WHERE order_id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

function frf_reply($row) {
    return [
        'ok' => true,
        'order_id' => (int)$row['order_id'],
        'refunded_etb' => (float)$row['refunded_etb'],
        'provider_status' => (string)$row['provider_status'],
    ];
}

// First non-null field from the candidate list (primary name first).
function frf_pick($row, $candidates) {
    foreach ($candidates as $name) {
        if (array_key_exists($name, $row) && $row[$name] !== null) {
            return $row[$name];
        }
    }
    return null;
}

// Was this order ALREADY refunded by a cancel path? A bot-requested
// cancel (stall rescue, auto-cancel) records in bot_order_rescues;
// a user-requested cancel records in bot_order_cancels (round-3
// cancel file, api-order-cancel.php — parked, may not be installed).
// Either row means "already refunded": a stored 'cancelled' order
// with a row here must never be refunded again. A missing table
// (file never installed) reads as "no row", never a 500.
function frf_has_refund_row($db, $order_id) {
    foreach (['bot_order_rescues', 'bot_order_cancels'] as $table) {
        try {
            $stmt = $db->prepare(
                "SELECT order_id FROM $table WHERE order_id = ? LIMIT 1"
            );
            $stmt->bind_param('i', $order_id);
            $stmt->execute();
            $found = $stmt->get_result()->fetch_assoc();
            $stmt->close();
            if ($found) return true;
        } catch (Throwable $e) {
            continue;
        }
    }
    return false;
}

// --- GodOfPanel status read -------------------------------------------
// ADAPTER (A2/A3): keep only the constant bot.php actually uses.
function frf_gop_key() {
    foreach (['GODOPANEL_API_KEY', 'GOD_OF_PANEL_API_KEY',
              'PROVIDER_API_KEY', 'PANEL_API_KEY'] as $name) {
        if (defined($name) && constant($name) !== '') {
            return (string)constant($name);
        }
    }
    $env = getenv('GODOFPANEL_API_KEY');
    return $env !== false && $env !== '' ? (string)$env : null;
}

function frf_gop_raw($action, $params) {
    $key = frf_gop_key();
    if ($key === null) return null;
    $query = http_build_query(array_merge(
        ['key' => $key, 'action' => $action], $params
    ));
    $ch = curl_init('https://godofpanel.com/api/v2?' . $query);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, '');
    $body = curl_exec($ch);
    curl_close($ch);
    if ($body === false || $body === '') return null;
    $decoded = json_decode($body, true);
    return is_array($decoded) ? $decoded : null;
}

// Read the provider's own status for one provider order id.
// Returns the lowercased status string or null when the provider
// could not be reached.
function frf_gop_status($provider_order_id) {
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
    $res = frf_gop_raw('status', ['order' => $provider_order_id]);
    if ($res === null || !isset($res['status'])) return null;
    return strtolower(trim((string)$res['status']));
}

// --- SMM status read (api-order-smm.php) -------------------------------
function frf_smm_status($provider_order_id) {
    if (!function_exists('smm_order_status')) return null;
    try {
        $res = smm_order_status($provider_order_id);
    } catch (Throwable $e) {
        return null;
    }
    if (!is_array($res) || !isset($res['status'])) return null;
    if ($res['status'] === null || $res['status'] === '') return null;
    return strtolower(trim((string)$res['status']));
}

// --- Main endpoint ------------------------------------------------------
function bot_fail_refund_order($order_id) {
    global $db;
    $input = json_decode(file_get_contents('php://input'), true);
    if (!is_array($input)) $input = [];
    $telegram_id = (int)($input['telegram_id'] ?? 0);
    if ($telegram_id <= 0) {
        frf_fail(400, 'telegram_id is required.');
    }
    frf_ensure_tables($db);

    // 1. A fail-refund row already exists -> return it, never twice.
    $existing = frf_row($db, $order_id);
    if ($existing !== null) {
        if ((int)$existing['telegram_id'] !== $telegram_id) {
            frf_fail(404, 'Order not found.');
        }
        bot_ok(array_merge(frf_reply($existing), ['duplicate' => true]));
        return;
    }

    // 2. Load the order; it must belong to telegram_id.
    $stmt = $db->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    $owner = $row ? frf_pick($row, ['telegram_id', 'tg_id', 'user_id']) : null;
    if (!$row || $owner === null || (int)$owner !== $telegram_id) {
        frf_fail(404, 'Order not found.');
    }
    $status = strtolower(trim((string)($row['status'] ?? '')));
    if (in_array($status, FRF_FINAL_WORDS, true)) {
        // Cancel-cutting (16 Nov 2026): a stored 'cancelled' /
        // 'canceled' is refundable ONLY when no cancel path already
        // refunded it (no bot_order_rescues / bot_order_cancels
        // row) — that is a provider-cancelled order, never
        // refunded. Any other final word, or a cancelled order
        // with a refund row, still 409s.
        $cancelled_word = in_array($status, ['cancelled', 'canceled'], true);
        if (!($cancelled_word && !frf_has_refund_row($db, $order_id))) {
            frf_fail(409, 'Order is already ' . $status . ' and cannot be refunded again.');
        }
    }

    $service_id = (int)(frf_pick($row, ['service_id', 'provider_service_id']) ?? 0);
    $total = frf_pick($row, ['total', 'charge', 'amount']);
    if ($total === null || !is_numeric($total)) {
        frf_fail(500, 'Order total is not on record, so no refund can be made.');
    }
    $refund = round((float)$total, 2);

    // The provider's own order number — without it there is nothing
    // to verify at the provider, so refuse rather than refund blind.
    $provider_order_id = frf_pick($row, ['api_order_id', 'provider_order_id', 'provider_id']);
    if ($provider_order_id === null || (string)$provider_order_id === '') {
        frf_fail(409, 'Order has no provider order id on record, so its provider status cannot be checked. No refund was made.');
    }
    $provider_order_id = (string)$provider_order_id;

    // SMM branch (api-order-smm.php): an SMM order reads its live
    // status from SMM, not GodOfPanel. Guarded by function_exists —
    // when the SMM file is not installed yet, smm_is_smm_order()
    // does not exist, $is_smm is false, and the order falls through
    // to the GodOfPanel path below, which fails honestly with the
    // provider's error.
    $is_smm = function_exists('smm_is_smm_order') && smm_is_smm_order($db, $order_id);

    // 3. Read the LIVE provider status. No provider cancel call is
    //    made here — the provider already ended the order.
    $live = $is_smm
        ? frf_smm_status($provider_order_id)
        : frf_gop_status($provider_order_id);
    if ($live === null || $live === '') {
        frf_fail(502, 'Provider did not answer the status check. No refund was made.');
    }
    if (!in_array($live, FRF_FAILED_WORDS, true)) {
        if ($live === 'partial') {
            frf_fail(409, 'Provider status is partial — use the partial refund path, not fail-refund. No refund was made.');
        }
        frf_fail(409, 'Provider status is ' . $live . ', not failed. No refund was made.');
    }
    $provider_status = substr($live, 0, 64);

    // 4. Atomic refund: re-check the fail-refund table under lock,
    //    mark the order refunded, credit the balance, record the
    //    refund. Any failure rolls the whole thing back.
    $db->begin_transaction();
    $stmt = $db->prepare('SELECT order_id FROM bot_order_fail_refunds WHERE order_id = ? FOR UPDATE');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $locked = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if ($locked) {
        $db->rollback();
        $again = frf_row($db, $order_id);
        if ($again !== null && (int)$again['telegram_id'] === $telegram_id) {
            bot_ok(array_merge(frf_reply($again), ['duplicate' => true]));
            return;
        }
        frf_fail(409, 'Order was already refunded.');
    }

    // The order may have finished while the provider call was in
    // flight — re-check its status under lock before touching money.
    $stmt = $db->prepare('SELECT status FROM orders WHERE id = ? FOR UPDATE');
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $fresh = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    $fresh_status = strtolower(trim((string)($fresh['status'] ?? '')));
    if (!$fresh || in_array($fresh_status, FRF_FINAL_WORDS, true)) {
        // Same provider-cancelled exception as the step-2 check
        // above: a stored 'cancelled' with no refund row may still
        // be refunded (the live word was already verified as
        // failed / canceled / cancelled).
        $fresh_cancelled = in_array($fresh_status, ['cancelled', 'canceled'], true);
        if (!($fresh_cancelled && !frf_has_refund_row($db, $order_id))) {
            $db->rollback();
            frf_fail(409, 'Order is no longer refundable (status: ' . ($fresh_status !== '' ? $fresh_status : 'unknown') . '). No refund was made.');
        }
    }

    $stmt = $db->prepare("UPDATE orders SET status = 'refunded' WHERE id = ? AND status IN ('pending','processing','in progress','inprogress','queued','failed','cancelled','canceled')");
    $stmt->bind_param('i', $order_id);
    $stmt->execute();
    $order_changed = $stmt->affected_rows;
    $stmt->close();
    if ($order_changed !== 1) {
        $db->rollback();
        frf_fail(409, 'Order is no longer refundable. No refund was made.');
    }

    // Credit exactly once: the fail-refund row UNIQUE key + the
    // checks above are what stop a duplicate credit, not this
    // UPDATE. (Same credit shape as the deposits endpoint:
    // auth.balance keyed by tg_id.)
    $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
    $stmt->bind_param('di', $refund, $telegram_id);
    $stmt->execute();
    $balance_changed = $stmt->affected_rows;
    $stmt->close();
    if ($balance_changed !== 1) {
        $db->rollback();
        frf_fail(500, 'Could not credit the balance. No refund was made.');
    }

    // Insert the fail-refund record. A duplicate key here (1062)
    // means a concurrent call won the race — roll back and return
    // its row.
    $stmt = $db->prepare('INSERT INTO bot_order_fail_refunds (order_id, telegram_id, service_id, refunded_etb, provider_status, provider_order_id) VALUES (?, ?, ?, ?, ?, ?)');
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
            $again = frf_row($db, $order_id);
            if ($again !== null && (int)$again['telegram_id'] === $telegram_id) {
                bot_ok(array_merge(frf_reply($again), ['duplicate' => true]));
                return;
            }
        }
        frf_fail(500, 'Could not record the refund. No refund was made.');
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
//   if (preg_match('#^orders/(\d+)/fail-refund$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_fail_refund_order((int)$m[1]); }
//
// (Add the same bot_rate_limit(...) call the other user endpoints use
// to that dispatch line — copy the exact call from the orders
// handler; the signature was not visible from outside the server.)
//
// LIVE CURL TEST — read this whole block before running it. The test
// refunds a REAL test order that FAILED at the provider (that is the
// point), so it must use a SMALL TEST order, with William's
// approval, on the operating account — NEVER a real user's order.
// To make a test order fail at the provider, place it on a service
// that is known to fail (or ask the provider's support for a failed
// test order) and confirm the provider status reads "failed" first.
// The refund returns the full order total, so the test is net-zero
// on the Paxyo balance (the provider must report failed for the
// refund to happen at all).
//   SECRET=<redacted>(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. Confirm the test order reads failed at the provider:
//   curl -s "https://paxyo.et/api/bot/orders/N?telegram_id=779060335" \
//     -H "X-Bot-Secret: <redacted>
//   -> expect the order with status "failed".
//   # 2. Fail-refund it:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/fail-refund \
//     -H "X-Bot-Secret: <redacted>
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true,"order_id":N,
//      "refunded_etb":<the order total>,"provider_status":"failed",
//      "duplicate":false}
//   # 3. Check the balance went back up by exactly the order total:
//   curl -s "https://paxyo.et/api/bot/balance?telegram_id=779060335" \
//     -H "X-Bot-Secret: <redacted>
//   # 4. Call it AGAIN — the same order must NOT refund twice:
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/fail-refund \
//     -H "X-Bot-Secret: <redacted>
//     -d '{"telegram_id":779060335}'
//   -> expect the SAME refunded_etb with "duplicate":true, and the
//      balance from step 3 UNCHANGED.
//   # 5. Wrong owner must get a 404 (no leaking whether the order
//   #    exists):
//   curl -s -X POST https://paxyo.et/api/bot/orders/N/fail-refund \
//     -H "X-Bot-Secret: <redacted>
//     -d '{"telegram_id":1}'
//   -> expect {"success":false,"error":"Order not found."}
//   # 6. A still-pending order must refuse with 409 (use a known
//   #    pending order id — this call touches nothing):
//   curl -s -X POST https://paxyo.et/api/bot/orders/<pending-id>/fail-refund \
//     -H "X-Bot-Secret: <redacted>
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":false,"error":"Provider status is ...,
//      not failed. No refund was made."}.
//   # 7. A completed order must refuse with 409 (same shape as
//   #    step 6, with a completed order id — touches nothing).
//   Then DELETE the test fail-refund row and confirm it is gone
//   (the refunded test order row itself stays, status 'refunded' —
//   that is the honest record of what happened):
//   mysql -e "DELETE FROM bot_order_fail_refunds WHERE order_id=N AND telegram_id=779060335; SELECT COUNT(*) FROM bot_order_fail_refunds WHERE order_id=N;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
