<?php
// ============================================================================
// Per-user invite codes + referral accounting for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot
// feature 1 (per-user invite codes).
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/referrals  {telegram_id, code}
//     -> {"ok":true,"referrer_telegram_id":N,"code_used":"...",
//         "already_recorded":false}
//        Records who referred a brand-new user. Idempotent: if the
//        user already has a referrer, the FIRST one wins and is
//        returned unchanged (already_recorded:true). A start with the
//        old shared code REF3723FB335 records referrer 0 ("shared")
//        — no per-user attribution, no bonus — and never breaks.
//   GET  /api/bot/referrals?telegram_id=X
//     -> {"code":"REF...","invite_link":"https://t.me/paxorder_bot
//         ?start=REF...","referrals":N,"bonus_earned":0.00,
//         "bonus_pending":N}
//        The user's own code + link and their referral stats.
//   ref_maybe_credit_bonus($db, $telegram_id, $deposit_id, $amount)
//     -> NOT an endpoint. Call it from the first-deposit credit
//        point (see "BONUS HOOK" below). On a user's FIRST completed
//        deposit it credits 20% of that deposit to the REFERRER's
//        Paxyo balance AND 20% to the referred user (the invitee)
//        themselves, once only, each side guarded by its own paid
//        flag (bonus_paid / invitee_bonus_paid). The shared code
//        (referrer 0) pays the invitee only — there is no referrer
//        to pay. It must run INSIDE the same database transaction as
//        the deposit credit, so a rollback undoes the bonuses too.
//        Both sides confirmed by William, 19:27 EAT 16 Nov 2026
//        (was referrer-only before; open question (b) below).
//
// TABLES (created automatically on first call, utf8mb4):
//   bot_referrals  id AUTO_INCREMENT PK, referrer_telegram_id BIGINT
//                  (0 = the shared code, no attribution),
//                  referred_telegram_id BIGINT UNIQUE (one referrer
//                  per new user — first code wins), code_used
//                  VARCHAR(16), bonus_paid TINYINT DEFAULT 0,
//                  bonus_amount DECIMAL(12,2) NULL,
//                  bonus_deposit_id INT NULL,
//                  bonus_paid_at TIMESTAMP NULL,
//                  invitee_bonus_paid TINYINT DEFAULT 0,
//                  invitee_bonus_amount DECIMAL(12,2) NULL,
//                  invitee_bonus_deposit_id INT NULL,
//                  invitee_bonus_paid_at TIMESTAMP NULL, created_at.
//                  (The invitee_* columns were added 16 Nov 2026 for
//                  the both-sides bonus; ref_ensure_tables() adds
//                  them to tables created by the older file, so no
//                  separate migration step is needed.)
//
// ---------------------------------------------------------------------------
// CODE-DERIVATION ALGORITHM — READ THIS FIRST (bot-side builder too)
// ---------------------------------------------------------------------------
// Every user has ONE stable code, derived ONLY from their Telegram id.
// No lookup table is needed to resolve a code: the code carries the
// owner id plus a checksum, so the server re-derives and verifies it.
//
//   1. Let T = the user's Telegram id as a DECIMAL string, e.g. "779060335".
//   2. middle = T written in BASE 36, digits "0-9A-Z", UPPERCASE, no
//      leading zeroes, no padding. (779060335 -> "CVTYSV".)
//   3. checksum = the FIRST 2 characters of the hex SHA-256 of the
//      ASCII string "paxyo-ref:" + T, UPPERCASE.
//      (SHA-256("paxyo-ref:779060335") starts "a3..." -> checksum "A3".)
//   4. code = "REF" + middle + checksum.
//      (779060335 -> "REFCVTYSVA3". 123456789 -> "REF21I3V91B".)
//
//   Validation (server AND bot must do exactly this): normalise the
//   input to UPPERCASE and trim whitespace; it must match
//   /^REF[0-9A-Z]+[0-9A-F]{2}$/; split off the last 2 chars as the
//   checksum and the rest after "REF" as the base-36 id; decode the
//   base-36 part back to an integer; re-derive the code from that
//   integer with steps 1-4 and require an EXACT match. Anything else
//   is rejected — the server never trusts an arbitrary string as a
//   code, and a code that decodes to id 0 or to the user themselves
//   is rejected (self-referral).
//
//   Python (bot side — MUST produce byte-identical codes):
//       import hashlib
//       _B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
//       def invite_code(telegram_id: int) -> str:
//           n = int(telegram_id); s = ""
//           while n > 0:
//               n, r = divmod(n, 36); s = _B36[r] + s
//           middle = s or "0"
//           chk = hashlib.sha256(
//               f"paxyo-ref:{int(telegram_id)}".encode("ascii")
//           ).hexdigest()[:2].upper()
//           return "REF" + middle + chk
//   PHP (this file): ref_code_for() / ref_code_owner() below — the
//   same steps, integer arithmetic only (no base_convert, which loses
//   precision on large numbers).
//
//   Why base-36 + checksum instead of a random code: the bot can
//   derive any user's code locally with no server round-trip, the
//   server can resolve any code with no lookup table, and a mistyped
//   code fails the checksum instead of crediting the wrong person.
//   A code is NOT a secret: it encodes the owner's Telegram id, which
//   the admin panel already shows. Forging a code only records a
//   referral; the bonus is paid ONLY when the referred user actually
//   makes a real first deposit, so a forged code cannot mint money.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-referrals.php        (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. Apply the BONUS HOOK patch to bot_dep_status() (see below —
//      it is a MANUAL patch inside bot.php, not a dispatch line).
//   4. php -l api/bot.php               (must pass before anything goes live)
//   5. Live curl test (see the bottom of this file) then DELETE the
//      test rows.
//
// BONUS HOOK — EXACT MANUAL PATCH (in live bot.php, inside
// bot_dep_status() from api-deposits.php — the ONLY first-deposit
// credit point visible from outside the server):
//   Find this block (it runs inside $db->begin_transaction(), after
//   Chapa verify says success AND the amounts match exactly):
//       $stmt = $db->prepare("UPDATE deposits SET status = 'completed', completed_at = NOW() WHERE id = ?");
//       ...
//       $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
//       $stmt->bind_param('di', $amt, $telegram_id);
//       $stmt->execute();
//       $stmt->close();
//   INSERT IMMEDIATELY AFTER that second $stmt->close() and BEFORE
//   the $db->commit(); line:
//       ref_maybe_credit_bonus($db, $telegram_id, $deposit_id, $amt);
//   That is the whole patch — one line, inside the existing
//   transaction, so the deposit credit and the referral bonus commit
//   or roll back together. Do NOT call it anywhere else in
//   bot_dep_status(): it must run ONLY on the success path, only
//   after the deposit row is 'completed' and the user's own balance
//   is credited, and NEVER on the failed/amount-mismatch paths.
//   This file CANNOT be spliced to do the hook by itself: the hook
//   lives inside an existing function, so a human (or a patch script
//   that matches the exact lines above) must insert that one line.
//   If the live bot.php credit block differs from api-deposits.php,
//   match it by meaning (after the auth-balance UPDATE, before
//   commit) and re-check with php -l.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use ref_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - NO account-existence check on POST, unlike deposits: a referral
//     must be recordable for a brand-new user whose auth row may not
//     exist yet (the bot calls POST /users first, but the order of
//     the two calls is not guaranteed). Orphan rows are tiny and
//     keyed by telegram_id. The BONUS, by contrast, is only ever paid
//     to a referrer who HAS an auth row — see ref_maybe_credit_bonus().
//   - "First deposit" means: no OTHER deposit row for this user is
//     already 'completed' at the moment the hook runs. The hook
//     counts completed deposits excluding the one being credited.
//   - The bonus is 20% of the referred user's FIRST deposit amount,
//     rounded to 2 decimals, credited TWICE: once to the
//     REFERRER's auth.balance and once to the referred user's own
//     auth.balance (both sides, 16 Nov 2026). The shared code pays
//     the invitee only. It is Paxyo balance (same as a refund),
//     never cash — the balance cannot be withdrawn as cash, per
//     the Paxyo terms.
//   - If the referrer's auth row is missing when the hook runs (user
//     deleted, or a forged code for an id that never signed up), the
//     bonus is NOT marked paid and NO balance is changed — the row
//     stays bonus_paid=0 so William/admin can see it and reconcile
//     it by hand. It is never silently written off.
//
// OPEN QUESTIONS (do not guess — confirm on the server / with William):
//   (a) UNVERIFIED — DOES THE SERVER CREDIT ANY 20% BONUS TODAY?
//       Nobody has checked whether a ?start=REF3723FB335 deep link
//       currently credits anything at all. This file is the FIRST
//       real referral accounting: before it, there was no referral
//       table and no bonus code path anywhere in the bot API files
//       available locally. Assume NO bonus is paid today until the
//       live test below proves the hook works. Do NOT tell users a
//       bonus is guaranteed until then.
//   (b) WHO GETS THE 20%? RESOLVED — BOTH (William, 19:27 EAT
//       16 Nov 2026): on the referred user's FIRST deposit, the
//       new user gets 20% of their own deposit AND the code owner
//       gets 20% too. Example: first deposit 100 ETB -> new user
//       +20 ETB, code owner +20 ETB; Paxyo pays 40 ETB total, once
//       only, first deposit only. The hook below pays both sides
//       (invitee side first, referrer side second, each guarded by
//       its own paid flag). The shared code REF3723FB335 pays the
//       invitee only — there is no referrer to pay — which is what
//       the launch post promised ("20% bonus on their first
//       deposit"). Before 16 Nov 2026 the hook paid the referrer
//       only; the invitee_* columns and the invitee half were
//       added then.
//   (c) ARE THERE OTHER DEPOSIT-CREDIT PATHS BESIDES bot_dep_status()?
//       The website checkout flow (webhook_handler.php and/or
//       recheck_deposit.php) may credit balances independently of the
//       bot API. If a referred user deposits on the WEBSITE instead of
//       through the bot, bot_dep_status() never runs and no bonus is
//       paid. Check those files on the server: if either of them marks
//       a deposit 'completed' and credits auth.balance, add the SAME
//       one-line ref_maybe_credit_bonus() call there (same position:
//       after the balance UPDATE, before commit) — otherwise website
//       first deposits silently skip the bonus.
//   (d) ASSUMED LIVE SCHEMA (not visible from outside the server —
//       verify each name before going live):
//         - auth.tg_id (the Telegram id) and auth.balance exist and
//           auth.balance accepts DECIMAL additions (as used by
//           api-deposits.php: UPDATE auth SET balance = balance + ?
//           WHERE tg_id = ?).
//         - deposits.user_id is the Telegram id, deposits.status is
//           one of 'pending' / 'completed' / 'failed', and a
//           completed_at column exists (all as in api-deposits.php).
//         - No existing referral/bonus table or bonus column exists;
//           bot_referrals is a brand-new table name.
//         - bot.php already defines bot_ok(), and the dispatch uses a
//           $bp variable holding $_GET['bot_path'] (as in the
//           sessions / delayed-orders / deposits files).
//         - bot_rate_limit() exists with the same call the orders
//           handler uses (signature not visible from outside).
//       If any name differs live, change ONLY that name in this file
//       and in the hook call — the logic does not depend on it.
//   (e) SHOULD A REFERRAL BE RECORDED AFTER THE USER ALREADY
//       DEPOSITED? This file says no: POST returns 409 when the user
//       already has a completed deposit, because a referral recorded
//       after the first deposit could never earn a bonus and would
//       only pollute the stats. The bot should therefore POST the
//       code on /start, BEFORE the user deposits. If William wants
//       late referrals allowed, drop that check (the bonus hook still
//       pays nothing for them, since it requires a first deposit
//       AFTER the referral row exists — no, it does not: the hook
//       only checks the referral row exists and bonus_paid=0, so a
//       late-recorded referral WOULD pay on the NEXT deposit only if
//       that deposit is still the user's first; after any completed
//       deposit the hook returns early. Late recording is harmless
//       but useless — keep the 409 so the bot can tell the user
//       plainly instead of silently recording a dead referral).
// ============================================================================

