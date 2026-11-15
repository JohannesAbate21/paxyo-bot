<?php
// ============================================================================
// Promo codes for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot, ideas batch 2 — PROMO CODES.
// SERVER SIDE ONLY.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/promo-codes/validate  {telegram_id, code}
//     -> {"ok":true,"percent":20,"message":"...","already_used":false}
//        Checks the code exists, is active, is not expired, is not
//        over max_uses, and has NOT already been redeemed by this
//        telegram_id. A redeemed code is NOT an error to the user —
//        it is "already used": ok:false, already_used:true, with a
//        plain message the bot can show. All business failures
//        return HTTP 200 with ok:false (only missing fields are
//        400), so the bot can display the message directly.
//   POST /api/bot/promo-codes/redeem  {telegram_id, code, deposit_id}
//     -> {"ok":true,"bonus_etb":20.00,"percent":20,"code":"...",
//         "deposit_id":N,"duplicate":false}
//        Credits bonus = deposit amount x percent to the user's
//        Paxyo balance, ONCE, in a transaction. Idempotent by
//        deposit_id: a repeat call returns the recorded bonus with
//        duplicate:true and NEVER credits a second time. The deposit
//        must be status 'completed' and belong to telegram_id — a
//        pending or failed deposit pays nothing.
//   POST /api/bot/promo-codes  {code, percent, active?, expires_at?,
//                               max_uses?}
//     -> {"ok":true,"code":"...","percent":20,"active":true,
//         "expires_at":null,"max_uses":null}
//        Creates a code. Gated by X-Bot-Secret and intended to be
//        called by the ADMIN BOT (or the admin panel server-side)
//        AFTER William confirms the code in chat — the same gate
//        the admin settings endpoint (api-admin-settings.php) uses.
//        See "CODE CREATION — GATE DECISION" below.
//   prc_maybe_redeem($db, $telegram_id, $code, $deposit_id, $amount)
//     -> NOT an endpoint. Called from bot_dep_status() (see
//        "PROMO HOOK" below). Runs INSIDE the caller's transaction:
//        it never begins or commits one itself.
//
// THE MONEY RULE — READ THIS FIRST:
//   A code NEVER changes a price and NEVER creates money from
//   nothing. The bonus is a deposit credit through deterministic
//   server code only, only on a REAL completed deposit, only once
//   per user (UNIQUE telegram_id+code), and only once per deposit
//   (UNIQUE deposit_id). The bonus is Paxyo balance (same as a
//   refund), never cash — the balance cannot be withdrawn as cash,
//   per the Paxyo Terms. A code deactivated or expired between the
//   deposit and the payment pays NOTHING — the hook re-validates
//   at credit time, it does not trust the earlier validate call.
//
// CODE CREATION — GATE DECISION (investigated, api-admin-stats.php
// / api-admin-settings.php):
//   The admin-panel human pages (admin-confused-chats.php) gate
//   with the PHP session admin_authenticated=true. The BOT admin
//   actions (settings write, broadcasts audience) gate with
//   X-Bot-Secret and rely on the calling bot to have checked its
//   own allowlist + Confirm step first. Promo-code creation is a
//   BOT admin action — William says "create promo code X for 10%"
//   to the new admin chat bot, the bot shows the code + percent,
//   William confirms, and only then the bot calls POST
//   /promo-codes. So this file uses X-Bot-Secret, NOT the admin
//   session. The admin bot's allowlist (ADMIN_TELEGRAM_IDS, empty
//   = refuses everyone) is what keeps anyone but William from
//   creating codes. If William instead wants codes created from
//   the human admin panel, that panel must call this endpoint
//   server-side with the secret — the secret must NEVER be put in
//   a browser page — or use the SQL INSERT in the footer instead.
//   No admin-panel session check exists in this file by design.
//
// TABLES (created automatically on first call, utf8mb4):
//   bot_promo_codes       code VARCHAR(32) PRIMARY KEY, percent INT
//                         (1..100), active TINYINT DEFAULT 1,
//                         expires_at DATETIME NULL,
//                         max_uses INT NULL (NULL = unlimited),
//                         created_at.
//   bot_promo_redemptions id AUTO_INCREMENT PK, telegram_id BIGINT,
//                         code VARCHAR(32), deposit_id INT,
//                         bonus_etb DECIMAL(12,2), created_at,
//                         UNIQUE (telegram_id, code) — once per user,
//                         UNIQUE (deposit_id) — one bonus per deposit.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-promo-codes.php      (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. Apply the PROMO HOOK patch to bot_dep_status() AND the one-line
//      patch to bot_dep_create() (see below — both are MANUAL patches
//      inside bot.php / api-deposits.php, not dispatch lines).
//   4. php -l api/bot.php               (must pass before anything goes live)
//   5. Live curl test (see the bottom of this file) then DELETE the
//      test rows. The curl test credits a REAL bonus on a REAL
//      completed deposit on purpose — use a small test deposit only,
//      with William's approval, and note the bonus in the test log.
//
// PROMO HOOK — EXACT MANUAL PATCH (in live bot.php, inside
// bot_dep_status() from api-deposits.php — the same place as the
// referral hook, ref_maybe_credit_bonus):
//   The credit block runs inside $db->begin_transaction(), after
//   Chapa verify says success AND the amounts match exactly, only
//   when the deposit row is still 'pending':
//       $stmt = $db->prepare("UPDATE deposits SET status = 'completed', completed_at = NOW() WHERE id = ?");
//       ...
//       $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
//       $stmt->bind_param('di', $amt, $telegram_id);
//       $stmt->execute();
//       $stmt->close();
//   INSERT IMMEDIATELY AFTER that second $stmt->close(), still
//   INSIDE the `if ($fresh && $fresh['status'] === 'pending')`
//   block, and BEFORE the $db->commit(); line:
//       $prc_meta = json_decode((string)($row['chapa_response'] ?? ''), true);
//       $prc_code = is_array($prc_meta) ? (string)($prc_meta['promo_code'] ?? '') : '';
//       if ($prc_code !== '') prc_maybe_redeem($db, $telegram_id, $prc_code, $deposit_id, $amt);
//   That is the whole hook — one call, inside the existing
//   transaction, so the deposit credit and the promo bonus commit
//   or roll back together. Do NOT call it anywhere else in
//   bot_dep_status(): it must run ONLY on the success path, only
//   after the deposit row is 'completed' and the user's own balance
//   is credited, and NEVER on the failed/amount-mismatch paths.
//   The hook IGNORES the helper's return value (same as the
//   referral hook): if the bonus cannot be paid at hook time (code
//   deactivated, already redeemed, auth row missing), the deposit
//   still completes and the bonus is simply not paid. It can be
//   paid afterwards by calling POST /promo-codes/redeem directly
//   (which re-checks everything and credits in its own
//   transaction) — or left unpaid, which is also a correct outcome.
//   This file CANNOT be spliced to do the hook by itself: the hook
//   lives inside an existing function, so a human (or a patch
//   script that matches the exact lines above) must insert it.
//   If the live bot.php credit block differs from api-deposits.php,
//   match it by meaning (after the auth-balance UPDATE, before
//   commit) and re-check with php -l.
//
// PROMO-CODE CARRY — ONE-LINE PATCH TO bot_dep_create() (required
// for the hook to see the code):
//   bot_dep_create() stores method+phone as JSON in chapa_response:
//       $meta_json = json_encode(['method' => $method, 'phone' => $phone]);
//   Change that ONE line to:
//       $prc_code_in = strtoupper(trim((string)($in['promo_code'] ?? '')));
//       if ($prc_code_in !== '' && !preg_match('/^[A-Z0-9][A-Z0-9_-]{2,31}$/', $prc_code_in)) dep_fail(400, 'promo_code is not valid.');
//       $meta_json = json_encode(['method' => $method, 'phone' => $phone, 'promo_code' => ($prc_code_in !== '' ? $prc_code_in : null)]);
//   The BOT must validate the code first (POST /promo-codes/validate)
//   and only send promo_code with the deposit create when validation
//   said ok:true — a mistyped code is caught in chat, not silently
//   stored. The server only format-checks here; the hook
//   re-validates everything at credit time. Website deposits never
//   go through bot_dep_create, so they never carry a code and never
//   earn a bonus through this hook (see A4).
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient methods
// to add, mirroring save_session / load_session in bot.py):
//   validate_promo(telegram_id, code) — POST /promo-codes/validate.
//     404-tolerant (endpoint not live yet -> None + warning, keep
//     working without a bonus). Returns the record; the bot shows
//     the message when ok is false and stores the code for the
//     deposit create when ok is true. A validate call NEVER credits
//     anything and NEVER reserves a use — the bonus is decided at
//     credit time, so two users validating the same limited code
//     race fairly at redeem time (first credit wins).
//   redeem_promo(telegram_id, code, deposit_id) — POST
//     /promo-codes/redeem. Called after a deposit completes when
//     the hook did not already pay (e.g. the deposit was made on
//     the website, or the hook ran before this file was installed).
//     404-tolerant. Safe to call twice: the second call returns
//     the recorded bonus with duplicate:true.
//   create is NOT a bot.py call — it belongs to the admin bot.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. deposits: id, user_id (= telegram id), amount, status
//       ('pending' / 'completed' / 'failed'), chapa_response (JSON
//       holding method/phone — api-deposits.php), completed_at.
//       All as in api-deposits.php (verified pattern, not a guess).
//   A2. auth: tg_id + balance (same columns the deposits endpoint
//       credits — verified pattern).
//   A3. bot_dep_status() is the ONLY bot-API deposit-credit path.
//       The website checkout flow (webhook_handler.php and/or
//       recheck_deposit.php) may credit balances independently of
//       the bot API — same caveat as the referral file. If either
//       of them marks a deposit 'completed' and credits
//       auth.balance, a website deposit that carries a validated
//       promo code will NOT get its bonus automatically: the code
//       is only stored by bot_dep_create, and the hook only runs
//       in bot_dep_status(). The manual POST /promo-codes/redeem
//       call is the fallback for those deposits. Check those files
//       on the server before promising website users a bonus.
//   A4. expires_at is compared against NOW() in the server's time
//       zone. If the server clock is not EAT, a code expiring at
//       midnight EAT will cut off 3 hours early/late. Set expiry
//       with a margin, or store UTC and convert at install time.
//   A5. bot_ok() is used for success replies (it adds
//       "success":true, as on the other endpoints). Errors use
//       prc_fail() below, which returns
//       {"success":false,"error":...,"message":...} — the bot
//       reads both keys. Add the same bot_rate_limit(...) call the
//       other user endpoints use to the dispatch lines (copy the
//       exact call from the orders handler — the signature was not
//       visible from outside the server).
//   A6. No existing promo-code table or bonus column exists;
//       bot_promo_codes / bot_promo_redemptions are brand-new names.
//   A7. Percent is an integer 1..100. A 100% code doubles a deposit
//       — William should only create one deliberately. There is no
//       separate "max bonus" cap in this file; if he wants one, add
//       a max_bonus_etb column and clamp in prc_maybe_redeem().
// ============================================================================

