"""Offline tests for targeted-broadcast audience selection (admin panel).

What this file pins — and what it does NOT do
------------------------------------------------
It pins the SELECTION RULES of the audience endpoint
(server/api-admin-broadcasts.php, the authoritative audience
contract), re-implemented here in plain Python against fixture
data, so the rules can be checked without a live database:

  * all             — every user in auth (every tg_id).
  * never_deposited — auth users with NO *completed* deposit.
                      A pending or failed deposit is not a deposit.
  * deposited       — users with at least one *completed* deposit.
                      A deposit row with no matching auth row still
                      counts (its user_id IS a Telegram id).
  * service         — users who ordered a given service at least
                      once. DISTINCT telegram_ids: a user who
                      ordered it twice counts ONCE; a user who never
                      ordered it is never included.

The SQL this mirrors (api-admin-broadcasts.php):
  all:             SELECT DISTINCT tg_id FROM auth
  deposited:       SELECT DISTINCT user_id FROM deposits
                     WHERE status = 'completed'
  never_deposited: SELECT DISTINCT a.tg_id FROM auth a
                     WHERE NOT EXISTS (SELECT 1 FROM deposits d
                       WHERE d.user_id = a.tg_id
                         AND d.status = 'completed')
                   (NOT EXISTS, not NOT IN, so a NULL user_id in
                   deposits can never wipe the whole list.)
  service:         SELECT DISTINCT telegram_id FROM orders
                     WHERE <service column> = ?   (provider service id)

It does NOT test a live DB, the PHP endpoint, or any Telegram
send. Sending is bot-side / existing-Broadcasting-path only (see
server/admin-targeted-broadcasts.php header H1). The send gate
tested here is only the rule "count 0 (or an empty message) means
nothing is recorded or sent".

Run:  python3 -m pytest test_targeted_broadcasts_offline.py -q
  or: python3 test_targeted_broadcasts_offline.py
"""

import unittest

# ---------------------------------------------------------------------------
# Fixture data (mirrors the live tables' relevant columns only)
# ---------------------------------------------------------------------------

# auth.tg_id — every registered user. tg_id IS the Telegram id.
# 1005 is deliberately NOT here: that user has a completed deposit
# but no auth row (deposit-only user — see DEPOSITS).
AUTH_IDS = [1001, 1002, 1003, 1004, 1006]

# deposits: (user_id, status). user_id IS the telegram id.
#   1002 deposited (completed) and later had a pending one too.
#   1003 has only a PENDING deposit — not a depositor.
#   1004 has only a FAILED deposit — not a depositor.
#   1005 has a completed deposit but NO auth row (deposit-only user).
#   None row: a NULL user_id must never wipe never_deposited.
DEPOSITS = [
    (1002, "completed"),
    (1002, "pending"),
    (1003, "pending"),
    (1004, "failed"),
    (1005, "completed"),
    (None, "completed"),
]

# orders: (telegram_id, service_id) — provider service id.
#   1001 ordered 6139 twice (must count once) and 1665 once.
#   1002 ordered 6139 once.
#   1003 ordered only 1665 — never 6139.
#   1006 ordered 6139 once.
ORDERS = [
    (1001, 6139),
    (1001, 6139),
    (1001, 1665),
    (1002, 6139),
    (1003, 1665),
    (1006, 6139),
]

# Catalogue rows the service picker searches (id, name, price ETB/1000).
SERVICES = [
    {"id": 6139, "name": "Telegram Post Views | Max 100K | Instant Start", "price": 1.05},
    {"id": 1665, "name": "TikTok Video Views | Fast", "price": 1.68},
    {"id": 1104, "name": "TikTok Followers | Real", "price": 172.20},
    {"id": 5535, "name": "TikTok Video Views | Cheapest", "price": 1.85},
]


# ---------------------------------------------------------------------------
# Mirror of the endpoint's selection rules (pure Python, fixture data)
# ---------------------------------------------------------------------------

