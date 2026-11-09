// Helpers for walking the Flutter web demo. See docs/test/WEB.md.

// Switch the semantics tree on. Call after EVERY full page load.
export async function enableSemantics(page) {
  await page.locator('flt-semantics-placeholder').dispatchEvent('click');
}

// Locator for Semantics(identifier: id), exposed as flt-semantics-identifier.
export function sid(page, id) {
  return page.locator(`[flt-semantics-identifier="${id}"]`);
}

// locator.fill empties Flutter fields: click, wait, select all, type slowly.
export async function typeInto(locator, text) {
  await locator.click();
  await locator.page().waitForTimeout(400);
  await locator.press('ControlOrMeta+a');
  await locator.pressSequentially(text, { delay: 25 });
}

// Collect dialogs, console errors and page errors. Call check() per route.
export function collectErrors(page) {
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console: ${m.text()}`);
  });
  page.on('dialog', (d) => errors.push(`dialog: ${d.message()}`));
  return {
    errors,
    async check() {
      const dialogs = await page.locator('[role=dialog],[role=alertdialog]').count();
      const strip = await sid(page, 'sdk.errors').count();
      const all = [...errors];
      if (dialogs > 0) all.push(`${dialogs} dialog element(s)`);
      if (strip > 0) all.push('inline error strip visible');
      return all;
    },
  };
}
