<?php
// ============================================================================
// Per-customer order preferences for the Paxyo Bot API
// (public_html/api/bot.php). Written 15 Nov 2026 for @paxorder_bot,
// the 13 approved order customizations (15 Nov 19:57 + 20:07 EAT)
// plus the new options approved 20:57 + 21:10 EAT the same day
// (#21, #24, #25, #27, #30–40) — SERVER SIDE ONLY.
//
// WHAT THE CUSTOMER ASKED FOR, in plain words in chat ("cheapest
// first", "ask me before you change service", "my link is ...",
// "never slower than 1 hour"). The bot stores them per user; this
// file is only the durable copy. The NORMAL way stays the default
// for everyone who set nothing — this file never invents a pref,
// never fills in a default, and never changes a pick on its own.
// The bot reads the prefs and applies them; the server just stores
// and returns them.
//
// DESIGN — SAME TABLE AS TRAITS, DIFFERENT KEYS (Option B, like
// api-user-traits.php): the prefs live in bot_user_traits, under
// keys prefixed "prf_" (prf_pick_order, prf_ask_first, ...). The
// learned traits (tone, usual_platform, usual_quantity,
// usual_service_id, last_deposit_method) live in the SAME row
// under their own keys, and neither file ever touches the other's
// keys: a prefs save merges ONLY prf_ keys (the traits survive),
// and a traits save merges ONLY trait keys (the prefs survive —
// trt_validate_traits drops unknown fields from the request, and
// its merge only applies the fields it validated). A prefs save
// can never wipe history/draft/lang (those live in bot_sessions,
// a different table), and a session save can never touch prefs.
// The bot's in-memory mirror (USER_TRAITS) holds both, but the
// code treats them as different things: learned traits never
// change a pick, explicit prefs do — only for the customer who
// set them.
//
// WHAT IT ADDS (all behind the existing X-Bot-Secret check in bot.php):
//   POST /api/bot/user-prefs   {telegram_id, prefs:{...}}
//     -> {"ok":true,"prefs":{...merged...},"updated_at":"..."}
//        MERGE (PATCH) semantics, exactly like /user-traits: only
//        the fields present in the request change. A field sent as
//        null is CLEARED; a field not sent is left exactly as
//        stored. Unknown fields are dropped, never stored. A known
//        field with a bad value FAILS the whole save with 400 —
//        fail closed, so a bad value can never silently become a
//        pref. The reply's prefs are the bot's own key names
//        (pref_pick_order, ...) — the prf_ prefix is stripped on
//        the way out and added on the way in, so the bot never
//        sees it.
//   GET  /api/bot/user-prefs?telegram_id=X
//     -> {"prefs":{...},"updated_at":"..."}  or  {"prefs":null}
//        when nothing is stored yet. NOTE: "no prefs stored" is a
//        200 with prefs:null — NOT a 404. A 404 means the endpoint
//        itself is not installed yet, and the bot must treat that
//        the same way ("nothing set yet") and keep working from
//        memory. Never raise into a chat either way.
//
// THE PREF SET (25 keys). The server stores ONLY what the bot
// sends; the ranges below are the second line of defence — the
// bot validates first (validate_pref in bot.py), the server
// validates again, and a bad value fails the whole save. See
// prf_validate_prefs() below for the exact rules.
//   pref_pick_order       "fastest" | "cheapest" — #4. Default is
//                         fastest; the server never assumes one.
//   pref_ask_first        bool — #6. Ask before moving a stuck order.
//   pref_max_slowness_min int, 5..10080 (minutes) — #8. Never use a
//                         service slower than this.
//   pref_default_link     string, max 500 chars — #11. The customer's
//                         usual link. Must look like a link.
//   pref_default_quantity object — #12. Keys "*" (any order) or
//                         "platform:metric" (e.g. "tiktok:views") or
//                         "*:metric"; values int 1..100,000,000.
//   pref_price_ceiling    number, > 0 and <= 100000 — #13. Never pay
//                         more than this ETB per 1,000.
//   pref_refill_only      bool — #14. Only services that offer refill.
//   pref_auto_repeat      object {interval_minutes, platform, metric}
//                         — #16. interval 30..43200 minutes;
//                         platform + metric are lowercase slugs.
//   pref_topup_missing    bool — #17. Order the missing part itself
//                         instead of only refunding.
//   pref_no_confirm       bool — #18. Place small orders without
//                         asking (explicit opt-in only).
//   pref_no_confirm_max_etb int, 1..100 — #18. The cap (at most
//                         100 ETB; the bot caps it, the server
//                         enforces it).
//   pref_quiet_hours      object {start, end} — #19. "HH:MM" EAT
//                         strings, start != end.
//   (New options, 15 Nov 2026 — approved 20:57 + 21:10 EAT.)
//   pref_favourite_services list of bare service ids ("5535"),
//                         1..20 — #21. Prefer these when they fit.
//   pref_low_balance_alert_etb int, 1..100000 — #24. Warn when the
//                         balance drops below this.
//   pref_weekly_spend_limit_etb int, 1..1000000 — #25. Refuse an
//                         order that would take the week's spending
//                         over this.
//   pref_saved_links      object name->link, max 10 — #31. Names
//                         are lowercase slugs; links as #11.
//   pref_auto_cancel_min  int, 5..10080 (minutes) — #34. Cancel
//                         and refund a stuck order after this long.
//   pref_start_fast_only  bool — #36. Only services that start
//                         within 15 minutes.
//   pref_language         "en" | "am" | "ti" | "om" — #37. Always
//                         reply in this language.
//   pref_double_confirm_etb int, 1..1000000 — #38. Ask twice
//                         before orders over this.
//   pref_banned_services  list of bare service ids, 1..50 — #39.
//                         Never use these services.
//   pref_try_new          bool — #40. Prefer services with no
//                         claimed time yet.
//   pref_watch_post       object {link, below?} — #30. Remembered
//                         only; the doing part is not switched on
//                         yet (the bot says so honestly).
//   pref_wait_price       object {platform, metric, target} — #33.
//                         Remembered only, same as #30.
//   pref_monthly_report   bool — #35. Remembered only, same as #30.
//
// HOW TO INSTALL (run on the server, in the DirectAdmin Terminal):
//   1. php -l api-user-prefs.php      (this file must pass on its own)
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
// to add, mirroring save_traits / load_traits in bot.py):
//   save_prefs(telegram_id, prefs) — POST /user-prefs, 404-tolerant
//     (return None on 404, log a warning, keep working from memory).
//     Send ONLY the prefs that changed; the server merges. To clear
//     one pref, send it as null — never send a whole prefs dict
//     rebuilt from a stale copy.
//   load_prefs(telegram_id) — GET /user-prefs?telegram_id=X.
//     Returns the prefs dict, or None when {"prefs":null} OR on
//     404 — the caller treats both as "nothing set yet".
//   Every call is best-effort and must never raise into a chat, like
//   the traits calls.
//
// NOTES FOR THE INSTALLER (check these against the live files first):
//   - bot_ok() is used for success replies (it adds "success":true, as
//     on the other endpoints). Errors use prf_fail() below, which
//     returns {"success":false,"error":...,"message":...} — the bot
//     reads both keys.
//   - Add the same bot_rate_limit(...) call the other user endpoints
//     use to the dispatch lines (copy the exact call from the orders
//     handler — the signature was not visible from outside the server).
//   - NO account-existence check here, unlike deposits: prefs must
//     be storable even for a brand-new user whose auth row does not
//     exist yet. Orphan rows are tiny (one per user) and keyed by
//     telegram_id, so this cannot grow out of control.
//   - No money moves here: these endpoints never touch balances,
//     orders, deposits or the provider. A prefs write cannot place,
//     cancel or change an order. The prefs only change what the BOT
//     picks and asks — the money steps stay deterministic.
// ============================================================================

