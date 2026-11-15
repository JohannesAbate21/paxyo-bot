<?php
// ============================================================================
// Per-user personality traits for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot,
// feature 5 (per-user personality: the bot remembers each user's
// traits) of the 5-of-8 approved batch — SERVER SIDE ONLY.
//
// DESIGN DECISION — OPTION B: a SEPARATE table + separate endpoints.
// Why not Option A (a traits column on bot_sessions)?
//   1. bot_sessions is LIVE and verified (installed 14 Nov 22:43 EAT,
//      retest 5/5 PASS). A new standalone file leaves that working
//      path untouched — no ALTER, no change to the session save/load
//      SQL, nothing that can regress a proven endpoint.
//   2. Separation is PROVABLE, not just promised: a traits save runs
//      SQL against bot_user_traits only, and a session save runs SQL
//      against bot_sessions only. No statement in either file can
//      touch the other store, so a stale or partial payload can never
//      wipe history/draft — or traits — by accident.
//   3. Different lifecycles: a session row is rewritten every turn
//      (history churns); traits change rarely, only when the bot has
//      actually learned something new. Separate rows mean a traits
//      save never rewrites a multi-KB history blob, and a session
//      save never risks clobbering traits.
//   4. Traits outlive a session: if a session row is ever cleared,
//      the user's learned preferences survive.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/user-traits   {telegram_id, traits:{...}}
//     -> {"ok":true,"traits":{...merged...},"updated_at":"..."}
//        MERGE (PATCH) semantics: only the fields present in the
//        request change. A field sent as null is CLEARED; a field
//        not sent is left exactly as stored. So a save of
//        {"tone":"brief"} never wipes usual_platform, and a save
//        made from a stale in-memory copy cannot resurrect a trait
//        the user already cleared. Unknown fields are dropped,
//        never stored.
//   GET  /api/bot/user-traits?telegram_id=X
//     -> {"traits":{...},"updated_at":"..."}  or  {"traits":null}
//        when nothing is stored yet. NOTE: "no traits stored" is a
//        200 with traits:null — NOT a 404. A 404 means the endpoint
//        itself is not installed yet, and the bot must treat that
//        the same way ("no traits yet") and keep working from
//        memory. Never raise into a chat either way.
//   POST /api/bot/user-traits/clear {telegram_id}
//     -> {"ok":true}   (deletes the row; idempotent — ok:true even
//        when no row existed. This is the "forget what you know
//        about me" path.)
//
// TABLE (created automatically on first call, utf8mb4 like the
// session/confusion tables):
//   bot_user_traits  telegram_id BIGINT PK, traits TEXT (JSON object,
//                    '{}' when nothing learned yet), updated_at
//
// THE TRAIT SET — deliberately SMALL (5 fields). The server stores
// ONLY what the bot sends; it NEVER invents a trait, never infers
// one from an order, and never fills in a default. A field is null
// until the bot has actually learned it from the user's own
// messages (learning thresholds — e.g. a platform seen 3 times —
// live in the bot, not here). See the field table in
// trt_validate_traits() below.
//   tone             'brief' | 'chatty' | 'formal' | null — learned,
//                    never assumed. No default: null means "not
//                    learned yet", and the bot uses its normal style.
//   usual_platform   lowercase slug, max 32 chars, e.g. 'tiktok',
//                    'instagram', 'telegram', 'youtube', 'facebook'.
//   usual_metric     lowercase slug, max 32 chars, e.g. 'views',
//                    'likes', 'followers', 'comments', 'subscribers'.
//   usual_quantity   INT, 1..100,000,000 — the quantity this user
//                    typically orders (e.g. 1000). The bot buckets
//                    it into quantity bands client-side; the server
//                    stores the plain number, not a band label.
//   usual_service_id INT, > 0 — the catalogue service this user
//                    usually orders (drives "same as usual").
//
// LANGUAGE — REUSED, NOT DUPLICATED: the bot already stores the
// user's language in bot_sessions.lang, and that stays the single
// source of truth. There is deliberately NO lang field in traits:
// two copies would drift (a session save updating one and not the
// other). The bot-side builder reads lang from load_session, as
// today, and reads traits from load_traits separately.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-user-traits.php     (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINES
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php             (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file) then DELETE the
//      test row.
//
// BOT-SIDE CONTRACT (for the bot.py builder — PaxyoClient methods
// to add, mirroring save_session / load_session in bot.py):
//   save_traits(telegram_id, traits) — POST /user-traits, 404-tolerant
//     (return None on 404, log a warning, keep working from memory).
//     Send ONLY the traits that changed; the server merges. To clear
//     one trait, send it as null — never send a whole traits dict
//     rebuilt from a stale copy.
//   load_traits(telegram_id) — GET /user-traits?telegram_id=X.
//     Returns the traits dict, or None when {"traits":null} OR on
//     404 — the caller treats both as "no traits yet".
//   clear_traits(telegram_id) — POST /user-traits/clear. 404-tolerant.
//   Every call is best-effort and must never raise into a chat, like
//   the session calls. Traits are applied to replies only; they
//   never change prices, totals, or which service is picked — the
//   money steps stay deterministic.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use trt_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - NO account-existence check here, unlike deposits: traits must
//     be storable even for a brand-new user whose auth row does not
//     exist yet. Orphan rows are tiny (one per user) and keyed by
//     telegram_id, so this cannot grow out of control.
//   - No money moves here: these endpoints never touch balances,
//     orders, deposits or the provider. A traits write cannot place,
//     cancel or change an order.
// ============================================================================

