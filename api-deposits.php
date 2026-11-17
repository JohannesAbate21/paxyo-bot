<?php
// ============================================================================
// Deposit endpoints for the Paxyo Bot API (public_html/api/bot.php).
// Written 13 Nov 2026 for @paxorder_bot deposit-by-chat (USSD push, no link).
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php,
// except the Chapa callback and the popup payment exchange — see below):
//   POST /api/bot/deposits                 {telegram_id, amount[, method, phone]}
//     -> amount-only (owner, 17 Nov 2026 — the bot asks for the amount
//        only in chat): {"deposit_id","popup_token","status":"pending",
//        "pushed":false,"auth_type":"popup"}. No Chapa call yet, no
//        checkout URL yet: the bot exchanges the one-time
//        popup_token for the checkout (next endpoint) right after
//        Confirm. The token is
//        a random 32-hex-char key stored on the deposit row; it can
//        only complete THAT one pending deposit — it cannot read,
//        change or spend anything else, and it dies with the deposit
//        (completed / failed / 48h). The bot NEVER holds a
//        secret or API key and NEVER creates a deposit itself.
//     -> with method + phone (the old full create, kept for other
//        callers): {"deposit_id","pushed":true,"auth_type":"ussd",
//        "status":"pending"} (Direct Charge USSD push, when Chapa
//        allows it), or {"deposit_id","pushed":false,
//        "auth_type":"checkout","checkout_url":"https://checkout.
//        chapa.co/...","status":"pending"} (standard Chapa checkout
//        fallback — 16 Nov 2026 — when Direct Charge is refused).
//        Methods: telebirr, cbe, cbebirr, mpesa.
//   POST /api/bot/deposits/{id}/payment   {token[, method, phone]}
//     -> the bot's exchange, right after Confirm: validates the
//        one-time token for THAT pending deposit (no X-Bot-Secret
//        — the token IS the auth, so this route must be exempt
//        from the secret check like the callback), then starts the
//        payment and returns {"deposit_id","pushed","auth_type",
//        "checkout_url","status":"pending"}. With no method/phone
//        (owner, 17 Nov 2026) the Direct Charge attempt is skipped
//        and the Chapa checkout is initialised straight away —
//        Chapa collects the method + phone on its own checkout
//        page, so the user never picks them in the bot or a popup.
//        With method + phone (the old popup exchange) the Direct
//        Charge attempt still runs first. Repeating the call with
//        the same token returns the SAME checkout URL —
//        never a second charge.
//   POST /api/bot/deposits/callback        {tx_ref, ...} (from Chapa)
//     -> always 200; verifies with Chapa and credits once, same rules
//        as the recheck below — so a user who pays gets credited
//        automatically, with no "I paid" tap at all. The bot's
//        scheduler (bot.py run_deposit_credit_cycle) watches the
//        deposit and messages the user the moment it completes.
//        Chapa calls it WITHOUT the X-Bot-Secret, so its dispatch
//        must be exempt from the secret check (see bot_dep_callback).
//   GET  /api/bot/deposits?telegram_id=X&limit=5
//     -> {"deposits":[{"id","amount","method","phone","status","created_at"}]}
//   GET  /api/bot/deposits/{id}?telegram_id=X
//     -> {"deposit":{"id","amount","method","phone","status","created_at"}}
//        Re-verifies with Chapa first when the deposit is still pending,
//        and credits once only — same rules as recheck_deposit.php.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-deposits.php            (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then append
//      this file's code WITHOUT its first line (the "<?php" opening tag —
//      bot.php is already inside one PHP block) to the end of bot.php.
//   3. php -l api/bot.php                 (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the test row.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as on
//     the other endpoints). Errors use dep_fail() below, which returns
//     {"success":false,"error":...,"message":...} — the bot reads both keys.
//   - The deposits table has NO method/phone columns, so method+phone are
//     stored as JSON in chapa_response and read back from there.
//   - If deposits.bot_id is NOT NULL without a default, add the same value
//     chapa_init.php uses to the INSERT in bot_dep_create().
//   - Add the same bot_rate_limit(...) call the other user endpoints use
//     to the three dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - Minimum deposit is 10 ETB (mirrors chapa_init.php); maximum 100,000.
//   - This code NEVER credits a balance except in bot_dep_status(), only
//     after Chapa verify says success AND the amounts match exactly.
// ============================================================================

// --- small helpers (dep_ prefix so nothing collides with bot.php) -----------

