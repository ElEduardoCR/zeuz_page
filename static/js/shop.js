/**
 * Lógica de UI: pintar carrito, checkout, y botones "Añadir al carrito".
 * Espera window.__CATALOG__ en /carrito para resolver nombres/precios.
 */
(function () {
  'use strict';

  // Helper: formato moneda MXN
  const fmt = (n) => '$' + Number(n).toLocaleString('es-MX', { maximumFractionDigits: 0 });
  const catalog = (window.__CATALOG__ || []).reduce((acc, p) => (acc[p.id] = p, acc), {});

  // -------- Botones "Añadir al carrito" --------
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.js-add-to-cart');
    if (!btn) return;
    const id = btn.dataset.id;
    if (!id) return;
    const qtyInput = btn.dataset.qtyInput && document.getElementById(btn.dataset.qtyInput);
    const qty = qtyInput ? Math.max(1, Math.min(99, parseInt(qtyInput.value, 10) || 1)) : 1;
    Cart.add(id, qty);
    flash(btn, '¡Añadido!');
  });

  function flash(btn, msg) {
    if (btn.dataset._busy === '1') return;
    btn.dataset._busy = '1';
    const original = btn.textContent;
    btn.textContent = msg;
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
      delete btn.dataset._busy;
    }, 1000);
  }

  // -------- Página /carrito --------
  function renderCart() {
    const empty = document.getElementById('cart-empty');
    const wrap = document.getElementById('cart-with-items');
    if (!empty || !wrap) return;

    const items = Cart.get();
    if (items.length === 0) {
      empty.hidden = false;
      wrap.hidden = true;
      return;
    }
    empty.hidden = true;
    wrap.hidden = false;

    const root = document.getElementById('cart-items');
    root.innerHTML = '';
    let total = 0;
    for (const it of items) {
      const p = catalog[it.id];
      if (!p) continue;
      const subtotal = p.price * it.qty;
      total += subtotal;
      const row = document.createElement('div');
      row.className = 'cart-item';
      row.innerHTML = `
        <div class="cart-item__media">
          <img src="/static/${p.image}" alt="${escapeHtml(p.name)}" />
        </div>
        <div>
          <p class="cart-item__title">${escapeHtml(p.name)}</p>
          <p class="cart-item__short">${escapeHtml(p.short)}</p>
          <div class="qty" style="margin-top: 8px;">
            <button class="qty__btn" data-action="dec" data-id="${p.id}" aria-label="Restar">−</button>
            <input type="number" min="1" max="99" value="${it.qty}" data-id="${p.id}" class="cart-item__qty-input" />
            <button class="qty__btn" data-action="inc" data-id="${p.id}" aria-label="Sumar">+</button>
          </div>
        </div>
        <div class="cart-item__controls">
          <div class="cart-item__price">${fmt(subtotal)}</div>
          <button class="cart-item__remove" data-action="remove" data-id="${p.id}">Quitar</button>
        </div>
      `;
      root.appendChild(row);
    }
    document.getElementById('cart-subtotal').textContent = fmt(total);
    document.getElementById('cart-total').textContent = fmt(total);
  }
  if (document.getElementById('cart-items')) {
    renderCart();
    Cart.onChange(renderCart);
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const id = btn.dataset.id;
      const items = Cart.get();
      const cur = items.find((i) => i.id === id);
      if (!cur) return;
      if (btn.dataset.action === 'inc') Cart.setQty(id, cur.qty + 1);
      if (btn.dataset.action === 'dec') Cart.setQty(id, Math.max(1, cur.qty - 1));
      if (btn.dataset.action === 'remove') Cart.remove(id);
    });
    document.addEventListener('change', (e) => {
      if (!e.target.classList.contains('cart-item__qty-input')) return;
      const v = Math.max(1, Math.min(99, parseInt(e.target.value, 10) || 1));
      Cart.setQty(e.target.dataset.id, v);
    });
  }

  // -------- Página /checkout --------
  function renderCheckoutSummary() {
    const root = document.getElementById('checkout-items');
    if (!root) return;
    const items = Cart.get();
    root.innerHTML = '';
    let total = 0;
    if (items.length === 0) {
      const p = document.createElement('p');
      p.style.color = 'var(--text-dim)';
      p.textContent = 'Tu carrito está vacío.';
      root.appendChild(p);
    } else {
      for (const it of items) {
        const p = catalog[it.id];
        if (!p) continue;
        const subtotal = p.price * it.qty;
        total += subtotal;
        const row = document.createElement('div');
        row.className = 'checkout-item';
        row.innerHTML = `
          <span class="checkout-item__name">${escapeHtml(p.name)}</span>
          <span class="checkout-item__qty">x ${it.qty}</span>
          <span class="checkout-item__price">${fmt(subtotal)}</span>
        `;
        root.appendChild(row);
      }
    }
    document.getElementById('checkout-subtotal').textContent = fmt(total);
    document.getElementById('checkout-total').textContent = fmt(total);
  }
  if (document.getElementById('checkout-items')) {
    renderCheckoutSummary();
    Cart.onChange(renderCheckoutSummary);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (m) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[m]));
  }
})();