// --- small helpers (trt_ prefix so nothing collides with bot.php) -----------

function trt_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function trt_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function trt_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function trt_ensure_table($db) {
    // utf8mb4 like the session/confusion tables (traits are ASCII
    // slugs today, but a future free-text field must not break).
    // set_charset is idempotent — harmless if bot.php already did it.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    // NOTE: no DEFAULT on the TEXT column — MySQL < 8.0.13 forbids
    // defaults on TEXT/BLOB. The INSERT below always supplies a value.
    $db->query("CREATE TABLE IF NOT EXISTS bot_user_traits (
        telegram_id BIGINT NOT NULL PRIMARY KEY,
        traits TEXT NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// --- trait validation -------------------------------------------------------
// The whole trait set, in one place. Returns [cleaned, error]:
//   cleaned — the validated fields, with nulls kept (null = clear it)
//   error   — null on success, otherwise a message naming the bad field.
// Unknown fields are DROPPED silently (forward-compatible: an older
// server ignores a newer bot's extra field instead of failing the
// save). A known field with a bad value FAILS the whole save with
// 400 — fail closed, so a bad value can never silently become a trait.

function trt_validate_traits($in) {
    $cleaned = [];
    if (isset($in['tone'])) {
        if ($in['tone'] === null) {
            $cleaned['tone'] = null;
        } elseif (is_string($in['tone']) && in_array($in['tone'], ['brief', 'chatty', 'formal'], true)) {
            $cleaned['tone'] = $in['tone'];
        } else {
            return [null, 'tone must be "brief", "chatty", "formal" or null.'];
        }
    }
    // usual_platform / usual_metric: lowercase slugs, max 32 chars.
    // The bot only sends platforms/metrics it knows; the pattern is
    // the second line of defence against a junk value being stored.
    foreach (['usual_platform', 'usual_metric'] as $field) {
        if (isset($in[$field])) {
            if ($in[$field] === null) {
                $cleaned[$field] = null;
            } elseif (is_string($in[$field]) && preg_match('/^[a-z0-9][a-z0-9_-]{0,31}$/', $in[$field])) {
                $cleaned[$field] = $in[$field];
            } else {
                return [null, $field . ' must be a lowercase slug of at most 32 characters, or null.'];
            }
        }
    }
    // usual_quantity: a plain integer, 1..100,000,000. Digit strings
    // are accepted (JSON numbers arrive as int anyway); floats,
    // booleans and negatives are rejected.
    if (isset($in['usual_quantity'])) {
        if ($in['usual_quantity'] === null) {
            $cleaned['usual_quantity'] = null;
        } elseif (is_int($in['usual_quantity']) || (is_string($in['usual_quantity']) && preg_match('/^\d+$/', $in['usual_quantity']))) {
            $qty = (int)$in['usual_quantity'];
            if ($qty < 1 || $qty > 100000000) {
                return [null, 'usual_quantity must be between 1 and 100000000, or null.'];
            }
            $cleaned['usual_quantity'] = $qty;
        } else {
            return [null, 'usual_quantity must be an integer, or null.'];
        }
    }
    // usual_service_id: a catalogue service id, positive integer.
    if (isset($in['usual_service_id'])) {
        if ($in['usual_service_id'] === null) {
            $cleaned['usual_service_id'] = null;
        } elseif (is_int($in['usual_service_id']) || (is_string($in['usual_service_id']) && preg_match('/^\d+$/', $in['usual_service_id']))) {
            $sid = (int)$in['usual_service_id'];
            if ($sid < 1) {
                return [null, 'usual_service_id must be a positive integer, or null.'];
            }
            $cleaned['usual_service_id'] = $sid;
        } else {
            return [null, 'usual_service_id must be an integer, or null.'];
        }
    }
    return [$cleaned, null];
}

function trt_decode($json) {
    $decoded = json_decode((string)$json, true);
    return is_array($decoded) ? $decoded : [];
}

function trt_load_row($db, $telegram_id) {
    $stmt = $db->prepare('SELECT traits, updated_at FROM bot_user_traits WHERE telegram_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// --- POST /api/bot/user-traits ----------------------------------------------
// Merge-upsert: only the fields present in the request change. A
// field sent as null is removed; a field not sent is untouched.
// This statement touches bot_user_traits ONLY — it cannot read or
// write bot_sessions (history/draft/lang), and no session save can
// touch this table. That is the separation, in the SQL itself.

function bot_trt_save() {
    $in = trt_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) trt_fail(400, 'telegram_id is required.');
    $traits_in = $in['traits'] ?? null;
    if (!is_array($traits_in)) trt_fail(400, 'traits must be an object.');
    list($cleaned, $error) = trt_validate_traits($traits_in);
    if ($error !== null) trt_fail(400, $error);

    $db = trt_db();
    if ($db === null) trt_fail(500, 'Database is not available.');
    trt_ensure_table($db);

    // Merge with what is already stored ({} when this is the first save).
    $existing = trt_load_row($db, $telegram_id);
    $merged = $existing ? trt_decode($existing['traits']) : [];
    foreach ($cleaned as $key => $value) {
        if ($value === null) {
            unset($merged[$key]);
        } else {
            $merged[$key] = $value;
        }
    }
    $merged_json = json_encode($merged);
    $stmt = $db->prepare('INSERT INTO bot_user_traits (telegram_id, traits) VALUES (?, ?) ON DUPLICATE KEY UPDATE traits = VALUES(traits)');
    $stmt->bind_param('is', $telegram_id, $merged_json);
    if (!$stmt->execute()) {
        $stmt->close();
        trt_fail(500, 'Could not save the traits.');
    }
    $stmt->close();
    $row = trt_load_row($db, $telegram_id);
    bot_ok(['ok' => true, 'traits' => $merged, 'updated_at' => $row ? $row['updated_at'] : null]);
}

// --- GET /api/bot/user-traits?telegram_id=X ---------------------------------

function bot_trt_load() {
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) trt_fail(400, 'telegram_id is required.');
    $db = trt_db();
    if ($db === null) trt_fail(500, 'Database is not available.');
    trt_ensure_table($db);
    $row = trt_load_row($db, $telegram_id);
    if (!$row) {
        // No traits stored yet — a 200 with traits:null, NOT a 404.
        // (A 404 means the endpoint is not installed; the bot treats
        // both as "no traits yet".)
        bot_ok(['traits' => null]);
        return;
    }
    bot_ok(['traits' => trt_decode($row['traits']), 'updated_at' => $row['updated_at']]);
}

// --- POST /api/bot/user-traits/clear ----------------------------------------
// Deletes the whole traits row ("forget what you know about me").
// Idempotent: ok:true even when no row existed. Touches
// bot_user_traits only — the session row (history/draft/lang) is
// never touched by this call.

function bot_trt_clear() {
    $in = trt_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) trt_fail(400, 'telegram_id is required.');
    $db = trt_db();
    if ($db === null) trt_fail(500, 'Database is not available.');
    trt_ensure_table($db);
    $stmt = $db->prepare('DELETE FROM bot_user_traits WHERE telegram_id = ?');
    $stmt->bind_param('i', $telegram_id);
    if (!$stmt->execute()) {
        $stmt->close();
        trt_fail(500, 'Could not clear the traits.');
    }
    $stmt->close();
    bot_ok(['ok' => true]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'user-traits/clear' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_trt_clear(); }
//   if ($bp === 'user-traits' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_trt_save(); }
//   if ($bp === 'user-traits' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_trt_load(); }
//   (Add the same bot_rate_limit(...) call the other user endpoints
//    use to each dispatch line — copy the exact call from the orders
//    handler; the signature was not visible from outside the server.
//    'user-traits/clear' must be checked before 'user-traits' only if
//    the dispatch uses prefix matching; with the exact === checks
//    above the order does not matter.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-user-traits.php` on
// the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account —
// no money moves, these endpoints never touch balances or orders):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. no traits yet -> traits:null (200, NOT 404):
//   curl -s "https://paxyo.et/api/bot/user-traits?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"traits":null}
//   # 2. save two traits (merge — only these two fields are stored):
//   curl -s -X POST https://paxyo.et/api/bot/user-traits \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"traits":{"tone":"brief","usual_platform":"tiktok"}}'
//   -> expect {"success":true,"ok":true,"traits":{"tone":"brief","usual_platform":"tiktok"},"updated_at":"..."}
//   # 3. load them back:
//   curl -s "https://paxyo.et/api/bot/user-traits?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"traits":{"tone":"brief","usual_platform":"tiktok"},"updated_at":"..."}
//   # 4. merge: add a third field, and prove the first two SURVIVE:
//   curl -s -X POST https://paxyo.et/api/bot/user-traits \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"traits":{"usual_quantity":1000}}'
//   -> expect {"success":true,"ok":true,"traits":{"tone":"brief","usual_platform":"tiktok","usual_quantity":1000},"updated_at":"..."}
//   # 5. clear one field with null, and prove the others SURVIVE:
//   curl -s -X POST https://paxyo.et/api/bot/user-traits \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"traits":{"tone":null}}'
//   -> expect {"success":true,"ok":true,"traits":{"usual_platform":"tiktok","usual_quantity":1000},"updated_at":"..."}
//   # 6. invalid value -> 400, nothing stored/changed:
//   curl -s -X POST https://paxyo.et/api/bot/user-traits \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"traits":{"tone":"sarcastic"}}'
//   -> expect {"success":false,"error":"tone must be \"brief\", \"chatty\", \"formal\" or null.",...}
//   # 7. unknown field -> dropped, save still succeeds:
//   curl -s -X POST https://paxyo.et/api/bot/user-traits \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"traits":{"favourite_colour":"blue"}}'
//   -> expect {"success":true,"ok":true,"traits":{"usual_platform":"tiktok","usual_quantity":1000},"updated_at":"..."}
//   # 8. session untouched: confirm the live session row is unchanged
//   #    (GET /sessions must return exactly what it returned before
//   #    step 2 — traits never touch bot_sessions):
//   curl -s "https://paxyo.et/api/bot/sessions?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect the same session as before the traits test.
//   # 9. clear the whole row:
//   curl -s -X POST https://paxyo.et/api/bot/user-traits/clear \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335}'
//   -> expect {"success":true,"ok":true}
//   # 10. load again -> traits:null:
//   curl -s "https://paxyo.et/api/bot/user-traits?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"traits":null}
//   Then DELETE the test row (belt and braces — step 9 already
//   removed it) and confirm it is gone:
//   mysql -e "DELETE FROM bot_user_traits WHERE telegram_id=779060335; SELECT COUNT(*) FROM bot_user_traits WHERE telegram_id=779060335;"
//   (use the same MySQL credentials db.php uses; never print them.)
// ============================================================================
