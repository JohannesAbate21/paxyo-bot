<?php
// ============================================================================
// "Confused chats" — admin section for @paxorder_bot (feature 4).
// Written 15 Nov 2026. Lists the bot_confusions log (see
// api-bot-sessions.php, smart-loop round 1) so William can see what
// the bot failed to understand, per user, and fix the wording or
// the training.
//
// WHAT IT IS: a human-admin page, opened in a browser from the
// Paxyo admin. It lists bot_confusions newest first — telegram_id,
// user_message, bot_reply, reason, created_at — paginated (50 per
// page), with a filter by reason (all / not_understood / garbled /
// correction / abandoned) and a search by telegram_id. Read-only:
// it never writes, never touches balances or orders, never calls
// the bot.
//
// AUTH — human-admin session, NOT X-Bot-Secret:
//   The live admin gates its APIs with a PHP session,
//   admin_authenticated=true (login at /admin/index.php — see
//   TO VERIFY below). This page reuses exactly that: session_start()
//   then require $_SESSION['admin_authenticated'] === true, else
//   redirect to the admin login. No bot secret anywhere on this
//   page, and the bot secret must never be added to it.
//
// INSTALL — where it goes (see TO VERIFY for the parts that could
// not be checked from outside the server):
//   1. Copy this file into the admin folder on paxyo.et, next to
//      the other admin sections — expected location:
//      public_html/px-4650dbff/confused-chats.php
//      (the admin lives at paxyo.et/px-4650dbff). If the live admin
//      keeps its sections somewhere else, put it there instead and
//      fix the two paths marked TO VERIFY below.
//   2. Link it from the admin navigation, labelled "Confused chats"
//      (English only — admin language rule), next to Orders/Users.
//   3. No database change: it reads bot_confusions, created by
//      api-bot-sessions.php (live since 14 Nov 2026). If the table
//      does not exist yet (endpoint never called), the page shows
//      "No confusion data yet" instead of an error.
//   4. No new secrets, no env vars, no cron. Open it once as the
//      admin and check: the list loads, the reason filter changes
//      the rows, a telegram_id search finds that user's rows.
//
// TO VERIFY DURING INSTALL (could not be confirmed locally — the
// live admin's files were not readable from outside the server):
//   V1. Admin folder: is the admin at public_html/px-4650dbff/?
//       If not, change $ADMIN_DIR below and the login redirect.
//   V2. Login URL: the redirect below sends a logged-out visitor
//       to /px-4650dbff/ (the admin entry point). If the login page
//       is a different file (e.g. /admin/index.php), change
//       $ADMIN_LOGIN_URL to that exact URL.
//   V3. Session key: the gate checks
//       $_SESSION['admin_authenticated'] === true. If the live
//       admin uses a different session key, change the check to
//       match — do NOT invent a second login system.
//   V4. Database include: the page includes ../db.php (the file
//       the live data source uses, public_html/db.php) and then
//       looks for the mysqli connection in $conn / $mysqli / $db /
//       $link, the same globals the bot.php splice files use. If
//       the admin already opens its own connection, delete the
//       require_once and keep the admin's connection instead.
//   V5. Shared layout: if the admin has a shared header/nav
//       include, wrap this page in it (same as the other sections)
//       instead of the standalone HTML below. Keep the table
//       compact and dense, like the other admin lists.
//   V6. bot_confusions columns: id, telegram_id, user_message
//       VARCHAR(500), bot_reply VARCHAR(500), reason, created_at
//       (api-bot-sessions.php). If a column is missing, the page
//       degrades to "No confusion data yet" — check the table
//       before assuming the bot logged nothing.
//
// STYLE: compact dense table (small rows, small padding — the
// admin lists rule), English only, no long explanatory text.
// ============================================================================

// --- config: fix these two lines at install time (see V1–V4) ---------------

$ADMIN_LOGIN_URL = '/px-4650dbff/';   // TO VERIFY (V2): admin login/entry URL
$DB_INCLUDE = __DIR__ . '/../db.php'; // TO VERIFY (V4): public_html/db.php

