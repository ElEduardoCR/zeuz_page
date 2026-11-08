/** Stripe handoff: submit only a reviewed quote, reuse the same attempt on retries. */
(() => {
  'use strict';
  const form = document.getElementById('checkout-form');
  if (!form) return;
  const button = document.getElementById('submit-btn');
  const fields = document.getElementById('checkout-contact');
  const errorBox = document.getElementById('form-error');
  const store = window.__STORE__ || {};
  const ATTEMPT_KEY = 'zeuz_checkout_attempt_v1';
  let attempt = null;
  let submitting = false;
  let requestController = null;
  let cartChanged = false;

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    errorBox.focus();
  }
  function syncButton() {
    const quote = window.StoreQuote && StoreQuote.get();
    button.disabled = submitting || !quote || quote.state !== 'ready'
      || !store.payments_enabled || !(store.gateways || []).includes('stripe');
  }
  function busy(value) {
    submitting = value;
    button.dataset.busy = String(value);
    fields.disabled = value;
    form.setAttribute('aria-busy', String(value));
    button.textContent = value ? 'Conectando con Stripe…' : 'Continuar a Stripe';
    syncButton();
  }
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    if (!window.crypto || !crypto.getRandomValues) throw new Error('Este navegador no permite iniciar el pago. Abre la página en un navegador actualizado.');
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  async function signatureFor(cart, customer, quoteToken) {
    if (!window.crypto || !crypto.subtle) throw new Error('Abre la tienda mediante su dirección HTTPS para continuar con el pago.');
    const value = JSON.stringify({ cart: StoreQuote.cartKey(cart), customer, quoteToken });
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
    return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  }
  function attemptFor(signature) {
    if (!attempt) {
      try { attempt = JSON.parse(sessionStorage.getItem(ATTEMPT_KEY) || 'null'); }
      catch (_) { attempt = null; }
    }
    if (!attempt || attempt.signature !== signature
        || !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(attempt.id || '')) {
      attempt = { signature, id: uuid() };
      // Store only a digest and random request ID, never customer contact details.
      try { sessionStorage.setItem(ATTEMPT_KEY, JSON.stringify(attempt)); } catch (_) { /* in-memory retry remains available */ }
    }
    return attempt.id;
  }
  function forgetAttempt() {
    attempt = null;
    try { sessionStorage.removeItem(ATTEMPT_KEY); } catch (_) { /* storage can be disabled */ }
  }

  window.addEventListener('store:quote', syncButton);
  Cart.onChange(() => {
    if (!submitting) return;
    cartChanged = true;
    if (requestController) requestController.abort();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    errorBox.hidden = true;
    const cart = Cart.get();
    if (!cart.length) { showError('Tu carrito está vacío. Añade un equipo antes de continuar.'); return; }
    if (!form.reportValidity()) return;
    const snapshot = StoreQuote.get();
    if (snapshot.state !== 'ready' || snapshot.cartKey !== StoreQuote.cartKey(cart)) {
      showError('Estamos actualizando tu selección. Revisa el total antes de continuar.');
      StoreQuote.refresh();
      return;
    }
    const customer = {
      name: form.elements.name.value.trim(),
      email: form.elements.email.value.trim().toLowerCase(),
      phone: form.elements.phone.value.trim(),
    };
    if (!customer.name || !customer.email) { showError('Completa tu nombre y correo electrónico.'); return; }
    busy(true);
    cartChanged = false;
    requestController = new AbortController();
    const timeout = setTimeout(() => requestController.abort(), 25000);
    let redirecting = false;
    try {
      const signature = await signatureFor(cart, customer, snapshot.quote.quote_token);
      if (requestController.signal.aborted || cartChanged) throw new DOMException('Aborted', 'AbortError');
      const attemptId = attemptFor(signature);
      const response = await fetch('/api/checkout', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cart, customer, quote_token: snapshot.quote.quote_token, attempt_id: attemptId }),
        signal: requestController.signal,
      });
      const data = await response.json();
      if (cartChanged) throw new DOMException('Aborted', 'AbortError');
      if (!response.ok || !data.ok) {
        if (data.code === 'quote_changed') {
          forgetAttempt();
          StoreQuote.refresh();
          throw new Error('El precio o el envío cambió. Revisa el nuevo total y vuelve a pulsar Continuar a Stripe si estás de acuerdo.');
        }
        if (data.code === 'attempt_conflict' || data.code === 'attempt_expired') forgetAttempt();
        if (data.code === 'stock_unavailable' || data.code === 'invalid_cart') StoreQuote.refresh();
        throw new Error(data.error || 'No pudimos abrir Stripe. Vuelve a intentarlo.');
      }
      let destination;
      try {
        if (typeof data.receipt_url === 'string') {
          destination = new URL(data.receipt_url, window.location.origin);
          if (destination.origin !== window.location.origin || destination.pathname !== '/pago/exito'
              || destination.hash || destination.username || destination.password
              || typeof data.order_id !== 'string' || !data.order_id
              || destination.searchParams.getAll('order').length !== 1
              || destination.searchParams.get('order') !== data.order_id
              || [...destination.searchParams.keys()].some(key => key !== 'order')) throw new Error();
        } else {
          if (typeof data.redirect_url !== 'string') throw new Error();
          destination = new URL(data.redirect_url);
          if (destination.protocol !== 'https:' || destination.hostname !== 'checkout.stripe.com'
              || destination.username || destination.password) throw new Error();
        }
      } catch (_) {
        throw new Error('No pudimos verificar la dirección de pago. Contacta con ZEUZ para recibir ayuda.');
      }
      if (typeof data.order_id !== 'string' || !data.order_id) {
        throw new Error('No pudimos recuperar la referencia del pedido. Vuelve a intentarlo.');
      }
      // Keep only the order reference and cart contents, never customer details.
      // The confirmed receipt uses this snapshot to preserve any later cart edits.
      attempt.orderId = data.order_id;
      attempt.cartKey = StoreQuote.cartKey(cart);
      try { sessionStorage.setItem(ATTEMPT_KEY, JSON.stringify(attempt)); } catch (_) { /* receipt will preserve the cart if storage is blocked */ }
      redirecting = true;
      window.location.assign(destination.href);
    } catch (error) {
      showError(cartChanged
        ? 'Tu carrito cambió en otra pestaña. Revisa la selección y el total antes de continuar.'
        : (error.name === 'AbortError'
          ? 'La conexión tardó demasiado. Vuelve a intentarlo; retomaremos el mismo intento de pago.'
          : (error.message === 'Failed to fetch' || error instanceof SyntaxError
            ? 'No pudimos conectar con la tienda. Revisa tu conexión y vuelve a intentarlo.'
            : error.message)));
    } finally {
      clearTimeout(timeout);
      requestController = null;
      if (!redirecting) busy(false);
    }
  });
  syncButton();
})();
