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