// --- admin session gate (same pattern as the live admin) --------------------

session_start();
if (empty($_SESSION['admin_authenticated']) || $_SESSION['admin_authenticated'] !== true) {
    header('Location: ' . $ADMIN_LOGIN_URL);
    exit;
}

// --- database connection (same globals as the bot.php splice files) --------

$conf_db = null;
if (file_exists($DB_INCLUDE)) {
    require_once $DB_INCLUDE;
}
foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
    if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
        $conf_db = $GLOBALS[$name];
        break;
    }
}

// --- inputs: page, reason filter, telegram_id search -----------------------

$conf_page = (int)($_GET['page'] ?? 1);
if ($conf_page < 1) $conf_page = 1;
$conf_per_page = 50;
$conf_offset = ($conf_page - 1) * $conf_per_page;

$conf_reason = strtolower(trim((string)($_GET['reason'] ?? '')));
$conf_reasons = ['not_understood', 'garbled', 'correction', 'abandoned'];
if ($conf_reason !== '' && !in_array($conf_reason, $conf_reasons, true)) $conf_reason = '';

$conf_tg = trim((string)($_GET['telegram_id'] ?? ''));
$conf_tg_id = 0;
if ($conf_tg !== '' && preg_match('/^\d+$/', $conf_tg)) $conf_tg_id = (int)$conf_tg;

// --- load rows (newest first). Table missing -> empty list, no error. -----

$conf_rows = [];
$conf_total = 0;
$conf_table_ok = false;
if ($conf_db !== null) {
    try {
        $conf_db->query("SET time_zone = '+03:00'"); // created_at shown in EAT
    } catch (mysqli_sql_exception $e) { /* display times fall back to server time */ }
    try {
        $check = $conf_db->query('SELECT 1 FROM bot_confusions LIMIT 1');
        if ($check !== false) {
            $conf_table_ok = true;
            $check->close();
        }
    } catch (mysqli_sql_exception $e) {
        $conf_table_ok = false;
    }
}
if ($conf_table_ok) {
    $where = [];
    $types = '';
    $params = [];
    if ($conf_reason !== '') {
        $where[] = 'reason = ?';
        $types .= 's';
        $params[] = $conf_reason;
    }
    if ($conf_tg_id > 0) {
        $where[] = 'telegram_id = ?';
        $types .= 'i';
        $params[] = $conf_tg_id;
    }
    $where_sql = $where ? (' WHERE ' . implode(' AND ', $where)) : '';

    try {
        $stmt = $conf_db->prepare('SELECT COUNT(*) FROM bot_confusions' . $where_sql);
        if ($types !== '') $stmt->bind_param($types, ...$params);
        $stmt->execute();
        $row = $stmt->get_result()->fetch_row();
        $stmt->close();
        $conf_total = $row ? (int)$row[0] : 0;
    } catch (mysqli_sql_exception $e) {
        $conf_total = 0;
    }

    try {
        $stmt = $conf_db->prepare(
            'SELECT id, telegram_id, user_message, bot_reply, reason, created_at '
            . 'FROM bot_confusions' . $where_sql . ' ORDER BY id DESC LIMIT ? OFFSET ?'
        );
        $list_types = $types . 'ii';
        $list_params = array_merge($params, [$conf_per_page, $conf_offset]);
        $stmt->bind_param($list_types, ...$list_params);
        $stmt->execute();
        $res = $stmt->get_result();
        while ($row = $res->fetch_assoc()) $conf_rows[] = $row;
        $stmt->close();
    } catch (mysqli_sql_exception $e) {
        $conf_rows = [];
    }
}

$conf_pages = $conf_total > 0 ? (int)ceil($conf_total / $conf_per_page) : 1;
if ($conf_page > $conf_pages) $conf_page = $conf_pages;

