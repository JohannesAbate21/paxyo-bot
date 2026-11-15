<?php
// ============================================================================
// Admin settings write for the Paxyo Bot API (public_html/api/bot.php).
// Written 15 Nov 2026 for the NEW admin chat bot (a brand-new bot,
// NOT @paxadmin_bot). The bot asks "change ticker display to ...",
// shows exactly what will change, William confirms, and only then
// the bot calls this endpoint. The endpoint is GENERIC by key —
// the ticker is simply the first key the bot wires up in chat;
// other settings follow the same call with a different key.
//
//   POST /api/bot/admin/settings  {key, value}
//     -> {"ok":true,"key":"ticker_text","value":"..."}  (inside bot_ok)
//   bot_ok() adds "success":true around it, as on every other
//   endpoint; the bot reads the named keys and ignores the rest.
//
// KEYS: lowercase letters, digits and underscores only, 1..64
// chars (e.g. "ticker_text"). The value is a plain string, max
// 2000 chars. Anything else -> 400, nothing written.
//
// AUTH: X-Bot-Secret, same as the session/confusion/stats
// endpoints. This is a BOT endpoint, called by the admin bot with
// the secret — it is NOT the human-admin session
// (admin_authenticated) and it must NOT be called from a
// user-facing page. Only the admin bot (William) can call it, and
// only after his Confirm tap in chat.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-settings.php   (this file must pass on its own)
//   2. python3 splice script: read bot.php, INSERT THE DISPATCH LINE
//      (see the bottom of this file) before the 404 fallback, then
//      append this file's code WITHOUT its first line (the "<?php"
//      opening tag — bot.php is already inside one PHP block) to the
//      end of bot.php.
//   3. php -l api/bot.php              (must pass before anything goes live)
//   4. Live curl test (see the bottom of this file). The test writes
//      ONE settings row (the ticker test value) — write it back to
//      the old value afterwards, or delete the test row, and confirm
//      the ticker on the site is unchanged.
//
// ASSUMPTIONS — the settings table shape is NOT confirmed from the
// local files (no local file reads the settings table), so the
// columns are DISCOVERED at runtime (information_schema) and the
// installer must verify them (see TO VERIFY below):
//   S1. There is a `settings` table with a key column and a value
//       column. Key column: first of (key, name, setting_key) that
//       exists. Value column: first of (value, setting_value,
//       setting) that exists. If the table or either column is
//       missing, the endpoint answers 500 with a plain message
//       ("settings table not found" / "settings table has no
//       key/value column") and writes nothing.
//   S2. The write is UPDATE-then-INSERT: UPDATE the row for the
//       key; if no row matched, INSERT it. This works whether or
//       not the key column is UNIQUE. (An INSERT ... ON DUPLICATE
//       KEY UPDATE would be shorter but fails without a unique
//       key, so it is not used.)
//   S3. TICKER KEY — TO VERIFY: the bot sends key "ticker_text".
//       Before going live, check what key the site / mini app
//       actually reads for the ticker text (grep the live files
//       for the ticker string, e.g. in get_service.php / the
//       admin settings page). If it is a different key, change
//       TICKER_SETTING_KEY in admin_bot.py to that key — this
//       endpoint needs no change, it writes whatever key it is
//       given. The live curl test below uses "ticker_text"; if the
//       real key differs, test with the real key instead.
//   S4. The value is stored verbatim (no HTML stripping, no
//       trimming beyond surrounding whitespace). The ticker is
//       displayed as text on the site; if the site ever renders
//       settings values as HTML, the display side must escape
//       them — that is the display side's job, not this endpoint's.
//   S5. No rate limit is applied here beyond bot.php's existing
//       X-Bot-Secret check. The admin bot calls this at most once
//       per confirmed setting change — a handful of calls a day.
// ============================================================================

// --- small helpers (stg_ prefix so nothing collides with bot.php) -----------

function stg_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function stg_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function stg_json_body() {
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) return [];
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

