/** Storefront interactions. Prices and totals are always quoted by the server. */
(function () {
  'use strict';
  const store = window.__STORE__ || { currency: 'MXN', locale: 'es-MX' };
  const catalog = Object.fromEntries((window.__CATALOG__ || []).map((product) => [product.id, product]));
  const totalIds = ['cart-subtotal', 'cart-shipping', 'cart-total', 'checkout-subtotal', 'checkout-tax', 'checkout-shipping', 'checkout-total'];
  let quoteTimer, quoteController, quoteVersion = 0, toastTimer, synchronizing = false;
  let quoteSnapshot = { state: 'idle', quote: null, cartKey: '' };
  function cartKey(items) {
    return JSON.stringify(items.map(item => ({ id: item.id, qty: item.qty }))
      .sort((left, right) => left.id.localeCompare(right.id)));
  }

  function fmt(amount) {
    const value = Number(amount);
    if (!Number.isFinite(value)) return '—';
    return '$' + value.toLocaleString(store.locale || 'es-MX', {
      minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
      maximumFractionDigits: 2,
    }) + ' ' + store.currency;
  }
  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
  }
  function paint(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }
  function showToast(message, cartLink = false) {
    const toast = document.getElementById('shop-toast');
    if (!toast) return;
    clearTimeout(toastTimer);
    toast.replaceChildren();
    const text = document.createElement('span');
    text.textContent = message;
    toast.appendChild(text);
    if (cartLink) {
      const link = document.createElement('a');
      link.href = '/carrito';
      link.textContent = 'Ver carrito';
      toast.appendChild(link);
    }
    toast.hidden = false;
    toastTimer = setTimeout(() => {
      if (!toast.contains(document.activeElement)) toast.hidden = true;
    }, 8000);
  }

  document.addEventListener('click', (event) => {
    const btn = event.target.closest('.js-add-to-cart');
    if (!btn || btn.disabled || btn.dataset._busy === '1') return;
    const qtyInput = btn.dataset.qtyInput && document.getElementById(btn.dataset.qtyInput);
    const qty = qtyInput ? Math.max(1, Math.min(99, Math.floor(Number(qtyInput.value)) || 1)) : 1;
    if (qtyInput) qtyInput.value = qty;
    if (!Cart.add(btn.dataset.id, qty)) return;
    const name = catalog[btn.dataset.id] ? catalog[btn.dataset.id].name : 'Producto';
    showToast(Cart.isPersistent()
      ? `${name} añadido al carrito.`
      : 'Añadido en esta página. Tu navegador no permite guardar el carrito.', true);
    const original = btn.textContent;
    btn.dataset._busy = '1';
    btn.textContent = 'Añadido';
    setTimeout(() => { btn.textContent = original; delete btn.dataset._busy; }, 900);
  });

  function quoteState(state, message, quote = null, cart = []) {
    quoteSnapshot = { state, quote, cartKey: cartKey(cart) };
    document.querySelectorAll('.cart-summary').forEach((summary) => {
      summary.setAttribute('aria-busy', state === 'pending' ? 'true' : 'false');
      let status = summary.querySelector('.quote-status');
      if (!status) {
        status = document.createElement('div');
        status.className = 'quote-status';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        summary.appendChild(status);
      }
      status.replaceChildren();
      status.hidden = !message;
      if (message) {
        const text = document.createElement('p');
        text.textContent = message;
        status.appendChild(text);
      }
      if (state === 'error') {
        const retry = document.createElement('button');
        retry.type = 'button';
        retry.className = 'quote-retry btn btn--secondary btn--sm';
        retry.textContent = 'Volver a calcular';
        retry.addEventListener('click', fetchQuote);
        status.appendChild(retry);
      }
    });
    const submit = document.getElementById('submit-btn');
    if (submit) submit.disabled = state !== 'ready' || submit.dataset.busy === 'true'
      || !store.payments_enabled || !(store.gateways || []).includes('stripe');
    if (state !== 'ready') {
      totalIds.forEach((id) => paint(id, '—'));
      document.querySelectorAll('[data-line-price]').forEach(el => { el.textContent = '—'; });
    }
    window.dispatchEvent(new CustomEvent('store:quote', { detail: quoteSnapshot }));
  }
  function cancelQuote() {
    ++quoteVersion;
    clearTimeout(quoteTimer);
    if (quoteController) quoteController.abort();
  }
  function fetchQuote() {
    cancelQuote();
    const version = quoteVersion;
    const cart = Cart.get();
    if (!cart.length) { quoteState('empty', ''); return; }
    quoteState('pending', 'Calculando tu selección…');
    quoteTimer = setTimeout(async () => {
      const controller = new AbortController();
      quoteController = controller;
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        const response = await fetch('/api/quote', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cart }), signal: controller.signal,
        });
        const data = await response.json();
        if (version !== quoteVersion) return;
        const fields = ['subtotal_gross', 'subtotal_net', 'tax', 'shipping', 'total'];
        if (!response.ok || !data.ok || data.currency !== 'MXN' || !data.totals
            || typeof data.quote_token !== 'string' || !/^[a-f0-9]{64}$/.test(data.quote_token)
            || !Array.isArray(data.items) || cartKey(data.items) !== cartKey(cart)
            || !data.items.every(item => Number.isSafeInteger(item.line_gross_cents) && item.line_gross_cents >= 0)
            || !fields.every((key) => typeof data.totals[key] === 'number'
              && Number.isFinite(data.totals[key]) && data.totals[key] >= 0)) {
          throw Object.assign(new Error('quote_unavailable'), { publicMessage: typeof data.error === 'string' ? data.error : null });
        }
        const totals = data.totals;
        paint('cart-subtotal', fmt(totals.subtotal_gross));
        paint('cart-shipping', totals.shipping > 0 ? fmt(totals.shipping) : 'Gratis');
        paint('cart-total', fmt(totals.total));
        paint('checkout-subtotal', fmt(totals.subtotal_net));
        paint('checkout-tax', fmt(totals.tax));
        paint('checkout-shipping', totals.shipping > 0 ? fmt(totals.shipping) : 'Gratis');
        paint('checkout-total', fmt(totals.total));
        const lines = new Map(data.items.map(item => [item.id, item.line_gross_cents]));
        document.querySelectorAll('[data-line-price]').forEach(el => {
          const cents = lines.get(el.dataset.linePrice);
          el.textContent = Number.isSafeInteger(cents) ? fmt(cents / 100) : '—';
        });
        quoteState('ready', '', data, cart);
      } catch (error) {
        if (version === quoteVersion) quoteState('error', error.name === 'AbortError'
          ? 'La consulta tardó demasiado. Vuelve a calcular el total.'
          : (error.publicMessage || 'No pudimos calcular el total. Revisa tu conexión y vuelve a intentarlo.'));
      } finally { clearTimeout(timeout); }
    }, 100);
  }

  window.StoreQuote = Object.freeze({ get: () => quoteSnapshot, refresh: fetchQuote, cartKey });

  function availableItems() {
    const items = Cart.get();
    const unavailable = items.filter((item) => !catalog[item.id] || catalog[item.id].external);
    if (unavailable.length) {
      synchronizing = true;
      unavailable.forEach((item) => Cart.remove(item.id));
      synchronizing = false;
      showToast('Quitamos de tu selección los productos que ya no están disponibles.');
    }
    return items.filter((item) => catalog[item.id] && !catalog[item.id].external);
  }
  function renderCart() {
    if (synchronizing) return;
    const empty = document.getElementById('cart-empty');
    const wrap = document.getElementById('cart-with-items');
    const root = document.getElementById('cart-items');
    if (!empty || !wrap || !root) return;
    const items = availableItems();
    empty.hidden = items.length > 0;
    wrap.hidden = items.length === 0;
    const focused = root.contains(document.activeElement) ? document.activeElement : null;
    const focusId = focused && focused.dataset.id;
    const focusAction = focused && focused.dataset.action;
    const focusInput = focused && focused.classList.contains('cart-item__qty-input');
    root.replaceChildren();
    for (const item of items) {
      const product = catalog[item.id];
      const row = document.createElement('div');
      row.className = 'cart-item';
      row.innerHTML = `
        <div class="cart-item__media"><img src="/static/${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" /></div>
        <div>
          <p class="cart-item__title">${escapeHtml(product.name)}</p>
          <p class="cart-item__short">${escapeHtml(product.short)}</p>
          <div class="qty" style="margin-top:8px">
            <button type="button" class="qty__btn" data-action="dec" data-id="${escapeHtml(item.id)}" aria-label="Restar una unidad de ${escapeHtml(product.name)}" ${item.qty === 1 ? 'disabled' : ''}>−</button>
            <input type="number" min="1" max="99" step="1" value="${item.qty}" data-id="${escapeHtml(item.id)}" class="cart-item__qty-input" aria-label="Cantidad de ${escapeHtml(product.name)}" />
            <button type="button" class="qty__btn" data-action="inc" data-id="${escapeHtml(item.id)}" aria-label="Sumar una unidad de ${escapeHtml(product.name)}" ${item.qty === 99 ? 'disabled' : ''}>+</button>
          </div>
        </div>
        <div class="cart-item__controls">
          <div class="cart-item__price" data-line-price="${escapeHtml(item.id)}">—</div>
          <button type="button" class="cart-item__remove" data-action="remove" data-id="${escapeHtml(item.id)}" aria-label="Quitar ${escapeHtml(product.name)}">Quitar</button>
        </div>`;
      root.appendChild(row);
    }
    if (focusId) {
      const candidates = [...root.querySelectorAll('[data-id]')];
      const replacement = candidates.find((el) => el.dataset.id === focusId &&
        (focusInput ? el.classList.contains('cart-item__qty-input') : el.dataset.action === focusAction));
      const target = replacement && !replacement.disabled ? replacement
        : candidates.find((el) => el.dataset.id === focusId && el.classList.contains('cart-item__qty-input'));
      if (target) target.focus({ preventScroll: true });
    }
    fetchQuote();
  }
  if (document.getElementById('cart-items')) {
    renderCart();
    Cart.onChange(renderCart);
    document.getElementById('cart-items').addEventListener('click', (event) => {
      const btn = event.target.closest('[data-action]');
      if (!btn || btn.disabled) return;
      const current = Cart.get().find((item) => item.id === btn.dataset.id);
      if (!current) return;
      if (btn.dataset.action === 'inc') Cart.setQty(current.id, current.qty + 1);
      if (btn.dataset.action === 'dec') Cart.setQty(current.id, Math.max(1, current.qty - 1));
      if (btn.dataset.action === 'remove') Cart.remove(current.id);
    });
    document.getElementById('cart-items').addEventListener('change', (event) => {
      if (!event.target.classList.contains('cart-item__qty-input')) return;
      const qty = Math.max(1, Math.min(99, Math.floor(Number(event.target.value)) || 1));
      Cart.setQty(event.target.dataset.id, qty);
    });
  }
  function renderCheckoutSummary() {
    if (synchronizing) return;
    const root = document.getElementById('checkout-items');
    if (!root) return;
    const items = availableItems();
    root.replaceChildren();
    if (!items.length) {
      const message = document.createElement('p');
      message.textContent = 'Tu carrito está vacío.';
      root.appendChild(message);
    }
    for (const item of items) {
      const product = catalog[item.id];
      const row = document.createElement('div');
      row.className = 'checkout-item';
      row.innerHTML = `<span class="checkout-item__name">${escapeHtml(product.name)}</span>
        <span class="checkout-item__qty">× ${item.qty}</span>
        <span class="checkout-item__price" data-line-price="${escapeHtml(item.id)}">—</span>`;
      root.appendChild(row);
    }
    fetchQuote();
  }
  if (document.getElementById('checkout-items')) {
    renderCheckoutSummary();
    Cart.onChange(renderCheckoutSummary);
  }
})();