function dep_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function dep_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function dep_chapa_secret() {
    if (defined('CHAPA_SECRET_KEY') && CHAPA_SECRET_KEY !== '') return CHAPA_SECRET_KEY;
    $env = getenv('CHAPA_SECRET_KEY');
    if ($env !== false && $env !== '') return $env;
    if (file_exists(__DIR__ . '/../chapa_config.php')) {
        require_once __DIR__ . '/../chapa_config.php';
        if (defined('CHAPA_SECRET_KEY') && CHAPA_SECRET_KEY !== '') return CHAPA_SECRET_KEY;
    }
    return null;
}

function dep_chapa_base() {
    if (defined('CHAPA_BASE_URL') && CHAPA_BASE_URL !== '') return rtrim(CHAPA_BASE_URL, '/');
    $env = getenv('CHAPA_BASE_URL');
    if ($env !== false && $env !== '') return rtrim($env, '/');
    return 'https://api.chapa.co/v1';
}

// One-time popup token: 32 hex chars of randomness, stored on
// the deposit row (chapa_response.popup_token). It is NOT a
// shared secret: it is minted per deposit, bound to that deposit
// id, and usable only to complete that one pending deposit.
function dep_popup_token() {
    return bin2hex(random_bytes(16));
}

function dep_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

// 09xxxxxxxx / 07xxxxxxxx / 2519xxxxxxxx / +2519xxxxxxxx -> 2519xxxxxxxx.
// Strict: the result must be 251 + 9 or 7 + 8 digits. A 9-digit example
// number (missing a digit) is rejected here; the bot lets the server decide.
function dep_normalize_phone($raw) {
    $d = preg_replace('/[^0-9]/', '', (string)$raw);
    if ($d === '') return null;
    if (strpos($d, '251') === 0) $n = $d;
    elseif (strpos($d, '0') === 0) $n = '251' . substr($d, 1);
    elseif (strlen($d) === 9) $n = '251' . $d;
    else return null;
    if (!preg_match('/^251[79][0-9]{8}$/', $n)) return null;
    return $n;
}

function dep_deposit_record($row) {
    $meta = [];
    if (!empty($row['chapa_response'])) {
        $decoded = json_decode($row['chapa_response'], true);
        if (is_array($decoded)) $meta = $decoded;
    }
    return [
        'id' => (int)$row['id'],
        'amount' => (float)$row['amount'],
        'method' => $meta['method'] ?? null,
        'phone' => $meta['phone'] ?? null,
        'status' => $row['status'],
        'created_at' => $row['created_at'],
    ];
}

// --- POST /api/bot/deposits -------------------------------------------------

