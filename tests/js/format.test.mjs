import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as fmt from "../../app/static/js/lib/format.js";

const cases = JSON.parse(readFileSync(new URL("../format_cases.json", import.meta.url)));

for (const c of cases) {
  test(`${c.fn}(${JSON.stringify(c.args)}) = ${c.out}`, () => {
    assert.equal(fmt[c.fn](...c.args), c.out);
  });
}

test("localtime shows the moment in the browser's time zone", () => {
  assert.equal(fmt.localtime(""), "");
  assert.equal(fmt.localtime("not a time"), "");
  const out = fmt.localtime("2026-11-24T10:00:00-05:00");        // 10:00 ET = 15:00 UTC, whatever zone the test machine is in
  assert.match(out, /^\d{1,2}:\d{2}:\d{2} (AM|PM)/);
  const d = new Date("2026-11-24T15:00:00Z");
  assert.ok(out.startsWith(`${d.getHours() % 12 || 12}:00:00 ${d.getHours() < 12 ? "AM" : "PM"}`));
});