// --- code derivation (must match the bot's Python exactly) ------------------

define('REF_SHARED_CODE', 'REF3723FB335');
define('REF_BOT_USERNAME', 'paxorder_bot');
define('REF_B36_DIGITS', '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ');

function ref_b36_encode($n) {
    // Integer base-36, most significant digit first, no padding.
    if ($n <= 0) return '0';
    $out = '';
    while ($n > 0) {
        $out = REF_B36_DIGITS[$n % 36] . $out;
        $n = intdiv($n, 36); // exact integer division — never float
    }
    return $out;
}

function ref_b36_decode($s) {
    // Returns the integer, or false when $s is not clean base-36.
    if ($s === '' || !preg_match('/^[0-9A-Z]+$/', $s)) return false;
    $n = 0;
    $len = strlen($s);
    for ($i = 0; $i < $len; $i++) {
        $d = strpos(REF_B36_DIGITS, $s[$i]);
        if ($d === false) return false;
        $n = $n * 36 + $d;
        if ($n <= 0) return false; // overflow guard (never hit for real ids)
    }
    return $n;
}

function ref_code_for($telegram_id) {
    // "REF" + base36(id) + first-2-hex-of-SHA256("paxyo-ref:<id>").
    $telegram_id = (int)$telegram_id;
    $middle = ref_b36_encode($telegram_id);
    $chk = strtoupper(substr(hash('sha256', 'paxyo-ref:' . $telegram_id), 0, 2));
    return 'REF' . $middle . $chk;
}