function bot_dep_create() {
    $in = dep_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) dep_fail(400, 'telegram_id is required.');
    $amount = $in['amount'] ?? null;
    if (!is_numeric($amount)) dep_fail(400, 'amount is required.');
    $amount = (float)$amount;
    if ($amount < 10) dep_fail(400, 'Minimum deposit is 10 ETB.');
    if ($amount > 100000) dep_fail(400, 'Maximum deposit is 100,000 ETB.');
    // Method + phone are OPTIONAL (owner, 17 Nov 2026): the bot
    // sends amount only, and the popup page supplies them later
    // (bot_dep_payment, authenticated by the one-time token). A
    // caller that DOES send them gets the old full create. One
    // without the other is refused — half a payment cannot start.
    // Four methods (owner, 16 Nov 2026): Telebirr, CBE Birr, CBE and
    // M-Pesa all work in chat. cbebirr is stored as 'cbe' (as before);
    // M-Pesa is stored as 'mpesa'. The Direct Charge type for M-Pesa
    // is 'mpesa'; if Chapa refuses it, the checkout fallback below
    // still pays (the hosted page offers M-Pesa).
    $method_in = strtolower(trim((string)($in['method'] ?? '')));
    $method = null;
    if ($method_in !== '') {
        if ($method_in === 'cbebirr') $method_in = 'cbe';
        if ($method_in !== 'telebirr' && $method_in !== 'cbe' && $method_in !== 'mpesa') {
            dep_fail(400, 'method must be telebirr, cbe or mpesa.');
        }
        $method = $method_in;
    }
    $phone = null;
    if (trim((string)($in['phone'] ?? '')) !== '') {
        $phone = dep_normalize_phone($in['phone']);
        if ($phone === null) dep_fail(400, 'Invalid phone number.');
    }
    if (($method === null) !== ($phone === null)) {
        dep_fail(400, 'method and phone must be sent together.');
    }
    $type = ($method === 'cbe') ? 'cbebirr' : $method;

    $db = dep_db();
    if ($db === null) dep_fail(500, 'Database is not available.');

    // The account must exist (same check as the orders endpoint).
    $stmt = $db->prepare('SELECT tg_id, username, first_name, email FROM auth WHERE tg_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $user = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$user) dep_fail(404, 'Account not found.');

    // Double-Confirm guard: an identical pending deposit created in the
    // last 60 seconds is returned instead of charging twice.
    // Amount-only (popup flow): a pending amount-only deposit for
    // the same amount returns its existing deposit_id + token, so
    // a double-tap on Confirm never makes two deposits. Full
    // (method + phone): the original guard — the duplicate returns
    // the ORIGINAL attempt's outcome (a checkout deposit repeats
    // its checkout_url, a pushed one repeats pushed true — never
    // the other way round; the outcome is stored in chapa_response
    // by the code below, dep_save_meta).
    $stmt = $db->prepare("SELECT id, amount, tx_ref, reference_id, status, chapa_response, created_at FROM deposits WHERE user_id = ? AND amount = ? AND status = 'pending' AND created_at >= NOW() - INTERVAL 60 SECOND ORDER BY id DESC LIMIT 5");
    $stmt->bind_param('id', $telegram_id, $amount);
    $stmt->execute();
    $recent = $stmt->get_result();
    while ($row = $recent->fetch_assoc()) {
        $rec = dep_deposit_record($row);
        $stored = json_decode((string)($row['chapa_response'] ?? ''), true);
        if (!is_array($stored)) $stored = [];
        if ($method === null && $rec['method'] === null && $rec['phone'] === null) {
            $stmt->close();
            bot_ok([
                'deposit_id' => $rec['id'],
                'popup_token' => $stored['popup_token'] ?? null,
                'pushed' => false,
                'auth_type' => 'popup',
                'status' => 'pending',
                'duplicate' => true,
            ]);
            return;
        }
        if ($method !== null && $rec['method'] === $method && $rec['phone'] === $phone) {
            $stmt->close();
            bot_ok([
                'deposit_id' => $rec['id'],
                'pushed' => !empty($stored['pushed']),
                'auth_type' => $stored['auth_type'] ?? 'ussd',
                'checkout_url' => $stored['checkout_url'] ?? null,
                'status' => 'pending',
                'duplicate' => true,
            ]);
            return;
        }
    }
    $stmt->close();

    // Create the deposit row exactly like chapa_init.php does.
    $tx_ref = 'paxyo-' . $telegram_id . '-' . time() . '-' . bin2hex(random_bytes(4));
    // PROMO-CODE CARRY (server/api-promo-codes.php): the code rides in
    // chapa_response so the credit hook can see it. The bot only ever
    // sends a code validate_promo already approved; the format is
    // checked here, the hook re-validates everything at credit time.
    // The same $meta array is re-saved below with the payment outcome
    // (pushed / checkout_url) — the promo_code must survive that save.
    $prc_code_in = strtoupper(trim((string)($in['promo_code'] ?? '')));
    if ($prc_code_in !== '' && !preg_match('/^[A-Z0-9][A-Z0-9_-]{2,31}$/', $prc_code_in)) dep_fail(400, 'promo_code is not valid.');
    $meta = ['method' => $method, 'phone' => $phone, 'promo_code' => ($prc_code_in !== '' ? $prc_code_in : null)];
    // Amount-only: mint the one-time popup token now, so the bot
    // can hand it to the popup page with the deposit id.
    if ($method === null) {
        $meta['popup_token'] = dep_popup_token();
    }
    $meta_json = json_encode($meta);
    $stmt = $db->prepare("INSERT INTO deposits (user_id, amount, tx_ref, reference_id, status, chapa_response, created_at) VALUES (?, ?, ?, ?, 'pending', ?, NOW())");
    $stmt->bind_param('idsss', $telegram_id, $amount, $tx_ref, $tx_ref, $meta_json);
    if (!$stmt->execute()) {
        $stmt->close();
        dep_fail(500, 'Could not create the deposit.');
    }
    $deposit_id = $db->insert_id;
    $stmt->close();

    // Amount-only (popup flow): the deposit row is pending and the
    // token is stored — nothing else happens server-side until the
    // popup page exchanges the token (bot_dep_payment). No Chapa
    // call, no checkout URL, no push.
    if ($method === null) {
        bot_ok([
            'deposit_id' => $deposit_id,
            'popup_token' => $meta['popup_token'],
            'pushed' => false,
            'auth_type' => 'popup',
            'status' => 'pending',
        ]);
        return;
    }

    // Start the payment (Direct Charge, else the checkout
    // fallback) — the shared routine bot_dep_payment uses too.
    list($pushed, $auth_type, $checkout_url, $pay_error) =
        dep_start_payment($db, $deposit_id, $tx_ref, $amount, $user, $method, $phone);
    if ($pushed === null) {
        dep_fail(502, $pay_error ?: 'Payment could not be started.');
    }
    $meta['pushed'] = $pushed;
    $meta['auth_type'] = $auth_type;
    $meta['checkout_url'] = $checkout_url;
    dep_save_meta($db, $deposit_id, $meta);
    bot_ok([
        'deposit_id' => $deposit_id,
        'pushed' => $pushed,
        'auth_type' => $auth_type,
        'checkout_url' => $checkout_url,
        'status' => 'pending',
    ]);
}