def resolve_audience(segment, service_id=None, auth_ids=None,
                     deposits=None, orders=None):
    """Return the sorted list of DISTINCT telegram ids for a segment.

    Raises ValueError for an unknown segment, or for the service
    segment without a valid service_id — the endpoint answers 400
    for both, never 500.
    """
    auth_ids = list(auth_ids if auth_ids is not None else AUTH_IDS)
    deposits = list(deposits if deposits is not None else DEPOSITS)
    orders = list(orders if orders is not None else ORDERS)

    valid = ("all", "never_deposited", "deposited", "service")
    if segment not in valid:
        raise ValueError("segment must be all, never_deposited, deposited or service.")
    if segment == "service":
        if service_id is None or int(service_id) <= 0:
            raise ValueError("service_id is required for the service segment.")

    # Completed deposits only — pending/failed are not deposits.
    # NULL user_ids are ignored (the SQL uses NOT EXISTS, not NOT IN).
    completed = {uid for (uid, status) in deposits
                 if status == "completed" and uid is not None}

    if segment == "all":
        ids = set(auth_ids)
    elif segment == "deposited":
        ids = set(completed)
    elif segment == "never_deposited":
        ids = {uid for uid in auth_ids if uid not in completed}
    else:  # service — DISTINCT telegram_id, ordered twice counts once.
        ids = {tid for (tid, sid) in orders if sid == int(service_id)}
    return sorted(ids)


def strip_ids_for_browser(audience_response):
    """What the admin page sends to the browser: the count only.

    The endpoint returns telegram_ids; this page must never forward
    them — the admin sees how many users match, never a list of
    other users' ids. Mirrors tb_audience_count() in
    admin-targeted-broadcasts.php.
    """
    return {
        "segment": audience_response["segment"],
        "service_id": audience_response.get("service_id"),
        "count": len(audience_response["telegram_ids"]),
    }


def send_gate(count, message):
    """May this broadcast be recorded/sent? (count, message) -> (bool, reason).

    Count 0 means nobody matches: nothing is recorded, nothing is
    sent. An empty message is refused the same way.
    """
    if not message or not message.strip():
        return False, "Write the message."
    if count <= 0:
        return False, "Nobody matches this audience — nothing sent."
    return True, ""


def search_services(query, services=None):
    """Service-picker search: by id (exact first, then substring)
    or by name substring (case-insensitive). Top 20. Mirrors
    tb_service_search() in admin-targeted-broadcasts.php.
    """
    services = list(services if services is not None else SERVICES)
    q = (query or "").strip()
    if not q:
        return []
    hits = []
    for s in services:
        if q.isdigit():
            if str(s["id"]) == q:
                hits.append((0, s))
                continue
            if q in str(s["id"]):
                hits.append((1, s))
                continue
        if q.lower() in s["name"].lower():
            hits.append((1, s))
    hits.sort(key=lambda t: (t[0], t[1]["id"]))
    return [s for (_, s) in hits[:20]]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAudienceAll(unittest.TestCase):
    def test_all_returns_every_auth_user(self):
        self.assertEqual(resolve_audience("all"), [1001, 1002, 1003, 1004, 1006])

    def test_all_excludes_deposit_only_user_with_no_auth_row(self):
        # 1005 has a completed deposit but no auth row: in `deposited`
        # but NOT in `all` (the endpoint reads `all` from auth only).
        self.assertNotIn(1005, resolve_audience("all"))


class TestAudienceDeposited(unittest.TestCase):
    def test_deposited_only_completed(self):
        # 1003 (pending only) and 1004 (failed only) are NOT depositors.
        self.assertEqual(resolve_audience("deposited"), [1002, 1005])

    def test_deposit_only_user_counts_as_deposited(self):
        self.assertIn(1005, resolve_audience("deposited"))

    def test_pending_and_failed_do_not_count(self):
        self.assertNotIn(1003, resolve_audience("deposited"))
        self.assertNotIn(1004, resolve_audience("deposited"))


