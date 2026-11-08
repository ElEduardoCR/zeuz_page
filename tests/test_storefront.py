"""Pruebas locales: sin credenciales, servicios externos ni pedidos reales."""
import os
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

# Importar la app inicializa la base; usa exclusivamente una SQLite en memoria
# y evita leer .env en este proceso de prueba.
with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:", "PAYMENTS_ENABLED": "false"}):
    with patch("dotenv.load_dotenv", return_value=False):
        import app as storefront


class PageElements(HTMLParser):
    """Inspecciona los controles reales, sin confundirlos con texto de scripts."""
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class StorefrontTests(unittest.TestCase):
    def setUp(self):
        self.client = storefront.app.test_client()
        storefront.app.config.update(TESTING=True, PAYMENTS_ENABLED=False)

    def test_checkout_is_closed_even_with_configured_gateways(self):
        with patch.object(storefront.payments_stripe, "is_configured", return_value=True), \
             patch.object(storefront.payments_mp, "is_configured", return_value=True), \
             patch.object(storefront.orders, "create_order") as create_order, \
             patch.object(storefront, "_start_stripe") as stripe, \
             patch.object(storefront, "_start_mercadopago") as mp:
            for gateway in ("stripe", "mercadopago"):
                response = self.client.post("/api/checkout", json={
                    "cart": [{"id": "zeuzdnc-touch", "qty": 1}],
                    "customer": {"name": "Prueba", "email": "test@example.com"},
                    "gateway": gateway,
                })
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json["code"], "payments_not_enabled")
            create_order.assert_not_called()
            stripe.assert_not_called()
            mp.assert_not_called()

    def test_disabled_store_context_has_no_payment_options(self):
        with storefront.app.test_request_context("/?region=MX"), \
             patch.object(storefront.payments_stripe, "is_configured", return_value=True), \
             patch.object(storefront.payments_mp, "is_configured", return_value=True):
            storefront.resolve_region()
            context = storefront.inject_globals()
            self.assertFalse(context["payments_enabled"])
            self.assertFalse(context["store"]["payments_enabled"])
            self.assertEqual(context["store"]["gateways"], [])

    def test_disabled_checkout_shows_summary_without_collecting_customer_data(self):
        for region in ("MX", "US"):
            with self.subTest(region=region):
                response = self.client.get("/checkout?region=" + region)
                self.assertEqual(response.status_code, 200)
                elements = PageElements(response.text).elements
                self.assertFalse(any(tag in {"form", "input", "textarea", "select"}
                                     for tag, attrs in elements))
                self.assertFalse(any(attrs.get("id") == "submit-btn"
                                     for tag, attrs in elements))
                self.assertTrue(any(attrs.get("id") == "checkout-items"
                                    for tag, attrs in elements))
                self.assertTrue(any(attrs.get("id") == "checkout-total"
                                    for tag, attrs in elements))
                self.assertIn("No se ha realizado ningún pedido ni cargo.", response.text)

    def test_home_presents_all_three_active_products(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        product_ids = [attrs["data-product-id"]
                       for tag, attrs in PageElements(response.text).elements
                       if tag == "article" and "data-product-id" in attrs]
        self.assertCountEqual(product_ids, ["zeuzdnc-touch", "zeuzdnc-headless", "izeuz-ios"])

    def test_download_page_links_to_both_downloads_and_their_checksums(self):
        response = self.client.get("/descargas")
        self.assertEqual(response.status_code, 200)
        links = {attrs.get("href") for tag, attrs in PageElements(response.text).elements if tag == "a"}
        for item in storefront.DOWNLOADS:
            self.assertIn("/descargas/" + item["id"], links)
            self.assertIn("/descargas/" + item["id"] + "/sha256", links)

    def test_product_pages_cart_and_legacy_links_render(self):
        for path in ("/carrito", "/producto/zeuzdnc-touch", "/producto/zeuzdnc-headless", "/producto/izeuz-ios"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        legacy = self.client.get("/producto/zeuzdnc-device")
        self.assertEqual(legacy.status_code, 301)
        self.assertTrue(legacy.headers["Location"].endswith("/producto/zeuzdnc-touch"))

    def test_future_opt_in_preserves_checkout_flow(self):
        storefront.app.config["PAYMENTS_ENABLED"] = True
        with patch.object(storefront.db, "is_persistent", return_value=True), \
             patch.object(storefront.payments_stripe, "is_configured", return_value=True), \
             patch.object(storefront.orders, "create_order", return_value="test-order"), \
             patch.object(storefront.orders, "update_order"), \
             patch.object(storefront, "_start_stripe", return_value={"ref": "test", "url": "https://example.com/test-checkout"}) as stripe:
            response = self.client.post("/api/checkout?region=US", json={
                "cart": [{"id": "zeuzdnc-touch", "qty": 1}],
                "customer": {"name": "Prueba", "email": "test@example.com"},
                "gateway": "stripe",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["redirect_url"], "https://example.com/test-checkout")
            stripe.assert_called_once()

    def test_quotes_still_work_and_ignore_client_prices(self):
        response = self.client.post("/api/quote?region=MX", json={
            "cart": [{"id": "zeuzdnc-touch", "qty": 2, "price": 0.01}]
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["currency"], "MXN")
        self.assertEqual(response.json["totals"]["total"], 20898)

    def test_both_downloads_redirect_to_their_published_assets(self):
        for item in storefront.DOWNLOADS:
            response = self.client.get("/descargas/" + item["id"])
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], item["download_url"])
            self.assertTrue(response.headers["Location"].startswith(
                "https://github.com/ElEduardoCR/zeuzagent/releases/download/"))

    def test_download_checksums_are_real_file_attachments(self):
        for item in storefront.DOWNLOADS:
            response = self.client.get("/descargas/" + item["id"] + "/sha256")
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment;", response.headers["Content-Disposition"])
            self.assertEqual(response.text, item["sha256"] + "  " + item["filename"] + "\n")

    def test_download_ids_cannot_redirect_or_expose_files(self):
        for path in ("/descargas/unknown", "/descargas/.env", "/descargas/unknown/sha256"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_store_alias_and_catalog_remain_available(self):
        for path in ("/tienda", "/catalogo", "/api/products", "/descargas"):
            self.assertEqual(self.client.get(path).status_code, 200)


if __name__ == "__main__":
    unittest.main()
