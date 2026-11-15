<?php
// ============================================================================
// Fraud watch for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot feature 17 — suspicious
// patterns are flagged to the admin (one alert per user per day
// max); the bot NEVER blocks a user automatically, it only flags.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/fraud-watch
//     -> {"flags":[{telegram_id, username, type, detail, count}, ...]}
//        One row per flagged user per pattern, only for patterns
//        that fired TODAY and have not been alerted yet today.
//        Calling the endpoint again the same day returns an empty
//        list (the alert is claimed at read time — see below), so
//        the bot's ~15-minute cycle cannot spam the admin.
//        Types:
//          "rapid_orders"     >= FRD_RAPID_ORDERS orders in the last
//                             10 minutes by one user.
//          "failed_deposits"  >= FRD_FAILED_DEPOSITS failed deposits
//                             in the last 24h by one user.
//          "new_account_burst" >= FRD_NEW_ACCOUNTS new accounts in
//                             the last hour (a burst, not one user:
//                             telegram_id is null, username is null,
//                             detail names the count).
//
// CLAIMING (how "one alert per user per day" works): the endpoint
// inserts (telegram_id, type, date) into bot_fraud_alerts with a
// UNIQUE key on (telegram_id, type, date) and INSERT IGNORE — only
// the flags whose insert actually landed are returned. A flag that
// fires again the same day inserts nothing and is NOT returned.
// The table is created automatically on first call (utf8mb4).
// "new_account_burst" claims under telegram_id 0, so a burst is
// also reported at most once a day.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_fraud_alerts  telegram_id BIGINT NOT NULL, flag_type
//                     VARCHAR(32) NOT NULL, alert_date DATE NOT
//                     NULL, created_at TIMESTAMP NOT NULL DEFAULT
//                     CURRENT_TIMESTAMP, UNIQUE (telegram_id,
//                     flag_type, alert_date).
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-fraud-watch.php        (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). Read-only in
//      effect: the only write is the alert-claim rows in
//      bot_fraud_alerts, which is exactly the dedupe mechanism. No
//      balances, orders or users change.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use frd_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - The bot calls this endpoint on its scheduler cycle (about
//     every 15 minutes). No per-user rate limit is applied here.
//   - The username in each flag comes from auth (best-effort); a
//     user with no auth row reads null. The flag still fires — the
//     telegram_id is what the admin needs.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. THRESHOLDS ARE A PROPOSAL, NOT A WILLIAM-APPROVED RULE.
//       FRD_RAPID_ORDERS = 5 orders in 10 minutes, FRD_FAILED_
//       DEPOSITS = 3 failed deposits in 24h, FRD_NEW_ACCOUNTS =
//       10 new accounts in 1 hour. These are my thresholds from
//       what "suspicious" usually looks like; William must confirm
//       or change them (they are the three constants at the top —
//       one line each).
//   A2. orders has telegram_id, status, created_at; deposits has
//       user_id (= telegram id, confirmed by the admin-stats file),
//       status, created_at; auth has tg_id, username, created_at.
//       A failed deposit is status = 'failed'. If the live table
//       also uses 'rejected' / 'cancelled' for failed payments,
//       add them to the failed-deposits query (and tell the deposits
//       owner, so the two places agree).
//   A3. "New accounts" is a count of auth rows created in the last
//       hour — it is a burst proxy, not a "one source" proof. The
//       server cannot see a shared source (IP / device) from the
//       tables it has; if William wants real source tracking, the
//       signup path must record it first.
//   A4. The alert claim is date-based in the server's timezone
//       (bot_fraud_alerts.alert_date is a DATE, compared with
//       CURDATE()). A flag that fires at 23:55 and again at 00:05
//       alerts twice — once per calendar day, which is the rule
//       William approved ("one alert per user per day").
// ============================================================================

// --- thresholds (A1: William must confirm or change these) ------------------
if (!defined('FRD_RAPID_ORDERS')) define('FRD_RAPID_ORDERS', 5);
if (!defined('FRD_RAPID_MINUTES')) define('FRD_RAPID_MINUTES', 10);
if (!defined('FRD_FAILED_DEPOSITS')) define('FRD_FAILED_DEPOSITS', 3);
if (!defined('FRD_FAILED_HOURS')) define('FRD_FAILED_HOURS', 24);
if (!defined('FRD_NEW_ACCOUNTS')) define('FRD_NEW_ACCOUNTS', 10);
if (!defined('FRD_NEW_ACCOUNTS_HOURS')) define('FRD_NEW_ACCOUNTS_HOURS', 1);

// --- small helpers (frd_ prefix so nothing collides with bot.php) -----------