// --- small helpers (prc_ prefix so nothing collides with bot.php) ----------

function prc_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function prc_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function prc_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function prc_ensure_tables($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_promo_codes (
        code VARCHAR(32) NOT NULL PRIMARY KEY,
        percent INT NOT NULL,
        active TINYINT(1) NOT NULL DEFAULT 1,
        expires_at DATETIME NULL,
        max_uses INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    $db->query("CREATE TABLE IF NOT EXISTS bot_promo_redemptions (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        code VARCHAR(32) NOT NULL,
        deposit_id INT NOT NULL,
        bonus_etb DECIMAL(12,2) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_prc_user_code (telegram_id, code),
        UNIQUE KEY uq_prc_deposit (deposit_id),
        INDEX idx_prc_code (code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Normalise a code the way the bot sends it: trim, uppercase.
function prc_norm_code($code) {
    return strtoupper(trim((string)$code));
}

function prc_code_ok($code) {
    return preg_match('/^[A-Z0-9][A-Z0-9_-]{2,31}$/', $code) === 1;
}

function prc_load_code($db, $code) {
    $stmt = $db->prepare('SELECT code, percent, active, expires_at, max_uses, created_at FROM bot_promo_codes WHERE code = ? LIMIT 1');
    $stmt->bind_param('s', $code);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

function prc_redemption_by_deposit($db, $deposit_id) {
    $stmt = $db->prepare('SELECT telegram_id, code, deposit_id, bonus_etb, created_at FROM bot_promo_redemptions WHERE deposit_id = ? LIMIT 1');
    $stmt->bind_param('i', $deposit_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

function prc_redemption_by_user_code($db, $telegram_id, $code) {
    $stmt = $db->prepare('SELECT telegram_id, code, deposit_id, bonus_etb, created_at FROM bot_promo_redemptions WHERE telegram_id = ? AND code = ? LIMIT 1');
    $stmt->bind_param('is', $telegram_id, $code);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

function prc_uses_count($db, $code) {
    $stmt = $db->prepare('SELECT COUNT(*) AS n FROM bot_promo_redemptions WHERE code = ?');
    $stmt->bind_param('s', $code);
    $stmt->execute();
    $n = (int)($stmt->get_result()->fetch_assoc()['n'] ?? 0);
    $stmt->close();
    return $n;
}

// --- shared validation ------------------------------------------------------
// Returns [code_row|null, message|null]: message is null when the code
// is usable for this user right now, otherwise the plain message the
// bot shows. $already_used is set true when this user already
// redeemed the code (the "already used" case, not an error).

function prc_check_usable($db, $telegram_id, $code, &$already_used) {
    $already_used = false;
    $row = prc_load_code($db, $code);
    if (!$row) return [null, 'That promo code does not exist.'];
    if ((int)$row['active'] !== 1) return [$row, 'This promo code is no longer active.'];
    if ($row['expires_at'] !== null && $row['expires_at'] !== '' && strtotime($row['expires_at']) !== false && strtotime($row['expires_at']) <= time()) {
        return [$row, 'This promo code has expired.'];
    }
    if ($row['max_uses'] !== null && (int)$row['max_uses'] > 0 && prc_uses_count($db, $code) >= (int)$row['max_uses']) {
        return [$row, 'This promo code has been used up.'];
    }
    if (prc_redemption_by_user_code($db, $telegram_id, $code) !== null) {
        $already_used = true;
        return [$row, 'You have already used this code.'];
    }
    return [$row, null];
}

// --- POST /api/bot/promo-codes/validate --------------------------------------
// Business failures are HTTP 200 with ok:false — the bot shows the
// message. Only missing/invalid fields are 400.

function bot_prc_validate() {
    $in = prc_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) prc_fail(400, 'telegram_id is required.');
    $code = prc_norm_code($in['code'] ?? '');
    if ($code === '' || !prc_code_ok($code)) prc_fail(400, 'code is required.');

    $db = prc_db();
    if ($db === null) prc_fail(500, 'Database is not available.');
    prc_ensure_tables($db);

    $already_used = false;
    list($row, $msg) = prc_check_usable($db, $telegram_id, $code, $already_used);
    if ($msg !== null) {
        bot_ok(['ok' => false, 'percent' => null, 'message' => $msg, 'already_used' => $already_used]);
        return;
    }
    bot_ok([
        'ok' => true,
        'percent' => (int)$row['percent'],
        'message' => 'Promo code valid: ' . (int)$row['percent'] . '% bonus on your deposit.',
        'already_used' => false,
    ]);
}

// --- Bonus helper: call from bot_dep_status() AND bot_prc_redeem() ---------
// MUST be called INSIDE a database transaction (the caller begins
// and commits). It never begins or commits one itself, never throws
// for a business reason — it returns ['paid'=>bool,
// 'bonus'=>float, 'duplicate'=>bool, 'reason'=>string] and the
// caller decides what to do. A database error inside is caught and
// reported as not-paid, so a bonus failure can never break the
// deposit credit that called it from the hook.

function prc_maybe_redeem($db, $telegram_id, $code, $deposit_id, $amount) {
    $telegram_id = (int)$telegram_id;
    $deposit_id = (int)$deposit_id;
    $amount = (float)$amount;
    $code = prc_norm_code($code);
    if ($telegram_id <= 0 || $deposit_id <= 0 || $amount <= 0 || $code === '') {
        return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'invalid arguments'];
    }

    try {
        // 1. Idempotent by deposit: this deposit already earned a
        //    bonus -> return the recorded bonus, never a second one.
        $by_deposit = prc_redemption_by_deposit($db, $deposit_id);
        if ($by_deposit !== null) {
            return [
                'paid' => true,
                'bonus' => (float)$by_deposit['bonus_etb'],
                'duplicate' => true,
                'reason' => 'bonus already paid for this deposit',
            ];
        }

        // 2. Lock the code row so two concurrent redeems of a
        //    limited code cannot both pass the max_uses check.
        $stmt = $db->prepare('SELECT code, percent, active, expires_at, max_uses FROM bot_promo_codes WHERE code = ? FOR UPDATE');
        $stmt->bind_param('s', $code);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_assoc();
        $stmt->close();
        if (!$row) {
            return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'promo code does not exist'];
        }
        if ((int)$row['active'] !== 1) {
            return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'promo code is not active'];
        }
        if ($row['expires_at'] !== null && $row['expires_at'] !== '' && strtotime($row['expires_at']) !== false && strtotime($row['expires_at']) <= time()) {
            return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'promo code has expired'];
        }
        if ($row['max_uses'] !== null && (int)$row['max_uses'] > 0 && prc_uses_count($db, $code) >= (int)$row['max_uses']) {
            return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'promo code has been used up'];
        }

        // 3. Once per user: this user already redeemed this code.
        if (prc_redemption_by_user_code($db, $telegram_id, $code) !== null) {
            return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'user already redeemed this code'];
        }

        // 4. The bonus: deposit amount x percent, rounded to 2dp.
        $bonus = round($amount * ((int)$row['percent'] / 100), 2);
        if ($bonus <= 0) {
            return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'bonus rounds to zero'];
        }

        // 5. Credit the USER's own Paxyo balance. No auth row ->
        //    change nothing, pay nothing (same rule as the referral
        //    hook: a missing account is never silently written off
        //    as paid — no redemption row is written either, so a
        //    later manual redeem can still pay it).
        $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
        $stmt->bind_param('di', $bonus, $telegram_id);
        $stmt->execute();
        $credited = $stmt->affected_rows;
        $stmt->close();
        if ($credited !== 1) {
            return ['paid' => false, 'bonus' => $bonus, 'duplicate' => false, 'reason' => 'user has no account — bonus left unpaid'];
        }

        // 6. Record the redemption. A duplicate key here (1062)
        //    means a concurrent call won the race — the credit in
        //    step 5 must not stand alone, so reverse it inside this
        //    same transaction (the caller rolls back or commits the
        //    whole thing, so the reversal is atomic with it).
        $stmt = $db->prepare('INSERT INTO bot_promo_redemptions (telegram_id, code, deposit_id, bonus_etb) VALUES (?, ?, ?, ?)');
        $stmt->bind_param('isid', $telegram_id, $code, $deposit_id, $bonus);
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
            $stmt = $db->prepare('UPDATE auth SET balance = balance - ? WHERE tg_id = ?');
            $stmt->bind_param('di', $bonus, $telegram_id);
            $stmt->execute();
            $stmt->close();
            if ($duplicate) {
                $again = prc_redemption_by_deposit($db, $deposit_id);
                if ($again !== null) {
                    return ['paid' => true, 'bonus' => (float)$again['bonus_etb'], 'duplicate' => true, 'reason' => 'bonus already paid for this deposit'];
                }
            }
            return ['paid' => false, 'bonus' => $bonus, 'duplicate' => false, 'reason' => 'could not record the redemption — credit reversed'];
        }
        return ['paid' => true, 'bonus' => $bonus, 'duplicate' => false, 'reason' => 'ok'];
    } catch (mysqli_sql_exception $e) {
        // Never let a bonus failure break the caller's transaction
        // (in particular, never break a deposit credit from the
        // hook). The caller owns commit/rollback; a thrown error
        // here would roll its deposit back too.
        return ['paid' => false, 'bonus' => 0.0, 'duplicate' => false, 'reason' => 'database error: ' . $e->getMessage()];
    }
}