class TestAudienceNeverDeposited(unittest.TestCase):
    def test_never_deposited_excludes_depositors(self):
        # 1002 has a completed deposit (plus a pending one) — out.
        self.assertEqual(resolve_audience("never_deposited"), [1001, 1003, 1004, 1006])

    def test_pending_only_user_is_never_deposited(self):
        self.assertIn(1003, resolve_audience("never_deposited"))

    def test_failed_only_user_is_never_deposited(self):
        self.assertIn(1004, resolve_audience("never_deposited"))

    def test_null_deposit_user_id_does_not_wipe_the_list(self):
        # A NULL user_id in deposits must not empty never_deposited
        # (the SQL uses NOT EXISTS, not NOT IN).
        self.assertEqual(len(resolve_audience("never_deposited")), 4)

    def test_deposited_plus_never_deposited_covers_all_auth_users(self):
        # Every auth user either has a completed deposit or does not.
        # (1005 is deposited-only, so it is in neither auth-side list.)
        combined = sorted(set(resolve_audience("deposited")) |
                          set(resolve_audience("never_deposited")))
        self.assertEqual([u for u in combined if u in AUTH_IDS], AUTH_IDS)


class TestAudienceService(unittest.TestCase):
    def test_service_returns_only_buyers_of_that_service(self):
        self.assertEqual(resolve_audience("service", 6139), [1001, 1002, 1006])

    def test_user_who_ordered_twice_counts_once(self):
        # 1001 ordered 6139 twice — appears exactly once.
        ids = resolve_audience("service", 6139)
        self.assertEqual(ids.count(1001), 1)

    def test_user_who_never_ordered_it_is_excluded(self):
        # 1003 ordered only 1665 — never 6139.
        self.assertNotIn(1003, resolve_audience("service", 6139))

    def test_user_who_ordered_another_service_only_is_excluded(self):
        self.assertEqual(resolve_audience("service", 1665), [1001, 1003])

    def test_service_nobody_ordered_is_empty(self):
        self.assertEqual(resolve_audience("service", 999999), [])

    def test_service_without_id_is_an_error(self):
        with self.assertRaises(ValueError):
            resolve_audience("service")
        with self.assertRaises(ValueError):
            resolve_audience("service", 0)

    def test_unknown_segment_is_an_error(self):
        with self.assertRaises(ValueError):
            resolve_audience("bogus")


class TestCountOnlyToBrowser(unittest.TestCase):
    def test_browser_payload_has_count_but_no_ids(self):
        response = {"segment": "service", "service_id": 6139,
                    "count": 3, "telegram_ids": [1001, 1002, 1006]}
        payload = strip_ids_for_browser(response)
        self.assertEqual(payload, {"segment": "service", "service_id": 6139, "count": 3})
        self.assertNotIn("telegram_ids", payload)


class TestSendGate(unittest.TestCase):
    def test_empty_audience_means_no_send(self):
        allowed, reason = send_gate(0, "Hello")
        self.assertFalse(allowed)
        self.assertIn("Nobody matches", reason)

    def test_empty_message_means_no_send(self):
        allowed, _ = send_gate(42, "   ")
        self.assertFalse(allowed)

    def test_nonempty_audience_and_message_may_send(self):
        allowed, reason = send_gate(3, "Hello")
        self.assertTrue(allowed)
        self.assertEqual(reason, "")


class TestServicePickerSearch(unittest.TestCase):
    def test_search_by_exact_id(self):
        self.assertEqual([s["id"] for s in search_services("6139")], [6139])

    def test_search_by_name_substring(self):
        # Contiguous substring: "TikTok Video Views" contains it.
        ids = [s["id"] for s in search_services("tiktok video views")]
        self.assertEqual(ids, [1665, 5535])

    def test_search_by_name_case_insensitive(self):
        self.assertEqual([s["id"] for s in search_services("TELEGRAM post")], [6139])

    def test_search_no_match_is_empty(self):
        self.assertEqual(search_services("zzz-no-such-service"), [])

    def test_search_empty_query_is_empty(self):
        self.assertEqual(search_services(""), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
