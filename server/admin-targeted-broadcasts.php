<?php
// ============================================================================
// Targeted broadcasts — admin page/section for the Paxyo admin
// (public_html/px-4650dbff/admin-targeted-broadcasts.php).
// Written 15 Nov 2026. NEW file only — nothing else in the admin or
// in bot.php is edited by this work.
//
// WHAT IT ADDS: audience targeting for the admin panel's
// Broadcasting section. The existing Broadcasting already supports
// scheduling, send history, delivery control (who got the message),
// deleting a sent message, and adding a photo — ALL OF THAT IS
// KEPT, untouched. The new part is ONLY who the broadcast goes to:
// the admin picks a segment (and a service for the service segment)
// and the broadcast goes only to the users who match.
//
// FLOW (admin side): pick segment (+ service) -> live count shown
// -> admin confirms -> send is recorded. The count is shown BEFORE
// sending, always. The admin never sees a list of other users'
// private details — only the COUNT. The telegram_ids stay
// server-side: this page calls the audience endpoint with the bot
// secret and strips the id list before anything reaches the
// browser (see tb_audience_count()).
//
// AUDIENCE CONTRACT — REUSED, NOT REINVENTED:
//   GET /api/bot/broadcasts/audience?segment=<segment>&service_id=<id>
//   (server/api-admin-broadcasts.php — that file is the authority)
//     all             — every user in auth (every tg_id).
//     never_deposited — users with NO completed deposit.
//     deposited       — users with at least one COMPLETED deposit
//                       (pending/failed do not count).
//     service         — users who ordered a given service at least
//                       once. A user who ordered it twice counts
//                       ONCE (DISTINCT telegram_id in the endpoint
//                       SQL, plus a belt-and-braces dedupe there);
//                       a user who never ordered it is never
//                       included.
//   The endpoint returns {segment, service_id, count,
//   telegram_ids}. This page reads ONLY the count.
//
// PATCH BLOCK — NONE REQUIRED:
//   api-admin-broadcasts.php already serves all four segments, so
//   NO change to that file is needed for this feature. The service
//   picker below resolves a service NAME to its id via
//   GET /api/bot/services (server-side, same secret), so no new
//   "service by name" segment is needed either. If a future segment
//   is ever wanted (e.g. "ordered in the last 7 days"), add it to
//   api-admin-broadcasts.php first, then add its label to
//   $TB_SEGMENTS below — do not invent a second audience endpoint
//   in this file.
//
// H1 — THE SEND STEP (READ BEFORE INSTALLING):
//   This page does NOT send Telegram messages itself. It cannot:
//   the admin panel holds no bot token, and the bot secret must
//   never be used to send from a browser page. What this page DOES
//   on Send: (1) re-resolves the audience server-side (fresh count,
//   refuses count 0), (2) records the broadcast in bot_broadcasts
//   (see table below) with status 'queued' (or 'scheduled' when a
//   future time is set), (3) calls tb_dispatch_to_existing_sender()
//   — which by default does NOTHING except report "not wired".
//   THE INSTALLER MUST WIRE THAT ONE FUNCTION to the existing
//   Broadcasting send mechanism (the mechanism the live admin's
//   Broadcasting section already uses to send, show delivery, and
//   delete a sent message). That mechanism is NOT in this repo, so
//   its name, file, and call shape could not be written here.
//   Until it is wired, broadcasts sit in bot_broadcasts as
//   'queued' and NOTHING is sent to any user — which is the safe
//   failure mode. The sender, once wired, is expected to read the
//   queued row, fetch the audience itself via the same endpoint,
//   send, then UPDATE the row: status 'sent', sent_at, delivered,
//   failed. Deleting a sent message also stays with the existing
//   sender (it needs the per-user Telegram message ids, which this
//   page never sees).
//
// H2 — HISTORY TABLE (ASSUMPTION — VERIFY AT INSTALL):
//   No broadcast-history table exists in this workspace, so this
//   page creates and reads its own clearly-named table:
//     bot_broadcasts (id, audience_segment, service_id,
//       service_name, message, photo_path, audience_count,
//       delivered, failed, status, send_at, sent_at, created_at)
//   If the live admin's Broadcasting section already keeps history
//   in another table, point tb_history_table() at that table
//   instead (or merge the two at install) — do NOT run two
//   competing history tables as if they were one. The history
//   shown here is the targeted-broadcast history only; the
//   existing Broadcasting history is separate until merged.
//
// AUTH — human-admin session, NOT X-Bot-Secret in the browser:
//   Same gate as admin-confused-chats.php: session_start() then
//   require $_SESSION['admin_authenticated'] === true, else
//   redirect to the admin login. The bot secret (BOT_API_SECRET,
//   from ../config_secret.php) is read SERVER-SIDE ONLY, used for
//   the curl calls below, and never printed, never put in HTML,
//   JS, URLs, or logs.
//
// INSTALL:
//   1. Copy this file to public_html/px-4650dbff/
//      admin-targeted-broadcasts.php (next to the other sections).
//   2. Link it from the admin navigation / Broadcasting section,
//      labelled "Targeted broadcasts" (English only).
//   3. php -l admin-targeted-broadcasts.php (must pass).
//   4. Wire tb_dispatch_to_existing_sender() — see H1. Until then,
//      sending records a queued row and sends nothing.
//   5. Open it as the admin and check: segment dropdown changes
//      the count, service search finds a service by id/name, a
//      count-0 audience refuses to send, a sent broadcast appears
//      in the history table below.
//   6. Curl test for the audience count (the endpoint this page
//      calls — read-only, sends nothing):
//        SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//        curl -s "https://paxyo.et/api/bot/broadcasts/audience?segment=service&service_id=6139" -H "X-Bot-Secret: $SECRET"
//        -> expect {"success":true,"segment":"service","service_id":6139,
//           "count":N,"telegram_ids":[...]}; cross-check with
//           SELECT COUNT(DISTINCT telegram_id) FROM orders
//           WHERE <live service column> = 6139.
//
// TO VERIFY DURING INSTALL (could not be confirmed locally — the
// live admin's files were not readable from outside the server):
//   V1. Admin folder: is the admin at public_html/px-4650dbff/?
//       If not, change $ADMIN_LOGIN_URL and the includes below.
//   V2. Login URL: the redirect sends a logged-out visitor to
//       /px-4650dbff/ (the admin entry point). If the login page
//       is a different file, change $ADMIN_LOGIN_URL.
//   V3. Session key: the gate checks
//       $_SESSION['admin_authenticated'] === true. If the live
//       admin uses a different session key, change the check to
//       match — do NOT invent a second login system.
//   V4. Database include: the page includes ../db.php (the file
//       the live data source uses, public_html/db.php) and then
//       looks for the mysqli connection in $conn / $mysqli / $db /
//       $link. If the admin already opens its own connection,
//       delete the require_once and keep the admin's connection.
//   V5. Bot secret include: ../config_secret.php must define
//       BOT_API_SECRET (same file bot.php uses). If the admin
//       keeps the secret elsewhere, change $SECRET_INCLUDE.
//   V6. Back link: the "Broadcasting" link at the top points to
//       './' (the admin entry). Change it to the exact URL of the
//       existing Broadcasting section if that is a different file.
//   V7. Shared layout: if the admin has a shared header/nav
//       include, wrap this page in it (same as the other sections)
//       instead of the standalone HTML below. Keep the form and
//       the table compact and dense, like the other admin lists.
//   V8. Photo storage: uploads go to px-4650dbff/uploads/
//       (created by this page if missing). If the existing
//       Broadcasting section stores photos elsewhere, change
//       $TB_UPLOAD_DIR so both use the same place.
//
// STYLE: compact dense form + table (small rows, small padding —
// the admin lists rule), English only, no long explanatory text,
// brand #3275dd for the primary button.
// ============================================================================