// --- POST /api/bot/promo-codes/redeem ---------------------------------------
// Body: {"telegram_id":N,"code":"...","deposit_id":N}. The deposit
// must be status 'completed' and belong to telegram_id — only a
// real completed deposit earns a bonus. Idempotent by deposit_id:
// a repeat call returns the recorded bonus with duplicate:true.

function bot_prc_redeem() {
    $in = prc_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) prc_fail(400, 'telegram_id is required.');
    $code = prc_norm_code($in['code'] ?? '');
    if ($code === '' || !prc_code_ok($code)) prc_fail(400, 'code is required.');
    $deposit_id = (int)($in['deposit_id'] ?? 0);
    if ($deposit_id <= 0) prc_fail(400, 'deposit_id is required.');

    $db = prc_db();
    if ($db === null) prc_fail(500, 'Database is not available.');
    prc_ensure_tables($db);

    // The deposit must exist, belong to this user, and be completed.
    // A missing / other-user deposit gets the same 404 (no leaking).
    $stmt = $db->prepare('SELECT id, user_id, amount, status FROM deposits WHERE id = ? LIMIT 1');
    $stmt->bind_param('i', $deposit_id);
    $stmt->execute();
    $dep = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$dep || (int)$dep['user_id'] !== $telegram_id) prc_fail(404, 'Deposit not found.');
    if (strtolower(trim((string)$dep['status'])) !== 'completed') {
        prc_fail(409, 'Deposit is not completed yet, so no bonus can be paid.');
    }

    $db->begin_transaction();
    $res = prc_maybe_redeem($db, $telegram_id, $code, $deposit_id, (float)$dep['amount']);
    if (!$res['paid']) {
        $db->rollback();
        // Distinguish "already paid" (which prc_maybe_redeem reports
        // as paid) from a real refusal: every not-paid outcome here
        // is a 409 with the helper's honest reason.
        prc_fail(409, 'Bonus could not be paid: ' . $res['reason'] . '.');
    }
    $db->commit();

    $row = prc_load_code($db, $code);
    bot_ok([
        'ok' => true,
        'bonus_etb' => round($res['bonus'], 2),
        'percent' => $row ? (int)$row['percent'] : null,
        'code' => $code,
        'deposit_id' => $deposit_id,
        'duplicate' => $res['duplicate'],
    ]);
}