// --- Shared payment start (Direct Charge, else checkout) -------------
// Used by bot_dep_create (full create) and bot_dep_payment (the
// bot's exchange, token alone after Confirm). Returns [pushed,
// auth_type, checkout_url, error]: on success pushed is true
// (USSD prompt sent) or false (checkout fallback), checkout_url
// is the hosted page (or null on a push); on failure pushed is
// null and error is the message to report. With no method/phone
// the Direct Charge attempt is skipped and the checkout is
// initialised straight away (Chapa collects method + phone on
// its own page). The deposit row stays pending either way — only
// a successful start stores an outcome in chapa_response.

function dep_start_payment($db, $deposit_id, $tx_ref, $amount, $user, $method, $phone) {
    // No method/phone (owner, 17 Nov 2026): the bot started the
    // payment with the token alone, and Chapa collects the method
    // + phone on its own checkout page. A Direct Charge push needs
    // a phone, so it is skipped and the checkout is initialised
    // straight away. Chapa's initialise API does not require a
    // phone number (Chapa's docs: a phone number is not required,
    // but if you pass one it must be 10 digits) — the checkout
    // page shows its own empty phone field for the user to fill in.
    if ($method === null || $phone === null) {
        $init = dep_chapa_initialize($deposit_id, $tx_ref, $amount, $user);
        if ($init === null) return [null, null, null, 'Payment could not be started.'];
        return [false, 'checkout', $init, null];
    }
    $type = ($method === 'cbe') ? 'cbebirr' : $method;
    // Chapa Direct Charge: pushes a USSD prompt to the customer's phone.
    // No checkout link is needed when it works (telebirr / cbebirr /
    // mpesa) — the fallback below covers the refused case.
    $secret = dep_chapa_secret();
    if ($secret === null) return [null, null, null, 'Payment service is not configured.'];
    $fields = [
        'amount' => (string)$amount,
        'currency' => 'ETB',
        'tx_ref' => $tx_ref,
        'mobile' => $phone,
    ];
    if (!empty($user['email'])) $fields['email'] = $user['email'];
    if (!empty($user['first_name'])) $fields['first_name'] = $user['first_name'];
    $ch = curl_init(dep_chapa_base() . '/charges?type=' . $type);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $fields,
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $secret],
        CURLOPT_TIMEOUT => 30,
    ]);
    $raw = curl_exec($ch);
    $http = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    $res = json_decode((string)$raw, true);
    if (is_array($res) && ($res['status'] ?? '') === 'success') {
        $data = $res['data'] ?? [];
        return [true, $data['auth_type'] ?? 'ussd', $data['checkout_url'] ?? null, null];
    }
    // Direct Charge failed (16 Nov 2026: this Chapa account is NOT
    // enabled for it — Chapa answers "You are not allowed for
    // direct charges"). Fall back to a standard Chapa checkout page
    // (/transaction/initialize): the popup page opens it, so the
    // user still pays without retyping anything. The deposit row
    // stays pending either way; only a successful initialize
    // returns a checkout_url. The same tx_ref is reused: a refused
    // charge creates no Chapa transaction, so the tx_ref is still
    // free.
    $init = dep_chapa_initialize($deposit_id, $tx_ref, $amount, $user);
    if ($init === null) {
        $msg = (is_array($res) && isset($res['message'])) ? (string)$res['message'] : 'Payment could not be started.';
        return [null, null, null, $msg];
    }
    return [false, 'checkout', $init, null];
}

// --- POST /api/bot/deposits/{id}/payment (bot's exchange) --------
// The bot calls this right after the user confirms the amount,
// with the one-time popup_token only. Auth is the token the bot
// was given at create time — NOT the X-Bot-Secret, so this route
// must be exempt from the secret check, like the callback. The
// token is bound to this deposit id and dies with the deposit; a
// wrong token, a missing deposit, or a deposit that is no longer
// pending is refused.
// Method + phone are OPTIONAL (owner, 17 Nov 2026): the bot
// starts the payment with the token alone, and Chapa collects
// the method + phone on its own checkout page — the user never
// picks them in the bot or a popup. One without the other is
// refused — half a payment cannot start. When both are sent
// (the old popup exchange) the Direct Charge attempt still runs.
// Repeating the call with the same token returns the SAME
// checkout URL (stored in chapa_response) — never a second
// charge, and a failed first attempt keeps the token usable so
// the user can retry.