date_default_timezone_set('Africa/Addis_Ababa');

// --- config: fix these lines at install time (see V1–V6, V8) ----------------

$ADMIN_LOGIN_URL = '/px-4650dbff/';            // TO VERIFY (V2)
$DB_INCLUDE      = __DIR__ . '/../db.php';     // TO VERIFY (V4)
$SECRET_INCLUDE  = __DIR__ . '/../config_secret.php'; // TO VERIFY (V5)
$TB_BACK_URL     = './';                       // TO VERIFY (V6)
$TB_UPLOAD_DIR   = __DIR__ . '/uploads';       // TO VERIFY (V8)
$TB_API_BASE     = 'https://paxyo.et/api/bot'; // Bot API base (same as bot.py default)
$TB_HISTORY_TABLE = 'bot_broadcasts';          // See H2

// Segments the admin can pick. Labels are English only. The keys
// MUST match the audience contract (api-admin-broadcasts.php).
$TB_SEGMENTS = [
    'all'             => 'All users',
    'never_deposited' => 'Never deposited',
    'deposited'       => 'Deposited',
    'service'         => 'Ordered a service',
];

// --- admin session gate (same pattern as admin-confused-chats.php) ----------

session_start();
if (empty($_SESSION['admin_authenticated']) || $_SESSION['admin_authenticated'] !== true) {
    header('Location: ' . $ADMIN_LOGIN_URL);
    exit;
}