function frd_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function frd_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function frd_ensure_tables($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_fraud_alerts (
        telegram_id BIGINT NOT NULL,
        flag_type VARCHAR(32) NOT NULL,
        alert_date DATE NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_frd_alert (telegram_id, flag_type, alert_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// Best-effort username for a telegram id, from auth. Null when the
// user has no auth row. Never throws.
function frd_username($db, $telegram_id) {
    try {
        $stmt = $db->prepare('SELECT username FROM auth WHERE tg_id = ? LIMIT 1');
        $stmt->bind_param('i', $telegram_id);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_assoc();
        $stmt->close();
        if ($row && (string)$row['username'] !== '') return (string)$row['username'];
    } catch (mysqli_sql_exception $e) { /* fall through */ }
    return null;
}

// Claim (telegram_id, type) for today. Returns true only when this
// call is the first claim of the day — that is the "one alert per
// user per day" rule. INSERT IGNORE + the UNIQUE key make the claim
// atomic: two concurrent cycles cannot both win.
function frd_claim($db, $telegram_id, $type) {
    try {
        $stmt = $db->prepare('INSERT IGNORE INTO bot_fraud_alerts (telegram_id, flag_type, alert_date) VALUES (?, ?, CURDATE())');
        $stmt->bind_param('is', $telegram_id, $type);
        $stmt->execute();
        $claimed = $stmt->affected_rows === 1;
        $stmt->close();
        return $claimed;
    } catch (mysqli_sql_exception $e) {
        return false;
    }
}

// --- GET /api/bot/fraud-watch ------------------------------------------------

function bot_frd_fraud_watch() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') frd_fail(405, 'Method not allowed.');
    $db = frd_db();
    if ($db === null) frd_fail(500, 'Database is not available.');
    frd_ensure_tables($db);

    $flags = [];

    // 1. Rapid-fire orders: many orders from one user in a short
    //    window. Any status counts — even failed ones are a burst.
    try {
        $res = $db->query(
            'SELECT telegram_id, COUNT(*) AS c FROM orders '
            . 'WHERE created_at >= DATE_SUB(NOW(), INTERVAL ' . (int)FRD_RAPID_MINUTES . ' MINUTE) '
            . 'GROUP BY telegram_id HAVING c >= ' . (int)FRD_RAPID_ORDERS . ' '
            . 'ORDER BY c DESC LIMIT 20'
        );
        if ($res !== false) {
            while ($row = $res->fetch_assoc()) {
                $tg = (int)$row['telegram_id'];
                if (!frd_claim($db, $tg, 'rapid_orders')) continue;
                $flags[] = [
                    'telegram_id' => $tg,
                    'username' => frd_username($db, $tg),
                    'type' => 'rapid_orders',
                    'detail' => (int)$row['c'] . ' orders in ' . (int)FRD_RAPID_MINUTES . ' minutes',
                    'count' => (int)$row['c'],
                ];
            }
        }
    } catch (mysqli_sql_exception $e) { /* a failed check flags nothing */ }

    // 2. Repeated failed payments: many failed deposits from one
    //    user in a day. A user whose card keeps failing is either
    //    testing stolen cards or stuck in a loop — either way the
    //    admin should look.
    try {
        $res = $db->query(
            "SELECT user_id, COUNT(*) AS c FROM deposits "
            . "WHERE status = 'failed' "
            . 'AND created_at >= DATE_SUB(NOW(), INTERVAL ' . (int)FRD_FAILED_HOURS . ' HOUR) '
            . 'GROUP BY user_id HAVING c >= ' . (int)FRD_FAILED_DEPOSITS . ' '
            . 'ORDER BY c DESC LIMIT 20'
        );
        if ($res !== false) {
            while ($row = $res->fetch_assoc()) {
                $tg = (int)$row['user_id'];
                if (!frd_claim($db, $tg, 'failed_deposits')) continue;
                $flags[] = [
                    'telegram_id' => $tg,
                    'username' => frd_username($db, $tg),
                    'type' => 'failed_deposits',
                    'detail' => (int)$row['c'] . ' failed deposits in ' . (int)FRD_FAILED_HOURS . 'h',
                    'count' => (int)$row['c'],
                ];
            }
        }
    } catch (mysqli_sql_exception $e) { /* a failed check flags nothing */ }

    // 3. New-account burst: many accounts created in the last hour.
    //    Not one user — telegram_id 0 claims it once a day.
    try {
        $res = $db->query(
            'SELECT COUNT(*) AS c FROM auth '
            . 'WHERE created_at >= DATE_SUB(NOW(), INTERVAL ' . (int)FRD_NEW_ACCOUNTS_HOURS . ' HOUR)'
        );
        if ($res !== false) {
            $row = $res->fetch_assoc();
            $burst = (int)($row['c'] ?? 0);
            if ($burst >= (int)FRD_NEW_ACCOUNTS && frd_claim($db, 0, 'new_account_burst')) {
                $flags[] = [
                    'telegram_id' => null,
                    'username' => null,
                    'type' => 'new_account_burst',
                    'detail' => $burst . ' new accounts in the last hour',
                    'count' => $burst,
                ];
            }
        }
    } catch (mysqli_sql_exception $e) { /* a failed check flags nothing */ }

    bot_ok(['flags' => $flags]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'fraud-watch' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_frd_fraud_watch(); }
//
// LIVE CURL TEST — the only write is the alert-claim rows in
// bot_fraud_alerts (the dedupe mechanism). No balances, orders or
// users change. To see a flag fire, the live data must actually
// cross a threshold — on a quiet day the honest answer is an empty
// list. To test the claim without waiting for a real burst, insert
// a test row into bot_fraud_alerts and check the second call:
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/fraud-watch" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"flags":[...]} — empty on a quiet day.
//   Call it AGAIN immediately — the second call must return the
//   same or fewer flags (a flag already claimed today never
//   re-appears). Then clean the test claim rows if you inserted any:
//   mysql -e "DELETE FROM bot_fraud_alerts WHERE alert_date=CURDATE();"
//   (use the same MySQL credentials db.php uses; never print them.)
//   NOTE: deleting today's claims re-arms the alerts — only do it
//   for a test, never after a real flag has been sent to the admin.
// ============================================================================