// Does table $table have column $col? (information_schema read; if
// the check itself fails, answer "no" — the caller degrades.)
function stg_has_column($db, $table, $col) {
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

// Does table $table exist at all?
function stg_has_table($db, $table) {
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

// Discover the settings key/value columns. Returns
// ['key' => col-or-null, 'value' => col-or-null].
function stg_discover_columns($db) {
    $key = null;
    foreach (['key', 'name', 'setting_key'] as $col) {
        if (stg_has_column($db, 'settings', $col)) { $key = $col; break; }
    }
    $value = null;
    foreach (['value', 'setting_value', 'setting'] as $col) {
        if (stg_has_column($db, 'settings', $col)) { $value = $col; break; }
    }
    return ['key' => $key, 'value' => $value];
}

// --- POST /api/bot/admin/settings --------------------------------------------

function bot_admin_settings_write() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') stg_fail(405, 'Method not allowed.');

    $db = stg_db();
    if ($db === null) stg_fail(500, 'Database is not available.');

    $in = stg_json_body();
    $key = trim((string)($in['key'] ?? ''));
    $value = (string)($in['value'] ?? '');
    if (!preg_match('/^[a-z0-9_]{1,64}$/', $key)) {
        stg_fail(400, 'key must be 1-64 lowercase letters, digits or underscores.');
    }
    $value = trim($value);
    if ($value === '') stg_fail(400, 'value must not be empty.');
    if (strlen($value) > 2000) stg_fail(400, 'value is too long (max 2000 characters).');

    if (!stg_has_table($db, 'settings')) {
        stg_fail(500, 'settings table not found — see S1 in api-admin-settings.php.');
    }
    $cols = stg_discover_columns($db);
    if ($cols['key'] === null || $cols['value'] === null) {
        stg_fail(500, 'settings table has no key/value column — see S1 in api-admin-settings.php.');
    }
    $key_col = $cols['key'];
    $val_col = $cols['value'];

    try {
        // UPDATE first; if no row matched, INSERT it (see S2).
        $stmt = $db->prepare('UPDATE `settings` SET `' . $val_col . '` = ? WHERE `' . $key_col . '` = ?');
        $stmt->bind_param('ss', $value, $key);
        $stmt->execute();
        $updated = $stmt->affected_rows;
        $stmt->close();
        if ($updated === 0) {
            $stmt = $db->prepare('INSERT INTO `settings` (`' . $key_col . '`, `' . $val_col . '`) VALUES (?, ?)');
            $stmt->bind_param('ss', $key, $value);
            $stmt->execute();
            $stmt->close();
        }
    } catch (mysqli_sql_exception $e) {
        // A duplicate-key race between the UPDATE and the INSERT
        // (two admins at once) lands here: the row exists now, so
        // one more UPDATE settles it.
        if ($db->errno === 1062) {
            try {
                $stmt = $db->prepare('UPDATE `settings` SET `' . $val_col . '` = ? WHERE `' . $key_col . '` = ?');
                $stmt->bind_param('ss', $value, $key);
                $stmt->execute();
                $stmt->close();
            } catch (mysqli_sql_exception $e2) {
                stg_fail(500, 'Could not save the setting.');
            }
        } else {
            stg_fail(500, 'Could not save the setting.');
        }
    }

    bot_ok(['ok' => true, 'key' => $key, 'value' => $value]);
}

// ============================================================================
// DISPATCH — insert this line in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/settings' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_admin_settings_write(); }
//
// LIVE CURL TEST (writes ONE settings row — write it back or delete
// it afterwards, and confirm the ticker on the site is unchanged):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # Read the current ticker value first (whatever the site reads):
//   mysql -e "SELECT * FROM settings WHERE \`key\`='ticker_text';"
//   # (adjust the column/key names to the live table — see S1/S3.)
//   curl -s -X POST https://paxyo.et/api/bot/admin/settings \
//     -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" \
//     -d '{"key":"ticker_text","value":"TEST — please ignore"}'
//   -> expect {"success":true,"ok":true,"key":"ticker_text",
//      "value":"TEST — please ignore"}
//   mysql -e "SELECT * FROM settings WHERE \`key\`='ticker_text';"
//   -> the row must now hold the test value.
//   # Write the old value back (same curl with the old value), then
//   # confirm the site ticker is back to normal.
//   curl -s -X POST https://paxyo.et/api/bot/admin/settings \
//     -H "X-Bot-Secret: $SECRET" -H "Content-Type: application/json" \
//     -d '{"key":"Bad Key!","value":"x"}'
//   -> expect HTTP 400, success:false, nothing written.
//   Without the header (or with a wrong secret) the request must be
//   refused by bot.php's existing X-Bot-Secret check, before this
//   code runs:
//   curl -s -X POST https://paxyo.et/api/bot/admin/settings \
//     -H "Content-Type: application/json" \
//     -d '{"key":"ticker_text","value":"x"}'
//   -> expect the usual auth error (401/403), NOT ok:true.
// ============================================================================