// --- database connection (same globals as the bot.php splice files) --------

$tb_db = null;
if (file_exists($DB_INCLUDE)) {
    require_once $DB_INCLUDE;
}
foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
    if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
        $tb_db = $GLOBALS[$name];
        break;
    }
}

// --- bot secret (server-side only — never printed or sent to browser) ------

$tb_secret = null;
if (file_exists($SECRET_INCLUDE)) {
    require_once $SECRET_INCLUDE;
}
if (defined('BOT_API_SECRET') && BOT_API_SECRET !== '') {
    $tb_secret = BOT_API_SECRET;
}

// --- small helpers (tb_ prefix so nothing collides) ------------------------

function tb_h($s) {
    return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
}

// Server-side GET to the Bot API with X-Bot-Secret. Returns the
// decoded JSON array, or ['ok' => false, 'error' => ...] on any
// failure. The secret travels only in this curl call.
function tb_bot_get($path) {
    if ($GLOBALS['tb_secret'] === null) {
        return ['ok' => false, 'error' => 'Bot API secret is not available on the server.'];
    }
    $ch = curl_init($GLOBALS['TB_API_BASE'] . $path);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 20,
        CURLOPT_HTTPHEADER => ['X-Bot-Secret: ' . $GLOBALS['tb_secret']],
    ]);
    $raw = curl_exec($ch);
    $http = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    if ($raw === false || $raw === '') {
        return ['ok' => false, 'error' => 'Bot API did not answer' . ($err !== '' ? (': ' . $err) : '.')];
    }
    $data = json_decode($raw, true);
    if (!is_array($data)) {
        return ['ok' => false, 'error' => 'Bot API returned an unreadable reply.'];
    }
    if ($http !== 200 || empty($data['success'])) {
        return ['ok' => false, 'error' => (string)($data['error'] ?? $data['message'] ?? ('Bot API error (HTTP ' . $http . ').'))];
    }
    return ['ok' => true, 'data' => $data];
}

// Audience COUNT only. Calls the audience endpoint server-side and
// returns ['ok'=>true,'segment'=>...,'service_id'=>...,'count'=>N].
// The telegram_ids from the endpoint are DELIBERATELY dropped here
// — the browser (and the admin's screen) gets a count, never a
// list of user ids. Returns ['ok'=>false,'error'=>...] on bad input
// or an endpoint failure.
function tb_audience_count($segment, $service_id) {
    $segment = strtolower(trim((string)$segment));
    if (!isset($GLOBALS['TB_SEGMENTS'][$segment])) {
        return ['ok' => false, 'error' => 'Pick a segment.'];
    }
    $service_id = ($segment === 'service') ? (int)$service_id : null;
    if ($segment === 'service' && $service_id <= 0) {
        return ['ok' => false, 'error' => 'Pick a service for the service segment.'];
    }
    $path = '/broadcasts/audience?segment=' . rawurlencode($segment);
    if ($service_id !== null) $path .= '&service_id=' . $service_id;
    $res = tb_bot_get($path);
    if (!$res['ok']) return $res;
    $data = $res['data'];
    // Count only — telegram_ids never leave this function.
    return [
        'ok' => true,
        'segment' => $segment,
        'service_id' => $service_id,
        'count' => (int)($data['count'] ?? 0),
    ];
}

