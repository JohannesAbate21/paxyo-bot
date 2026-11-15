<?php
// ============================================================================
// Provider price-change watch snapshot for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot,
// feature 6 (provider price-change watch) of the 10-feature build
// round — SERVER SIDE ONLY.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET  /api/bot/price-watch/snapshot
//     -> {"ok":true,"prices":{"5535":1.85,"7675":1.68}}
//        The last stored snapshot: service_id -> price in ETB per
//        1000. When NO snapshot exists yet the reply is
//        {"ok":true,"prices":{}} — an EMPTY prices object, NOT a
//        404 — so the bot can bootstrap on its first run (a 404
//        means the endpoint itself is not installed yet, and the
//        bot must treat that the same way: "no snapshot yet").
//   POST /api/bot/price-watch/snapshot  {prices:{...}}
//     -> {"ok":true,"stored":7175}
//        REPLACES the entire snapshot in one transaction: the old
//        rows are deleted and the new map is inserted. stored is
//        the number of rows written. Sending {"prices":{}} clears
//        the snapshot (stored:0) — that is a deliberate clear, not
//        an error.
//
// WHAT THE PRICES ARE: ETB per 1000, exactly as the bot's catalogue
// reports them — the provider rate x420 multiplier is ALREADY
// applied by the services endpoint, so this file never converts
// anything and never sees a provider rate. The bot compares the
// stored snapshot with the fresh catalogue on each run and reports
// the services whose price moved. This file stores and returns
// numbers only; all comparison / reporting logic lives in the bot.
//
// TABLE (created automatically on first call, utf8mb4):
//   bot_price_snapshot  service_id BIGINT PK,
//                       price_etb DECIMAL(12,4),
//                       updated_at DATETIME
//                       (ON UPDATE CURRENT_TIMESTAMP)
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-price-watch.php     (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php             (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test rows.
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient methods
// to add, mirroring save_session / load_session in bot.py):
//   get_price_snapshot() — GET /price-watch/snapshot, 404-tolerant
//     (return None on 404, log a warning, keep working — the watch
//     simply is not switched on yet). Returns the prices dict, or
//     {} when the server has no snapshot yet. Keys arrive as
//     strings ("5535") — the bot must compare them as strings or
//     cast both sides to int, never assume JSON int keys.
//   save_price_snapshot(prices) — POST /price-watch/snapshot with
//     {"prices": {service_id: price_etb}}, 404-tolerant the same
//     way. Returns the stored count, or None on 404. Prices are
//     ETB per 1000 as the catalogue reports them.
//   Both calls are best-effort and must never raise into a chat,
//   like the session calls. A failed save means the next run
//   compares against the older snapshot — the watch degrades, it
//   never breaks ordering.
//   The bot's watch loop: load snapshot -> fetch the live catalogue
//   -> compare -> report the services whose price changed -> save
//   the fresh snapshot. The save REPLACES the whole snapshot, so
//   the bot must always send the FULL current catalogue map, never
//   a partial one — a partial save would delete every service it
//   did not include.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use pw_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to both dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - NO account-existence checks here: the snapshot is global, not
//     per user. No telegram_id is sent or stored.
//   - No money moves here: these endpoints never touch balances,
//     orders, deposits or the provider. A snapshot write cannot
//     place, cancel or change an order, and it never changes a
//     selling price — it only records what the catalogue said.
//   - REPLACE semantics are deliberate: the catalogue is ~7,175
//     services and the bot always has the full map in hand, so a
//     full replace is simpler and safer than per-service upserts
//     (a service that left the catalogue disappears from the
//     snapshot instead of lingering forever). The replace runs in
//     ONE transaction: if any insert fails, the rollback restores
//     the old snapshot whole.
//   - Validation is fail-closed: a non-numeric service id, a
//     negative price, or a map larger than PW_MAX_ENTRIES rejects
//     the WHOLE save with 400 and stores nothing — a half-stored
//     snapshot would make the next comparison meaningless.
//   - Prices are stored as DECIMAL(12,4) and rounded to 4 decimals
//     on write, so the stored value is exactly what the bot sent
//     (to 4 decimals). GET returns them as JSON numbers.
//
// OPEN QUESTIONS (do not guess — confirm on the server / with William):
//   (a) The snapshot holds the FULL catalogue (~7,175 rows). If the
//       live catalogue grows far past that, PW_MAX_ENTRIES (20,000)
//       is the cap to raise — change the constant, nothing else.
//   (b) The bot's watch cadence (how often it compares and saves)
//       is a bot-side decision; this file imposes none. A save on
//       every bot wake would churn the table for no benefit —
//       once or twice a day is the sensible default.
// ============================================================================

// Maximum entries in one snapshot save. The live catalogue is ~7,175
// services; 20,000 leaves room to grow. Raise this constant if the
// catalogue ever outgrows it.
define('PW_MAX_ENTRIES', 20000);

// --- small helpers (pw_ prefix so nothing collides with bot.php) ------------

function pw_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function pw_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function pw_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function pw_ensure_table($db) {
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_price_snapshot (
        service_id BIGINT NOT NULL PRIMARY KEY,
        price_etb DECIMAL(12,4) NOT NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// --- GET /api/bot/price-watch/snapshot --------------------------------------
// Returns the whole stored snapshot as {service_id: price_etb}.
// An empty object {} when no snapshot exists yet — NOT a 404.
// (A 404 means the endpoint is not installed; the bot treats both
// as "no snapshot yet" and bootstraps from the live catalogue.)

function bot_pw_get_snapshot() {
    $db = pw_db();
    if ($db === null) pw_fail(500, 'Database is not available.');
    pw_ensure_table($db);

    // An object, not an array: json_encode of an empty PHP array is
    // [], but the contract is {} — an empty OBJECT.
    $prices = (object)[];
    $result = $db->query('SELECT service_id, price_etb FROM bot_price_snapshot ORDER BY service_id ASC');
    if ($result) {
        while ($row = $result->fetch_assoc()) {
            $prices->{(string)$row['service_id']} = (float)$row['price_etb'];
        }
        $result->free();
    }
    bot_ok(['ok' => true, 'prices' => $prices]);
}

// --- POST /api/bot/price-watch/snapshot -------------------------------------
// Body: {"prices": {"5535": 1.85, "7675": 1.68, ...}}
// REPLACES the entire snapshot in one transaction and returns the
// number of rows stored. Sending {"prices": {}} clears the snapshot
// (stored:0). Fail-closed: any bad key or value rejects the whole
// save and stores nothing.

function bot_pw_set_snapshot() {
    $in = pw_json_body();
    $prices_in = $in['prices'] ?? null;
    if (!is_array($prices_in)) pw_fail(400, 'prices must be an object mapping service_id to price_etb.');
    if (count($prices_in) > PW_MAX_ENTRIES) pw_fail(400, 'prices has too many entries (max ' . PW_MAX_ENTRIES . ').');

    // Validate the whole map BEFORE touching the database, so a bad
    // entry can never leave a half-replaced snapshot behind.
    $clean = [];
    foreach ($prices_in as $sid => $price) {
        if (!preg_match('/^\d+$/', (string)$sid) || (int)$sid <= 0) {
            pw_fail(400, 'prices keys must be positive service ids.');
        }
        if (!is_numeric($price) || (float)$price < 0 || (float)$price > 99999999.9999) {
            pw_fail(400, 'price for service ' . $sid . ' must be a number between 0 and 99999999.9999.');
        }
        $clean[(int)$sid] = round((float)$price, 4);
    }

    $db = pw_db();
    if ($db === null) pw_fail(500, 'Database is not available.');
    pw_ensure_table($db);

    $db->begin_transaction();
    $stored = 0;
    try {
        if (!$db->query('DELETE FROM bot_price_snapshot')) {
            throw new mysqli_sql_exception('Could not clear the old snapshot.', 0);
        }
        if (!empty($clean)) {
            // Chunked multi-row INSERT (500 rows per statement).
            // Values are ints/floats validated above, so no user
            // string ever reaches the SQL.
            foreach (array_chunk($clean, 500, true) as $chunk) {
                $values = [];
                foreach ($chunk as $sid => $price) {
                    $values[] = '(' . (int)$sid . ', ' . number_format($price, 4, '.', '') . ')';
                }
                $sql = 'INSERT INTO bot_price_snapshot (service_id, price_etb) VALUES ' . implode(',', $values);
                if (!$db->query($sql)) {
                    throw new mysqli_sql_exception('Could not store the snapshot.', 0);
                }
                $stored += count($chunk);
            }
        }
        $db->commit();
    } catch (mysqli_sql_exception $e) {
        // Any failure mid-replace: roll back so the old snapshot
        // stands whole — never a half-new, half-old mix.
        try { $db->rollback(); } catch (mysqli_sql_exception $ignored) { }
        pw_fail(500, 'Could not store the price snapshot.');
    }
    bot_ok(['ok' => true, 'stored' => $stored]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'price-watch/snapshot' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_pw_get_snapshot(); }
//   if ($bp === 'price-watch/snapshot' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_pw_set_snapshot(); }
// (Add the same bot_rate_limit(...) call the other user endpoints use
//  to both lines — copy the exact call from the orders handler; with
//  the exact === checks above the order of the two lines does not
//  matter.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-price-watch.php` on
// the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (no money moves — these endpoints never touch
// balances or orders; the test uses throwaway service ids 9990001
// and 9990002, which are not real catalogue services):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. no snapshot yet -> empty object (200, NOT 404):
//   curl -s "https://paxyo.et/api/bot/price-watch/snapshot" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"prices":{}}
//   # 2. store a small map:
//   curl -s -X POST https://paxyo.et/api/bot/price-watch/snapshot \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"prices":{"9990001":1.85,"9990002":2.14}}'
//   -> expect {"success":true,"ok":true,"stored":2}
//   # 3. read it back:
//   curl -s "https://paxyo.et/api/bot/price-watch/snapshot" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"prices":{"9990001":1.85,"9990002":2.14}}
//   # 4. store a CHANGED map (replace: 9990001 moves, 9990002 drops,
//   #    9990003 appears) — the old snapshot must be gone whole:
//   curl -s -X POST https://paxyo.et/api/bot/price-watch/snapshot \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"prices":{"9990001":1.90,"9990003":0.5}}'
//   -> expect {"success":true,"ok":true,"stored":2}
//   # 5. read it back — 9990002 must be GONE, 9990001 must be 1.9:
//   curl -s "https://paxyo.et/api/bot/price-watch/snapshot" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"prices":{"9990001":1.9,"9990003":0.5}}
//   # 6. a bad value rejects the WHOLE save and stores nothing:
//   curl -s -X POST https://paxyo.et/api/bot/price-watch/snapshot \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"prices":{"9990001":-1}}'
//   -> expect {"success":false,"error":"price for service 9990001 must be a number between 0 and 99999999.9999."}
//   # 7. read again — step 5's snapshot must be UNCHANGED:
//   curl -s "https://paxyo.et/api/bot/price-watch/snapshot" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"ok":true,"prices":{"9990001":1.9,"9990003":0.5}}
//   Then DELETE the test rows and confirm they are gone:
//   mysql -e "DELETE FROM bot_price_snapshot WHERE service_id IN (9990001, 9990002, 9990003); SELECT COUNT(*) FROM bot_price_snapshot WHERE service_id IN (9990001, 9990002, 9990003);"
//   (use the same MySQL credentials db.php uses; never print them.)
//   NOTE: if a REAL snapshot is already stored when this test runs,
//   step 2 REPLACES it — back it up first:
//   mysqldump ... bot_price_snapshot > /tmp/pw-snapshot-backup.sql
//   (or SELECT it out), and restore it after the test.
// ============================================================================
