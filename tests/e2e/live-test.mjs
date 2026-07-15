/**
 * Live E2E test — browser → backend → browser
 * Run: node tests/e2e/live-test.mjs
 * Requires server running at http://127.0.0.1:8000
 */
import { chromium } from 'playwright';

const BASE = 'http://127.0.0.1:8000';
let pass = 0, fail = 0;

function check(label, ok, detail) {
  if (ok) { pass++; console.log(`  PASS  ${label}`); }
  else     { fail++; console.log(`  FAIL  ${label} — ${detail || ''}`); }
}

// ── test cases ──
const TEST_CASES = [
  {
    name: '中文典型Prompt - medium',
    level: 'medium',
    text: '请帮我分析一下这份销售数据，找出其中的异常值和增长趋势，非常感谢您的帮助！',
    expectSavings: true,   // should reduce tokens
  },
  {
    name: '英文典型Prompt - medium',
    level: 'medium',
    text: 'Could you please help me analyze this sales data and find any anomalies? Thank you so much!',
    expectSavings: true,
  },
  {
    name: '中文极端客套 - aggressive',
    level: 'aggressive',
    text: '能否请您帮我看一下这个数据集，麻烦您给个意见？谢谢您了！祝您工作顺利！',
    expectSavings: true,
  },
  {
    name: '纯命令文本 - medium',
    level: 'medium',
    text: '分析Q3销售数据，找出前5大增长区域。',
    expectSavings: false,  // clean text, should NOT compress much
  },
  {
    name: '英文纯命令 - medium',
    level: 'medium',
    text: 'Analyze Q3 sales data and identify top-performing regions.',
    expectSavings: false,
  },
  {
    name: '中文口语 - medium',
    level: 'medium',
    text: '那个就是说，我觉得这个方案还是非常特别极其好的，对吧？你知道吗？',
    expectSavings: true,
  },
  {
    name: '中文敬语堆叠 - medium',
    level: 'medium',
    text: '麻烦您帮我分析一下这个数据，非常感谢！辛苦您了！',
    expectSavings: true,
  },
  {
    name: '英文请求 - medium',
    level: 'medium',
    text: 'I would like you to help me analyze the quarterly report and provide insights. Thanks!',
    expectSavings: true,
  },
];