// Service search (for the picker): id or name substring, top 20.
// Server-side call to GET /api/bot/services, cached for 1 hour so
// a keystroke does not re-fetch ~7,000 services every time.
function tb_service_search($q) {
    $q = trim((string)$q);
    if ($q === '') return ['ok' => true, 'results' => []];
    $cache_file = sys_get_temp_dir() . '/paxyo_tb_services.json';
    $services = null;
    if (is_readable($cache_file) && (time() - filemtime($cache_file) < 3600)) {
        $services = json_decode((string)file_get_contents($cache_file), true);
        if (!is_array($services)) $services = null;
    }
    if ($services === null) {
        $res = tb_bot_get('/services');
        if (!$res['ok']) return $res;
        $services = $res['data']['services'] ?? $res['data'];
        if (!is_array($services)) {
            return ['ok' => false, 'error' => 'Service list came back unreadable.'];
        }
        @file_put_contents($cache_file, json_encode($services));
    }
    $qlow = mb_strtolower($q, 'UTF-8');
    $is_num = ctype_digit($q);
    $hits = [];
    foreach ($services as $s) {
        if (!is_array($s)) continue;
        $id = (int)($s['id'] ?? $s['provider_service_id'] ?? 0);
        $name = (string)($s['name'] ?? '');
        if ($id <= 0 || $name === '') continue;
        $match = false;
        if ($is_num) {
            // Exact id first, then id substring.
            if ((string)$id === $q) { $hits[] = ['id' => $id, 'name' => $name, 'price' => $s['price'] ?? null, 'exact' => true]; continue; }
            if (strpos((string)$id, $q) !== false) $match = true;
        }
        if (!$match && mb_strpos(mb_strtolower($name, 'UTF-8'), $qlow) !== false) $match = true;
        if ($match) $hits[] = ['id' => $id, 'name' => $name, 'price' => $s['price'] ?? null, 'exact' => false];
        if (count($hits) >= 200) break; // cap the scan; ranking below trims to 20
    }
    usort($hits, function ($a, $b) {
        if ($a['exact'] !== $b['exact']) return $a['exact'] ? -1 : 1;
        return $a['id'] - $b['id'];
    });
    $hits = array_slice($hits, 0, 20);
    foreach ($hits as &$h) unset($h['exact']);
    return ['ok' => true, 'results' => $hits];
}

// Look up one service's name by id (for the history row). Best
// effort: falls back to null when the catalogue is unreachable.
function tb_service_name($service_id) {
    $res = tb_service_search((string)$service_id);
    if (!$res['ok']) return null;
    foreach ($res['results'] as $r) {
        if ((int)$r['id'] === (int)$service_id) return (string)$r['name'];
    }
    return null;
}

// Ensure the history table exists. Creates bot_broadcasts (see H2)
// when it is missing; returns false (no throw) when the DB is
// unavailable or the CREATE fails.
function tb_ensure_history_table() {
    $db = $GLOBALS['tb_db'];
    if ($db === null) return false;
    $t = $GLOBALS['TB_HISTORY_TABLE'];
    $sql = 'CREATE TABLE IF NOT EXISTS `' . $t . '` ('
        . '`id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, '
        . '`audience_segment` VARCHAR(32) NOT NULL, '
        . '`service_id` INT NULL, '
        . '`service_name` VARCHAR(255) NULL, '
        . '`message` TEXT NOT NULL, '
        . '`photo_path` VARCHAR(255) NULL, '
        . '`audience_count` INT NOT NULL DEFAULT 0, '
        . '`delivered` INT NULL, '
        . '`failed` INT NULL, '
        . '`status` VARCHAR(32) NOT NULL DEFAULT \'queued\', '
        . '`send_at` DATETIME NULL, '
        . '`sent_at` DATETIME NULL, '
        . '`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, '
        . 'INDEX (`status`), INDEX (`created_at`)'
        . ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4';
    try {
        return $db->query($sql) !== false;
    } catch (mysqli_sql_exception $e) {
        return false;
    }
}

// ============================================================================
// THE SEND HAND-OFF — tb_dispatch_to_existing_sender().
// ----------------------------------------------------------------------------
// BY DEFAULT THIS DOES NOTHING except report "not wired" (see H1).
// The installer MUST replace the body of this ONE function with a
// call to the existing Broadcasting send mechanism — the mechanism
// the live admin's Broadcasting section already uses. That
// mechanism is NOT in this repo, so its name/file/call shape could
// not be written here; do NOT guess it. Two shapes are acceptable:
//   (a) call the existing sender directly here (pass it the
//       $broadcast_id; it reads the row from bot_broadcasts, fetches
//       the audience itself via GET /broadcasts/audience, sends,
//       then UPDATEs the row: status 'sent', sent_at, delivered,
//       failed); or
//   (b) leave this function as-is and let the existing sender poll
//       bot_broadcasts for status 'queued'/'scheduled' rows — in
//       that case delete the "not wired" return and have the sender
//       do the UPDATE above.
// Either way: a row is recorded BEFORE this function runs, so a
// failed/unwired dispatch never loses the broadcast — it stays
// 'queued' and nothing is sent to any user.
// Expected return: ['ok' => true] when the existing sender has
// accepted the broadcast, ['ok' => false, 'error' => ...] otherwise.
// ============================================================================
function tb_dispatch_to_existing_sender($broadcast_id) {
    // NOT WIRED — see H1 in the file header. Replace this body at
    // install time with the call to the existing Broadcasting send
    // mechanism. Until then, sending records the row and sends
    // nothing (safe failure mode).
    return ['ok' => false, 'error' => 'Send step not wired yet: connect tb_dispatch_to_existing_sender() to the existing Broadcasting sender (see H1 in this file). The broadcast is saved as queued.'];
}

