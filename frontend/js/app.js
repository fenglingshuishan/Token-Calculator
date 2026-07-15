(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { groups: [], last: null, previewTimer: null };
  const examples = {
    product: `请帮我设计一个后台用户管理模块。\n\n要求：\n- 支持邮箱和手机号登录\n- 连续失败 5 次后锁定 30 分钟\n- 管理员操作必须记录审计日志\n- 输出数据库表、API 列表和验收标准\n\n非常感谢您的帮助！`,
    code: `您好，请帮我编写一个 Python 函数，读取 CSV 销售数据并按月份汇总。\n\n约束：\n1. 只能使用标准库\n2. 无效日期要跳过并返回错误列表\n3. 金额使用 Decimal，不能使用 float\n4. 保留类型注解和单元测试\n\n谢谢！`
  };

  async function api(path, options) {
    const response = await fetch(path, options);
    let data;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok) throw new Error(data && data.detail ? data.detail : `请求失败 (${response.status})`);
    return data;
  }
  const post = (path, body) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  function money(value) { return value == null ? '无法计算' : '$' + Number(value).toLocaleString('zh-CN', {minimumFractionDigits: value && Math.abs(value) < .01 ? 6 : 2, maximumFractionDigits: 6}); }
  function toast(message) { const el = $('toast'); el.textContent = message; el.classList.add('show'); clearTimeout(el._timer); el._timer = setTimeout(() => el.classList.remove('show'), 2200); }
  function setServer(ok, text) { const el = $('server-state'); el.className = 'server-state ' + (ok ? 'ok' : 'bad'); el.querySelector('span').textContent = text; }
  function selectedOption() { return $('model').selectedOptions[0]; }
  function selectedGroup() { const option = selectedOption(); return option ? state.groups.find(g => g.group_id === option.dataset.group) : null; }
  function selectedModel() { const option = selectedOption(); return option ? option.dataset.model : null; }
  function escapeHtml(value) { const div = document.createElement('div'); div.textContent = value == null ? '' : String(value); return div.innerHTML; }

  async function boot() {
    try {
      const health = await api('/health');
      setServer(true, `本地服务已连接 · v${health.version}`);
      const data = await api('/api/models');
      state.groups = data.groups;
      $('model').innerHTML = '';
      data.groups.forEach(group => {
        const optgroup = document.createElement('optgroup');
        optgroup.label = group.display_name;
        group.models.forEach(model => {
          const option = document.createElement('option');
          option.value = `${group.group_id}::${model}`;
          option.dataset.group = group.group_id;
          option.dataset.model = model;
          option.textContent = model;
          optgroup.appendChild(option);
        });
        $('model').appendChild(optgroup);
      });
      const saved = localStorage.getItem('prompt-workbench-model');
      if (saved && Array.from($('model').options).some(option => option.value === saved)) $('model').value = saved;
      updateModelNote();
    } catch (error) {
      setServer(false, '本地服务不可用');
      $('model').innerHTML = '<option>无法加载模型</option>';
      toast(error.message + '。请确认已运行 python run.py。');
    }
    updateRunState();
  }

  function updateModelNote() {
    const group = selectedGroup();
    if (!group) return;
    const price = (group.model_pricing || {})[selectedModel()];
    $('model-note').textContent = price ? `输入 $${price.input}/M · 输出 $${price.output}/M · ${price.verified ? '价格有官方来源' : '价格需人工复核'}` : '此模型没有内置价格，只提供 Token 结果';
    localStorage.setItem('prompt-workbench-model', $('model').value);
    previewTokens();
  }
  function updateRunState() {
    const hasText = $('source').value.trim().length > 0;
    const llmReady = $('strategy').value !== 'llm' || $('api-key').value.trim().length > 0;
    $('run').disabled = !hasText || !llmReady || !selectedGroup();
    $('char-count').textContent = `${$('source').value.length.toLocaleString()} 字符`;
  }
  function updateStrategy() {
    const llm = $('strategy').value === 'llm';
    $('llm-config-button').hidden = !llm;
    $('action-hint').textContent = llm ? '系统会单独计算本次 LLM 压缩成本；请求失败时不会伪装成本地结果。' : '本地模式不会上传内容，也不会删除列表、代码和不确定性表达。';
    $('run').querySelector('span').textContent = llm ? '开始 LLM 压缩' : '开始安全优化';
    if (llm && !$('api-key').value.trim() && !$('llm-dialog').open) $('llm-dialog').showModal();
    updateRunState();
  }
  function updateProvider() {
    document.querySelector('.custom-only').hidden = $('provider').value !== 'custom';
    if ($('provider').value === 'deepseek' && $('llm-model').value === 'gpt-4o-mini') $('llm-model').value = 'deepseek-v4-flash';
  }

  function previewTokens() {
    clearTimeout(state.previewTimer);
    const text = $('source').value;
    if (!text.trim() || !selectedGroup()) { $('token-preview').textContent = text ? '选择模型后计数' : '等待输入'; return; }
    $('token-preview').textContent = '正在计数…';
    state.previewTimer = setTimeout(async () => {
      try {
        const data = await post('/api/tokenize', {text, group_ids: [selectedGroup().group_id], mode: 'input'});
        const item = data.results[0];
        $('token-preview').textContent = `${item.available ? '' : '约 '}${item.tokens.toLocaleString()} tokens · ${item.available ? '精确' : '估算'}`;
      } catch (_) { $('token-preview').textContent = '暂时无法计数'; }
    }, 450);
  }

  function buildRequest() {
    const group = selectedGroup();
    const strategy = $('strategy').value;
    const request = {
      text: $('source').value.trim(), strategy, level: 'medium',
      group_id: group.group_id, model_id: selectedModel(),
      economics: {reuse_count: Number($('reuse').value) || 1, expected_output_tokens: 0, cache_hit_rate: (Number($('cache-rate').value) || 0) / 100}
    };
    if ($('target-input-price').value !== '') request.economics.target_input_price = Number($('target-input-price').value);
    if (strategy === 'llm') {
      request.llm_config = {provider: $('provider').value, api_key: $('api-key').value.trim(), model: $('llm-model').value.trim()};
      if ($('api-base').value.trim()) request.llm_config.api_base = $('api-base').value.trim();
      if ($('llm-input-price').value !== '') request.llm_config.input_price = Number($('llm-input-price').value);
      if ($('llm-output-price').value !== '') request.llm_config.output_price = Number($('llm-output-price').value);
    }
    return request;
  }

  async function run() {
    if ($('run').disabled) return;
    document.body.classList.add('loading'); $('run').disabled = true;
    $('run').querySelector('span').textContent = '正在分析';
    try {
      const result = await post('/api/compress', buildRequest());
      state.last = result; render(result);
      document.querySelector('.steps li:nth-child(3)').classList.add('active');
    } catch (error) { toast(error.message); }
    finally { document.body.classList.remove('loading'); updateStrategy(); }
  }

  function render(data) {
    document.body.classList.add('show-result');
    $('empty-state').hidden = true; $('result').hidden = false;
    const gid = selectedGroup().group_id;
    const original = data.original_tokens[gid] || 0;
    const compressed = data.compressed_tokens[gid] || 0;
    const saved = data.savings.tokens_saved;
    $('original-tokens').textContent = original.toLocaleString();
    $('compressed-tokens').textContent = compressed.toLocaleString();
    $('saved-tokens').textContent = `${saved >= 0 ? '−' : '+'}${Math.abs(saved).toLocaleString()} (${Math.abs(data.savings.percentage)}%)`;
    $('saved-tokens').style.color = saved >= 0 ? '' : 'var(--bad)';
    $('output').value = data.compressed_text;
    const exact = !data.token_count_method.includes('estimate');
    $('trust-badge').className = 'trust ' + (exact ? 'exact' : 'estimate');
    $('trust-badge').textContent = data.status === 'rejected' ? '✕ 结构校验未通过' : data.status === 'no_change' ? '— 无有效减少' : exact ? '✓ 精确且已降 Token' : '≈ 已减少（Token 为估算）';
    $('copy').disabled = data.status !== 'completed';
    $('download').disabled = data.status !== 'completed';
    $('method-label').textContent = data.strategy === 'llm' ? 'LLM 语义压缩' : '安全本地清理';
    $('warnings').innerHTML = (data.warnings || []).map(w => `<div class="notice">${escapeHtml(w)}</div>`).join('');
    const econ = data.economics;
    $('per-use').textContent = money(econ.per_use_savings_usd);
    $('compression-cost').textContent = money(econ.compression_cost_usd);
    $('net-saving').textContent = money(econ.net_savings_usd);
    $('break-even').textContent = econ.break_even_uses == null ? (data.strategy === 'rule' ? '立即' : '无法计算') : `${econ.break_even_uses.toLocaleString()} 次`;
    const profit = $('profit-state');
    profit.className = econ.profitable === true ? 'profit-good' : econ.profitable === false ? 'profit-bad' : '';
    profit.textContent = econ.profitable === true ? '✓ 当前场景可回本' : econ.profitable === false ? '当前场景未回本' : '数据不足';
    $('pricing-source').innerHTML = econ.pricing_source === 'user' ? '使用你本次输入的目标模型价格。' : econ.pricing_source ? `价格日期 ${escapeHtml(econ.pricing_as_of || '未知')} · <a href="${escapeHtml(econ.pricing_source)}" target="_blank" rel="noreferrer">查看官方来源</a>` : '价格没有官方来源，请填写目标模型输入价后计算费用。';
    const changes = data.changes || [];
    $('change-count').textContent = `(${changes.length})`;
    $('change-list').innerHTML = changes.length ? changes.map(change => `<li><b>${escapeHtml(change.rule)}</b></li>`).join('') : '<li>没有执行任何删除，原文已保留。</li>';
    if (window.innerWidth < 1050) $('result').scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  async function copyResult() { try { await navigator.clipboard.writeText($('output').value); toast('已复制到剪贴板'); } catch (_) { $('output').select(); document.execCommand('copy'); toast('已复制'); } }
  function download() { const blob = new Blob([$('output').value], {type:'text/plain;charset=utf-8'}); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'optimized-prompt.txt'; link.click(); URL.revokeObjectURL(link.href); }
  function useResult() { $('source').value = $('output').value; $('empty-state').hidden = false; $('result').hidden = true; document.body.classList.remove('show-result'); state.last = null; updateRunState(); previewTokens(); $('source').focus(); toast('结果已放回编辑区'); }

  function selectResultTab(name) {
    document.querySelectorAll('[data-result-tab]').forEach(button => button.classList.toggle('active', button.dataset.resultTab === name));
    document.querySelectorAll('[data-result-pane]').forEach(pane => pane.classList.toggle('active', pane.dataset.resultPane === name));
  }

  async function loadTokenizerStatus() {
    $('tokenizer-list').innerHTML = '<p>正在检查本机缓存…</p>';
    try {
      const data = await api('/api/tokenizers/status');
      $('tokenizer-list').innerHTML = data.tokenizers.map(item => `<div class="tokenizer-item"><div><b>${escapeHtml(item.group_id)}</b><br><span>${escapeHtml(item.message)}</span></div><em class="tokenizer-state ${item.ready ? 'ready' : 'missing'}">${item.ready ? '精确' : '需准备'}</em></div>`).join('');
      const running = ['queued', 'running'].includes(data.job.state);
      $('prepare-tokenizers').disabled = running;
      $('prepare-tokenizers').querySelector('span').textContent = running ? (data.job.message || '正在准备…') : '准备全部分词器';
      if (running) setTimeout(loadTokenizerStatus, 1800);
      if (data.job.state === 'completed') toast(data.job.message);
    } catch (error) { $('tokenizer-list').innerHTML = `<div class="notice">${escapeHtml(error.message)}</div>`; }
  }

  async function prepareTokenizers() {
    $('prepare-tokenizers').disabled = true;
    $('prepare-tokenizers').querySelector('span').textContent = '正在启动下载…';
    try {
      await post('/api/tokenizers/prepare', {group_ids: []});
      setTimeout(loadTokenizerStatus, 500);
    } catch (error) { toast(error.message); $('prepare-tokenizers').disabled = false; }
  }

  $('source').addEventListener('input', () => { updateRunState(); previewTokens(); });
  $('model').addEventListener('change', updateModelNote);
  $('strategy').addEventListener('change', updateStrategy);
  $('provider').addEventListener('change', updateProvider);
  $('api-key').addEventListener('input', updateRunState);
  $('run').addEventListener('click', run);
  $('copy').addEventListener('click', copyResult);
  $('download').addEventListener('click', download);
  $('use-result').addEventListener('click', useResult);
  $('back-editor').addEventListener('click', () => document.body.classList.remove('show-result'));
  $('llm-config-button').addEventListener('click', () => $('llm-dialog').showModal());
  $('llm-save').addEventListener('click', () => { $('llm-dialog').close(); updateRunState(); toast('LLM 设置仅在本次页面中生效'); });
  $('tokenizer-button').addEventListener('click', () => { $('tokenizer-dialog').showModal(); loadTokenizerStatus(); });
  $('refresh-tokenizers').addEventListener('click', loadTokenizerStatus);
  $('prepare-tokenizers').addEventListener('click', prepareTokenizers);
  document.querySelectorAll('[data-result-tab]').forEach(button => button.addEventListener('click', () => selectResultTab(button.dataset.resultTab)));
  document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => { $('source').value = examples[button.dataset.example]; updateRunState(); previewTokens(); $('source').focus(); }));
  document.addEventListener('keydown', event => { if (event.ctrlKey && event.key === 'Enter') run(); });
  $('help-button').addEventListener('click', () => $('help-dialog').showModal());
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(button.dataset.close).close()));
  boot();
})();
