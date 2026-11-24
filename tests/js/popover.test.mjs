import { test } from "node:test";
import assert from "node:assert/strict";
import { popoverPosition } from "../../app/static/js/lib/popover.js";

const vp = { width: 1000, height: 700 };

test("the box opens under the button, centred on it", () => {
  const at = popoverPosition({ left: 400, top: 100, bottom: 120, width: 20 }, { width: 200, height: 60 }, vp);
  assert.deepEqual(at, { left: 310, top: 126 });
});

test("it flips above the button when there is no room below", () => {
  const at = popoverPosition({ left: 400, top: 650, bottom: 670, width: 20 }, { width: 200, height: 80 }, vp);
  assert.equal(at.top, 650 - 6 - 80);
});

test("it stays inside the viewport at either edge", () => {
  assert.equal(popoverPosition({ left: 0, top: 10, bottom: 30, width: 20 }, { width: 200, height: 50 }, vp).left, 8);
  assert.equal(popoverPosition({ left: 990, top: 10, bottom: 30, width: 20 }, { width: 200, height: 50 }, vp).left, 1000 - 200 - 8);
});

// ---- open / close behaviour against a tiny fake DOM (no browser needed)
import { installPopovers } from "../../app/static/js/lib/popover.js";

function fakeEl(extra = {}) {
  const el = { attrs: {}, style: {}, children: [], hidden: false, textContent: "", className: "", dataset: {}, focused: false,
    setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
    replaceChildren() { this.children = []; }, append(...c) { this.children.push(...c); },
    appendChild(c) { this.children.push(c); }, contains(t) { return t === this || this.children.includes(t); },
    getBoundingClientRect() { return { left: 100, top: 100, bottom: 120, width: 20, height: 20 }; },
    focus() { this.focused = true; }, closest(sel) { return sel === ".info-btn" && this.isInfo ? this : null; }, ...extra };
  return el;
}

function setup() {
  const handlers = {}, body = fakeEl();
  const doc = { body, documentElement: { clientWidth: 1000, clientHeight: 700 }, createElement: () => fakeEl(),
    addEventListener(type, fn) { handlers[type] = fn; } };
  globalThis.window = { addEventListener() {} };
  installPopovers(doc);
  const btn = fakeEl({ isInfo: true, dataset: { infoTitle: "Delta", info: "Dollars per point." } });
  const click = (target) => { const ev = { target, prevented: false, preventDefault() { this.prevented = true; }, stopPropagation() {} }; handlers.click(ev); return ev; };
  return { handlers, body, btn, click, pop: () => body.children[0] };
}

test("clicking an ⓘ opens the box with its title and words, and does not toggle a <summary>", () => {
  const t = setup();
  const ev = t.click(t.btn);
  assert.equal(ev.prevented, true);
  assert.equal(t.pop().hidden, false);
  assert.equal(t.pop().children[0].textContent, "Delta");
  assert.equal(t.pop().children[1].textContent, "Dollars per point.");
  assert.equal(t.btn.attrs["aria-expanded"], "true");
});

test("Escape closes it and returns focus to the button", () => {
  const t = setup();
  t.click(t.btn);
  t.handlers.keydown({ key: "Escape" });
  assert.equal(t.pop().hidden, true);
  assert.equal(t.btn.attrs["aria-expanded"], "false");
  assert.equal(t.btn.focused, true);
});

test("a click outside closes it, a click on the same ⓘ again closes it, a click inside does not", () => {
  const t = setup();
  t.click(t.btn);
  t.click(t.pop().children[1]);                      // inside the box
  assert.equal(t.pop().hidden, false);
  t.click(fakeEl());                                  // somewhere else
  assert.equal(t.pop().hidden, true);
  t.click(t.btn); t.click(t.btn);                     // open, then the same button again
  assert.equal(t.pop().hidden, true);
});
