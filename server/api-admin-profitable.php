<?php
// ============================================================================
// Most profitable services for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot
// feature 16 — the admin bot /profitable lists the services earning
// the most.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   GET /api/bot/admin/profitable
//     -> {"services":[{service_id, service_name, orders, quantity,
//         revenue_etb, profit_etb}, ...]}
//        Top 10 by profit, all time. Profit and revenue come from
//        COMPLETED orders only (a placed-but-unfinished order has
//        earned nothing yet), using the same economics as the
//        admin-stats endpoint: revenue = SUM(total) of completed
//        orders, profit = revenue x 220/420 (the owner buys 1 USD
//        for 200 ETB and sells at 420 ETB — see A2). Because the
//        margin is uniform across services (every service sells at
//        rate x 420 and costs rate x 200), profit ranking is the
//        same as revenue ranking; the endpoint still reports both
//        figures so the admin bot shows the profit, not just the
//        revenue.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-admin-profitable.php   (this file must pass on its own)
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
//     on the other endpoints). Errors use prf_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - This is an ADMIN read (the admin bot calls it with the same
//     X-Bot-Secret). No per-user rate limit is applied here.
//
// ASSUMPTIONS — TO VERIFY ON THE SERVER DURING INSTALL:
//   A1. orders has id, telegram_id, total, quantity (or qty),
//       status, service_id (or provider_service_id / service), and
//       optionally service_name, created_at — the same columns the
//       admin-stats endpoint assumes. The code discovers the service
//       and quantity columns the same way (information_schema), so a
//       differently-named column still works — but confirm the real
//       names with SHOW COLUMNS FROM orders and trim the lists.
//   A2. Economics (same as api-admin-stats.php A6): the selling
//       price is provider rate x 420 ETB and the owner buys 1 USD
//       for 200 ETB, so provider cost = revenue x 200/420 and net
//       profit = revenue x 220/420. If William ever changes the 420
//       multiplier in Settings, this split must change with it — it
//       is NOT read from settings here.
//   A3. "Completed" means status = 'completed' only (the same
//       single spelling the admin-stats endpoint uses for revenue).
//       Orders with status 'complete' / 'success' / 'paid' are NOT
//       counted as revenue here — if the live table uses one of
//       those spellings for finished orders, add it to
//       PRF_COMPLETED_STATUSES below (and tell the admin-stats
//       owner, so the two endpoints agree).
//   A4. Service names: the local `services` table is checked first
//       (name by provider_service_id, then by id — same as
//       adm_service_name); when there is no services table or no
//       row, the name falls back to orders.service_name when the
//       orders row carries it, else "Service #<id>".
// ============================================================================

// --- small helpers (prf_ prefix so nothing collides with bot.php) -----------

if (!defined('PRF_COMPLETED_STATUSES')) define('PRF_COMPLETED_STATUSES', 'completed');

function prf_db() {
    foreach (['conn', 'mysqli', 'db', 'link'] as $name) {
        if (isset($GLOBALS[$name]) && $GLOBALS[$name] instanceof mysqli) {
            return $GLOBALS[$name];
        }
    }
    return null;
}

function prf_fail($code, $msg) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode(['success' => false, 'error' => $msg, 'message' => $msg]);
    exit;
}

