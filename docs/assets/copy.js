/* Adds a copy button to every code block.
   Progressive enhancement: if this never runs, the pages are unaffected. */
document.addEventListener('DOMContentLoaded', () => {
  if (!navigator.clipboard) return;

  for (const pre of document.querySelectorAll('pre')) {
    const wrap = document.createElement('div');
    wrap.className = 'pre-wrap';
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);

    const button = document.createElement('button');
    button.className = 'copy';
    button.type = 'button';
    button.textContent = 'Copy';
    button.setAttribute('aria-label', 'Copy to clipboard');

    button.addEventListener('click', async () => {
      try {
        // innerText keeps the line breaks that textContent would flatten.
        await navigator.clipboard.writeText(pre.innerText.replace(/\n$/, ''));
        button.textContent = 'Copied';
        button.classList.add('done');
      } catch {
        button.textContent = 'Press ⌘C';
      }
      setTimeout(() => {
        button.textContent = 'Copy';
        button.classList.remove('done');
      }, 1600);
    });

    wrap.appendChild(button);
  }
});