// ════════════════════════════════════════════════════════════════════
async function run() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  // ── Collect diagnostics ──
  const jsErrors = [];
  page.on('pageerror', e => jsErrors.push(e.message));
  const apiCalls = [];
  page.on('request', req => {
    if (req.url().includes('/api/')) apiCalls.push(req.url());
  });
  const apiResponses = [];
  page.on('response', res => {
    if (res.url().includes('/api/')) apiResponses.push({ url: res.url(), status: res.status() });
  });

  // ════════════════════════════════════════════════════════════════
  console.log('=== 1. PAGE LOAD ===');
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  const title = await page.title();
  check('title contains Prompt', title.includes('Prompt') || title.includes('优化'), title);
  check('textarea exists', !!(await page.$('#input-textarea')), '');
  check('compress button exists', !!(await page.$('#btn-compress')), '');
  check('model selector has options', (await page.$$('#global-model-selector option')).length >= 8, '');
  check('placeholder visible', await page.evaluate(() => {
    const el = document.getElementById('result-placeholder');
    return el && window.getComputedStyle(el).display !== 'none';
  }), '');
  await page.screenshot({ path: 'screenshots/live-01-page-load.png', fullPage: true });

  // ════════════════════════════════════════════════════════════════
  console.log('=== 2. COMPRESSION TESTS (frontend -> backend -> frontend) ===');

  for (const tc of TEST_CASES) {
    console.log(`\n  --- ${tc.name} ---`);

    // Set level
    await page.selectOption('#compression-level', tc.level);

    // Type text
    await page.fill('#input-textarea', '');
    await page.fill('#input-textarea', tc.text);

    // Read live stats BEFORE compress
    const charBeforeEl = await page.textContent('#char-count');
    const tokenEstBeforeEl = await page.textContent('#est-tokens');
    console.log(`  input: ${charBeforeEl.trim()} / ${tokenEstBeforeEl.trim()}`);

    // Click compress
    await page.click('#btn-compress');
    await page.waitForTimeout(3000);

    // Read results AFTER compress
    const origTok = await page.textContent('#orig-tokens');
    const compTok = await page.textContent('#comp-tokens');
    const savingsBadge = await page.textContent('#savings-badge');
    const changesCount = await page.textContent('#changes-count');
    const statusText = await page.textContent('#status-text');

    const orig = parseInt(origTok.trim(), 10) || 0;
    const comp = parseInt(compTok.trim(), 10) || 0;
    const saved = orig - comp;
    const pct = orig > 0 ? Math.round((saved / orig) * 100) : 0;

    console.log(`  result: ${orig} -> ${comp} tokens (↓${pct}%), ${changesCount.trim()} changes`);
    console.log(`  status: ${statusText.trim()}`);

    // Assertions
    check('original tokens > 0', orig > 0, String(orig));
    if (tc.expectSavings) {
      check('tokens reduced', saved > 0, `saved ${saved} (${pct}%)`);
      check('changes have entries', parseInt(changesCount.trim(), 10) > 0, changesCount.trim());
      check('savings badge shows', savingsBadge.trim().startsWith('↓') || savingsBadge.trim() !== '--', savingsBadge.trim());
    } else {
      check('clean text — little/no reduction', pct <= 15, `${pct}% — clean text should not be mangled`);
    }

    // Check text diff card has content.
    // compressed display now shows CLEAN compressed text (not diff-highlighted original).
    const origTextEl = await page.textContent('#original-text-display');
    const compText = await page.textContent('#compressed-text-display');
    check('original text display populated', origTextEl.trim().length > 0, String(origTextEl.trim().length));
    check('compressed text display populated', compText.trim().length > 0, String(compText.trim().length));
    if (tc.expectSavings) {
      // Compressed text should be shorter than original
      check('compressed shorter than original', compText.trim().length < origTextEl.trim().length,
        'orig=' + origTextEl.trim().length + ' comp=' + compText.trim().length);
    }
  }

  // ════════════════════════════════════════════════════════════════
  console.log('\n=== 3. MODEL SWITCHING ===');
  await page.selectOption('#global-model-selector', 'qwen');
  await page.waitForTimeout(1000);
  const modelAfterSwitch = await page.textContent('#status-model');
  check('status bar shows new model', modelAfterSwitch.trim().includes('Qwen'), modelAfterSwitch.trim());

  // Use longer text for model differentiation test
  await page.fill('#input-textarea', '请帮我分析一下这份非常复杂的数据，找出异常值，非常感谢！');
  await page.click('#btn-compress');
  await page.waitForTimeout(3000);
  const qwenOrig = (await page.textContent('#orig-tokens')).trim();
  console.log(`  Qwen tokenize: ${qwenOrig} tokens`);

  await page.selectOption('#global-model-selector', 'deepseek_v4');
  await page.waitForTimeout(1000);
  await page.click('#btn-compress');
  await page.waitForTimeout(3000);
  const dsOrig = (await page.textContent('#orig-tokens')).trim();
  console.log(`  DeepSeek tokenize: ${dsOrig} tokens`);
  // Qwen and DeepSeek use different tokenizers — counts may differ for CJK text
  console.log(`  Qwen=${qwenOrig}, DeepSeek=${dsOrig}`);

  // ════════════════════════════════════════════════════════════════
  console.log('\n=== 4. UNDO & EXPORT ===');
  await page.click('#btn-undo');
  await page.waitForTimeout(500);
  check('placeholder returns after undo', await page.evaluate(() => {
    const el = document.getElementById('result-placeholder');
    return el && window.getComputedStyle(el).display !== 'none';
  }), '');

  await page.fill('#input-textarea', 'test export');
  await page.click('#btn-compress');
  await page.waitForTimeout(2000);
  const exportBtn = await page.$('#btn-export');
  check('export button enabled', exportBtn && !(await exportBtn.isDisabled()), '');

  // ════════════════════════════════════════════════════════════════
  console.log('\n=== 5. COST SIMULATOR ===');
  const costAnnual = await page.textContent('#cost-annual-save');
  check('cost annual save shown', costAnnual.trim().includes('$'), costAnnual.trim());

  // ════════════════════════════════════════════════════════════════
  console.log('\n=== 6. COLLAPSIBLE SECTIONS ===');
  await page.evaluate(() => {
    document.querySelectorAll('.collapsible').forEach(el => el.setAttribute('open', ''));
  });
  await page.waitForTimeout(500);
  const bodyText = await page.textContent('body');
  check('model comparison table visible', bodyText.includes('多模型对比'), '');
  check('cost simulator visible', bodyText.includes('成本模拟器'), '');
  check('changes log visible', bodyText.includes('压缩变更记录'), '');

  // ════════════════════════════════════════════════════════════════
  console.log('\n=== 7. DIAGNOSTICS ===');
  check('zero JS console errors', jsErrors.length === 0, jsErrors.join('; ') || 'none');
  console.log(`  API calls captured: ${apiCalls.length}`);
  const failedApi = apiResponses.filter(r => r.status >= 400);
  check('zero API errors', failedApi.length === 0, failedApi.map(r => `${r.url} (${r.status})`).join('; ') || 'none');

  await page.screenshot({ path: 'screenshots/live-99-final.png', fullPage: true });

  // ════════════════════════════════════════════════════════════════
  await browser.close();
  console.log(`\n${'='.repeat(50)}`);
  console.log(`TOTAL: ${pass + fail} checks — ${pass} PASS, ${fail} FAIL`);
  console.log(`${'='.repeat(50)}`);
  if (fail > 0) process.exit(1);
}

run().catch(e => { console.error('TEST CRASHED:', e.message); process.exit(1); });
