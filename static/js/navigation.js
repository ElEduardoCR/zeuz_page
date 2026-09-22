/* Native details keeps the mobile navigation usable without JavaScript. */
(() => {
  const menu = document.querySelector('.mobile-menu');
  if (!menu) return;
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menu.open) {
      menu.open = false;
      menu.querySelector('summary').focus();
    }
  });
  document.addEventListener('click', (event) => {
    if (!menu.contains(event.target) || event.target.closest('a')) menu.open = false;
  });
  const desktop = window.matchMedia('(min-width: 981px)');
  desktop.addEventListener('change', () => { if (desktop.matches) menu.open = false; });
})();
