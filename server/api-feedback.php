<?php
// ============================================================================
// Feedback "asked once" backstop for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot,
// feature 10 (feedback check 7 days after first order) of the
// 10-feature build round — SERVER SIDE ONLY.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/feedback/asked?telegram_id=X
//     -> {"ok":true,"asked":false}   (never asked this user yet)
//     -> {"ok":true,"asked":true}    (already asked — do not ask again)
//   POST /api/bot/feedback/asked  {telegram_id}
//     -> {"ok":true,"asked":true}
//        Records that the user has been asked for feedback.
//        Idempotent: safe to call twice — the second call changes
//        nothing and returns the same reply.
//
// WHY THIS EXISTS: the bot's feedback check asks a user once, 7 days
// after their first order. The bot keeps that "already asked" state
// in memory — and in-memory state is LOST on every restart (Render
// free tier sleeps, deploys wipe the process). Without a durable
// record, a restarted bot would ask the same user again. This
// endpoint is the durable backstop: before asking, the bot consults
// GET; after asking, it records POST. One row per user, nothing more.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_feedback_asked  telegram_id BIGINT PK,
//                       asked_at DATETIME
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-feedback.php       (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php            (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test row.
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient methods
// to add, mirroring save_session / load_session in bot.py):
//   feedback_asked(telegram_id) — GET /feedback/asked?telegram_id=X,
//     404-tolerant (return None on 404, log a warning, keep working
//     from memory — the backstop simply is not switched on yet).
//     Returns True/False, or None on 404.
//   mark_feedback_asked(telegram_id) — POST /feedback/asked,
//     404-tolerant the same way. Returns True, or None on 404.
//   Flow: when the 7-day feedback check fires, the bot first checks
//   its in-memory state; if that says "not asked", it ALSO checks
//   GET /feedback/asked — if either says asked, it stays silent.
//   After sending the feedback question it calls POST
//   /feedback/asked (and marks it in memory too). Both calls are
//   best-effort and must never raise into a chat, like the session
//   calls. If the POST fails, the in-memory mark still stops a
//   repeat ask in this process — the worst case is one repeat ask
//   after a restart, never a crash.
//   This endpoint stores ONLY that the user was asked. It never
//   stores the feedback itself — the answer goes to support, not
//   here.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use fb_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to both dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - NO account-existence check here: a feedback ask must be
//     recordable even for a user whose auth row is gone. Orphan rows
//     are tiny (one per user) and keyed by telegram_id.
//   - No money moves here: these endpoints never touch balances,
//     orders, deposits or the provider.
//   - asked_at keeps the FIRST ask time: a repeat POST does not move
//     it (ON DUPLICATE KEY UPDATE asked_at = asked_at). The first
//     ask is the meaningful date — when the 7-day clock was
//     satisfied — not the last repeat.
//   - There is deliberately NO "un-ask" / delete endpoint: once a
//     user has been asked, that fact stands. If William ever wants
//     to re-ask a user, delete that user's row by hand in MySQL.
//
// OPEN QUESTIONS (do not guess — confirm on the server / with William):
//   (a) None on the server side — the only open item is bot-side:
//       the exact 7-day timing and the feedback question wording
//       live in the bot, not here.
// ============================================================================

// --- small helpers (fb_ prefix so nothing collides with bot.php) ------------

function fb_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function fb_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function fb_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function fb_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_feedback_asked (
        telegram_id BIGINT NOT NULL PRIMARY KEY,
        asked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// --- GET /api/bot/feedback/asked?telegram_id=X ------------------------------
// Returns whether this user has already been asked for feedback.
// A 200 with asked:false when nothing is stored — NOT a 404.
// (A 404 means the endpoint is not installed; the bot treats both
// as "not asked yet".)

function bot_fb_asked_get() {
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) fb_fail(400, 'telegram_id is required.');
    $db = fb_db();
    if ($db === null) fb_fail(500, 'Database is not available.');
    fb_ensure_table($db);
    $stmt = $db->prepare('SELECT telegram_id FROM bot_feedback_asked WHERE telegram_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    bot_ok(['ok' => true, 'asked' => (bool)$row]);
}

// --- POST /api/bot/feedback/asked -------------------------------------------
// Body: {"telegram_id": <user>}
// Records that the user has been asked for feedback. Idempotent:
// INSERT ... ON DUPLICATE KEY UPDATE — safe to call twice, the
// second call changes nothing (asked_at keeps the first ask time)
// and returns the same reply.

function bot_fb_asked_mark() {
    $in = fb_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) fb_fail(400, 'telegram_id is required.');
    $db = fb_db();
    if ($db === null) fb_fail(500, 'Database is not available.');
    fb_ensure_table($db);
    $stmt = $db->prepare('INSERT INTO bot_feedback_asked (telegram_id) VALUES (?) ON DUPLICATE KEY UPDATE asked_at = asked_at');
    $stmt->bind_param('i', $telegram_id);
    // PHP 8.1+ mysqli throws instead of returning false — catch it
    // the same way the referrals file does, so a failure is a clean
    // 500, not an uncaught exception.
    $ok = false;
    try {
        $ok = $stmt->execute();
    } catch (mysqli_sql_exception $e) {
        $ok = false;
    }
    $stmt->close();
    if (!$ok) fb_fail(500, 'Could not record that feedback was asked.');
    bot_ok(['ok' => true, 'asked' => true]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'feedback/asked' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_fb_asked_get(); }
//   if ($bp === 'feedback/asked' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_fb_asked_mark(); }
// (Add the same bot_rate_limit(...) call the other user endpoints use
//  to both lines — copy the exact call from the orders handler; with
//  the exact === checks above the order of the two lines does not
//  matter.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-feedback.php` on
// the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account —
// no money moves, these endpoints never touch balances or orders):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. not asked yet -> asked:false (200, NOT 404):
//   curl -s "https://paxyo.et/api/bot/feedback/asked?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"asked":false}
//   # 2. mark asked:
//   curl -s -X POST https://paxyo.et/api/bot/feedback/asked \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true,"asked":true}
//   # 3. mark again -> identical reply, still one row:
//   curl -s -X POST https://paxyo.et/api/bot/feedback/asked \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true,"asked":true}
//   # 4. read it back -> asked:true:
//   curl -s "https://paxyo.et/api/bot/feedback/asked?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"asked":true}
//   # 5. missing telegram_id -> 400:
//   curl -s "https://paxyo.et/api/bot/feedback/asked" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":false,"error":"telegram_id is required."}
//   Then DELETE the test row and confirm it is gone:
//   mysql -e "DELETE FROM bot_feedback_asked WHERE telegram_id=779060335; SELECT COUNT(*) FROM bot_feedback_asked WHERE telegram_id=779060335;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
