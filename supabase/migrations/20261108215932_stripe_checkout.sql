-- Backend-only orders and idempotent Checkout attempts.

-- Existing orders are preserved. Apply with a privileged migration role.

BEGIN;

SET LOCAL search_path = public, pg_catalog;

CREATE TABLE IF NOT EXISTS orders (
	id VARCHAR(40) NOT NULL,
	created_at BIGINT NOT NULL,
	updated_at BIGINT NOT NULL,
	status VARCHAR(24) NOT NULL,
	gateway VARCHAR(24) NOT NULL,
	region VARCHAR(4) NOT NULL,
	currency VARCHAR(4) NOT NULL,
	subtotal_net_cents BIGINT NOT NULL,
	tax_cents BIGINT NOT NULL,
	shipping_cents BIGINT NOT NULL,
	total_cents BIGINT NOT NULL,
	items_json TEXT NOT NULL,
	customer_name VARCHAR(160) NOT NULL,
	customer_email VARCHAR(160) NOT NULL,
	customer_phone VARCHAR(60) NOT NULL,
	ship_line1 VARCHAR(200) NOT NULL,
	ship_line2 VARCHAR(200) NOT NULL,
	ship_city VARCHAR(120) NOT NULL,
	ship_state VARCHAR(120) NOT NULL,
	ship_zip VARCHAR(24) NOT NULL,
	ship_country VARCHAR(4) NOT NULL,
	notes TEXT NOT NULL,
	gateway_ref VARCHAR(255) NOT NULL,
	gateway_payment_id VARCHAR(255) NOT NULL,
	gateway_status VARCHAR(80) NOT NULL,
	gateway_url TEXT NOT NULL,
	tracking_carrier VARCHAR(80) NOT NULL,
	tracking_number VARCHAR(120) NOT NULL,
	shipped_at BIGINT,
	admin_notes TEXT NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_orders_gateway_ref ON orders (gateway_ref);

CREATE INDEX IF NOT EXISTS ix_orders_status ON orders (status);

CREATE INDEX IF NOT EXISTS ix_orders_created_at ON orders (created_at);

CREATE TABLE IF NOT EXISTS checkout_attempts (
	attempt_id VARCHAR(36) NOT NULL,
	order_id VARCHAR(40) NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	owner_hash VARCHAR(64) NOT NULL,
	payment_mode VARCHAR(16) NOT NULL,
	created_at BIGINT NOT NULL,
	session_expires_at BIGINT DEFAULT '0' NOT NULL,
	PRIMARY KEY (attempt_id),
	UNIQUE (order_id),
	FOREIGN KEY(order_id) REFERENCES orders (id)
);

ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.checkout_attempts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.orders, public.checkout_attempts FROM PUBLIC, anon, authenticated;

-- No browser/Data API access policies. The backend database role must have

-- only the required SELECT/INSERT/UPDATE rights and RLS access approved by the owner.

COMMIT;
