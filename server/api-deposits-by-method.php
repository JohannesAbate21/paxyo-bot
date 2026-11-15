<?php
// ============================================================================
// Deposit method report for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot feature 18 — the admin bot
// /deposits-by-method shows deposits broken down by method
// (Telebirr, CBE, M-Pesa, CBE Birr) for the last 7 days + all time.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/admin/deposits-by-method
//     -> {"methods":[{method, count_7d, amount_7d, count_all,
//         amount_all}, ...]}
//        One row per method, in a fixed order (Telebirr, CBE, M-Pesa,
//        CBE Birr). Only COMPLETED deposits count — a pending or
//        failed deposit is not money in. The 7-day window is the last
//        7 EAT calendar days, today included (same window shape as
//        the admin-stats endpoint).
//
// HOW THE METHOD IS READ: the deposits table carries chapa_response
// (JSON) — the create endpoint stores the Chapa charge reply there,
// and the reply carries the payment method. The code reads the
// method from that JSON (candidates below); when the JSON has no
// method, or the row has no chapa_response at all, the deposit is
// counted under "Unknown" instead of being dropped silently.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-deposits-by-method.php  (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php               (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). Read-only: no
//      money moves, no rows change.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use dbm_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - This is an ADMIN read (the admin bot calls it with the same
//     X-Bot-Secret). No per-user rate limit is applied here.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. deposits has amount, status, created_at (the admin-stats
//       endpoint already assumes these) and chapa_response (JSON —
//       the deposits file stores the Chapa charge reply there). If
//       chapa_response does not exist, every deposit reads as
//       "Unknown" — the report still works, it just cannot split by
//       method. Check with SHOW COLUMNS FROM deposits.
//   A2. The method inside chapa_response: the Chapa charge reply
//       carries the payment type under one of the keys in
//       DBM_METHOD_KEYS below (the deposits file reads `method` from
//       the same reply for the deposit record — confirm that key
//       name there and trim this list). Values are normalised:
//       telebirr -> Telebirr, cbe -> CBE, cbebirr -> CBE Birr,
//       mpesa -> M-Pesa.
//   A3. CAVEAT (do not "fix" silently): the deposits create
//       endpoint normalises cbebirr -> cbe at create time (see
//       api-deposits.php), so a CBE Birr deposit may be stored as
//       method "cbe" and will then show under CBE, not CBE Birr,
//       in this report. That is a data problem, not a report bug:
//       until the create endpoint stores cbebirr separately, the
//       CBE Birr row will under-count. Flag it to William if the
//       live numbers look wrong for CBE Birr.
//   A4. EAT is UTC+3 all year (no daylight saving in Ethiopia), so
//       the UTC bounds are a fixed -3h shift — same as the
//       admin-stats endpoint. created_at is compared against UTC
//       bounds (see its A2).
// ============================================================================

// --- small helpers (dbm_ prefix so nothing collides with bot.php) -----------

// Chapa reply keys that may carry the payment method, in order.
// TO VERIFY (A2): confirm against api-deposits.php.
if (!defined('DBM_METHOD_KEYS')) define('DBM_METHOD_KEYS', 'method,payment_method,type,channel');

function dbm_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function dbm_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function dbm_has_column($db, $table, $col) {
    try {
        $stmt = $db->prepare('SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ? LIMIT 1');
        $stmt->bind_param('ss', $table, $col);
        $stmt->execute();
        $found = $stmt->get_result()->fetch_assoc() !== null;
        $stmt->close();
        return $found;
    } catch (mysqli_sql_exception $e) {
        return false;
    }
}

// Window of the last 7 EAT calendar days, today included, as UTC
// bounds for created_at. Same shape as adm_window(7).
function dbm_window_7d() {
    $tz = new DateTimeZone('Africa/Addis_Ababa');
    $now = new DateTime('now', $tz);
    $start_eat = new DateTime($now->format('Y-m-d') . ' 00:00:00', $tz);
    $start_eat->modify('-6 days');
    $end_eat = new DateTime($now->format('Y-m-d') . ' 00:00:00', $tz);
    $end_eat->modify('+1 day');
    $utc = new DateTimeZone('UTC');
    $start_eat->setTimezone($utc);
    $end_eat->setTimezone($utc);
    return [
        'date' => $now->format('Y-m-d'),
        'from' => (clone $start_eat)->setTimezone($tz)->format('Y-m-d'),
        'start_utc' => $start_eat->format('Y-m-d H:i:s'),
        'end_utc' => $end_eat->format('Y-m-d H:i:s'),
    ];
}

// Normalise a raw method value from the Chapa reply to the display
// label the admin bot shows. Unknown values pass through as-is
// (capitalised), never dropped.
function dbm_method_label($raw) {
    $v = strtolower(trim((string)$raw));
    $v = str_replace([' ', '-', '_'], '', $v);
    switch ($v) {
        case 'telebirr':
        case 'telebirrussd':
            return 'Telebirr';
        case 'cbe':
        case 'cbebank':
        case 'cbe_bank':
        case 'commercialbankofethiopia':
            return 'CBE';
        case 'cbebirr':
        case 'cbebirrussd':
            return 'CBE Birr';
        case 'mpesa':
        case 'm-pesa':
        case 'mpesastk':
            return 'M-Pesa';
        case '':
            return 'Unknown';
        default:
            return ucfirst(trim((string)$raw));
    }
}

