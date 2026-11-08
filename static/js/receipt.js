/** Complete only this browser's confirmed checkout, preserving later cart edits. */
(() => {
  'use strict';
  const receiptElement = document.getElementById('confirmed-order');
  if (!receiptElement || !window.Cart || !window.StoreQuote) return;
  const attemptKey = 'zeuz_checkout_attempt_v1';
  let receipt, attempt;
  try {
    receipt = JSON.parse(receiptElement.textContent);
    attempt = JSON.parse(sessionStorage.getItem(attemptKey) || 'null');
  } catch (_) { return; }
  if (!receipt || receipt.paid !== true || typeof receipt.id !== 'string' || !receipt.id
      || !attempt || attempt.orderId !== receipt.id) return;

  // A stale receipt cannot delete a newer checkout attempt. Remove this matched
  // attempt even if the user changed the cart while paying, so a repeat purchase
  // gets a fresh attempt instead of returning to the previous receipt.
  try { sessionStorage.removeItem(attemptKey); } catch (_) { return; }
  if (typeof attempt.cartKey === 'string' && attempt.cartKey === StoreQuote.cartKey(Cart.get())) {
    Cart.clear();
  }
})();