function prf_has_column($db, $table, $col) {
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

function prf_has_table($db, $table) {
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

// Discover which service/quantity columns orders actually has.
// Same candidate order as the admin-stats endpoint.
function prf_discover_orders_columns($db) {
    $service = null;
    $service_is_name = false;
    foreach (['service_id', 'provider_service_id', 'service'] as $col) {
        if (prf_has_column($db, 'orders', $col)) { $service = $col; break; }
    }
    if ($service === null && prf_has_column($db, 'orders', 'service_name')) {
        $service = 'service_name';
        $service_is_name = true;
    }
    $quantity = null;
    foreach (['quantity', 'qty'] as $col) {
        if (prf_has_column($db, 'orders', $col)) { $quantity = $col; break; }
    }
    return ['service' => $service, 'service_is_name' => $service_is_name, 'quantity' => $quantity];
}

// Service display name: the local services table first (same as
// adm_service_name), then the orders row's own service_name when it
// has one, else "Service #<id>".
function prf_service_name($db, $service_id, $fallback_name = null) {
    $service_id = (int)$service_id;
    if ($service_id <= 0) return $fallback_name ?: 'Service #?';
    if (prf_has_table($db, 'services') && prf_has_column($db, 'services', 'name')) {
        $join_col = null;
        foreach (['provider_service_id', 'id'] as $col) {
            if (prf_has_column($db, 'services', $col)) { $join_col = $col; break; }
        }
        if ($join_col !== null) {
            try {
                $stmt = $db->prepare('SELECT name FROM services WHERE `' . $join_col . '` = ? LIMIT 1');
                $stmt->bind_param('i', $service_id);
                $stmt->execute();
                $row = $stmt->get_result()->fetch_assoc();
                $stmt->close();
                if ($row && (string)$row['name'] !== '') return (string)$row['name'];
            } catch (mysqli_sql_exception $e) { /* fall through */ }
        }
    }
    if ($fallback_name !== null && (string)$fallback_name !== '') return (string)$fallback_name;
    return 'Service #' . $service_id;
}

// --- GET /api/bot/admin/profitable ------------------------------------------

function bot_prf_profitable() {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') prf_fail(405, 'Method not allowed.');
    $db = prf_db();
    if ($db === null) prf_fail(500, 'Database is not available.');
    try { $db->query("SET time_zone = '+00:00'"); } catch (mysqli_sql_exception $e) { /* keep going */ }

    $cols = prf_discover_orders_columns($db);
    if ($cols['service'] === null) {
        // No service column at all: there is nothing to rank by.
        bot_ok(['services' => []]);
        return;
    }
    $svc_col = $cols['service'];
    $qty_col = $cols['quantity'];
    $qty_expr = $qty_col !== null
        ? 'COALESCE(SUM(`' . $qty_col . '`), 0)'
        : '0';
    // When orders carries its own service_name, keep one per service
    // id for the fallback name (MAX is arbitrary but stable — the
    // name does not change per order).
    $name_expr = prf_has_column($db, 'orders', 'service_name')
        ? ', MAX(service_name) AS svc_name'
        : '';

    $sql = "SELECT `$svc_col` AS svc, COUNT(*) AS orders, COALESCE(SUM(total), 0) AS revenue, $qty_expr AS quantity $name_expr "
        . "FROM orders WHERE status = 'completed' GROUP BY `$svc_col` ORDER BY revenue DESC LIMIT 10";
    try {
        $res = $db->query($sql);
    } catch (mysqli_sql_exception $e) {
        prf_fail(500, 'Could not read the orders table.');
    }
    if ($res === false) prf_fail(500, 'Could not read the orders table.');

    $services = [];
    while ($row = $res->fetch_assoc()) {
        $revenue = round((float)$row['revenue'], 2);
        $services[] = [
            'service_id' => $cols['service_is_name'] ? null : (int)$row['svc'],
            'service_name' => $cols['service_is_name']
                ? (string)$row['svc']
                : prf_service_name($db, (int)$row['svc'], $row['svc_name'] ?? null),
            'orders' => (int)$row['orders'],
            'quantity' => (int)$row['quantity'],
            'revenue_etb' => $revenue,
            // Same economics as admin-stats (A2): profit = revenue x 220/420.
            'profit_etb' => round($revenue * 220 / 420, 2),
        ];
    }
    bot_ok(['services' => $services]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'admin/profitable' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_prf_profitable(); }
//
// LIVE CURL TEST — read-only, no money moves, no rows change:
//   S=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   curl -s "https://paxyo.et/api/bot/admin/profitable" \
//     -H "X-Bot-Secret: $S"
//   -> expect {"success":true,"services":[{service_id, service_name,
//      orders, quantity, revenue_etb, profit_etb}, ...]} with at most
//      10 rows, ordered by profit_etb descending. Cross-check one
//      row against the admin panel: its revenue_etb must equal the
//      SUM(total) of that service's completed orders, and its
//      profit_etb must equal revenue_etb x 220/420 (rounded to 2dp).
// ============================================================================
