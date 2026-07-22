/**
 * Carrito simple en localStorage.
 * Formato: { items: { [productId]: qty } }
 *
 * Expone window.Cart con:
 *   - get()            -> [{id, qty}, ...]
 *   - count()          -> total de unidades
 *   - add(id, qty=1)
 *   - setQty(id, qty)
 *   - remove(id)
 *   - clear()
 *   - onChange(cb)     -> se suscribe a cambios
 */
(function () {
  'use strict';
  const KEY = 'zeuz_dnc_cart_v1';
  const EVT = 'cart:change';

  function read() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return { items: {} };
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object' || !parsed.items) return { items: {} };
      return parsed;
    } catch (e) {
      return { items: {} };
    }
  }
  function write(state) {
    localStorage.setItem(KEY, JSON.stringify(state));
    window.dispatchEvent(new CustomEvent(EVT, { detail: state }));
    updateBadge();
  }
  function updateBadge() {
    const total = count();
    document.querySelectorAll('#cart-count, .cart-btn__count').forEach((el) => {
      el.textContent = total > 0 ? String(total) : '';
      if (total === 0) el.setAttribute('data-empty', 'true');
      else el.removeAttribute('data-empty');
    });
  }
  function get() {
    const s = read();
    return Object.entries(s.items).map(([id, qty]) => ({ id, qty: Number(qty) || 0 }));
  }
  function count() {
    return get().reduce((a, b) => a + b.qty, 0);
  }
  function add(id, qty = 1) {
    if (!id) return;
    const s = read();
    s.items[id] = Math.max(0, Math.min(99, (Number(s.items[id]) || 0) + qty));
    if (s.items[id] === 0) delete s.items[id];
    write(s);
  }
  function setQty(id, qty) {
    const s = read();
    const n = Math.max(0, Math.min(99, Number(qty) || 0));
    if (n === 0) delete s.items[id];
    else s.items[id] = n;
    write(s);
  }
  function remove(id) {
    const s = read();
    delete s.items[id];
    write(s);
  }
  function clear() {
    write({ items: {} });
  }
  function onChange(cb) {
    window.addEventListener(EVT, (e) => cb(e.detail));
  }

  // Pintar badge al cargar
  document.addEventListener('DOMContentLoaded', updateBadge);
  updateBadge();

  window.Cart = { get, count, add, setQty, remove, clear, onChange };
})();