function bot_dep_payment($deposit_id) {
    $in = dep_json_body();
    $token = (string)($in['token'] ?? '');
    if ($token === '') dep_fail(400, 'token is required.');
    $method_in = strtolower(trim((string)($in['method'] ?? '')));
    if ($method_in === 'cbebirr') $method_in = 'cbe';
    $method = null;
    if ($method_in !== '') {
        if ($method_in !== 'telebirr' && $method_in !== 'cbe' && $method_in !== 'mpesa') {
            dep_fail(400, 'method must be telebirr, cbe or mpesa.');
        }
        $method = $method_in;
    }
    $phone = null;
    if (trim((string)($in['phone'] ?? '')) !== '') {
        $phone = dep_normalize_phone($in['phone']);
        if ($phone === null) dep_fail(400, 'Invalid phone number.');
    }
    if (($method === null) !== ($phone === null)) {
        dep_fail(400, 'method and phone must be sent together.');
    }
    $db = dep_db();
    if ($db === null) dep_fail(500, 'Database is not available.');
    $stmt = $db->prepare('SELECT id, user_id, amount, tx_ref, reference_id, status, chapa_response, created_at FROM deposits WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $deposit_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) dep_fail(404, 'Deposit not found.');
    if ($row['status'] !== 'pending') {
        bot_ok(['deposit_id' => (int)$row['id'], 'status' => $row['status']]);
        return;
    }
    $meta = json_decode((string)($row['chapa_response'] ?? ''), true);
    if (!is_array($meta)) $meta = [];
    $stored_token = (string)($meta['popup_token'] ?? '');
    if ($stored_token === '' || !hash_equals($stored_token, $token)) {
        dep_fail(403, 'Invalid or expired deposit token.');
    }
    // Already exchanged (e.g. the page reloaded): return the same
    // outcome — never start a second payment for this deposit.
    if (!empty($meta['checkout_url']) || !empty($meta['pushed'])) {
        bot_ok([
            'deposit_id' => (int)$row['id'],
            'pushed' => !empty($meta['pushed']),
            'auth_type' => $meta['auth_type'] ?? 'checkout',
            'checkout_url' => $meta['checkout_url'] ?? null,
            'status' => 'pending',
        ]);
        return;
    }
    $telegram_id = (int)$row['user_id'];
    $stmt = $db->prepare('SELECT tg_id, username, first_name, email FROM auth WHERE tg_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $user = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$user) dep_fail(404, 'Account not found.');
    $meta['method'] = $method;
    $meta['phone'] = $phone;
    $amount = (float)$row['amount'];
    $tx_ref = $row['tx_ref'] !== '' ? $row['tx_ref'] : $row['reference_id'];
    list($pushed, $auth_type, $checkout_url, $pay_error) =
        dep_start_payment($db, $deposit_id, $tx_ref, $amount, $user, $method, $phone);
    if ($pushed === null) {
        dep_save_meta($db, $deposit_id, $meta);
        dep_fail(502, $pay_error ?: 'Payment could not be started.');
    }
    $meta['pushed'] = $pushed;
    $meta['auth_type'] = $auth_type;
    $meta['checkout_url'] = $checkout_url;
    dep_save_meta($db, $deposit_id, $meta);
    bot_ok([
        'deposit_id' => (int)$row['id'],
        'pushed' => $pushed,
        'auth_type' => $auth_type,
        'checkout_url' => $checkout_url,
        'status' => 'pending',
    ]);
}

// --- Chapa checkout fallback (deposit popup, 16 Nov 2026) ---------------

function dep_save_meta($db, $deposit_id, $meta) {
    $json = json_encode($meta);
    $stmt = $db->prepare('UPDATE deposits SET chapa_response = ? WHERE id = ?');
    $stmt->bind_param('si', $json, $deposit_id);
    $stmt->execute();
    $stmt->close();
}

function dep_chapa_initialize($deposit_id, $tx_ref, $amount, $user) {
    // POST /transaction/initialize -> the hosted checkout page URL,
    // or null when Chapa refuses. The page is method-agnostic (the
    // payer picks Telebirr / CBE / M-Pesa on it), so one fallback
    // covers all four chat methods. return_url lands on the popup's
    // success view (server/deposit-app.html ?paid=1); callback_url is
    // the bot-API receiver below, which credits on Chapa's callback
    // so a user who pays gets credited automatically, no tap needed.
    // Email is required by Chapa: the auth email when the user has
    // one, else the Paxyo no-reply (Telegram-only users have none).
    $secret = dep_chapa_secret();
    if ($secret === null) return null;
    $email = !empty($user['email']) ? (string)$user['email'] : 'noreply@paxyo.et';
    $first = !empty($user['first_name']) ? (string)$user['first_name'] : 'Paxyo';
    $fields = [
        'amount' => (string)$amount,
        'currency' => 'ETB',
        'email' => $email,
        'first_name' => $first,
        'last_name' => 'Customer',
        'tx_ref' => $tx_ref,
        'callback_url' => 'https://paxyo.et/api/bot/deposits/callback',
        'return_url' => 'https://paxyo.et/deposit-app.html?paid=1&deposit_id=' . (int)$deposit_id,
        'customization[title]' => 'Paxyo deposit',
    ];
    $ch = curl_init(dep_chapa_base() . '/transaction/initialize');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $fields,
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $secret],
        CURLOPT_TIMEOUT => 30,
    ]);
    $raw = curl_exec($ch);
    curl_close($ch);
    $res = json_decode((string)$raw, true);
    if (!is_array($res) || ($res['status'] ?? '') !== 'success') return null;
    $url = $res['data']['checkout_url'] ?? null;
    if (!is_string($url) || $url === '') return null;
    return $url;
}

