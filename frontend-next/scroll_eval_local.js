const { chromium } = require('./node_modules/playwright');
const path = require('path');
const artifactsDir = 'C:/Users/Huraira Maqbool/.gemini/antigravity/brain/92182f8e-b811-4f4b-b814-d7e62ecdb21b';
const storageState = path.join(artifactsDir, 'scratch/storage_state.json');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    storageState,
    viewport: { width: 1400, height: 900 }
  });
  const page = await ctx.newPage();
  await page.goto('http://localhost:3000/evaluation');
  await page.waitForSelector('text=Backend connectivity', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(6000);

  // Scroll the inner scrollable container
  const scrollTo = async (px) => {
    await page.evaluate((px) => {
      const candidates = Array.from(document.querySelectorAll('*'));
      for (const el of candidates) {
        const s = window.getComputedStyle(el);
        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 50) {
          el.scrollTop = px;
          break;
        }
      }
    }, px);
    await page.waitForTimeout(400);
  };

  // Scroll to RAGAS metric bars + sparklines
  await scrollTo(900);
  await page.screenshot({ path: path.join(artifactsDir, 'real_eval_scroll900.png') });

  // Scroll to history table
  await scrollTo(2800);
  await page.screenshot({ path: path.join(artifactsDir, 'real_eval_scroll2800.png') });

  console.log('Done');
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
