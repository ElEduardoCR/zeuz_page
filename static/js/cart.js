/** Persistent cart with an in-memory fallback when browser storage is blocked. */
(function () {
  'use strict';
  const KEY = 'zeuz_dnc_cart_v1';
  const EVT = 'cart:change';
  let memory = { items: Object.create(null) };
  let persistent = true;

  function validId(id) {
    return typeof id === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/.test(id)
      && !['constructor', 'prototype', '__proto__'].includes(id);
  }
  function quantity(value) {
    if (typeof value !== 'number' && typeof value !== 'string') return 0;
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, Math.min(99, Math.floor(number))) : 0;
  }
  function sanitize(state) {
    const items = Object.create(null);
    if (state && typeof state === 'object' && !Array.isArray(state)
        && state.items && typeof state.items === 'object' && !Array.isArray(state.items)) {
      for (const [id, value] of Object.entries(state.items).slice(0, 100)) {
        const qty = quantity(value);
        if (validId(id) && qty > 0) items[id] = qty;
      }
    }
    return { items };
  }
  function parse(raw) {
    try { return sanitize(raw ? JSON.parse(raw) : null); }
    catch (_) { return sanitize(null); }
  }
  function read() {
    if (persistent) {
      try { memory = parse(window.localStorage.getItem(KEY)); }
      catch (_) { persistent = false; }
    }
    return sanitize(memory);
  }
  function notify() {
    updateBadge();
    window.dispatchEvent(new CustomEvent(EVT, { detail: sanitize(memory) }));
  }
  function write(state) {
    memory = sanitize(state);
    if (persistent) {
      try { window.localStorage.setItem(KEY, JSON.stringify(memory)); }
      catch (_) { persistent = false; }
    }
    notify();
  }
  function updateBadge() {
    const total = count();
    document.querySelectorAll('.cart-btn').forEach((el) => {
      el.setAttribute('aria-label', total > 0 ? `Carrito, ${total} ${total === 1 ? 'producto' : 'productos'}` : 'Carrito');
    });
    document.querySelectorAll('#cart-count, .cart-btn__count').forEach((el) => {
      el.textContent = total > 0 ? String(total) : '';
      if (total === 0) el.setAttribute('data-empty', 'true');
      else el.removeAttribute('data-empty');
    });
  }
  function get() {
    return Object.entries(read().items).map(([id, qty]) => ({ id, qty }));
  }
  function count() { return get().reduce((sum, item) => sum + item.qty, 0); }
  function add(id, qty = 1) {
    if (!validId(id) || quantity(qty) === 0) return false;
    const state = read();
    state.items[id] = Math.min(99, (state.items[id] || 0) + quantity(qty));
    write(state);
    return true;
  }
  function setQty(id, qty) {
    if (!validId(id)) return;
    const state = read();
    const number = quantity(qty);
    if (number === 0) delete state.items[id];
    else state.items[id] = number;
    write(state);
  }
  function remove(id) {
    if (!validId(id)) return;
    const state = read();
    delete state.items[id];
    write(state);
  }
  function clear() { write({ items: {} }); }
  function onChange(cb) {
    const handler = (event) => cb(event.detail);
    window.addEventListener(EVT, handler);
    return () => window.removeEventListener(EVT, handler);
  }

  window.addEventListener('storage', (event) => {
    if (!persistent || (event.key !== KEY && event.key !== null)) return;
    memory = parse(event.key === null ? null : event.newValue);
    notify();
  });
  document.addEventListener('DOMContentLoaded', updateBadge);
  window.Cart = { get, count, add, setQty, remove, clear, onChange, isPersistent: () => persistent };
  updateBadge();
})();