// Pull the method out of one deposit row: the chapa_response JSON
// first (keys in DBM_METHOD_KEYS) — the raw Chapa reply is the
// source of truth, because the stored `method` column is
// normalised at create time (cbebirr -> cbe, see A3). A plain
// `method` column is the fallback when there is no reply JSON.
// Returns the raw value or null.
function dbm_row_method($row, $has_method_col) {
    if (isset($row['chapa_response']) && (string)$row['chapa_response'] !== '') {
        $decoded = json_decode((string)$row['chapa_response'], true);
        if (is_array($decoded)) {
            foreach (explode(',', DBM_METHOD_KEYS) as $key) {
                if (isset($decoded[$key]) && (string)$decoded[$key] !== '') {
                    return $decoded[$key];
                }
            }
            // Some Chapa replies nest the charge under data / tx.
            foreach (['data', 'tx', 'transaction'] as $nest) {
                if (isset($decoded[$nest]) && is_array($decoded[$nest])) {
                    foreach (explode(',', DBM_METHOD_KEYS) as $key) {
                        if (isset($decoded[$nest][$key]) && (string)$decoded[$nest][$key] !== '') {
                            return $decoded[$nest][$key];
                        }
                    }
                }
            }
        }
    }
    if ($has_method_col && isset($row['method']) && (string)$row['method'] !== '') {
        return $row['method'];
    }
    return null;
}

// --- GET /api/bot/admin/deposits-by-method ---------------------------------

function bot_dbm_deposits_by_method() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') dbm_fail(405, 'Method not allowed.');
    $db = dbm_db();
    if ($db === null) dbm_fail(500, 'Database is not available.');
    try { $db->query("SET time_zone = '+00:00'"); } catch (mysqli_sql_exception $e) { /* keep going */ }

    $win = dbm_window_7d();
    $has_method_col = dbm_has_column($db, 'deposits', 'method');
    $has_response_col = dbm_has_column($db, 'deposits', 'chapa_response');
    $cols = 'amount, created_at';
    if ($has_method_col) $cols .= ', method';
    if ($has_response_col) $cols .= ', chapa_response';

    // All completed deposits, all time — the split into 7-day vs
    // all-time happens in PHP (one read, and the method lives in a
    // JSON column, so SQL cannot group by it reliably).
    $methods = [
        'Telebirr' => ['method' => 'Telebirr', 'count_7d' => 0, 'amount_7d' => 0.0, 'count_all' => 0, 'amount_all' => 0.0],
        'CBE' => ['method' => 'CBE', 'count_7d' => 0, 'amount_7d' => 0.0, 'count_all' => 0, 'amount_all' => 0.0],
        'M-Pesa' => ['method' => 'M-Pesa', 'count_7d' => 0, 'amount_7d' => 0.0, 'count_all' => 0, 'amount_all' => 0.0],
        'CBE Birr' => ['method' => 'CBE Birr', 'count_7d' => 0, 'amount_7d' => 0.0, 'count_all' => 0, 'amount_all' => 0.0],
        'Unknown' => ['method' => 'Unknown', 'count_7d' => 0, 'amount_7d' => 0.0, 'count_all' => 0, 'amount_all' => 0.0],
    ];
    try {
        $res = $db->query("SELECT $cols FROM deposits WHERE status = 'completed'");
    } catch (mysqli_sql_exception $e) {
        dbm_fail(500, 'Could not read the deposits table.');
    }
    if ($res === false) dbm_fail(500, 'Could not read the deposits table.');
    while ($row = $res->fetch_assoc()) {
        $label = dbm_method_label(dbm_row_method($row, $has_method_col));
        if (!isset($methods[$label])) {
            $methods[$label] = ['method' => $label, 'count_7d' => 0, 'amount_7d' => 0.0, 'count_all' => 0, 'amount_all' => 0.0];
        }
        $amount = (float)$row['amount'];
        $methods[$label]['count_all']++;
        $methods[$label]['amount_all'] = round($methods[$label]['amount_all'] + $amount, 2);
        $created = (string)($row['created_at'] ?? '');
        if ($created >= $win['start_utc'] && $created < $win['end_utc']) {
            $methods[$label]['count_7d']++;
            $methods[$label]['amount_7d'] = round($methods[$label]['amount_7d'] + $amount, 2);
        }
    }
    // Fixed order first, then any unexpected method labels, then
    // Unknown last — the admin bot prints them in this order.
    $ordered = [];
    foreach (['Telebirr', 'CBE', 'M-Pesa', 'CBE Birr'] as $label) {
        $ordered[] = $methods[$label];
        unset($methods[$label]);
    }
    foreach ($methods as $label => $entry) {
        if ($label === 'Unknown') continue;
        $ordered[] = $entry;
    }
    $ordered[] = $methods['Unknown'];
    bot_ok([
        'methods' => $ordered,
        'from' => $win['from'],
        'date' => $win['date'],
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/deposits-by-method' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_dbm_deposits_by_method(); }
//
// LIVE CURL TEST — read-only, no money moves, no rows change:
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/admin/deposits-by-method" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"methods":[{method, count_7d, amount_7d,
//      count_all, amount_all}, ...]} with Telebirr, CBE, M-Pesa and
//      CBE Birr rows. Cross-check: the SUM of count_all over the
//      four methods plus Unknown must equal the count of completed
//      deposits in the admin panel, and the SUM of amount_all must
//      equal their total. If CBE Birr shows 0 while William knows
//      CBE Birr deposits happened, read A3 — the create endpoint
//      normalises cbebirr to cbe, so they are counted under CBE.
// ============================================================================