// --- Chapa verify + credit (ONE routine, TWO entry points) ---------------
// dep_verify_and_credit() is the old bot_dep_status() pending block,
// moved verbatim: same Chapa verify, same amount match, same
// credit-once transaction, same failed/48h rules. bot_dep_status()
// (the explicit "did my deposit go through?" recheck) and
// bot_dep_callback() (Chapa's server-side
// callback) both call it, so a deposit credits exactly once however
// the payment is confirmed. NOTHING about the credit rules changed:
// the only new thing is the second caller.

function dep_verify_and_credit($db, $row) {
    $deposit_id = (int)$row['id'];
    $telegram_id = (int)$row['user_id'];
    $record = dep_deposit_record($row);
    $message = null;
    $secret = dep_chapa_secret();
    if ($secret === null) return [$record, $message];
    $ref = $row['tx_ref'] !== '' ? $row['tx_ref'] : $row['reference_id'];
    $ch = curl_init(dep_chapa_base() . '/transaction/verify/' . rawurlencode($ref));
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $secret],
        CURLOPT_TIMEOUT => 30,
    ]);
    $raw = curl_exec($ch);
    $http = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    $res = json_decode((string)$raw, true);
    if (is_array($res) && $http === 200 && isset($res['data'])) {
        $data = $res['data'];
        $dstatus = strtolower((string)($data['status'] ?? ''));
        $damount = (float)($data['amount'] ?? 0);
        if ($dstatus === 'success') {
            // Credit once only, and only when the amounts match.
            if (abs($damount - (float)$row['amount']) > 0.009) {
                $message = 'Amount mismatch — the deposit was not credited.';
                return [$record, $message];
            }
            $db->begin_transaction();
            $stmt = $db->prepare('SELECT status FROM deposits WHERE id = ? FOR UPDATE');
            $stmt->bind_param('i', $deposit_id);
            $stmt->execute();
            $fresh = $stmt->get_result()->fetch_assoc();
            $stmt->close();
            if ($fresh && $fresh['status'] === 'pending') {
                $stmt = $db->prepare("UPDATE deposits SET status = 'completed', completed_at = NOW() WHERE id = ?");
                $stmt->bind_param('i', $deposit_id);
                $stmt->execute();
                $stmt->close();
                $amt = (float)$row['amount'];
                $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
                $stmt->bind_param('di', $amt, $telegram_id);
                $stmt->execute();
                $stmt->close();
                // LIVE HOOK POINTS — the promo hook (prc_maybe_redeem)
                // and the referral hook (ref_maybe_credit_bonus) run
                // HERE in live bot.php, after the balance credit and
                // before commit, inside this same pending block:
                //   $prc_meta = json_decode((string)($row['chapa_response'] ?? ''), true);
                //   $prc_code = is_array($prc_meta) ? (string)($prc_meta['promo_code'] ?? '') : '';
                //   if ($prc_code !== '') prc_maybe_redeem($db, $telegram_id, $prc_code, $deposit_id, $amt);
                //   ref_maybe_credit_bonus($db, $telegram_id, $deposit_id, $amt);
                // Both are guarded so this file still works standalone
                // (php -l + the repo has neither function). The live
                // install MUST keep EXACTLY ONE call site per hook:
                // when this refactor lands in bot.php, DELETE the old
                // hook calls from bot_dep_status() — they now live
                // here. A hook that cannot pay (code deactivated,
                // already redeemed, no auth row) simply does not pay;
                // the deposit still completes.
                if (function_exists('prc_maybe_redeem')) {
                    $prc_meta = json_decode((string)($row['chapa_response'] ?? ''), true);
                    $prc_code = is_array($prc_meta) ? (string)($prc_meta['promo_code'] ?? '') : '';
                    if ($prc_code !== '') prc_maybe_redeem($db, $telegram_id, $prc_code, $deposit_id, $amt);
                }
                if (function_exists('ref_maybe_credit_bonus')) {
                    ref_maybe_credit_bonus($db, $telegram_id, $deposit_id, $amt);
                }
            }
            $db->commit();
            $record['status'] = 'completed';
        } elseif ($dstatus === 'failed' || $dstatus === 'cancelled' || $dstatus === 'rejected'
            || strpos($dstatus, 'reject') !== false || strpos($dstatus, 'cancel') !== false) {
            $stmt = $db->prepare("UPDATE deposits SET status = 'failed' WHERE id = ? AND status = 'pending'");
            $stmt->bind_param('i', $deposit_id);
            $stmt->execute();
            $stmt->close();
            $record['status'] = 'failed';
        } else {
            // Still pending at Chapa: fail it after 48 hours.
            $stmt = $db->prepare("UPDATE deposits SET status = 'failed' WHERE id = ? AND status = 'pending' AND created_at < NOW() - INTERVAL 48 HOUR");
            $stmt->bind_param('i', $deposit_id);
            $stmt->execute();
            if ($stmt->affected_rows > 0) $record['status'] = 'failed';
            $stmt->close();
        }
    }
    // If verify errored or returned nothing usable, the stored
    // status is returned unchanged — never guess.
    return [$record, $message];
}

