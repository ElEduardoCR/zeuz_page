/* Progressive enhancement: readable without JavaScript and with reduced motion. */
(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const revealItems = [...document.querySelectorAll('[data-reveal]')];
  let revealObserver;
  function setupReveals() {
    if (revealObserver) revealObserver.disconnect();
    revealItems.forEach(el => el.classList.remove('reveal-ready'));
    if (reduced.matches || !('IntersectionObserver' in window)) return;
    revealObserver = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      revealObserver.unobserve(entry.target);
    }), { threshold: 0.08 });
    revealItems.forEach(el => {
      if (el.getBoundingClientRect().top < innerHeight) return;
      el.classList.add('reveal-ready');
      revealObserver.observe(el);
    });
  }
  const hero = document.querySelector('[data-hero-parallax]');
  const workflow = document.querySelector('.workflow');
  const stories = [...document.querySelectorAll('[data-story]')];
  const label = document.querySelector('[data-workflow-label]');
  const labels = ['Selecciona tu programa', 'Revisa el código y el perfil', 'Confirma el envío a tu CNC'];
  const progress = document.querySelector('.scroll-progress span');
  let scheduled = false;
  let previousStep = -1;
  function update() {
    scheduled = false;
    const height = document.documentElement.scrollHeight - innerHeight;
    if (progress) progress.style.transform = `scaleX(${height > 0 ? scrollY / height : 0})`;
    if (hero) {
      const rect = hero.getBoundingClientRect();
      const amount = Math.max(0, Math.min(1, (innerHeight - rect.top) / innerHeight));
      hero.style.setProperty('--hero-scale', reduced.matches ? 1 : .94 + amount * .06);
    }
    if (workflow && stories.length) {
      let active = 0;
      stories.forEach((story, index) => { if (story.getBoundingClientRect().top < innerHeight * .52) active = index; });
      if (active !== previousStep) {
        previousStep = active;
        workflow.dataset.step = active;
        stories.forEach((story, index) => story.classList.toggle('is-active', index === active));
        document.querySelectorAll('[data-path]').forEach((el, index) => el.classList.toggle('is-active', index <= active));
        if (label) label.textContent = labels[active];
      }
    }
  }
  function schedule() { if (!scheduled) { scheduled = true; requestAnimationFrame(update); } }
  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule);
  reduced.addEventListener('change', () => { setupReveals(); update(); });
  setupReveals(); update();
})();