// --- JSON actions (count + service search): no HTML after these -----------

$tb_action = (string)($_GET['action'] ?? '');
if ($tb_action === 'count') {
    header('Content-Type: application/json');
    echo json_encode(tb_audience_count($_GET['segment'] ?? '', $_GET['service_id'] ?? ''));
    exit;
}
if ($tb_action === 'service_search') {
    header('Content-Type: application/json');
    echo json_encode(tb_service_search($_GET['q'] ?? ''));
    exit;
}

// --- POST: send (record first, then hand off — see H1) ---------------------

$tb_notice = '';
$tb_notice_ok = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST' && (string)($_POST['action'] ?? '') === 'send') {
    $p_segment = strtolower(trim((string)($_POST['segment'] ?? '')));
    $p_service_id = (int)($_POST['service_id'] ?? 0);
    $p_message = trim((string)($_POST['message'] ?? ''));
    $p_schedule = trim((string)($_POST['schedule_at'] ?? ''));

    $p_error = '';
    if (!isset($TB_SEGMENTS[$p_segment])) {
        $p_error = 'Pick a segment.';
    } elseif ($p_segment === 'service' && $p_service_id <= 0) {
        $p_error = 'Pick a service for the service segment.';
    } elseif ($p_message === '') {
        $p_error = 'Write the message.';
    } elseif (mb_strlen($p_message, 'UTF-8') > 4096) {
        $p_error = 'Message is too long (max 4096 characters).';
    }

    // Re-resolve the audience server-side, fresh. The count the
    // browser showed is never trusted — this is the count that
    // decides whether anything is recorded.
    $p_count = null;
    if ($p_error === '') {
        $aud = tb_audience_count($p_segment, $p_service_id);
        if (!$aud['ok']) {
            $p_error = $aud['error'];
        } elseif ($aud['count'] <= 0) {
            $p_error = 'Nobody matches this audience — nothing sent.';
        } else {
            $p_count = $aud['count'];
        }
    }

    // Schedule: a future time stores the broadcast as 'scheduled';
    // empty or past means send now ('queued' for the sender).
    $p_send_at = null;
    $p_status = 'queued';
    if ($p_error === '' && $p_schedule !== '') {
        $dt = DateTime::createFromFormat('Y-m-d\TH:i', $p_schedule);
        if ($dt === false) {
            $p_error = 'Schedule time is not valid.';
        } else {
            $p_send_at = $dt->format('Y-m-d H:i:s');
            if ($dt->getTimestamp() > time()) $p_status = 'scheduled';
        }
    }

    // Photo attach (kept from the existing Broadcasting): optional
    // image, max 5 MB. Stored under px-4650dbff/uploads/; the path
    // is recorded with the broadcast so the sender can attach it.
    $p_photo_path = null;
    if ($p_error === '' && !empty($_FILES['photo']) && (int)$_FILES['photo']['error'] !== UPLOAD_ERR_NO_FILE) {
        $f = $_FILES['photo'];
        if ((int)$f['error'] !== UPLOAD_ERR_OK) {
            $p_error = 'Photo upload failed.';
        } elseif ((int)$f['size'] > 5 * 1024 * 1024) {
            $p_error = 'Photo is too large (max 5 MB).';
        } else {
            $ext = strtolower((string)pathinfo((string)$f['name'], PATHINFO_EXTENSION));
            if (!in_array($ext, ['jpg', 'jpeg', 'png', 'gif', 'webp'], true)) {
                $p_error = 'Photo must be a JPG, PNG, GIF or WebP image.';
            } elseif (!is_dir($TB_UPLOAD_DIR) && !@mkdir($TB_UPLOAD_DIR, 0755, true)) {
                $p_error = 'Photo folder is not writable.';
            } else {
                $p_photo_path = 'uploads/tb_' . bin2hex(random_bytes(8)) . '.' . $ext;
                if (!move_uploaded_file((string)$f['tmp_name'], $TB_UPLOAD_DIR . '/' . basename($p_photo_path))) {
                    $p_error = 'Photo could not be saved.';
                    $p_photo_path = null;
                }
            }
        }
    }

    if ($p_error === '') {
        if ($tb_db === null || !tb_ensure_history_table()) {
            $p_error = 'Database is not available — the broadcast was not saved.';
        } else {
            $p_service_name = ($p_segment === 'service') ? tb_service_name($p_service_id) : null;
            try {
                $stmt = $tb_db->prepare(
                    'INSERT INTO `' . $TB_HISTORY_TABLE . '` '
                    . '(audience_segment, service_id, service_name, message, photo_path, audience_count, status, send_at) '
                    . 'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
                );
                $sid = ($p_segment === 'service') ? $p_service_id : null;
                $stmt->bind_param('sisssiss', $p_segment, $sid, $p_service_name, $p_message, $p_photo_path, $p_count, $p_status, $p_send_at);
                $stmt->execute();
                $p_id = (int)$stmt->insert_id;
                $stmt->close();
            } catch (mysqli_sql_exception $e) {
                $p_error = 'The broadcast could not be saved.';
                $p_id = 0;
            }
            if ($p_error === '' && $p_id > 0) {
                if ($p_status === 'scheduled') {
                    $tb_notice = 'Broadcast #' . $p_id . ' scheduled for ' . $p_send_at . ' (' . $p_count . ' users).';
                    $tb_notice_ok = true;
                } else {
                    $disp = tb_dispatch_to_existing_sender($p_id);
                    if ($disp['ok']) {
                        $tb_notice = 'Broadcast #' . $p_id . ' sent to ' . $p_count . ' users.';
                        $tb_notice_ok = true;
                    } else {
                        // Recorded, not sent — safe failure mode (see H1).
                        $tb_notice = 'Broadcast #' . $p_id . ' saved (' . $p_count . ' users) but not sent: ' . (string)$disp['error'];
                        $tb_notice_ok = false;
                    }
                }
            }
        }
    }
    if ($p_error !== '') {
        $tb_notice = $p_error;
        $tb_notice_ok = false;
    }
}