// --- POST /api/bot/deposits/callback (Chapa server callback) -------------
// Chapa POSTs here when a checkout payment finishes. The callback
// itself is UNTRUSTED input: it only ever triggers a Chapa verify
// (server-side secret), and credit happens only on verify success +
// amount match, exactly like the recheck — a forged callback with a
// made-up tx_ref finds no row, and one with a real tx_ref still
// needs Chapa to say success. Always answers 200 so Chapa stops
// retrying. INSTALL NOTE: Chapa calls this WITHOUT the X-Bot-Secret,
// so this route must be exempt from bot.php's secret check (place
// its dispatch before the check, or add 'deposits/callback' to the
// exemption — verify how live bot.php enforces the secret first).
// Without the exemption the callback 401s and the deposit only
// credits when the bot rechecks it — the popup still works.

function bot_dep_callback() {
    $in = dep_json_body();
    if (!is_array($in) || empty($in)) {
        $in = $_POST;
    }
    $tx_ref = (string)($in['tx_ref'] ?? $in['reference'] ?? '');
    if ($tx_ref === '') {
        bot_ok(['ok' => true, 'message' => 'no tx_ref']);
        return;
    }
    $db = dep_db();
    if ($db === null) {
        bot_ok(['ok' => true, 'message' => 'database unavailable']);
        return;
    }
    $stmt = $db->prepare('SELECT id, user_id, amount, tx_ref, reference_id, status, chapa_response, created_at FROM deposits WHERE tx_ref = ? OR reference_id = ? LIMIT 1');
    $stmt->bind_param('ss', $tx_ref, $tx_ref);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row) {
        bot_ok(['ok' => true, 'message' => 'deposit not found']);
        return;
    }
    if ($row['status'] === 'pending') {
        dep_verify_and_credit($db, $row);
    }
    bot_ok(['ok' => true, 'deposit_id' => (int)$row['id']]);
}

// --- GET /api/bot/deposits/{id}?telegram_id=X (rechecks with Chapa) --------

