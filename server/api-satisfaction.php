<?php
// ============================================================================
// Satisfaction score for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for @paxorder_bot feature 20 — the admin bot
// /satisfaction shows the 👍/👎 feedback score, and the morning
// report carries the same line.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/satisfaction
//     -> {"total":20,"positive":17,"negative":3,"percent_positive":85}
//        Aggregates bot_order_ratings (the table the feedback check
//        and the rating buttons write: order_id PK, telegram_id,
//        service_id, rating ENUM('good','bad'), created_at). One row
//        per order — a user who taps twice on the same order cannot
//        count twice, because the ratings endpoint enforces once per
//        order (409 after the first). percent_positive is the share
//        of 'good' over all ratings, rounded to a whole number; with
//        no ratings yet it is null (the admin bot says "no feedback
//        yet" instead of a 0% that would read as all-bad).
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-satisfaction.php        (this file must pass on its own)
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
//     on the other endpoints). Errors use sat_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - This is an ADMIN read (the admin bot calls it with the same
//     X-Bot-Secret). No per-user rate limit is applied here.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. bot_order_ratings exists with the columns
//       api-order-ratings.php creates (order_id, telegram_id,
//       service_id, rating, created_at). If the table does not exist
//       yet (the ratings endpoint was never installed), the counts
//       read 0 — the endpoint still answers, it just reports no
//       feedback yet. That is the honest answer until ratings land.
//   A2. rating values are 'good' / 'bad' (the ENUM in the ratings
//       file). Any other stored value is ignored by both counts.
// ============================================================================

// --- small helpers (sat_ prefix so nothing collides with bot.php) -----------

function sat_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function sat_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function sat_has_table($db, $table) {
    try {
        $stmt = $db->prepare('SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? LIMIT 1');
        $stmt->bind_param('s', $table);
        $stmt->execute();
        $found = $stmt->get_result()->fetch_assoc() !== null;
        $stmt->close();
        return $found;
    } catch (mysqli_sql_exception $e) {
        return false;
    }
}

// --- GET /api/bot/satisfaction ----------------------------------------------

function bot_sat_satisfaction() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') sat_fail(405, 'Method not allowed.');
    $db = sat_db();
    if ($db === null) sat_fail(500, 'Database is not available.');

    $total = 0;
    $positive = 0;
    $negative = 0;
    if (sat_has_table($db, 'bot_order_ratings')) {
        try {
            $res = $db->query("SELECT rating, COUNT(*) AS c FROM bot_order_ratings WHERE rating IN ('good','bad') GROUP BY rating");
            if ($res !== false) {
                while ($row = $res->fetch_assoc()) {
                    if ($row['rating'] === 'good') $positive = (int)$row['c'];
                    if ($row['rating'] === 'bad') $negative = (int)$row['c'];
                }
            }
        } catch (mysqli_sql_exception $e) {
            sat_fail(500, 'Could not read the ratings table.');
        }
    }
    $total = $positive + $negative;
    bot_ok([
        'total' => $total,
        'positive' => $positive,
        'negative' => $negative,
        'percent_positive' => $total > 0 ? (int)round(100 * $positive / $total) : null,
    ]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'satisfaction' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_sat_satisfaction(); }
//
// LIVE CURL TEST — read-only, no money moves, no rows change:
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/satisfaction" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"total":N,"positive":N,"negative":N,
//      "percent_positive":N|null}. Cross-check: total must equal the
//      row count of bot_order_ratings, and positive + negative must
//      equal total.
// ============================================================================
