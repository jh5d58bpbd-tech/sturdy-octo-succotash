// HTML → A4 PDF（Chromium / Playwright）。使い方: node tools/pdf.js in.html out.pdf
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [, , input, output] = process.argv;
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(input));
  await page.pdf({ path: output, format: 'A4', printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  await browser.close();
})();
