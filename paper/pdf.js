// Print paper/build/manuscript.html to PDF with the preinstalled Chromium (Node Playwright).
// Usage: node paper/pdf.js <html> <pdf>
const { chromium } = require('playwright');
(async () => {
  const [html, pdf] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + html, { waitUntil: 'networkidle' });
  await page.pdf({ path: pdf, format: 'A4', printBackground: true,
    margin: { top: '18mm', bottom: '18mm', left: '16mm', right: '16mm' },
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#666">' +
      '<span class="pageNumber"></span> / <span class="totalPages"></span></div>' });
  await browser.close();
})();