function conf_h($s) {
    return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
}
function conf_qs($overrides) {
    $q = [
        'reason' => $GLOBALS['conf_reason'],
        'telegram_id' => $GLOBALS['conf_tg'],
    ];
    foreach ($overrides as $k => $v) $q[$k] = $v;
    $q = array_filter($q, function ($v) { return $v !== '' && $v !== null; });
    return $q ? ('?' . http_build_query($q)) : '';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Confused chats — Paxyo Admin</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; font-size: 14px; margin: 16px; color: #111; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #666; font-size: 12px; margin-bottom: 12px; }
  form.filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }
  form.filters select, form.filters input { font-size: 14px; padding: 5px 8px; }
  form.filters button { font-size: 14px; padding: 5px 12px; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 5px 8px; border-bottom: 1px solid #e5e5e5; text-align: left; vertical-align: top; }
  th { font-size: 12px; color: #666; font-weight: 600; }
  td.msg { max-width: 320px; overflow-wrap: anywhere; }
  td.id { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .reason { white-space: nowrap; }
  .empty { color: #666; padding: 16px 0; }
  .pager { margin-top: 12px; font-size: 13px; }
  .pager a { margin-right: 10px; }
</style>
</head>
<body>
<h1>Confused chats</h1>
<p class="sub">Messages the bot did not understand, newest first. <?php echo $conf_total; ?> total.</p>

<form class="filters" method="get" action="">
  <label>Reason
    <select name="reason">
      <option value=""<?php echo $conf_reason === '' ? ' selected' : ''; ?>>All reasons</option>
      <?php foreach ($conf_reasons as $r): ?>
      <option value="<?php echo conf_h($r); ?>"<?php echo $conf_reason === $r ? ' selected' : ''; ?>><?php echo conf_h($r); ?></option>
      <?php endforeach; ?>
    </select>
  </label>
  <label>Telegram ID
    <input type="text" name="telegram_id" value="<?php echo conf_h($conf_tg); ?>" placeholder="e.g. 779060335" inputmode="numeric">
  </label>
  <button type="submit">Filter</button>
  <?php if ($conf_reason !== '' || $conf_tg !== ''): ?><a href="?">Clear</a><?php endif; ?>
</form>

<?php if ($conf_db === null): ?>
<p class="empty">Database is not available. Check the db.php include (see V4 in the file header).</p>
<?php elseif (!$conf_table_ok): ?>
<p class="empty">No confusion data yet. The bot_confusions table does not exist — it is created the first time the bot logs a confusion (api-bot-sessions.php, live since 14 Nov 2026).</p>
<?php elseif (!$conf_rows): ?>
<p class="empty">No confused chats match this filter.</p>
<?php else: ?>
<table>
  <thead>
    <tr><th>ID</th><th>Telegram ID</th><th>User message</th><th>Bot reply</th><th>Reason</th><th>Time (EAT)</th></tr>
  </thead>
  <tbody>
    <?php foreach ($conf_rows as $r): ?>
    <tr>
      <td class="id"><?php echo (int)$r['id']; ?></td>
      <td class="id"><?php echo (int)$r['telegram_id']; ?></td>
      <td class="msg"><?php echo conf_h($r['user_message']); ?></td>
      <td class="msg"><?php echo conf_h($r['bot_reply']); ?></td>
      <td class="reason"><?php echo conf_h($r['reason']); ?></td>
      <td class="id"><?php echo conf_h($r['created_at']); ?></td>
    </tr>
    <?php endforeach; ?>
  </tbody>
</table>
<div class="pager">
  Page <?php echo $conf_page; ?> of <?php echo $conf_pages; ?>
  <?php if ($conf_page > 1): ?><a href="<?php echo conf_h(conf_qs(['page' => $conf_page - 1])); ?>">&laquo; Previous</a><?php endif; ?>
  <?php if ($conf_page < $conf_pages): ?><a href="<?php echo conf_h(conf_qs(['page' => $conf_page + 1])); ?>">Next &raquo;</a><?php endif; ?>
</div>
<?php endif; ?>
</body>
</html>