function bot_dep_status($deposit_id) {
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) dep_fail(400, 'telegram_id is required.');
    $db = dep_db();
    if ($db === null) dep_fail(500, 'Database is not available.');
    $stmt = $db->prepare('SELECT id, user_id, amount, tx_ref, reference_id, status, chapa_response, created_at FROM deposits WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $deposit_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$row || (int)$row['user_id'] !== $telegram_id) dep_fail(404, 'Deposit not found.');
    $record = dep_deposit_record($row);

    if ($row['status'] === 'pending') {
        // Same verify + credit as before — now the shared routine
        // (see dep_verify_and_credit above). The amount-mismatch
        // message is the only non-record reply, as before.
        list($record, $message) = dep_verify_and_credit($db, $row);
        if ($message !== null) {
            bot_ok(['deposit' => $record, 'message' => $message]);
            return;
        }
    }
    // Referral-bonus notice data (16 Nov 2026): the bot messages
    // both sides when a first-deposit bonus lands. Attached on every
    // read of the deposit, paid/notified flags gated on THIS deposit
    // id (see ref_bonus_for_deposit in api-referrals.php) — the bot
    // notifies a side only when paid and not yet notified, then acks
    // it (POST /referrals/notify-ack). Guarded: this file works
    // standalone without the referrals file.
    if (function_exists('ref_bonus_for_deposit')) {
        $rb = ref_bonus_for_deposit($db, $telegram_id, $deposit_id);
        if ($rb !== null) $record['referral_bonus'] = $rb;
    }
    bot_ok(['deposit' => $record]);
}

// --- GET /api/bot/deposits?telegram_id=X&limit=5 ----------------------------

function bot_dep_list() {
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) dep_fail(400, 'telegram_id is required.');
    $limit = (int)($_GET['limit'] ?? 5);
    if ($limit < 1) $limit = 5;
    if ($limit > 20) $limit = 20;
    $db = dep_db();
    if ($db === null) dep_fail(500, 'Database is not available.');
    $stmt = $db->prepare('SELECT id, amount, status, chapa_response, created_at FROM deposits WHERE user_id = ? ORDER BY id DESC LIMIT ?');
    $stmt->bind_param('ii', $telegram_id, $limit);
    $stmt->execute();
    $res = $stmt->get_result();
    $out = [];
    while ($row = $res->fetch_assoc()) $out[] = dep_deposit_record($row);
    $stmt->close();
    bot_ok(['deposits' => $out]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'deposits' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_dep_create(); }
//   if ($bp === 'deposits' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_dep_list(); }
//   if (preg_match('#^deposits/([0-9]+)$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_dep_status((int)$m[1]); }
//   if (preg_match('#^deposits/([0-9]+)/payment$#', $bp, $m) && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_dep_payment((int)$m[1]); }
//   if ($bp === 'deposits/callback' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_dep_callback(); }
//   The callback line MUST be exempt from the X-Bot-Secret check:
//   Chapa posts it without the secret (see bot_dep_callback). Place
//   it before the secret check, or add 'deposits/callback' to the
//   exemption — verify how live bot.php enforces the secret first.
//   Without the exemption the callback 401s and the deposit only
//   credits when the bot's recheck / credit watcher asks again.
//   The payment line MUST ALSO be exempt: the popup page calls it
//   with the one-time popup_token (its own auth), not the secret.
//   Without the exemption the popup cannot start the payment.
//
// INSTALL NOTES (16 Nov 2026 — this file changed the deposit flow):
//   - bot_dep_create() now: accepts mpesa; on Direct Charge failure
//     creates a standard Chapa checkout and returns checkout_url.
//     It REPLACES the old bot_dep_create() entirely — but keep the
//     promo-code carry line (it is already in this file).
//   - bot_dep_status() is now a thin wrapper over the new shared
//     dep_verify_and_credit() (same verify, amount match, credit-once
//     transaction, failed/48h rules — moved verbatim). The promo hook
//     (prc_maybe_redeem) and referral hook (ref_maybe_credit_bonus)
//     now live INSIDE dep_verify_and_credit(), guarded by
//     function_exists — DELETE the old hook calls from live
//     bot_dep_status() when this lands, so each hook has EXACTLY ONE
//     call site. Verify with grep before php -l.
//   - server/deposit-app.html must be copied to public_html/
//     deposit-app.html in the same install (the popup page + the
//     return_url target). Check it does not already exist first.
//   - php -l api-deposits.php, then php -l api/bot.php after splicing.
//
// LIVE CURL TEST (safe — the test number is 9 digits, not a real account,
// so Chapa should reject the charge; no push is sent, no money moves):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s -X POST https://paxyo.et/api/bot/deposits \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"amount":10,"method":"telebirr","phone":"0993873830"}'
//   -> expect an error about the number (deposit row stays pending).
//   curl -s "https://paxyo.et/api/bot/deposits?telegram_id=779060335&limit=5" \
//     -H "X-Bot-Secret: $SECRET"
//   curl -s "https://paxyo.et/api/bot/deposits/<id>?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   Then DELETE the test row and confirm it is gone:
//   mysql -e "DELETE FROM deposits WHERE id=<id>; SELECT COUNT(*) FROM deposits WHERE id=<id>;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
