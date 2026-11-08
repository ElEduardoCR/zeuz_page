# Stripe integration — 8 November 2026

Scope: official ZEUZ storefront only, Mexico shipping, MXN, hosted Stripe Checkout. Existing catalog prices, IVA and shipping preserved and editable. Mercado Libre listing is a separate future task.

## Verification

- 35 Python tests cover strict cart validation, server prices, changed quotes, concurrent attempts, idempotency, signed webhooks, amount/currency/session checks, protected payment states, private order responses and explicit PostgreSQL driver selection.
- 14 checkout and 12 receipt JavaScript tests cover network retries, changed prices, cross-tab cart changes, double clicks, validated redirects and safe cart cleanup after a confirmed payment.
- Completed a real Stripe sandbox Checkout from the local storefront, using fictitious contact/address information and Stripe's test card. The MXN total was 894884 cents (device 869884 + shipping 25000). Stripe confirmed the payment and the application showed the confirmed test receipt. No real charge or email was sent.
- Checkout verified at 390px. Summary appears before contact fields on mobile; order references wrap without horizontal overflow.
- Existing production database recovered successfully. Orders were empty before provisioning. Added `checkout_attempts`, enabled RLS and revoked browser-role access to both tables.
- Runtime uses a dedicated `zeuz_shop_app` login with SELECT/INSERT/UPDATE on the two tables and explicit backend-only RLS policies. It cannot DELETE or CREATE tables. Client-to-pooler TLS verified.
- Production credentials are stored as sensitive Vercel variables; live credentials are not shared with preview deployments or committed to Git.

## Operational limits

Stock is validated against the editable catalog per cart. This integration does not reserve or automatically decrement warehouse stock across independent purchases.

## Production delivery

The first delivery exposed a runtime dependency difference: a newer SQLAlchemy selected psycopg v3 while the installed driver was psycopg2. Fixed by selecting `postgresql+psycopg2` explicitly and constraining SQLAlchemy below 2.1; added a regression test.

After the fix, created and immediately expired a live Checkout session without entering payment information or charging a card. Stripe delivered its signed `checkout.session.expired` event to `https://www.zeuzdnc.com/webhook/stripe`; the deployed application changed its matching persistent order from pending to cancelled. The production payment switch was enabled only after this delivery check passed.