// --- small helpers (prf_ prefix so nothing collides with bot.php) -----------

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

function prf_json_body() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function prf_ensure_table($db) {
    // The table is shared with api-user-traits.php (bot_user_traits);
    // creating it here is idempotent — harmless when it already exists.
    if (method_exists($db, 'set_charset')) $db->set_charset('utf8mb4');
    $db->query("CREATE TABLE IF NOT EXISTS bot_user_traits (
        telegram_id BIGINT NOT NULL PRIMARY KEY,
        traits TEXT NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

// --- pref validation --------------------------------------------------------
// The whole pref set, in one place. Returns [cleaned, error]:
//   cleaned — the validated fields, with nulls kept (null = clear it)
//   error   — null on success, otherwise a message naming the bad field.
// Unknown fields are DROPPED silently (forward-compatible: an older
// server ignores a newer bot's extra field instead of failing the
// save). A known field with a bad value FAILS the whole save with
// 400 — fail closed, so a bad value can never silently become a pref.
// The bot sends pref_* keys; the server stores them as prf_* in the
// shared row, and strips the prefix again on load.

function prf_is_int_value($v) {
    return is_int($v) || (is_string($v) && preg_match('/^\d+$/', $v));
}

function prf_is_slug($v) {
    return is_string($v) && preg_match('/^[a-z0-9][a-z0-9_-]{0,31}$/', $v);
}

function prf_is_clock($v) {
    return is_string($v) && preg_match('/^([01][0-9]|2[0-3]):[0-5][0-9]$/', $v);
}

function prf_is_link($v) {
    return is_string($v) && strlen($v) <= 500 && strpos($v, ' ') === false
        && preg_match('/^(https?:\/\/|t\.me\/|www\.|@|[a-z0-9.-]+\.[a-z]{2,}(\/\S*)?$)/i', $v);
}

function prf_is_service_id_list($v, $max) {
    // A list of bare service-id strings ("5535"), 1..$max, deduped.
    // A JSON object (associative array) is not a list.
    if (!is_array($v) || empty($v) || count($v) > $max) return false;
    if (array_keys($v) !== range(0, count($v) - 1)) return false;
    $seen = [];
    foreach ($v as $item) {
        if (!is_string($item) && !is_int($item)) return false;
        $item = (string)$item;
        if (!preg_match('/^\d{1,8}$/', $item)) return false;
        if (isset($seen[$item])) return false;
        $seen[$item] = true;
    }
    return true;
}

function prf_validate_prefs($in) {
    $cleaned = [];
    // pref_pick_order (#4): "fastest" | "cheapest".
    if (isset($in['pref_pick_order'])) {
        if ($in['pref_pick_order'] === null) {
            $cleaned['pref_pick_order'] = null;
        } elseif (is_string($in['pref_pick_order']) && in_array($in['pref_pick_order'], ['fastest', 'cheapest'], true)) {
            $cleaned['pref_pick_order'] = $in['pref_pick_order'];
        } else {
            return [null, 'pref_pick_order must be "fastest" or "cheapest", or null.'];
        }
    }
    // Boolean prefs (#6, #14, #17, #18, #36, #40, #35): real JSON
    // booleans only — the strings "true"/"false" and 0/1 are
    // rejected.
    foreach (['pref_ask_first', 'pref_refill_only', 'pref_topup_missing', 'pref_no_confirm', 'pref_start_fast_only', 'pref_try_new', 'pref_monthly_report'] as $field) {
        if (isset($in[$field])) {
            if ($in[$field] === null) {
                $cleaned[$field] = null;
            } elseif (is_bool($in[$field])) {
                $cleaned[$field] = $in[$field];
            } else {
                return [null, $field . ' must be a boolean, or null.'];
            }
        }
    }
    // pref_max_slowness_min (#8): integer minutes, 5..10080 (7 days).
    if (isset($in['pref_max_slowness_min'])) {
        if ($in['pref_max_slowness_min'] === null) {
            $cleaned['pref_max_slowness_min'] = null;
        } elseif (prf_is_int_value($in['pref_max_slowness_min'])) {
            $minutes = (int)$in['pref_max_slowness_min'];
            if ($minutes < 5 || $minutes > 10080) {
                return [null, 'pref_max_slowness_min must be between 5 and 10080, or null.'];
            }
            $cleaned['pref_max_slowness_min'] = $minutes;
        } else {
            return [null, 'pref_max_slowness_min must be an integer, or null.'];
        }
    }
    // pref_default_link (#11): a string that looks like a link —
    // http(s)://, t.me/, www., @handle, or a bare domain. No spaces.
    if (isset($in['pref_default_link'])) {
        if ($in['pref_default_link'] === null) {
            $cleaned['pref_default_link'] = null;
        } elseif (is_string($in['pref_default_link']) && strlen($in['pref_default_link']) <= 500 && strpos($in['pref_default_link'], ' ') === false && preg_match('/^(https?:\/\/|t\.me\/|www\.|@|[a-z0-9.-]+\.[a-z]{2,}(\/\S*)?$)/i', $in['pref_default_link'])) {
            $cleaned['pref_default_link'] = trim($in['pref_default_link']);
        } else {
            return [null, 'pref_default_link must be a link, or null.'];
        }
    }
    // pref_default_quantity (#12): an object. Keys are "*" (any
    // order), "platform:metric" or "*:metric"; values are integers
    // 1..100,000,000. An empty object is rejected (nothing to store).
    if (isset($in['pref_default_quantity'])) {
        if ($in['pref_default_quantity'] === null) {
            $cleaned['pref_default_quantity'] = null;
        } elseif (is_array($in['pref_default_quantity']) && !empty($in['pref_default_quantity'])) {
            $quantities = [];
            foreach ($in['pref_default_quantity'] as $qkey => $qvalue) {
                // Keys: "*" (any order), "platform:metric", "*:metric"
                // (any platform, one metric), or a bare metric slug.
                if (!is_string($qkey) || ($qkey !== '*' && !preg_match('/^(\*:[a-z_]+|[a-z]+:[a-z_]+|[a-z_]+)$/', $qkey))) {
                    return [null, 'pref_default_quantity keys must be "*" or "platform:metric", or null.'];
                }
                if (!prf_is_int_value($qvalue)) {
                    return [null, 'pref_default_quantity values must be integers, or null.'];
                }
                $qty = (int)$qvalue;
                if ($qty < 1 || $qty > 100000000) {
                    return [null, 'pref_default_quantity values must be between 1 and 100000000, or null.'];
                }
                $quantities[$qkey] = $qty;
            }
            $cleaned['pref_default_quantity'] = $quantities;
        } else {
            return [null, 'pref_default_quantity must be an object, or null.'];
        }
    }
    // pref_price_ceiling (#13): a number, > 0 and <= 100000 ETB
    // per 1,000. Integers and floats both arrive as numbers.
    if (isset($in['pref_price_ceiling'])) {
        if ($in['pref_price_ceiling'] === null) {
            $cleaned['pref_price_ceiling'] = null;
        } elseif (is_numeric($in['pref_price_ceiling'])) {
            $price = (float)$in['pref_price_ceiling'];
            if ($price <= 0 || $price > 100000) {
                return [null, 'pref_price_ceiling must be between 0 and 100000, or null.'];
            }
            $cleaned['pref_price_ceiling'] = $price;
        } else {
            return [null, 'pref_price_ceiling must be a number, or null.'];
        }
    }
    // pref_auto_repeat (#16): {interval_minutes, platform, metric}.
    // interval 30..43200 minutes (30 days); platform + metric are
    // lowercase slugs.
    if (isset($in['pref_auto_repeat'])) {
        if ($in['pref_auto_repeat'] === null) {
            $cleaned['pref_auto_repeat'] = null;
        } elseif (is_array($in['pref_auto_repeat'])) {
            $repeat = $in['pref_auto_repeat'];
            if (!isset($repeat['interval_minutes']) || !prf_is_int_value($repeat['interval_minutes'])) {
                return [null, 'pref_auto_repeat.interval_minutes must be an integer, or null.'];
            }
            $interval = (int)$repeat['interval_minutes'];
            if ($interval < 30 || $interval > 43200) {
                return [null, 'pref_auto_repeat.interval_minutes must be between 30 and 43200, or null.'];
            }
            if (!isset($repeat['platform']) || !prf_is_slug($repeat['platform'])) {
                return [null, 'pref_auto_repeat.platform must be a lowercase slug, or null.'];
            }
            if (!isset($repeat['metric']) || !prf_is_slug($repeat['metric'])) {
                return [null, 'pref_auto_repeat.metric must be a lowercase slug, or null.'];
            }
            $cleaned['pref_auto_repeat'] = [
                'interval_minutes' => $interval,
                'platform' => $repeat['platform'],
                'metric' => $repeat['metric'],
            ];
        } else {
            return [null, 'pref_auto_repeat must be an object, or null.'];
        }
    }
    // pref_no_confirm_max_etb (#18): integer, 1..100. The bot caps
    // the customer's number at 100; the server enforces it.
    if (isset($in['pref_no_confirm_max_etb'])) {
        if ($in['pref_no_confirm_max_etb'] === null) {
            $cleaned['pref_no_confirm_max_etb'] = null;
        } elseif (prf_is_int_value($in['pref_no_confirm_max_etb'])) {
            $cap = (int)$in['pref_no_confirm_max_etb'];
            if ($cap < 1 || $cap > 100) {
                return [null, 'pref_no_confirm_max_etb must be between 1 and 100, or null.'];
            }
            $cleaned['pref_no_confirm_max_etb'] = $cap;
        } else {
            return [null, 'pref_no_confirm_max_etb must be an integer, or null.'];
        }
    }
    // pref_quiet_hours (#19): {start, end} as "HH:MM" EAT strings,
    // start != end (a zero-length window is meaningless).
    if (isset($in['pref_quiet_hours'])) {
        if ($in['pref_quiet_hours'] === null) {
            $cleaned['pref_quiet_hours'] = null;
        } elseif (is_array($in['pref_quiet_hours'])) {
            $hours = $in['pref_quiet_hours'];
            if (!isset($hours['start']) || !prf_is_clock($hours['start'])) {
                return [null, 'pref_quiet_hours.start must be "HH:MM", or null.'];
            }
            if (!isset($hours['end']) || !prf_is_clock($hours['end'])) {
                return [null, 'pref_quiet_hours.end must be "HH:MM", or null.'];
            }
            if ($hours['start'] === $hours['end']) {
                return [null, 'pref_quiet_hours.start and end must differ.'];
            }
            $cleaned['pref_quiet_hours'] = [
                'start' => $hours['start'],
                'end' => $hours['end'],
            ];
        } else {
            return [null, 'pref_quiet_hours must be an object, or null.'];
        }
    }
    // pref_favourite_services (#21): bare service ids, 1..20.
    if (isset($in['pref_favourite_services'])) {
        if ($in['pref_favourite_services'] === null) {
            $cleaned['pref_favourite_services'] = null;
        } elseif (prf_is_service_id_list($in['pref_favourite_services'], 20)) {
            $cleaned['pref_favourite_services'] = array_values(array_map('strval', $in['pref_favourite_services']));
        } else {
            return [null, 'pref_favourite_services must be a list of 1..20 service ids, or null.'];
        }
    }
    // pref_banned_services (#39): bare service ids, 1..50.
    if (isset($in['pref_banned_services'])) {
        if ($in['pref_banned_services'] === null) {
            $cleaned['pref_banned_services'] = null;
        } elseif (prf_is_service_id_list($in['pref_banned_services'], 50)) {
            $cleaned['pref_banned_services'] = array_values(array_map('strval', $in['pref_banned_services']));
        } else {
            return [null, 'pref_banned_services must be a list of 1..50 service ids, or null.'];
        }
    }
    // Integer-amount prefs (#24, #25, #38, #34): plain ranges.
    $int_ranges = [
        'pref_low_balance_alert_etb' => [1, 100000],
        'pref_weekly_spend_limit_etb' => [1, 1000000],
        'pref_double_confirm_etb' => [1, 1000000],
        'pref_auto_cancel_min' => [5, 10080],
    ];
    foreach ($int_ranges as $field => $range) {
        if (isset($in[$field])) {
            if ($in[$field] === null) {
                $cleaned[$field] = null;
            } elseif (prf_is_int_value($in[$field])) {
                $amount = (int)$in[$field];
                if ($amount < $range[0] || $amount > $range[1]) {
                    return [null, $field . ' must be between ' . $range[0] . ' and ' . $range[1] . ', or null.'];
                }
                $cleaned[$field] = $amount;
            } else {
                return [null, $field . ' must be an integer, or null.'];
            }
        }
    }
    // pref_language (#37): "en" | "am" | "ti" | "om".
    if (isset($in['pref_language'])) {
        if ($in['pref_language'] === null) {
            $cleaned['pref_language'] = null;
        } elseif (is_string($in['pref_language']) && in_array($in['pref_language'], ['en', 'am', 'ti', 'om'], true)) {
            $cleaned['pref_language'] = $in['pref_language'];
        } else {
            return [null, 'pref_language must be "en", "am", "ti" or "om", or null.'];
        }
    }
    // pref_saved_links (#31): object name->link, max 10. Names are
    // lowercase slugs; links look like a link (same rule as #11).
    if (isset($in['pref_saved_links'])) {
        if ($in['pref_saved_links'] === null) {
            $cleaned['pref_saved_links'] = null;
        } elseif (is_array($in['pref_saved_links']) && !empty($in['pref_saved_links']) && count($in['pref_saved_links']) <= 10) {
            $links = [];
            foreach ($in['pref_saved_links'] as $name => $link) {
                if (!is_string($name) || !preg_match('/^[a-z0-9_-]{1,30}$/', $name)) {
                    return [null, 'pref_saved_links names must be lowercase slugs, or null.'];
                }
                if (!prf_is_link($link)) {
                    return [null, 'pref_saved_links values must be links, or null.'];
                }
                $links[strtolower($name)] = trim($link);
            }
            $cleaned['pref_saved_links'] = $links;
        } else {
            return [null, 'pref_saved_links must be an object of 1..10 name->link pairs, or null.'];
        }
    }
    // pref_watch_post (#30): {link, below?}. Remembered only — the
    // doing part is not switched on yet; the server still validates
    // the shape so a bad row can never be stored.
    if (isset($in['pref_watch_post'])) {
        if ($in['pref_watch_post'] === null) {
            $cleaned['pref_watch_post'] = null;
        } elseif (is_array($in['pref_watch_post'])) {
            $watch = $in['pref_watch_post'];
            if (!isset($watch['link']) || !prf_is_link($watch['link'])) {
                return [null, 'pref_watch_post.link must be a link, or null.'];
            }
            $cleaned_watch = ['link' => trim($watch['link'])];
            if (isset($watch['below'])) {
                if (!prf_is_int_value($watch['below'])) {
                    return [null, 'pref_watch_post.below must be an integer, or null.'];
                }
                $below = (int)$watch['below'];
                if ($below < 1 || $below > 100000000) {
                    return [null, 'pref_watch_post.below must be between 1 and 100000000, or null.'];
                }
                $cleaned_watch['below'] = $below;
            }
            $cleaned['pref_watch_post'] = $cleaned_watch;
        } else {
            return [null, 'pref_watch_post must be an object, or null.'];
        }
    }
    // pref_wait_price (#33): {platform, metric, target}. Remembered
    // only, same as #30.
    if (isset($in['pref_wait_price'])) {
        if ($in['pref_wait_price'] === null) {
            $cleaned['pref_wait_price'] = null;
        } elseif (is_array($in['pref_wait_price'])) {
            $wait = $in['pref_wait_price'];
            if (!isset($wait['platform']) || !prf_is_slug($wait['platform'])) {
                return [null, 'pref_wait_price.platform must be a lowercase slug, or null.'];
            }
            if (!isset($wait['metric']) || !prf_is_slug($wait['metric'])) {
                return [null, 'pref_wait_price.metric must be a lowercase slug, or null.'];
            }
            if (!isset($wait['target']) || !is_numeric($wait['target'])) {
                return [null, 'pref_wait_price.target must be a number, or null.'];
            }
            $target = (float)$wait['target'];
            if ($target <= 0 || $target > 100000) {
                return [null, 'pref_wait_price.target must be between 0 and 100000, or null.'];
            }
            $cleaned['pref_wait_price'] = [
                'platform' => $wait['platform'],
                'metric' => $wait['metric'],
                'target' => $target,
            ];
        } else {
            return [null, 'pref_wait_price must be an object, or null.'];
        }
    }
    return [$cleaned, null];
}

function prf_decode($json) {
    $decoded = json_decode((string)$json, true);
    return is_array($decoded) ? $decoded : [];
}

function prf_load_row($db, $telegram_id) {
    $stmt = $db->prepare('SELECT traits, updated_at FROM bot_user_traits WHERE telegram_id = ? LIMIT 1');
    $stmt->bind_param('i', $telegram_id);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    $stmt->close();
    return $row ?: null;
}

// The stored row mixes learned traits and explicit prefs under
// different keys. These two helpers are the only place the prf_
// prefix is applied / stripped, so the bot only ever sees its own
// pref_* names and the traits file never sees a prf_ key.
function prf_strip_prefix($stored) {
    $prefs = [];
    foreach ((array)$stored as $key => $value) {
        if (strpos($key, 'prf_') === 0) {
            $prefs['pref_' . substr($key, 4)] = $value;
        }
    }
    return $prefs;
}

function prf_add_prefix($prefs) {
    $stored = [];
    foreach ((array)$prefs as $key => $value) {
        $stored['prf_' . substr($key, 5)] = $value;
    }
    return $stored;
}

// --- POST /api/bot/user-prefs ------------------------------------------------
// Merge-upsert, exactly like /user-traits: only the fields present
// in the request change. A field sent as null is removed; a field
// not sent is untouched. This statement touches bot_user_traits
// ONLY — and within the row, only prf_ keys. The learned traits
// (tone, usual_*, last_deposit_method) are loaded, carried through
// the merge untouched, and written back unchanged.

function bot_prf_save() {
    $in = prf_json_body();
    $telegram_id = (int)($in['telegram_id'] ?? 0);
    if ($telegram_id <= 0) prf_fail(400, 'telegram_id is required.');
    $prefs_in = $in['prefs'] ?? null;
    if (!is_array($prefs_in)) prf_fail(400, 'prefs must be an object.');
    list($cleaned, $error) = prf_validate_prefs($prefs_in);
    if ($error !== null) prf_fail(400, $error);

    $db = prf_db();
    if ($db === null) prf_fail(500, 'Database is not available.');
    prf_ensure_table($db);

    // Merge with what is already stored ({} when this is the first save).
    $existing = prf_load_row($db, $telegram_id);
    $merged = $existing ? prf_decode($existing['traits']) : [];
    $prefixed = prf_add_prefix($cleaned);
    foreach ($prefixed as $key => $value) {
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
        prf_fail(500, 'Could not save the prefs.');
    }
    $stmt->close();
    $row = prf_load_row($db, $telegram_id);
    bot_ok(['ok' => true, 'prefs' => prf_strip_prefix($merged), 'updated_at' => $row ? $row['updated_at'] : null]);
}

// --- GET /api/bot/user-prefs?telegram_id=X -----------------------------------

function bot_prf_load() {
    $telegram_id = (int)($_GET['telegram_id'] ?? 0);
    if ($telegram_id <= 0) prf_fail(400, 'telegram_id is required.');
    $db = prf_db();
    if ($db === null) prf_fail(500, 'Database is not available.');
    prf_ensure_table($db);
    $row = prf_load_row($db, $telegram_id);
    if (!$row) {
        // No prefs stored yet — a 200 with prefs:null, NOT a 404.
        // (A 404 means the endpoint is not installed; the bot treats
        // both as "nothing set yet".)
        bot_ok(['prefs' => null]);
        return;
    }
    $prefs = prf_strip_prefix(prf_decode($row['traits']));
    bot_ok(['prefs' => empty($prefs) ? null : $prefs, 'updated_at' => $row['updated_at']]);
}

// ============================================================================
// DISPATCH — insert these lines in bot.php BEFORE the 404 fallback:
//   $bp = $_GET['bot_path'] ?? '';
//   if ($bp === 'user-prefs' && $_SERVER['REQUEST_METHOD'] === 'POST') { bot_prf_save(); }
//   if ($bp === 'user-prefs' && $_SERVER['REQUEST_METHOD'] === 'GET') { bot_prf_load(); }
//   (Add the same bot_rate_limit(...) call the other user endpoints
//    use to each dispatch line — copy the exact call from the orders
//    handler; the signature was not visible from outside the server.)
//
// php -l NOTE: php is NOT installed in this offline workspace, so this
// file could NOT be linted here. Run `php -l api-user-prefs.php` on
// the server (step 1 of the install) and `php -l api/bot.php` after
// splicing (step 3) — both must pass before anything goes live.
//
// LIVE CURL TEST (uses telegram_id 779060335, the operating account —
// no money moves, these endpoints never touch balances or orders):
//   SECRET=$(php -r 'require "config_secret.php"; echo BOT_API_SECRET;')
//   # 1. no prefs yet -> prefs:null (200, NOT 404):
//   curl -s "https://paxyo.et/api/bot/user-prefs?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"prefs":null}
//   # 2. save two prefs (merge — only these two fields are stored):
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_pick_order":"cheapest","pref_ask_first":true}}'
//   -> expect {"success":true,"ok":true,"prefs":{"pref_pick_order":"cheapest","pref_ask_first":true},"updated_at":"..."}
//   # 3. load them back:
//   curl -s "https://paxyo.et/api/bot/user-prefs?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"prefs":{"pref_pick_order":"cheapest","pref_ask_first":true},"updated_at":"..."}
//   # 4. merge: add a third pref, and prove the first two SURVIVE:
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_quiet_hours":{"start":"22:00","end":"07:00"}}}'
//   -> expect {"success":true,"ok":true,"prefs":{"pref_pick_order":"cheapest","pref_ask_first":true,"pref_quiet_hours":{"start":"22:00","end":"07:00"}},"updated_at":"..."}
//   # 5. clear one pref with null, and prove the others SURVIVE:
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_ask_first":null}}'
//   -> expect {"success":true,"ok":true,"prefs":{"pref_pick_order":"cheapest","pref_quiet_hours":{"start":"22:00","end":"07:00"}},"updated_at":"..."}
//   # 6. invalid value -> 400, nothing stored/changed:
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_pick_order":"random"}}'
//   -> expect {"success":false,"error":"pref_pick_order must be \"fastest\" or \"cheapest\", or null.",...}
//   # 6b. a cap above 100 -> 400, nothing stored/changed:
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_no_confirm_max_etb":500}}'
//   -> expect {"success":false,"error":"pref_no_confirm_max_etb must be between 1 and 100, or null.",...}
//   # 6c. a new key saves, a bad new key -> 400:
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_favourite_services":["5535","6001"],"pref_language":"am"}}'
//   -> expect {"success":true,"ok":true,"prefs":{...,"pref_favourite_services":["5535","6001"],"pref_language":"am",...},"updated_at":"..."}
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_favourite_services":["abc"]}}'
//   -> expect {"success":false,"error":"pref_favourite_services must be a list of 1..20 service ids, or null.",...}
//   # 7. unknown field -> dropped, save still succeeds:
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_favourite_colour":"blue"}}'
//   -> expect {"success":true,"ok":true,"prefs":{"pref_pick_order":"cheapest","pref_quiet_hours":{"start":"22:00","end":"07:00"}},"updated_at":"..."}
//   # 8. traits untouched: save a LEARNED trait through /user-traits
//   #    and prove the prefs SURVIVE the merge (and vice versa —
//   #    step 4 already proved a prefs save keeps the traits):
//   curl -s -X POST https://paxyo.et/api/bot/user-traits \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"traits":{"tone":"brief"}}'
//   -> expect {"success":true,"ok":true,"traits":{"tone":"brief"},"updated_at":"..."}
//   curl -s "https://paxyo.et/api/bot/user-prefs?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"prefs":{"pref_pick_order":"cheapest","pref_quiet_hours":{"start":"22:00","end":"07:00"}},"updated_at":"..."}
//   # 9. clear the prefs (delete the row's prf_ keys — the traits
//   #    stay; there is no separate clear endpoint, a null per key
//   #    clears one pref at a time — include the keys step 6c saved):
//   curl -s -X POST https://paxyo.et/api/bot/user-prefs \
//     -H "X-Bot-Secret: $SECRET" -H 'Content-Type: application/json' \
//     -d '{"telegram_id":779060335,"prefs":{"pref_pick_order":null,"pref_quiet_hours":null,"pref_favourite_services":null,"pref_language":null}}'
//   -> expect {"success":true,"ok":true,"prefs":{},"updated_at":"..."}
//   # 10. load again -> prefs:null (the row still holds the trait,
//   #    so the prefs read is empty):
//   curl -s "https://paxyo.et/api/bot/user-prefs?telegram_id=779060335" \
//     -H "X-Bot-Secret: $SECRET"
//   -> expect {"success":true,"prefs":null}
//   Then DELETE the test row (belt and braces — step 9 cleared the
//   prefs, step 8's trait is still there; remove the whole row only
//   if the operating account has no traits worth keeping):
//   mysql -e "DELETE FROM bot_user_traits WHERE telegram_id=779060335;"
//   (use the same MySQL credentials db.php uses; never print them.
//   Only delete the row when the account's stored traits are test
//   data — never delete a real user's row.)
// ============================================================================
