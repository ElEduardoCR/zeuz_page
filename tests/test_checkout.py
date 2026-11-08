"""Contrato de compra y eventos: SQLite aislada, Stripe simulado, sin .env."""
import copy
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select, func
from test_storefront import storefront


def product():
    return {"id": "device", "name": "ZEUZ de prueba", "short": "Prueba", "stock": 10,
            "price": {"net": 100.0, "tax": 16.0, "gross": 116.0, "currency": "MXN"}}


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_engine, self.old_ready = storefront.db._engine, storefront.db._ready
        storefront.db._engine = create_engine("sqlite:///" + str(Path(self.temp.name) / "test.db"),
            connect_args={"check_same_thread": False, "timeout": 10})
        self.assertTrue(storefront.db.init_db())
        self.old_secret = storefront.app.secret_key
        storefront.app.secret_key = "test-fixture-session-secret-32-characters"
        storefront.app.config.update(TESTING=True, PAYMENTS_ENABLED=True)
        self.client = storefront.app.test_client()
        self.products = [product()]
        self.patches = [
            patch.object(storefront.catalog, "all_products", side_effect=lambda region: copy.deepcopy(self.products)),
            patch.object(storefront.payments_stripe, "is_configured", return_value=True),
            patch.object(storefront.payments_stripe, "payment_mode", return_value="test"),
            patch.object(storefront.db, "is_persistent", return_value=True),
            patch.object(storefront, "_start_stripe", side_effect=lambda oid, *args: {
                "ref": "cs_test_" + oid, "url": "https://checkout.stripe.com/c/pay/" + oid,
                "expires_at": int(time.time()) + 3600}),
            patch.object(storefront.notifications, "notify_paid_order", return_value=True),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.start_stripe = self.mocks[-2]
        self.notify = self.mocks[-1]
        self.cart = [{"id": "device", "qty": 1}]

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        storefront.app.secret_key = self.old_secret
        storefront.app.config["PAYMENTS_ENABLED"] = False
        storefront.db._engine.dispose()
        storefront.db._engine, storefront.db._ready = self.old_engine, self.old_ready
        self.temp.cleanup()

    def quote(self, cart=None, client=None):
        return (client or self.client).post("/api/quote", json={"cart": self.cart if cart is None else cart})

    def payload(self):
        quote = self.quote()
        self.assertEqual(quote.status_code, 200)
        return {"cart": self.cart, "quote_token": quote.json["quote_token"],
                "attempt_id": str(uuid.uuid4()), "customer": {"name": "Cliente Prueba", "email": "test@example.com"}}

    def checkout(self, payload=None):
        return self.client.post("/api/checkout", json=payload or self.payload())

    def event(self, order_id, event_type="checkout.session.completed", **changes):
        order = storefront.orders.get_order(order_id)
        attempt = storefront.orders.get_order_attempt(order_id)
        obj = {"id": order["gateway_ref"], "object": "checkout.session", "mode": "payment", "status": "complete",
               "payment_status": "paid", "payment_intent": "pi_test_fixture", "client_reference_id": order_id,
               "metadata": {"order_id": order_id, "attempt_id": attempt["attempt_id"], "region": "MX"},
               "amount_total": order["total_cents"], "currency": "mxn", "livemode": False,
               "collected_information": {"shipping_details": {"address": {
                   "line1": "Calle de prueba 1", "line2": "", "city": "Chihuahua", "state": "CHH", "postal_code": "31000", "country": "MX"}}}}
        obj.update(changes)
        return {"id": "evt_" + uuid.uuid4().hex, "object": "event", "type": event_type, "data": {"object": obj}}

    def webhook(self, event):
        with patch.object(storefront.payments_stripe, "verify_webhook", return_value=event):
            return self.client.post("/webhook/stripe", data=b"fixture", content_type="application/json")

    def test_quote_uses_server_prices_and_aggregates_duplicates(self):
        response = self.quote([{"id": "device", "qty": 2, "price": 0.01}, {"id": "device", "qty": 3}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["items"][0]["qty"], 5)
        self.assertEqual(response.json["items"][0]["line_gross_cents"], 58000)
        self.assertEqual(response.json["totals"]["total"], 830)
        self.assertRegex(response.json["quote_token"], r"^[0-9a-f]{64}$")

    def test_malformed_quantities_products_and_cart_are_rejected(self):
        cases = [None, {}, "device", [None], [{"id": "unknown", "qty": 1}],
                 [{"id": "device", "qty": 1}] * 101]
        cases += [[{"id": "device", "qty": value}] for value in (0, -1, 1.1, True, "2", None, 100)]
        for cart in cases:
            with self.subTest(cart=cart):
                response = self.client.post("/api/quote", json={"cart": cart})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/api/quote", data='{"cart":[]}').status_code, 400)
        self.assertEqual(self.client.post("/api/quote", json=[]).status_code, 400)

    def test_stock_is_checked_after_duplicate_aggregation(self):
        response = self.quote([{"id": "device", "qty": 6}, {"id": "device", "qty": 6}])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["code"], "stock_unavailable")
        self.products[0]["stock"] = 0
        self.assertEqual(self.quote().status_code, 409)

    def test_price_precision_does_not_differ_from_stripe_line_amounts(self):
        self.products[0]["price"].update(net=8900.005, tax=1424.0, gross=10324.01)
        response = self.quote([{"id": "device", "qty": 2}])
        self.assertEqual(response.status_code, 200)
        expected_cents = sum(item["unit_gross_cents"] * item["qty"] for item in response.json["items"])
        expected_cents += round(response.json["totals"]["shipping"] * 100)
        self.assertEqual(round(response.json["totals"]["total"] * 100), expected_cents)

    def test_quote_and_checkout_reject_other_countries_currencies_and_gateways(self):
        for extras in ({"region": "US"}, {"country": "US"}, {"currency": "USD"}, {"gateway": "mercadopago"}):
            for endpoint in ("/api/quote", "/api/checkout"):
                response = self.client.post(endpoint, json={"cart": self.cart, **extras})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/api/quote?region=US", json={"cart": self.cart}).status_code, 400)
        self.assertEqual(self.client.get("/region/US").status_code, 404)
        self.assertEqual(self.client.post("/webhook/mp").status_code, 410)
        self.start_stripe.assert_not_called()

    def test_changed_price_requires_quote_refresh_before_any_order(self):
        payload = self.payload()
        self.products[0]["price"].update(net=200.0, tax=32.0, gross=232.0)
        response = self.checkout(payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["code"], "quote_changed")
        self.start_stripe.assert_not_called()
        self.assertEqual(storefront.orders.list_orders(), [])

    def test_customer_attempt_and_cookie_validation(self):
        payload = self.payload()
        for customer in ({}, {"name": "A", "email": "bad"}, {"name": [], "email": "test@example.com"},
                         {"name": "A", "email": "test@example.com", "country": "US"}):
            response = self.checkout({**payload, "customer": customer})
            self.assertEqual(response.status_code, 400)
        for attempt in (None, "bad", str(uuid.uuid1()), 2):
            self.assertEqual(self.checkout({**payload, "attempt_id": attempt}).status_code, 400)
        response = storefront.app.test_client().post("/api/checkout", json=payload)
        self.assertEqual(response.json["code"], "cookies_required")
        self.start_stripe.assert_not_called()

    def test_same_attempt_creates_one_order_and_one_session(self):
        payload = self.payload()
        first, second = self.checkout(payload), self.checkout(payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json, second.json)
        self.assertEqual(len(storefront.orders.list_orders()), 1)
        self.start_stripe.assert_called_once()
        self.assertEqual(self.start_stripe.call_args.args[-1], payload["attempt_id"])

    def test_network_failure_preserves_attempt_and_pending_order_for_retry(self):
        payload = self.payload()
        real_side_effect = self.start_stripe.side_effect
        self.start_stripe.side_effect = RuntimeError("network")
        self.assertEqual(self.checkout(payload).status_code, 503)
        order_id = storefront.orders.list_orders()[0]["id"]
        self.assertEqual(storefront.orders.get_order(order_id)["status"], "pending")
        self.start_stripe.side_effect = real_side_effect
        response = self.checkout(payload)
        self.assertEqual(response.json["order_id"], order_id)
        self.assertEqual(len(storefront.orders.list_orders()), 1)

    def test_attempt_cannot_be_reused_for_other_contact_or_other_shopper(self):
        payload = self.payload()
        self.assertEqual(self.checkout(payload).status_code, 200)
        self.assertEqual(self.checkout({**payload, "customer": {"name": "Otro", "email": "other@example.com"}}).json["code"], "attempt_conflict")
        other = storefront.app.test_client()
        self.quote(client=other)
        self.assertEqual(other.post("/api/checkout", json=payload).json["code"], "attempt_conflict")
        self.assertEqual(len(storefront.orders.list_orders()), 1)

    def test_expired_attempt_does_not_create_a_second_stripe_session(self):
        payload = self.payload()
        response = self.checkout(payload)
        with storefront.db.get_engine().begin() as conn:
            conn.execute(storefront.db.checkout_attempts.update().values(session_expires_at=1))
        self.assertEqual(self.checkout(payload).json["code"], "attempt_expired")
        self.start_stripe.assert_called_once()

    def test_paid_attempt_returns_owned_receipt_instead_of_new_checkout(self):
        payload = self.payload()
        order_id = self.checkout(payload).json["order_id"]
        self.webhook(self.event(order_id))
        result = self.checkout(payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["receipt_url"], "/pago/exito?order=" + order_id)
        self.assertNotIn("redirect_url", result.json)
        self.start_stripe.assert_called_once()

    def test_order_status_and_return_pages_require_browser_ownership(self):
        response = self.checkout()
        order_id = response.json["order_id"]
        mine = self.client.get("/api/order/" + order_id)
        self.assertEqual(mine.status_code, 200)
        self.assertNotIn("customer_email", mine.json["order"])
        self.assertNotIn("ship_line1", mine.json["order"])
        self.assertEqual(mine.json["order"]["payment_mode"], "test")
        other = storefront.app.test_client()
        self.assertEqual(other.get("/api/order/" + order_id).status_code, 404)
        page = other.get("/pago/exito?order=" + order_id)
        self.assertNotIn(order_id, page.text)
        self.assertNotIn("test@example.com", page.text)
        self.assertIn("no-store", page.headers["Cache-Control"])

    def test_return_does_not_reconcile_unrelated_session(self):
        order_id = self.checkout().json["order_id"]
        with patch.object(storefront.payments_stripe, "get_session") as get_session:
            self.client.get("/pago/exito?order=" + order_id + "&session_id=cs_unrelated")
            get_session.assert_not_called()
        self.assertEqual(storefront.orders.get_order(order_id)["status"], "pending")

    def test_duplicate_and_late_webhooks_do_not_downgrade_or_notify_twice(self):
        order_id = self.checkout().json["order_id"]
        paid = self.event(order_id)
        self.assertEqual(self.webhook(paid).status_code, 200)
        self.assertEqual(self.webhook(paid).status_code, 200)
        for event_type in ("checkout.session.expired", "checkout.session.async_payment_failed"):
            self.assertEqual(self.webhook(self.event(order_id, event_type, payment_status="unpaid")).status_code, 200)
        self.assertEqual(storefront.orders.get_order(order_id)["status"], "paid")
        self.notify.assert_called_once()
        for protected in ("shipped", "refunded"):
            storefront.orders.update_order(order_id, status=protected)
            self.webhook(paid)
            self.webhook(self.event(order_id, "checkout.session.expired"))
            self.assertEqual(storefront.orders.get_order(order_id)["status"], protected)
        self.notify.assert_called_once()

    def test_unpaid_completion_waits_until_async_payment_is_paid(self):
        order_id = self.checkout().json["order_id"]
        self.webhook(self.event(order_id, payment_status="unpaid"))
        self.assertEqual(storefront.orders.get_order(order_id)["status"], "pending_payment")
        self.notify.assert_not_called()
        self.webhook(self.event(order_id, "checkout.session.async_payment_succeeded"))
        self.assertEqual(storefront.orders.get_order(order_id)["status"], "paid")
        self.notify.assert_called_once()

    def test_webhook_rejects_tampered_identity_amount_currency_mode_or_country(self):
        order_id = self.checkout().json["order_id"]
        for changes in ({"id": "cs_other"}, {"currency": "usd"}, {"amount_total": 1}, {"amount_total": True},
                        {"livemode": True}, {"metadata": {"order_id": order_id}}, {"mode": "subscription"},
                        {"collected_information": {"shipping_details": {"address": {"country": "US", "line1": "x"}}}}):
            with self.subTest(changes=changes):
                self.assertEqual(self.webhook(self.event(order_id, **changes)).status_code, 400)
        self.assertEqual(storefront.orders.get_order(order_id)["status"], "pending")
        self.notify.assert_not_called()

    def test_concurrent_paid_events_have_only_one_notification(self):
        order_id = self.checkout().json["order_id"]
        event = self.event(order_id)["data"]["object"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: storefront._apply_stripe_paid(order_id, event), range(4)))
        self.assertEqual(results.count(True), 1)
        self.notify.assert_called_once()

    def test_concurrent_attempt_claims_share_one_order(self):
        items, totals = storefront.price_cart(self.cart, storefront.catalog.get_region("MX"))
        kwargs = dict(region="MX", currency="MXN", gateway="stripe", items=items,
                      customer={"name": "Test", "email": "test@example.com"},
                      subtotal_net=totals["subtotal_net"], tax=totals["tax"], shipping=totals["shipping"], total=totals["total"],
                      attempt={"attempt_id": str(uuid.uuid4()), "payload_hash": "a" * 64, "owner_hash": "b" * 64, "payment_mode": "test"})
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _: storefront.orders.create_order(**kwargs), range(4)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(storefront.orders.list_orders()), 1)

    def test_signed_webhook_rejects_bad_signature_and_accepts_raw_body(self):
        order_id = self.checkout().json["order_id"]
        payload = json.dumps(self.event(order_id), separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        key = "whsec_fixture_not_a_real_secret"
        digest = hmac.new(key.encode(), timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": key}):
            invalid = self.client.post("/webhook/stripe", data=payload, headers={"Stripe-Signature": "t=" + timestamp + ",v1=bad"})
            self.assertEqual(invalid.status_code, 400)
            valid = self.client.post("/webhook/stripe", data=payload, headers={"Stripe-Signature": "t=" + timestamp + ",v1=" + digest})
            self.assertEqual(valid.status_code, 200)
        self.assertEqual(storefront.orders.get_order(order_id)["status"], "paid")


class StripePayloadTests(unittest.TestCase):
    def test_hosted_checkout_is_mxn_only_and_uses_idempotency(self):
        stripe = MagicMock()
        stripe.StripeError = RuntimeError
        stripe.checkout.Session.create.return_value = SimpleNamespace(id="cs_test_fixture", url="https://checkout.stripe.com/test", expires_at=123)
        with patch.object(storefront.payments_stripe, "_client", return_value=stripe):
            result = storefront.payments_stripe.create_checkout_session(
                items=[{"name": "ZEUZ", "description": "", "unit_gross_cents": 11600, "qty": 1}],
                order_id="order", currency="MXN", region="MX", shipping_cents=25000,
                success_url="https://example.com/success", cancel_url="https://example.com/cancel",
                customer_email="test@example.com", attempt_id="attempt")
        payload = stripe.checkout.Session.create.call_args.kwargs
        self.assertEqual(payload["idempotency_key"], "zeuz-checkout-attempt")
        self.assertEqual(payload["adaptive_pricing"], {"enabled": False})
        self.assertEqual(payload["shipping_address_collection"]["allowed_countries"], ["MX"])
        self.assertEqual(payload["line_items"][0]["price_data"]["currency"], "mxn")
        self.assertEqual(result["expires_at"], 123)

    def test_non_mexico_session_cannot_be_created(self):
        with patch.object(storefront.payments_stripe, "_client") as client:
            with self.assertRaises(RuntimeError):
                storefront.payments_stripe.create_checkout_session(items=[], order_id="x", currency="USD", region="US", shipping_cents=0,
                    success_url="", cancel_url="", customer_email="", attempt_id="x")
            client.assert_not_called()


class PersistenceTests(unittest.TestCase):
    def test_postgres_urls_select_installed_driver_without_changing_connection_parts(self):
        suffix = "fixture_user:p%40ss%2Fword@db.example.invalid:6543/fixture_db?sslmode=require&connect_timeout=5"
        for scheme, expected in (
            ("postgres://", "postgresql+psycopg2://"),
            ("postgresql://", "postgresql+psycopg2://"),
            ("postgresql+psycopg2://", "postgresql+psycopg2://"),
            ("postgresql+psycopg://", "postgresql+psycopg://"),
        ):
            with self.subTest(scheme=scheme), patch.dict(os.environ, {"DATABASE_URL": scheme + suffix}):
                self.assertEqual(storefront.db.database_url(), expected + suffix)
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}):
            self.assertEqual(storefront.db.database_url(), "sqlite:///:memory:")

    def test_real_engine_is_checked_instead_of_configured_url(self):
        original, ready = storefront.db._engine, storefront.db._ready
        try:
            storefront.db._ready = True
            for url in ("sqlite:///:memory:", "sqlite:////tmp/zeuz-fallback.db"):
                storefront.db._engine = create_engine(url)
                with patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake/unused"}):
                    self.assertFalse(storefront.db.is_persistent())
                storefront.db._engine.dispose()
            storefront.db._engine = create_engine("sqlite:////var/data/not-opened.db")
            with patch.dict(os.environ, {"VERCEL": "1"}):
                self.assertFalse(storefront.db.is_persistent())
            storefront.db._engine.dispose()
        finally:
            storefront.db._engine, storefront.db._ready = original, ready