// --- POST /api/bot/promo-codes (create) -------------------------------------
// Body: {"code":"WELCOME10","percent":10,"active":true,
//        "expires_at":"2026-12-31 23:59:59"|null,"max_uses":100|null}.
// Called by the ADMIN BOT after William confirms the code in chat
// (see "CODE CREATION — GATE DECISION" in the header). Duplicate
// code -> 409, nothing changed. To deactivate a code later, run:
//   UPDATE bot_promo_codes SET active = 0 WHERE code = '...';
// (No deactivate endpoint — deactivation is an admin-panel action,
// not a chat action.)

function bot_prc_create() {
    $in = prc_json_body();
    $code = prc_norm_code($in['code'] ?? '');
    if ($code === '' || !prc_code_ok($code)) prc_fail(400, 'code must be 3-32 letters, digits, _ or -.');
    $percent = $in['percent'] ?? null;
    if (!is_int($percent) && !(is_string($percent) && preg_match('/^\d+$/', $percent))) {
        prc_fail(400, 'percent must be an integer between 1 and 100.');
    }
    $percent = (int)$percent;
    if ($percent < 1 || $percent > 100) prc_fail(400, 'percent must be an integer between 1 and 100.');
    $active = isset($in['active']) ? ((int)(bool)$in['active']) : 1;
    $expires_at = null;
    if (isset($in['expires_at']) && $in['expires_at'] !== null && trim((string)$in['expires_at']) !== '') {
        $ts = strtotime((string)$in['expires_at']);
        if ($ts === false) prc_fail(400, 'expires_at must be a date/time like "2026-12-31 23:59:59".');
        $expires_at = date('Y-m-d H:i:s', $ts);
    }
    $max_uses = null;
    if (isset($in['max_uses']) && $in['max_uses'] !== null && trim((string)$in['max_uses']) !== '') {
        if (!is_int($in['max_uses']) && !(is_string($in['max_uses']) && preg_match('/^\d+$/', (string)$in['max_uses']))) {
            prc_fail(400, 'max_uses must be a positive integer or null.');
        }
        $max_uses = (int)$in['max_uses'];
        if ($max_uses < 1) prc_fail(400, 'max_uses must be a positive integer or null.');
    }

    $db = prc_db();
    if ($db === null) prc_fail(500, 'Database is not available.');
    prc_ensure_tables($db);

    $stmt = $db->prepare('INSERT INTO bot_promo_codes (code, percent, active, expires_at, max_uses) VALUES (?, ?, ?, ?, ?)');
    // bind_param needs variables, and a NULL max_uses binds as NULL
    // with the 'i' type when the variable holds null.
    $stmt->bind_param('siisi', $code, $percent, $active, $expires_at, $max_uses);
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
        if ($duplicate) prc_fail(409, 'A promo code with that code already exists.');
        prc_fail(500, 'Could not create the promo code.');
    }
    bot_ok([
        'ok' => true,
        'code' => $code,
        'percent' => $percent,
        'active' => ($active === 1),
        'expires_at' => $expires_at,
        'max_uses' => $max_uses,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'promo-codes/validate' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_prc_validate(); }
//   if ($bp === 'promo-codes/redeem' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_prc_redeem(); }
//   if ($bp === 'promo-codes' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_prc_create(); }
//   (Add the same bot_rate_limit(...) call the other user endpoints
//    use to each dispatch line — copy the exact call from the orders
//    handler; the signature was not visible from outside the server.
//    'promo-codes/validate' and 'promo-codes/redeem' must be checked
//    before 'promo-codes' only if the dispatch uses prefix matching;
//    with the exact === checks above the order does not matter.)
//
// PROMO HOOK + bot_dep_create PATCH — see the header ("PROMO HOOK"
// and "PROMO-CODE CARRY"). Both are manual patches, not dispatch
// lines. Apply them, then php -l api/bot.php.
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-promo-codes.php` on
// the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 4) — both must pass before anything goes live.
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account.
// The redeem steps credit a REAL bonus on a REAL completed deposit —
// use a small test deposit only, with William's approval, and note
// the bonus in the test log. All other steps move no money):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. create a test code, 10%, max 5 uses:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"code":"TEST10","percent":10,"max_uses":5}'
//   -> expect {"success":true,"ok":true,"code":"TEST10","percent":10,
//      "active":true,"expires_at":null,"max_uses":5}
//   # 2. create it again -> 409, nothing changed:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"code":"TEST10","percent":10}'
//   -> expect {"success":false,"error":"A promo code with that code already exists."}
//   # 3. validate it (lowercase input is normalised) -> ok:true:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/validate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"test10"}'
//   -> expect {"success":true,"ok":true,"percent":10,
//      "message":"Promo code valid: 10% bonus on your deposit.","already_used":false}
//   # 4. validate a code that does not exist -> ok:false, 200:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/validate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"NOPE99"}'
//   -> expect {"success":true,"ok":false,"percent":null,
//      "message":"That promo code does not exist.","already_used":false}
//   # 5. redeem it on a REAL completed test deposit id D (amount A):
//   #    first confirm the deposit is completed:
//   curl -s "https://paxyo.et/api/bot/deposits/D?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/redeem \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"TEST10","deposit_id":D}'
//   -> expect {"success":true,"ok":true,"bonus_etb":<A x 10%, 2dp>,
//      "percent":10,"code":"TEST10","deposit_id":D,"duplicate":false}
//   #    and the balance must have risen by exactly bonus_etb:
//   curl -s "https://paxyo.et/api/bot/balance?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   # 6. redeem the SAME deposit again -> same bonus, duplicate:true,
//   #    balance UNCHANGED:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/redeem \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"TEST10","deposit_id":D}'
//   -> expect "duplicate":true, same bonus_etb, balance unchanged.
//   # 7. validate again for the same user -> "already used":
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/validate \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"TEST10"}'
//   -> expect {"success":true,"ok":false,"percent":null,
//      "message":"You have already used this code.","already_used":true}
//   # 8. redeem on a PENDING deposit id P -> 409, nothing credited:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes/redeem \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"TEST10","deposit_id":P}'
//   -> expect {"success":false,"error":"Deposit is not completed yet, ..."}.
//   # 9. create with percent 0 -> 400, nothing stored:
//   curl -s -X POST https://paxyo.et/api/bot/promo-codes \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"code":"BADPCT","percent":0}'
//   -> expect {"success":false,"error":"percent must be an integer between 1 and 100."}
//   # 10. hook check (only after the hook patch is installed): make a
//   #    NEW small test deposit carrying the code (bot sends
//   #    promo_code with the deposit create — see "PROMO-CODE
//   #    CARRY"), complete it, then check:
//   #      SELECT telegram_id, code, deposit_id, bonus_etb
//   #        FROM bot_promo_redemptions WHERE code='TEST10';
//   #    -> a second row for the new deposit, bonus = 10% of it, with
//   #       NO manual redeem call. (Use a DIFFERENT test user for this
//   #       step, or a second code — the operating account already
//   #       redeemed TEST10 once and the once-per-user rule will
//   #       correctly refuse a second bonus.)
//   Then DELETE the test rows and confirm they are gone:
//   mysql -e "DELETE FROM bot_promo_redemptions WHERE code='TEST10'; DELETE FROM bot_promo_codes WHERE code='TEST10'; SELECT COUNT(*) FROM bot_promo_codes WHERE code='TEST10'; SELECT COUNT(*) FROM bot_promo_redemptions WHERE code='TEST10';"
//   (use the same MySQL credentials db.php uses; never print them.)
//   NOTE: the bonus credited in step 5 stays in the test account's
//   balance (it is real Paxyo balance, like a refund). Note the
//   amount in the test log; do not try to reverse it by hand-editing
//   auth.balance — ask William if he wants it left or adjusted.
//   SQL ALTERNATIVE for creating a code without the endpoint
//   (William / admin, in the DirectAdmin Terminal):
//   mysql -e "INSERT INTO bot_promo_codes (code, percent, active, expires_at, max_uses) VALUES ('WELCOME10', 10, 1, NULL, NULL);"
// ============================================================================
