/* Read-only browser smoke test. No analysis, deletion or export is submitted. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const base = process.env.APP_URL || 'http://localhost:5173';
  const output = path.join(__dirname, '..', 'storage', 'qa', 'ui-smoke');
  fs.mkdirSync(output, { recursive: true });
  const options = { headless: true };
  if (process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
  else if (process.platform === 'win32') options.channel = 'msedge';
  const browser = await chromium.launch(options);
  const page = await browser.newPage();
  const errors = [];
  const failures = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('response', (response) => {
    if (response.status() >= 500) failures.push({ url: response.url(), status: response.status() });
  });
  const response = await fetch(new URL('/api/projects', base));
  if (!response.ok) throw new Error('Project API returned ' + response.status);
  const projects = await response.json();
  const routes = ['/', '/transcriptions', '/projects', '/settings', '/library'];
  if (projects[0]) routes.push('/transcriptions/' + projects[0].id);
  const results = [];
  try {
    for (const theme of ['light', 'dark']) {
      await page.emulateMedia({ colorScheme: theme });
      for (const [width, height] of [
        [1366, 768],
        [1366, 597],
        [390, 844],
      ]) {
        await page.setViewportSize({ width, height });
        for (const route of routes) {
          await page.goto(new URL(route, base).href);
          await page.locator('h1').waitFor();
          await page.waitForTimeout(500);
          const overflow = await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
          );
          results.push({ route, width, height, theme, overflow });
          const filename = [theme, width, height, route.replaceAll('/', '_')].join('-') + '.png';
          await page.screenshot({ path: path.join(output, filename), fullPage: true });
        }
      }
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(
    path.join(output, 'results.json'),
    JSON.stringify({ results, errors, failures }, null, 2),
  );
  console.log(
    JSON.stringify(
      { pages: results.length, errors, failures, overflows: results.filter((r) => r.overflow) },
      null,
      2,
    ),
  );
  if (errors.length || failures.length || results.some((r) => r.overflow)) process.exitCode = 1;
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
