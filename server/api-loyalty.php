<?php
// ============================================================================
// Loyalty bonus for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot, feature 9 (loyalty bonus
// after 10 completed orders) of the 10-feature build round —
// SERVER SIDE ONLY.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/loyalty/check  {telegram_id}
//     -> {"ok":true,"awarded":false,"milestone":0,"bonus_etb":0,
//         "orders_total_etb":12.40,"orders_count":4,
//         "already_awarded":false}
//        No milestone reached yet (fewer than 10 completed orders).
//     -> {"ok":true,"awarded":true,"milestone":1,"bonus_etb":2.31,
//         "orders_total_etb":46.20,"orders_count":10,
//         "already_awarded":false,"username":"lebo72"}
//        Milestone 1 reached: 10 completed orders, 10% of their
//        combined total credited to the user's Paxyo balance.
//        Every reply also carries "username" (best-effort from the
//        auth table; null when unknown) so the bot can tell the
//        admin WHO the bonus went to when it is credited.
//     -> {"ok":true,"awarded":false,"milestone":1,"bonus_etb":0,
//         "orders_total_etb":46.20,"orders_count":13,
//         "already_awarded":true}
//        Milestone 1 was already paid on an earlier call — safe to
//        call again, nothing moves twice.
//
// THE BONUS — 10% of the milestone's 10 orders, Paxyo balance only:
//   milestone = floor(completed_orders / 10). A milestone is the
//   10 completed orders (milestone-1)*10+1 .. milestone*10, oldest
//   first by order id. bonus_etb = 10% of their combined ETB total,
//   computed in whole cents so a 10% share never rounds to a wrong
//   figure. The bonus is credited to the user's Paxyo balance
//   (auth.balance — the same column the referral bonus uses) —
//   never cash, per the Paxyo terms. The bonus is paid ONLY on real
//   completed orders, once per milestone, never twice.
//
//   LOYALTY_BONUS_PERCENT = 10 below is the ONE place the percent
//   lives server-side. The bot-side constant is
//   LOYALTY_BONUS_PERCENT = 10 as well. Change the number here (and
//   there) and the bonus changes everywhere. William can change it
//   in one place.
//
// IDEMPOTENCY — safe to call repeatedly, and safe under races:
//   1. The award row is UNIQUE(telegram_id, milestone): a second
//      call for the same milestone finds the row and returns
//      awarded:false without touching the balance.
//   2. The credit + award insert run inside ONE transaction: if
//      the insert hits the UNIQUE key (two calls racing), the
//      whole transaction rolls back, undoing the credit — so the
//      bonus can never be paid twice.
//   3. Only status='completed' orders count (see "STATUS" below).
//      Cancelled / refunded / failed orders never count, and an
//      order that later changes status cannot retroactively earn
//      a bonus for a milestone already paid — the window is fixed
//      by order id at award time.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_loyalty_awards  telegram_id BIGINT, milestone INT,
//                       bonus_etb DECIMAL(12,2),
//                       orders_total_etb DECIMAL(12,2),
//                       awarded_at DATETIME,
//                       UNIQUE(telegram_id, milestone)
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-loyalty.php        (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php            (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test row.
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient method
// to add, mirroring save_session / load_session in bot.py):
//   check_loyalty(telegram_id) — POST /loyalty/check, 404-tolerant
//     (return None on 404, log a warning, keep working — the bonus
//     simply is not switched on yet). Call it after an order
//     completes (and only then — the check is cheap, but there is
//     no reason to call it on every message). On awarded:true the
//     bot tells the user the bonus figure from the reply — never
//     a figure it computed itself. On awarded:false the bot says
//     nothing (or, when milestone is 0, how many completed orders
//     remain until the next bonus: (milestone+1)*10 - orders_count).
//   Reply fields: awarded (bool), milestone (int — 0 when no
//   milestone reached yet), bonus_etb (float, 0 when not awarded),
//   orders_total_etb (float — the combined ETB total of the orders
//   in the current milestone window: exactly 10 orders when a
//   milestone is complete, the partial set when it is not),
//   orders_count (int — the user's total completed orders),
//   already_awarded (bool — true when this milestone was paid on
//   an earlier call).
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use loy_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch line (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - NO account-existence check before counting: a user with no
//     completed orders simply gets awarded:false. The BALANCE credit,
//     by contrast, requires an auth row — see loy_award() step 4.
//   - No money is created from nothing: the bonus is 10% of money the
//     user already spent on real completed orders, paid once per
//     milestone, from Paxyo's margin (the same economics as the
//     referral bonus).
//   - STATUS: only orders with status exactly 'completed' count.
//     This matches api-admin-stats.php (SUM(total) WHERE status =
//     'completed') and api-order-ratings.php ("only status
//     'completed' counts as finished"). api-order-rescue.php ALSO
//     treats 'complete' / 'success' / 'paid' as finished spellings
//     — if the live orders table actually uses one of those, this
//     file under-counts. Confirm with SELECT DISTINCT status FROM
//     orders on the server before going live (see OPEN QUESTIONS (a)).
//   - TOTAL COLUMN: the order total is read as 'total' first, then
//     'charge', then 'amount' (the same fallback list
//     api-order-rescue.php uses — primary name first). If the live
//     orders table names it differently, change ONLY the list in
//     loy_pick_order_field().
//   - OWNER COLUMN: the WHERE clause uses telegram_id (the owner
//     column api-order-rescue.php assumes first). If the live
//     orders table calls it user_id, change the two queries in
//     loy_completed_orders().
//   - If 10 completed orders have a combined total of 0 ETB (only
//     possible if orders were free), the bonus rounds to 0: no
//     credit is made and no award row is written, so the milestone
//     stays open and the next check retries. This cannot happen
//     with real paid orders.
//
// OPEN QUESTIONS (do not guess — confirm on the server / with William):
//   (a) STATUS SPELLING — see "STATUS" above. 'completed' is the
//       spelling every verified endpoint uses, but the rescue file's
//       broader list ('complete', 'success', 'paid') means the live
//       table may hold one of those. One SELECT DISTINCT status
//       FROM orders settles it.
//   (b) LOYALTY_BONUS_PERCENT = 10 is William's approved figure for
//       this round (10% of the 10 orders' total). If he wants a
//       different percent, change the constant — nothing else.
//   (c) The award test below only covers the no-milestone path.
//       A real award moves real money (10% of 10 real orders) and
//       needs William's approval + a user who genuinely has 10
//       completed orders. There is NO safe curl-only test for the
//       award path — do NOT fake it by hand-editing orders rows.
// ============================================================================

// The loyalty bonus percent. Change this ONE number to change the
// bonus everywhere. The bot-side constant LOYALTY_BONUS_PERCENT = 10
// must match it.
define('LOYALTY_BONUS_PERCENT', 10);

// --- small helpers (loy_ prefix so nothing collides with bot.php) -----------

function loy_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function loy_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function loy_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function loy_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_loyalty_awards (
        telegram_id BIGINT NOT NULL,
        milestone INT NOT NULL,
        bonus_etb DECIMAL(12,2) NOT NULL,
        orders_total_etb DECIMAL(12,2) NOT NULL,
        awarded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_loy_user_milestone (telegram_id, milestone),
        INDEX idx_loy_user (telegram_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Pick the first candidate column that exists on the row and is not
// null/empty. Same fallback list api-order-rescue.php uses — primary
// name first ('total', then 'charge', then 'amount'). Returns the raw
// value, or null when no candidate column has a value.
function loy_pick_order_field($row, $candidates) {
    foreach ($candidates as $col) {
        if (array_key_exists($col, $row) && $row[$col] !== null && $row[$col] !== '') {
            return $row[$col];
        }
    }
    return null;
}

function loy_award_row($db, $telegram_id, $milestone) {
    $stmt = $db->prepare('SELECT telegram_id, milestone, bonus_etb, orders_total_etb, awarded_at FROM bot_loyalty_awards WHERE telegram_id = ? AND milestone = ? LIMIT 1');
    $stmt->bind_param('ii', $telegram_id, $milestone);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// All of the user's COMPLETED orders, oldest first by order id.
// Each entry is ['id' => int, 'total' => float|null] — total is null
// when no candidate total column had a numeric value on that row
// (the caller fails honestly instead of inventing a figure).
function loy_completed_orders($db, $telegram_id) {
    $stmt = $db->prepare("SELECT * FROM orders WHERE telegram_id = ? AND status = 'completed' ORDER BY id ASC");
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $result = $stmt->get_result();
    $orders = [];
    while ($row = $result->fetch_assoc()) {
        $total = loy_pick_order_field($row, ['total', 'charge', 'amount']);
        $orders[] = [
            'id' => (int)($row['id'] ?? 0),
            'total' => ($total === null || !is_numeric($total)) ? null : (float)$total,
        ];
    }
    $stmt->close();
    return $orders;
}

// The user's username from auth, best-effort — the bot reports it
// to the admin when a bonus is credited. Null when the user has no
// auth row or no username; never fails the check.
function loy_username($db, $telegram_id) {
    try {
        $stmt = $db->prepare('SELECT username FROM auth WHERE tg_id = ? LIMIT 1');
        $stmt->bind_param('i', $telegram_id);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_assoc();
        $stmt->close();
        $name = $row['username'] ?? null;
        return ($name === null || $name === '') ? null : (string)$name;
    } catch (mysqli_sql_exception $ignored) {
        return null;
    }
}

function loy_reply($awarded, $milestone, $bonus_etb, $orders_total_etb, $orders_count, $already_awarded, $username = null) {
    bot_ok([
        'ok' => true,
        'awarded' => $awarded,
        'milestone' => $milestone,
        'bonus_etb' => $bonus_etb,
        'orders_total_etb' => $orders_total_etb,
        'orders_count' => $orders_count,
        'already_awarded' => $already_awarded,
        'username' => $username,
    ]);
}

// --- POST /api/bot/loyalty/check --------------------------------------------
// Body: {"telegram_id": <user>}
// Counts the user's COMPLETED orders only. milestone =
// floor(completed_count / 10). If no milestone is reached, or the
// milestone was already awarded, returns awarded:false and moves no
// money. Otherwise credits 10% of that milestone's 10 orders to the
// user's Paxyo balance and records the award — inside one
// transaction, so the bonus can never be paid twice.

function bot_loy_check() {
    $in = loy_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) loy_fail(400, 'telegram_id is required.');

    $db = loy_db();
    if ($db === null) loy_fail(500, 'Database is not available.');
    loy_ensure_table($db);
    $username = loy_username($db, $telegram_id);

    $orders = loy_completed_orders($db, $telegram_id);
    $count = count($orders);
    $milestone = (int)floor($count / 10);

    // No milestone reached yet: report progress, move no money.
    if ($milestone === 0) {
        $partial_total = 0.0;
        foreach ($orders as $o) {
            if ($o['total'] !== null) $partial_total += $o['total'];
        }
        loy_reply(false, 0, 0.0, round($partial_total, 2), $count, false, $username);
        return;
    }

    // The 10 orders of this milestone, oldest first.
    $window = array_slice($orders, ($milestone - 1) * 10, 10);
    $window_total = 0.0;
    foreach ($window as $o) {
        if ($o['total'] === null) {
            // An order total is not on record — say so plainly
            // instead of guessing a bonus from a partial total.
            loy_fail(500, 'An order total is not on record, so the loyalty bonus cannot be calculated.');
        }
        $window_total += $o['total'];
    }
    $window_total = round($window_total, 2);

    // Already awarded? The idempotency check — re-checked again
    // inside the transaction below, in case a concurrent call paid
    // this milestone between this read and the credit.
    if (loy_award_row($db, $telegram_id, $milestone)) {
        loy_reply(false, $milestone, 0.0, $window_total, $count, true, $username);
        return;
    }

    // 10% of the milestone's combined total, in whole cents — so a
    // small total never rounds to a wrong figure.
    $total_cents = (int)round($window_total * 100);
    $bonus_cents = (int)round($total_cents * LOYALTY_BONUS_PERCENT / 100);
    $bonus = $bonus_cents / 100.0;
    if ($bonus <= 0) {
        // 10 completed orders totalling 0 ETB: nothing to credit and
        // no award row is written, so the milestone stays open and
        // the next check retries. Cannot happen with real paid orders.
        loy_reply(false, $milestone, 0.0, $window_total, $count, false, $username);
        return;
    }

    // Credit + award in ONE transaction. If the award insert hits
    // the UNIQUE key (a racing call paid first), the rollback undoes
    // the credit — the bonus can never be paid twice.
    $db->begin_transaction();
    try {
        if (loy_award_row($db, $telegram_id, $milestone)) {
            $db->rollback();
            loy_reply(false, $milestone, 0.0, $window_total, $count, true, $username);
            return;
        }

        // Credit the user's Paxyo balance — the exact pattern
        // api-referrals.php uses for the referral bonus
        // (UPDATE auth SET balance = balance + ? WHERE tg_id = ?).
        // If they have no auth row, change nothing and fail honestly.
        $stmt = $db->prepare('UPDATE auth SET balance = balance + ? WHERE tg_id = ?');
        $stmt->bind_param('di', $bonus, $telegram_id);
        $stmt->execute();
        $credited = $stmt->affected_rows;
        $stmt->close();
        if ($credited !== 1) {
            $db->rollback();
            loy_fail(500, 'Could not credit the loyalty bonus: the user has no Paxyo account.');
        }

        // Record the award — guarded by UNIQUE(telegram_id, milestone).
        $stmt = $db->prepare('INSERT INTO bot_loyalty_awards (telegram_id, milestone, bonus_etb, orders_total_etb) VALUES (?, ?, ?, ?)');
        $stmt->bind_param('iidd', $telegram_id, $milestone, $bonus, $window_total);
        // PHP 8.1+ mysqli throws on duplicate key (1062) instead of
        // returning false — a race between two check calls for the
        // same milestone must return the first award, not an empty
        // 500 (same lesson as the referrals file, found live 15 Nov
        // 2026).
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
            $db->rollback();
            if ($duplicate) {
                loy_reply(false, $milestone, 0.0, $window_total, $count, true, $username);
                return;
            }
            loy_fail(500, 'Could not record the loyalty award.');
        }

        $db->commit();
    } catch (mysqli_sql_exception $e) {
        // Any other DB failure mid-transaction: roll back so no
        // credit stands without its award row.
        try { $db->rollback(); } catch (mysqli_sql_exception $ignored) { }
        loy_fail(500, 'Could not credit the loyalty bonus.');
    }

    loy_reply(true, $milestone, $bonus, $window_total, $count, false, $username);
}

// ============================================================================
// DISPATCH — insert this line in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'loyalty/check' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_loy_check(); }
// (Add the same bot_rate_limit(...) call the other user endpoints use
//  to the line — copy the exact call from the orders handler.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-loyalty.php` on
// the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (uses telegram_id 779060337, a THROWAWAY id with no
// orders — the no-milestone path moves NO money, so it is safe to run
// without approval):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. fresh id, no completed orders -> awarded:false, milestone:0:
//   curl -s -X POST https://paxyo.et/api/bot/loyalty/check \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060337}'
//   -> expect {"success":true,"ok":true,"awarded":false,"milestone":0,
//      "bonus_etb":0,"orders_total_etb":0,"orders_count":0,
//      "already_awarded":false}
//   # 2. same call again -> identical reply, still no award row:
//   curl -s -X POST https://paxyo.et/api/bot/loyalty/check \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060337}'
//   -> expect the same as step 1.
//   # 3. missing telegram_id -> 400, nothing stored:
//   curl -s -X POST https://paxyo.et/api/bot/loyalty/check \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{}'
//   -> expect {"success":false,"error":"telegram_id is required."}
//   # 4. the operating account (779060335) reports its real progress
//   #    — read-only, moves no money unless it has an UNAWARDED
//   #    milestone, in which case this call WOULD credit 10%:
//   curl -s -X POST https://paxyo.et/api/bot/loyalty/check \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect awarded:false (milestone 0, or already_awarded:true)
//      OR awarded:true with the real 10% bonus — ONLY run this step
//      with William's approval, and if it awards, verify:
//        SELECT telegram_id, milestone, bonus_etb, orders_total_etb
//          FROM bot_loyalty_awards WHERE telegram_id=779060335;
//      and that auth.balance for tg_id 779060335 rose by exactly
//      bonus_etb. A real award is real Paxyo balance (not cash) and
//      is NOT reversed by the cleanup below.
//   Then DELETE the test rows and confirm they are gone (this only
//   removes award rows for ids that never earned one — step 4's row,
//   if it awarded, must be reconciled by hand, not deleted here):
//   mysql -e "DELETE FROM bot_loyalty_awards WHERE telegram_id=779060337; SELECT COUNT(*) FROM bot_loyalty_awards WHERE telegram_id=779060337;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