// --- history: targeted broadcasts, newest first (compact, 50 rows) ----------

$tb_rows = [];
$tb_history_ok = false;
if ($tb_db !== null && tb_ensure_history_table()) {
    try {
        $res = $tb_db->query(
            'SELECT id, audience_segment, service_id, service_name, message, photo_path, '
            . 'audience_count, delivered, failed, status, send_at, sent_at, created_at '
            . 'FROM `' . $TB_HISTORY_TABLE . '` ORDER BY id DESC LIMIT 50'
        );
        if ($res !== false) {
            $tb_history_ok = true;
            while ($row = $res->fetch_assoc()) $tb_rows[] = $row;
            $res->close();
        }
    } catch (mysqli_sql_exception $e) {
        $tb_history_ok = false;
    }
}

function tb_seg_label($seg) {
    return $GLOBALS['TB_SEGMENTS'][$seg] ?? $seg;
}
function tb_short_msg($msg) {
    $m = trim((string)$msg);
    if (mb_strlen($m, 'UTF-8') > 60) $m = mb_substr($m, 0, 60, 'UTF-8') . '…';
    return $m;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Targeted broadcasts — Paxyo Admin</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; font-size: 14px; margin: 16px; color: #111; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #666; font-size: 12px; margin-bottom: 12px; }
  .back { font-size: 13px; }
  .notice { padding: 8px 10px; margin-bottom: 12px; font-size: 13px; border: 1px solid #e5e5e5; background: #f7f7f7; }
  .notice.ok { border-color: #3275dd; background: #eef4fe; }
  form.send { display: grid; gap: 10px; max-width: 560px; margin-bottom: 16px; }
  form.send label { font-size: 13px; font-weight: 600; display: grid; gap: 4px; }
  form.send select, form.send input, form.send textarea { font-size: 14px; padding: 6px 8px; font-weight: 400; }
  form.send textarea { min-height: 90px; resize: vertical; }
  .count { font-size: 14px; font-weight: 600; }
  .count.zero { color: #b00; }
  .svc-results { border: 1px solid #e5e5e5; max-height: 180px; overflow-y: auto; }
  .svc-results button { display: block; width: 100%; text-align: left; font-size: 13px; padding: 6px 8px; background: #fff; border: 0; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
  .svc-results button:hover { background: #eef4fe; }
  .svc-picked { font-size: 13px; font-weight: 400; }
  .svc-picked button { font-size: 12px; padding: 2px 8px; cursor: pointer; }
  button.primary { background: #3275dd; color: #fff; border: 0; font-size: 14px; padding: 8px 16px; cursor: pointer; }
  button.primary:disabled { background: #9db8e8; cursor: not-allowed; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 5px 8px; border-bottom: 1px solid #e5e5e5; text-align: left; vertical-align: top; }
  th { font-size: 12px; color: #666; font-weight: 600; }
  td.num { white-space: nowrap; font-variant-numeric: tabular-nums; }
  td.msg { max-width: 320px; overflow-wrap: anywhere; }
  .empty { color: #666; padding: 16px 0; }
</style>
</head>
<body>
<p class="back"><a href="<?php echo tb_h($TB_BACK_URL); ?>">&laquo; Broadcasting</a></p>
<h1>Targeted broadcasts</h1>
<p class="sub">Send to a group, not everyone. Pick who, check the count, then send.</p>

<?php if ($tb_notice !== ''): ?>
<p class="notice<?php echo $tb_notice_ok ? ' ok' : ''; ?>"><?php echo tb_h($tb_notice); ?></p>
<?php endif; ?>

<form class="send" method="post" action="" enctype="multipart/form-data" id="tb-form">
  <input type="hidden" name="action" value="send">
  <input type="hidden" name="service_id" id="tb-service-id" value="">

  <label>Send to
    <select name="segment" id="tb-segment">
      <?php foreach ($TB_SEGMENTS as $k => $label): ?>
      <option value="<?php echo tb_h($k); ?>"><?php echo tb_h($label); ?></option>
      <?php endforeach; ?>
    </select>
  </label>

  <label id="tb-service-wrap" style="display:none">Service — search by ID or name
    <input type="text" id="tb-service-q" placeholder="e.g. 6139 or Telegram Post Views" autocomplete="off">
    <span class="svc-picked" id="tb-service-picked"></span>
    <span class="svc-results" id="tb-service-results" style="display:none"></span>
  </label>

  <label>Message
    <textarea name="message" id="tb-message" maxlength="4096" placeholder="Write the message"></textarea>
  </label>

  <label>Photo (optional)
    <input type="file" name="photo" accept=".jpg,.jpeg,.png,.gif,.webp">
  </label>

  <label>Schedule (optional — leave empty to send now)
    <input type="datetime-local" name="schedule_at">
  </label>

  <p class="count" id="tb-count">Audience: —</p>

  <div><button type="submit" class="primary" id="tb-send" disabled>Send broadcast</button></div>
</form>

<h1 style="font-size:16px">History</h1>
<?php if ($tb_db === null || !$tb_history_ok): ?>
<p class="empty">No targeted-broadcast history yet.</p>
<?php elseif (!$tb_rows): ?>
<p class="empty">No targeted broadcasts yet.</p>
<?php else: ?>
<table>
  <thead>
    <tr><th>ID</th><th>When</th><th>Send to</th><th>Message</th><th>Users</th><th>Delivered</th><th>Failed</th><th>Status</th></tr>
  </thead>
  <tbody>
    <?php foreach ($tb_rows as $r): ?>
    <tr>
      <td class="num"><?php echo (int)$r['id']; ?></td>
      <td class="num"><?php echo tb_h($r['created_at']); ?></td>
      <td><?php echo tb_h(tb_seg_label((string)$r['audience_segment'])); ?><?php if (!empty($r['service_id'])): ?> #<?php echo (int)$r['service_id']; ?><?php if (!empty($r['service_name'])): ?> — <?php echo tb_h($r['service_name']); ?><?php endif; ?><?php endif; ?><?php if (!empty($r['photo_path'])): ?> (photo)<?php endif; ?></td>
      <td class="msg"><?php echo tb_h(tb_short_msg((string)$r['message'])); ?></td>
      <td class="num"><?php echo (int)$r['audience_count']; ?></td>
      <td class="num"><?php echo $r['delivered'] === null ? '—' : (int)$r['delivered']; ?></td>
      <td class="num"><?php echo $r['failed'] === null ? '—' : (int)$r['failed']; ?></td>
      <td><?php echo tb_h((string)$r['status']); ?><?php if (!empty($r['send_at']) && (string)$r['status'] === 'scheduled'): ?> <?php echo tb_h($r['send_at']); ?><?php endif; ?></td>
    </tr>
    <?php endforeach; ?>
  </tbody>
</table>
<?php endif; ?>

<script>
(function () {
  var seg = document.getElementById('tb-segment');
  var svcWrap = document.getElementById('tb-service-wrap');
  var svcQ = document.getElementById('tb-service-q');
  var svcId = document.getElementById('tb-service-id');
  var svcPicked = document.getElementById('tb-service-picked');
  var svcResults = document.getElementById('tb-service-results');
  var msg = document.getElementById('tb-message');
  var countEl = document.getElementById('tb-count');
  var sendBtn = document.getElementById('tb-send');
  var form = document.getElementById('tb-form');
  var lastCount = 0;

  function updateSend() {
    sendBtn.disabled = !(lastCount > 0 && msg.value.trim() !== '');
  }

  function fetchCount() {
    var s = seg.value;
    var url = '?action=count&segment=' + encodeURIComponent(s);
    if (s === 'service' && svcId.value) url += '&service_id=' + encodeURIComponent(svcId.value);
    if (s === 'service' && !svcId.value) {
      countEl.textContent = 'Audience: pick a service first';
      countEl.classList.remove('zero');
      lastCount = 0; updateSend(); return;
    }
    countEl.textContent = 'Audience: checking…';
    fetch(url).then(function (r) { return r.json(); }).then(function (d) {
      if (d.ok) {
        lastCount = d.count;
        countEl.textContent = 'Audience: ' + d.count + ' user' + (d.count === 1 ? '' : 's');
        countEl.classList.toggle('zero', d.count === 0);
      } else {
        lastCount = 0;
        countEl.textContent = 'Audience: ' + (d.error || 'could not be counted');
        countEl.classList.add('zero');
      }
      updateSend();
    }).catch(function () {
      lastCount = 0;
      countEl.textContent = 'Audience: could not be counted';
      countEl.classList.add('zero');
      updateSend();
    });
  }

  seg.addEventListener('change', function () {
    svcWrap.style.display = (seg.value === 'service') ? 'grid' : 'none';
    fetchCount();
  });
  msg.addEventListener('input', updateSend);

  var svcTimer = null;
  svcQ.addEventListener('input', function () {
    clearTimeout(svcTimer);
    var q = svcQ.value.trim();
    if (q.length < 2) { svcResults.style.display = 'none'; svcResults.innerHTML = ''; return; }
    svcTimer = setTimeout(function () {
      fetch('?action=service_search&q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          svcResults.innerHTML = '';
          if (!d.ok || !d.results || d.results.length === 0) {
            svcResults.style.display = 'none'; return;
          }
          d.results.forEach(function (s) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = '#' + s.id + ' — ' + s.name + (s.price !== null && s.price !== undefined ? ' (' + s.price + ' ETB/1000)' : '');
            b.addEventListener('click', function () {
              svcId.value = s.id;
              svcPicked.innerHTML = '';
              var t = document.createTextNode('#' + s.id + ' — ' + s.name + ' ');
              var x = document.createElement('button');
              x.type = 'button';
              x.textContent = 'Clear';
              x.addEventListener('click', function () {
                svcId.value = ''; svcPicked.innerHTML = ''; svcQ.value = ''; fetchCount();
              });
              svcPicked.appendChild(t); svcPicked.appendChild(x);
              svcResults.style.display = 'none'; svcResults.innerHTML = '';
              svcQ.value = '';
              fetchCount();
            });
            svcResults.appendChild(b);
          });
          svcResults.style.display = 'block';
        });
    }, 250);
  });

  form.addEventListener('submit', function (e) {
    if (lastCount <= 0) { e.preventDefault(); return; }
    var label = seg.options[seg.selectedIndex].text;
    if (seg.value === 'service' && svcId.value) label += ' #' + svcId.value;
    if (!window.confirm('Send this message to ' + lastCount + ' users (' + label + ')?\n\n' + msg.value.trim())) {
      e.preventDefault();
    }
  });

  fetchCount();
})();
</script>
</body>
</html>
