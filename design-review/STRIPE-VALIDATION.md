# Stripe integration — 8 November 2026

Scope: official ZEUZ storefront only, Mexico shipping, MXN, hosted Stripe Checkout. Existing catalog prices, IVA and shipping preserved and editable. Mercado Libre listing is a separate future task.

## Verification

- 34 Python tests cover strict cart validation, server prices, changed quotes, concurrent attempts, idempotency, signed webhooks, amount/currency/session checks, protected payment states and private order responses.
- 14 checkout and 12 receipt JavaScript tests cover network retries, changed prices, cross-tab cart changes, double clicks, validated redirects and safe cart cleanup after a confirmed payment.
- Completed a real Stripe sandbox Checkout from the local storefront, using fictitious contact/address information and Stripe's test card. The MXN total was 894884 cents (device 869884 + shipping 25000). Stripe confirmed the payment and the application showed the confirmed test receipt. No real charge or email was sent.
- Checkout verified at 390px. Summary appears before contact fields on mobile; order references wrap without horizontal overflow.
- Existing production database recovered successfully. Orders were empty before provisioning. Added `checkout_attempts`, enabled RLS and revoked browser-role access to both tables.
- Runtime uses a dedicated `zeuz_shop_app` login with SELECT/INSERT/UPDATE on the two tables and explicit backend-only RLS policies. It cannot DELETE or CREATE tables. Client-to-pooler TLS verified.
- Production credentials are stored as sensitive Vercel variables; live credentials are not shared with preview deployments or committed to Git.

## Operational limits

Stock is validated against the editable catalog per cart. This integration does not reserve or automatically decrement warehouse stock across independent purchases.

The local sandbox verifies payment creation and return reconciliation. Production webhook delivery and activation must be recorded below after the deployment is checked.
