// ⓘ popovers: one small box shared by every .info-btn. Opens on click or Enter/Space (the button is a real
// <button>), closes on Esc, on a click outside, or when another ⓘ is opened. The words come from app/info_text.py.

// Where to put the box: under the button, flipped above when there is no room, kept inside the viewport.
export function popoverPosition(anchor, size, viewport, gap = 6, margin = 8) {
  let top = anchor.bottom + gap;
  if (top + size.height > viewport.height - margin && anchor.top - gap - size.height >= margin) top = anchor.top - gap - size.height;
  let left = anchor.left + anchor.width / 2 - size.width / 2;
  left = Math.max(margin, Math.min(left, viewport.width - size.width - margin));
  return { left: Math.round(left), top: Math.round(Math.max(margin, top)) };
}

export function installPopovers(doc = document) {
  let pop = null, current = null;

  function close(returnFocus = false) {
    if (!pop || pop.hidden) return;
    pop.hidden = true;
    if (current) {
      current.setAttribute("aria-expanded", "false");
      current.removeAttribute("aria-describedby");
      if (returnFocus) current.focus();
    }
    current = null;
  }

  function open(btn) {
    if (!pop) {
      pop = doc.createElement("div");
      pop.id = "info-pop"; pop.setAttribute("role", "tooltip"); pop.hidden = true;
      pop.className = "info-pop";
      doc.body.appendChild(pop);
    }
    close();
    pop.replaceChildren();
    const h = doc.createElement("div"); h.className = "info-pop-title"; h.textContent = btn.dataset.infoTitle || "";
    const p = doc.createElement("div"); p.textContent = btn.dataset.info || "";
    pop.append(h, p);
    pop.hidden = false;
    const r = btn.getBoundingClientRect(), box = pop.getBoundingClientRect();
    const at = popoverPosition(r, { width: box.width, height: box.height }, { width: doc.documentElement.clientWidth, height: doc.documentElement.clientHeight });
    pop.style.left = `${at.left}px`; pop.style.top = `${at.top}px`;
    btn.setAttribute("aria-expanded", "true"); btn.setAttribute("aria-describedby", "info-pop");
    current = btn;
  }

  doc.addEventListener("click", (ev) => {
    const btn = ev.target.closest && ev.target.closest(".info-btn");
    if (btn) {
      ev.preventDefault(); ev.stopPropagation();          // an ⓘ inside a <summary> must not toggle it
      if (btn === current && !pop.hidden) close(); else open(btn);
      return;
    }
    if (pop && !pop.hidden && !pop.contains(ev.target)) close();
  }, true);
  doc.addEventListener("keydown", (ev) => { if (ev.key === "Escape") close(true); });
  window.addEventListener("resize", () => close());
  return { close };
}