function ref_code_owner($code) {
    // Returns the owner's telegram_id, or false when the code is not
    // a valid per-user code. The shared code is NOT resolved here —
    // callers handle REF3723FB335 separately (referrer 0).
    $code = strtoupper(trim((string)$code));
    if ($code === REF_SHARED_CODE) return false;
    if (!preg_match('/^REF[0-9A-Z]+[0-9A-F]{2}$/', $code)) return false;
    $body = substr($code, 3);
    $middle = substr($body, 0, -2);
    $owner = ref_b36_decode($middle);
    if ($owner === false || $owner <= 0) return false;
    // Re-derive and require an exact match: a mistyped code fails
    // the checksum here instead of crediting the wrong person.
    if (ref_code_for($owner) !== $code) return false;
    return $owner;
}

function ref_invite_link($telegram_id) {
    return 'https://t.me/' . REF_BOT_USERNAME . '?start=' . ref_code_for($telegram_id);
}

// --- small helpers (ref_ prefix so nothing collides with bot.php) ----------

function ref_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function ref_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function ref_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function ref_ensure_tables($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_referrals (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        referrer_telegram_id BIGINT NOT NULL,
        referred_telegram_id BIGINT NOT NULL,
        code_used VARCHAR(16) NOT NULL,
        bonus_paid TINYINT(1) NOT NULL DEFAULT 0,
        bonus_amount DECIMAL(12,2) NULL,
        bonus_deposit_id INT NULL,
        bonus_paid_at TIMESTAMP NULL,
        invitee_bonus_paid TINYINT(1) NOT NULL DEFAULT 0,
        invitee_bonus_amount DECIMAL(12,2) NULL,
        invitee_bonus_deposit_id INT NULL,
        invitee_bonus_paid_at TIMESTAMP NULL,
        invitee_bonus_notified TINYINT(1) NOT NULL DEFAULT 0,
        referrer_bonus_notified TINYINT(1) NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ref_referred (referred_telegram_id),
        INDEX idx_ref_referrer (referrer_telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    // Both-sides bonus (16 Nov 2026): tables created by the older
    // file lack the invitee_* columns — add them in place (same
    // SHOW COLUMNS pattern as api-order-dripfeed.php). No separate
    // migration step: the first call after install fixes the table.
    $have = [];
    $res = $db->query('SHOW COLUMNS FROM bot_referrals');
    if ($res) {
        while ($row = $res->fetch_assoc()) {
            $have[strtolower((string)$row['Field'])] = true;
        }
        $res->close();
    }
    if (empty($have['invitee_bonus_paid'])) {
        $db->query('ALTER TABLE bot_referrals ADD COLUMN invitee_bonus_paid TINYINT(1) NOT NULL DEFAULT 0');
    }
    if (empty($have['invitee_bonus_amount'])) {
        $db->query('ALTER TABLE bot_referrals ADD COLUMN invitee_bonus_amount DECIMAL(12,2) NULL');
    }
    if (empty($have['invitee_bonus_deposit_id'])) {
        $db->query('ALTER TABLE bot_referrals ADD COLUMN invitee_bonus_deposit_id INT NULL');
    }
    if (empty($have['invitee_bonus_paid_at'])) {
        $db->query('ALTER TABLE bot_referrals ADD COLUMN invitee_bonus_paid_at TIMESTAMP NULL');
    }
    // Bonus notices (16 Nov 2026): the bot messages each side once
    // when their first-deposit bonus lands — the notified flags are
    // the exactly-once gate (see ref_bonus_for_deposit).
    if (empty($have['invitee_bonus_notified'])) {
        $db->query('ALTER TABLE bot_referrals ADD COLUMN invitee_bonus_notified TINYINT(1) NOT NULL DEFAULT 0');
    }
    if (empty($have['referrer_bonus_notified'])) {
        $db->query('ALTER TABLE bot_referrals ADD COLUMN referrer_bonus_notified TINYINT(1) NOT NULL DEFAULT 0');
    }
}

function ref_row($row) {
    return [
        'id' => (int)$row['id'],
        'referrer_telegram_id' => (int)$row['referrer_telegram_id'],
        'referred_telegram_id' => (int)$row['referred_telegram_id'],
        'code_used' => $row['code_used'],
        'bonus_paid' => ((int)$row['bonus_paid'] === 1),
        'bonus_amount' => $row['bonus_amount'] === null ? null : (float)$row['bonus_amount'],
        'bonus_deposit_id' => $row['bonus_deposit_id'] === null ? null : (int)$row['bonus_deposit_id'],
        'bonus_paid_at' => $row['bonus_paid_at'],
        'created_at' => $row['created_at'],
    ];
}

function ref_load_by_referred($db, $telegram_id) {
    $stmt = $db->prepare('SELECT * FROM bot_referrals WHERE referred_telegram_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// --- Referral-bonus block for one deposit ---------------------------------
// Bonus notices (16 Nov 2026): the bot messages both sides when a
// first-deposit bonus lands. Returns the referral_bonus block for
// the deposit record, or null when this deposit paid no referral
// bonus. Each side counts only when its paid flag is set AND its
// bonus deposit id is THIS deposit — an earlier bonus never leaks
// into a later deposit's record. The notified flags are the
// exactly-once gate: the bot messages a side only when paid and not
// yet notified, then acks it (bot_ref_notify_ack), so a second
// recheck — even after a bot restart — never re-sends it. Runs
// ref_ensure_tables first so a table created by the older file gains
// the notified columns before the row is read.
function ref_bonus_for_deposit($db, $telegram_id, $deposit_id) {
    $telegram_id = (int)$telegram_id;
    $deposit_id = (int)$deposit_id;
    if ($telegram_id <= 0 || $deposit_id <= 0) return null;
    ref_ensure_tables($db);
    $ref = ref_load_by_referred($db, $telegram_id);
    if (!$ref) return null;
    $invitee_paid = ((int)($ref['invitee_bonus_paid'] ?? 0) === 1)
        && (int)($ref['invitee_bonus_deposit_id'] ?? 0) === $deposit_id;
    $referrer_paid = ((int)($ref['bonus_paid'] ?? 0) === 1)
        && (int)($ref['bonus_deposit_id'] ?? 0) === $deposit_id;
    if (!$invitee_paid && !$referrer_paid) return null;
    return [
        'referrer' => (int)$ref['referrer_telegram_id'],
        'invitee_paid' => $invitee_paid,
        'referrer_paid' => $referrer_paid,
        'invitee_bonus' => $invitee_paid ? (float)$ref['invitee_bonus_amount'] : 0.0,
        'referrer_bonus' => $referrer_paid ? (float)$ref['bonus_amount'] : 0.0,
        'invitee_notified' => ((int)($ref['invitee_bonus_notified'] ?? 0) === 1),
        'referrer_notified' => ((int)($ref['referrer_bonus_notified'] ?? 0) === 1),
    ];
}

// --- POST /api/bot/referrals ------------------------------------------------
// Body: {"telegram_id": <new user>, "code": "<code from /start payload>"}
// Records the referrer for a brand-new user. Idempotent — first code
// wins. The bot should call this on /start, BEFORE the user deposits.

function bot_ref_record() {
    $in = ref_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) ref_fail(400, 'telegram_id is required.');
    $code = strtoupper(trim((string)($in['code'] ?? '')));
    if ($code === '') ref_fail(400, 'code is required.');

    // The old shared code: record referrer 0, no attribution, no bonus.
    if ($code === REF_SHARED_CODE) {
        $referrer = 0;
    } else {
        $referrer = ref_code_owner($code);
        if ($referrer === false) ref_fail(400, 'Invite code is not valid.');
        if ($referrer === $telegram_id) ref_fail(400, 'You cannot use your own invite code.');
    }

    $db = ref_db();
    if ($db === null) ref_fail(500, 'Database is not available.');
    ref_ensure_tables($db);

    // Idempotent: a user who already has a referrer keeps the first.
    $existing = ref_load_by_referred($db, $telegram_id);
    if ($existing) {
        bot_ok([
            'ok' => true,
            'referrer_telegram_id' => (int)$existing['referrer_telegram_id'],
            'code_used' => $existing['code_used'],
            'already_recorded' => true,
        ]);
        return;
    }

    // A user who already completed a deposit cannot gain a referrer
    // afterwards — the bonus is first-deposit only (see header (e)).
    $stmt = $db->prepare("SELECT COUNT(*) AS n FROM deposits WHERE user_id = ? AND status = 'completed'");
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $n = (int)($stmt->get_result()->fetch_assoc()['n'] ?? 0);
    $stmt->close();
    if ($n > 0) ref_fail(409, 'User already deposited; a referral cannot be recorded afterwards.');

    $stmt = $db->prepare('INSERT INTO bot_referrals (referrer_telegram_id, referred_telegram_id, code_used) VALUES (?, ?, ?)');
    $stmt->bind_param('iis', $referrer, $telegram_id, $code);
    // PHP 8.1+ mysqli throws on duplicate key (1062) instead of
    // returning false — a race between two /start calls for the same
    // user must return the first row, not an empty 500 (same lesson
    // as the delayed-orders file, found live 15 Nov 2026).
    $duplicate = false;
    $inserted = false;
    try {
        $inserted = $stmt->execute();
        if (!$inserted) $duplicate = ((int)$db->errno === 1062);
    } catch (mysqli_sql_exception $e) {
        $duplicate = ((int)$e->getCode() === 1062);
    }
    $stmt->close();
    if (!$inserted) {
        if ($duplicate) {
            $row = ref_load_by_referred($db, $telegram_id);
            if ($row) {
                bot_ok([
                    'ok' => true,
                    'referrer_telegram_id' => (int)$row['referrer_telegram_id'],
                    'code_used' => $row['code_used'],
                    'already_recorded' => true,
                ]);
                return;
            }
        }
        ref_fail(500, 'Could not record the referral.');
    }
    bot_ok([
        'ok' => true,
        'referrer_telegram_id' => $referrer,
        'code_used' => $code,
        'already_recorded' => false,
    ]);
}

// --- GET /api/bot/referrals?telegram_id=X -----------------------------------
// Returns the user's own code + invite link and their referral stats.
// "referrals" counts users they referred (shared-code rows, referrer 0,
// belong to nobody). "bonus_earned" is the sum of bonuses actually
// paid to them. "bonus_pending" counts referred users whose bonus has
// not been paid yet (they have not made a first deposit, or the
// referrer had no auth row when the hook ran).

function bot_ref_stats() {
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) ref_fail(400, 'telegram_id is required.');
    $db = ref_db();
    if ($db === null) ref_fail(500, 'Database is not available.');
    ref_ensure_tables($db);

    $stmt = $db->prepare('SELECT COUNT(*) AS n, COALESCE(SUM(bonus_amount), 0) AS earned, COALESCE(SUM(CASE WHEN bonus_paid = 0 THEN 1 ELSE 0 END), 0) AS pending FROM bot_referrals WHERE referrer_telegram_id = ?');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    bot_ok([
        'code' => ref_code_for($telegram_id),
        'invite_link' => ref_invite_link($telegram_id),
        'referrals' => (int)($row['n'] ?? 0),
        'bonus_earned' => (float)($row['earned'] ?? 0),
        'bonus_pending' => (int)($row['pending'] ?? 0),
    ]);
}

// --- POST /api/bot/referrals/notify-ack --------------------------------------
// Body: {"telegram_id": <invitee>, "deposit_id": <id>, "side":
// "invitee"|"referrer"}. Marks one side's bonus message as sent, so
// a later recheck of the same deposit never re-sends it. The server
// only sets the flag when that side's bonus was really paid for this
// deposit (paid flag set AND bonus deposit id matches) — the bot
// cannot mark a bonus notified that was never paid. Idempotent:
// acking twice is a no-op success. Called by the bot AFTER it sends
// (invitee) or appends (referrer) the bonus message.
function bot_ref_notify_ack() {
    $in = ref_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    $deposit_id = (int)($in['deposit_id'] ?? 0);
    $side = strtolower(trim((string)($in['side'] ?? '')));
    if ($telegram_id <= 0 || $deposit_id <= 0) ref_fail(400, 'telegram_id and deposit_id are required.');
    if ($side !== 'invitee' && $side !== 'referrer') ref_fail(400, 'side must be invitee or referrer.');
    $db = ref_db();
    if ($db === null) ref_fail(500, 'Database is not available.');
    ref_ensure_tables($db);
    $ref = ref_load_by_referred($db, $telegram_id);
    if (!$ref) ref_fail(404, 'No referral recorded.');
    if ($side === 'invitee') {
        $paid = ((int)($ref['invitee_bonus_paid'] ?? 0) === 1);
        $paid_dep = (int)($ref['invitee_bonus_deposit_id'] ?? 0);
        $col = 'invitee_bonus_notified';
    } else {
        $paid = ((int)($ref['bonus_paid'] ?? 0) === 1);
        $paid_dep = (int)($ref['bonus_deposit_id'] ?? 0);
        $col = 'referrer_bonus_notified';
    }
    if (!$paid || $paid_dep !== $deposit_id) ref_fail(409, 'No bonus was paid for this deposit.');
    // $col is an internal constant from the branch above, never user input.
    $stmt = $db->prepare("UPDATE bot_referrals SET $col = 1 WHERE referred_telegram_id = ?");
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $stmt->close();
    bot_ok(['ok' => true, 'side' => $side, 'notified' => true]);
}

// --- Bonus hook: call from the first-deposit credit point -------------------
// MUST be called INSIDE the deposit-credit transaction, AFTER the
// deposit row is marked 'completed' and the depositor's own balance
// is credited, BEFORE commit. See "BONUS HOOK" in the header.
// BOTH SIDES (William, 19:27 EAT 16 Nov 2026): on a referred
// user's FIRST completed deposit, the invitee gets +20% of their own
// deposit AND the referrer gets +20% of it. The two sides are
// independent: each is guarded by its own paid flag, so a retry
// after a partial failure pays only the side that is still unpaid,
// and a second deposit pays nothing. The shared code (referrer 0)
// pays the invitee only — there is no referrer to pay.
// Returns ['paid'=>bool (referrer paid, legacy key), 'bonus'=>float,
// 'referrer'=>int, 'referrer_paid'=>bool, 'referrer_bonus'=>float,
// 'invitee_paid'=>bool, 'invitee_bonus'=>float, 'reason'=>string].
// It never throws for a missing referral / missing referrer — those
// are normal "no bonus due" outcomes, not errors.

function ref_credit_bonus_side($db, $referred_id, $tg_id, $bonus, $deposit_id,
    $flag_col, $amount_col, $dep_col, $at_col) {
    // Credit $bonus to $tg_id's Paxyo balance and mark this side paid
    // for the referral row. Returns true only when BOTH landed; a
    // credit whose flag could not be set is reversed inside this same
    // transaction, so no money moves without the flag. The column
    // names are internal constants from the caller, never user input.
    // A missing auth row (0-row credit) just returns false and leaves
    // the side unpaid for reconciliation — it never throws.
    $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
    $stmt->bind_param('di', $bonus, $tg_id);
    $stmt->execute();
    $credited = $stmt->affected_rows;
    $stmt->close();
    if ($credited !== 1) return false;
    $stmt = $db->prepare("UPDATE bot_referrals SET $flag_col = 1, $amount_col = ?, $dep_col = ?, $at_col = NOW() WHERE referred_telegram_id = ? AND $flag_col = 0");
    $stmt->bind_param('dii', $bonus, $deposit_id, $referred_id);
    $stmt->execute();
    $marked = $stmt->affected_rows;
    $stmt->close();
    if ($marked !== 1) {
        // Near-impossible (the FOR UPDATE lock in the caller
        // serialises concurrent hook runs for this user), but if it
        // ever happens the credit must not stand alone: reverse it
        // inside this same transaction so no money moves without
        // the flag.
        $stmt = $db->prepare('UPDATE auth SET balance = balance - ? WHERE tg_id = ?');
        $stmt->bind_param('di', $bonus, $tg_id);
        $stmt->execute();
        $stmt->close();
        return false;
    }
    return true;
}

function ref_maybe_credit_bonus($db, $telegram_id, $deposit_id, $amount) {
    $telegram_id = (int)$telegram_id;
    $deposit_id = (int)$deposit_id;
    $amount = (float)$amount;
    $out = [
        'paid' => false, 'bonus' => 0.0, 'referrer' => 0,
        'referrer_paid' => false, 'referrer_bonus' => 0.0,
        'invitee_paid' => false, 'invitee_bonus' => 0.0,
        'reason' => 'invalid arguments',
    ];
    if ($telegram_id <= 0 || $deposit_id <= 0 || $amount <= 0) {
        return $out;
    }

    // 1. First deposit only: any OTHER completed deposit disqualifies.
    $stmt = $db->prepare("SELECT COUNT(*) AS n FROM deposits WHERE user_id = ? AND status = 'completed' AND id <> ?");
    $stmt->bind_param('ii', $telegram_id, $deposit_id);
    $stmt->execute();
    $n = (int)($stmt->get_result()->fetch_assoc()['n'] ?? 0);
    $stmt->close();
    if ($n > 0) {
        $out['reason'] = 'not the first deposit';
        return $out;
    }

    // The invitee_* columns must exist before the row below is read
    // (a table created by the older file gains them here — cheap,
    // and this point is only reached on a first deposit).
    ref_ensure_tables($db);

    // 2. Lock the referral row: two concurrent rechecks for the same
    //    deposit cannot both pay. (The caller already holds the
    //    deposit row lock via SELECT ... FOR UPDATE.)
    $stmt = $db->prepare('SELECT * FROM bot_referrals WHERE referred_telegram_id = ? FOR UPDATE');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $ref = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    if (!$ref) {
        $out['reason'] = 'no referral recorded';
        return $out;
    }
    $referrer = (int)$ref['referrer_telegram_id'];
    $out['referrer'] = $referrer;

    // 3. 20% of the first deposit, rounded to 2 decimals — the same
    //    amount for both sides.
    $bonus = round($amount * 0.20, 2);
    if ($bonus <= 0) {
        $out['reason'] = 'bonus rounds to zero';
        return $out;
    }
    $out['bonus'] = $bonus;

    // 4. Invitee side: +20% of their own first deposit, on top of
    //    the deposit itself (their auth row exists — the deposit just
    //    credited it). Runs even for the shared code (referrer 0):
    //    there is no referrer to pay, but the invitee still gets
    //    their 20% — the launch post's promise.
    $invitee_already = ((int)($ref['invitee_bonus_paid'] ?? 0) === 1);
    if (!$invitee_already) {
        if (ref_credit_bonus_side($db, $telegram_id, $telegram_id, $bonus, $deposit_id,
            'invitee_bonus_paid', 'invitee_bonus_amount', 'invitee_bonus_deposit_id', 'invitee_bonus_paid_at')) {
            $out['invitee_paid'] = true;
            $out['invitee_bonus'] = $bonus;
        }
    }

    // 5. Referrer side: the original 20% (15 Nov 2026). Skipped for
    //    the shared code (referrer 0: nobody to pay). Runs even when
    //    the invitee side failed — the two sides are independent,
    //    and a retry pays only the side still unpaid.
    $referrer_already = ((int)$ref['bonus_paid'] === 1);
    if ($referrer > 0 && !$referrer_already) {
        if (ref_credit_bonus_side($db, $telegram_id, $referrer, $bonus, $deposit_id,
            'bonus_paid', 'bonus_amount', 'bonus_deposit_id', 'bonus_paid_at')) {
            $out['referrer_paid'] = true;
            $out['referrer_bonus'] = $bonus;
            $out['paid'] = true;
        }
    }

    $invitee_done = $out['invitee_paid'] || $invitee_already;
    $referrer_done = ($referrer <= 0) || $out['referrer_paid'] || $referrer_already;
    if ($out['invitee_paid'] || $out['referrer_paid']) {
        $out['reason'] = ($invitee_done && $referrer_done)
            ? 'ok'
            : ($invitee_done
                ? 'invitee paid; referrer bonus could not be credited'
                : 'referrer paid; invitee bonus could not be credited');
    } elseif ($invitee_done && $referrer_done) {
        // A retry after both sides already paid: nothing was due.
        $out['reason'] = 'bonus already paid';
    } else {
        $out['reason'] = 'no bonus could be credited';
    }
    return $out;
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'referrals' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_ref_record(); }
//   if ($bp === 'referrals' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_ref_stats(); }
//   if ($bp === 'referrals/notify-ack' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_ref_notify_ack(); }
// (Add the same bot_rate_limit(...) call the other user endpoints use
//  to both lines — copy the exact call from the orders handler.)
//
// BONUS HOOK — one-line MANUAL patch, NOT a dispatch line (see header):
//   In bot_dep_status(), after the auth-balance UPDATE and before
//   $db->commit(); insert:
//       ref_maybe_credit_bonus($db, $telegram_id, $deposit_id, $amt);
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account —
// no money moves: these endpoints never touch balances or orders, and
// the bonus hook is NOT triggered by any call below because no deposit
// is credited):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. my own code — 779060335 derives to REFCVTYSVA3:
//   curl -s "https://paxyo.et/api/bot/referrals?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"code":"REFCVTYSVA3",
//      "invite_link":"https://t.me/paxorder_bot?start=REFCVTYSVA3",
//      "referrals":0,"bonus_earned":0,"bonus_pending":0}
//   # 2. record a referral with ANOTHER user's code (123456789 ->
//   #    REF21I3V91B). This is a test-only code; nobody owns it live:
//   curl -s -X POST https://paxyo.et/api/bot/referrals \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"REF21I3V91B"}'
//   -> expect {"success":true,"ok":true,"referrer_telegram_id":123456789,
//      "code_used":"REF21I3V91B","already_recorded":false}
//   # 3. same call again -> first wins, same referrer, no second row:
//   curl -s -X POST https://paxyo.et/api/bot/referrals \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"REF21I3V91B"}'
//   -> expect "already_recorded":true, same referrer_telegram_id.
//   # 4. a different code for the same user must NOT replace the first:
//   curl -s -X POST https://paxyo.et/api/bot/referrals \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"REF3723FB335"}'
//   -> expect "already_recorded":true, referrer_telegram_id still 123456789.
//   # 5. self-referral is rejected (own code REFCVTYSVA3):
//   curl -s -X POST https://paxyo.et/api/bot/referrals \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"REFCVTYSVA3"}'
//   -> expect {"success":false,"error":"You cannot use your own invite code."}
//   # 6. a mistyped code fails the checksum (last char changed):
//   curl -s -X POST https://paxyo.et/api/bot/referrals \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"code":"REF21I3V91C"}'
//   -> expect {"success":false,"error":"Invite code is not valid."}
//   # 7. shared code on a FRESH test id (no row yet) records referrer 0.
//   #    Use a throwaway id, e.g. 779060336, then delete it below:
//   curl -s -X POST https://paxyo.et/api/bot/referrals \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060336,"code":"REF3723FB335"}'
//   -> expect {"success":true,"ok":true,"referrer_telegram_id":0,
//      "code_used":"REF3723FB335","already_recorded":false}
//   # 8. BONUS HOOK — verify by code inspection + a REAL first deposit
//   #    ONLY when William authorises one: after a referred user makes
//   #    their first deposit and it completes, check:
//   #      SELECT referrer_telegram_id, bonus_paid, bonus_amount,
//   #             bonus_deposit_id,
//   #             invitee_bonus_paid, invitee_bonus_amount,
//   #             invitee_bonus_deposit_id FROM bot_referrals
//   #       WHERE referred_telegram_id=<the new user>;
//   #    -> expect bonus_paid=1, bonus_amount = 20% of the deposit,
//   #       bonus_deposit_id = that deposit's id; AND
//   #       invitee_bonus_paid=1, invitee_bonus_amount = the same
//   #       20%, invitee_bonus_deposit_id = the same deposit id.
//   #       Both the referrer's and the new user's auth.balance
//   #       increased by exactly that amount. A shared-code user
//   #       (referrer 0) expects invitee_bonus_paid=1 and
//   #       bonus_paid=0. A SECOND deposit for the same user must
//   #       change nothing. There is NO safe curl-only test for the
//   #       hook — it only fires on a real completed deposit, by
//   #       design. Do NOT fake one by hand-editing a deposits row
//   #       to 'completed': that would credit a balance.
//   Then DELETE the test rows and confirm they are gone:
//   mysql -e "DELETE FROM bot_referrals WHERE referred_telegram_id IN (779060335, 779060336); SELECT COUNT(*) FROM bot_referrals WHERE referred_telegram_id IN (779060335, 779060336);"
//   (use the same MySQL credentials db.php uses; never print them.)
//   NOTE: step 2/3 leave the operating account with NO referral row
//   after cleanup, so a later real /start with a code still works.
// ============================================================================
