(function() {
"use strict";

// =============================================================
// Prompt Optimization Workstation v4
// =============================================================
var $ = function(id) { return document.getElementById(id); };
var esc = function(t) { if (!t) return ''; return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); };
var fmt = function(n) { if (n==null||isNaN(n)) return '--'; return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g,','); };
var fmt$ = function(n) { if (n==null||isNaN(n)) return '$--'; if (Math.abs(n)<0.0001) return '$0'; return '$'+n.toFixed(4); };

// ---- State ----
var STATE = {
  groupId: 'o200k_base',
  inputText: '',
  strategy: 'rule',
  level: 'medium',
  compressedText: '',
  changes: [],
  lastResult: null,
  monthlyCalls: 10000,
  llmProvider: 'openai',
  llmModel: 'gpt-4o-mini',
  llmApiKey: '',
  llmApiBase: ''
};

// ---- Model data ----
var MODEL_GROUPS = [];
var FALLBACK = [
  {id:'o200k_base', displayName:'OpenAI (o200k_base)', models:['GPT-5.6 Luna'], pricing:{input:1.0,output:6.0,cacheHit:0.1}},
  {id:'cl100k_base', displayName:'OpenAI Legacy (cl100k_base)', models:['GPT-4-turbo'], pricing:{input:10.0,output:30.0}},
  {id:'llama3', displayName:'Meta Llama 4', models:['Llama 4 Maverick'], pricing:{input:0.27,output:0.85,cacheHit:0.09}},
  {id:'qwen', displayName:'Alibaba Qwen 3', models:['Qwen 3.7 Plus'], pricing:{input:0.32,output:1.28,cacheHit:0.10}},
  {id:'deepseek_v4', displayName:'DeepSeek V4', models:['DeepSeek V4 Flash'], pricing:{input:0.14,output:0.28,cacheHit:0.0028}},
  {id:'mistral', displayName:'Mistral AI', models:['Mistral Large 3'], pricing:{input:0.50,output:1.50,cacheHit:0.25}},
  {id:'gemma', displayName:'Google Gemma', models:['Gemma 4 12B'], pricing:{input:0.15,output:0.60,cacheHit:0.10}},
  {id:'glm', displayName:'Z.ai GLM-4.7', models:['GLM-4.7'], pricing:{input:0.60,output:2.20,cacheHit:0.11}}
];

function getGroup(id) { return MODEL_GROUPS.find(function(g) { return g.id === id; }); }

// ---- API helpers ----
function apiPost(path, body) {
  return fetch(path, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) })
    .then(function(r) { if (!r.ok) return r.json().then(function(d) { throw new Error(d.detail||r.statusText); }); return r.json(); });
}

// ---- Token estimation fallback ----
function countCJK(t) { var m = t.match(/[一-鿿㐀-䶿＀-￯　-〿]/g); return m?m.length:0; }
var TCOEF = {o200k_base:[0.25,0.65],cl100k_base:[0.25,0.65],llama3:[0.28,0.70],qwen:[0.30,0.45],deepseek_v4:[0.30,0.45],mistral:[0.28,0.55],gemma:[0.28,0.55],glm:[0.30,0.45]};
function estTokens(t,gid) { if(!t)return 0; var cjk=countCJK(t),asc=t.length-cjk,c=TCOEF[gid]||[0.25,0.60]; return Math.max(1,Math.ceil(asc*c[0]+cjk*c[1])); }

// ---- Fetch models from backend ----
function loadModels() {
  function mapGroup(g) {
    var p = g.pricing;
    return {id:g.group_id, displayName:g.display_name, provider:g.provider||'', type:g.type||'open',
      models:g.models||[], maxTokens:g.max_tokens, vocabSize:g.vocab_size, library:g.library, encoding:g.encoding,
      pricing:p?{input:p.input,output:p.output,cacheHit:p.cache_hit}:null};
  }
  try { var c = sessionStorage.getItem('mg'); if (c) { var p = JSON.parse(c); if (p.length) return Promise.resolve(p); } } catch(e){}
  return fetch('/api/models').then(function(r) { return r.json(); })
    .then(function(d) { var g = d.groups.map(mapGroup); try{sessionStorage.setItem('mg',JSON.stringify(g));}catch(e){} return g; })
    .catch(function() { return FALLBACK; });
}

// ---- Populate selectors ----
function populateSelectors() {
  var sel = $('global-model-selector'); if (!sel) return;
  sel.innerHTML = '';
  MODEL_GROUPS.forEach(function(g) {
    var o = document.createElement('option'); o.value = g.id;
    o.textContent = g.displayName + ((g.models&&g.models[0])?' ('+g.models[0]+')':'');
    if (g.id === STATE.groupId) o.selected = true;
    sel.appendChild(o);
  });
  // Cost model selector
  var cs = $('cost-model'); if (!cs) return;
  cs.innerHTML = '';
  ['GPT-5.6 Luna','GPT-4o','GPT-4o-mini','DeepSeek V4 Flash','DeepSeek V4 Pro','Qwen 3.7 Plus','Llama 4 Maverick','Mistral Large 3','Gemma 4 12B','GLM-4.7'].forEach(function(m) {
    var o = document.createElement('option'); o.value = m; o.textContent = m; cs.appendChild(o);
  });
}

// ---- Local rule compression (fast preview, backend is authoritative) ----
function compressLocal(text, level) {
  if (!text||!text.trim()) return {compressedText:text,changes:[],stats:{originalChars:0,compressedChars:0,operationsCount:0}};
  var blocks = [];
  var rest = text.replace(/```[\s\S]*?```/g, function(m) { blocks.push(m); return '\x00CB'+(blocks.length-1)+'\x00'; });

  // Level 1
  var rules = [
    {re:/\n{3,}/g, to:'\n\n'}, {re:/([。！？,!?])\1+/g, to:'$1'}, {re:/[ \t]{2,}/g, to:' '}, {re:/^[ \t]+|[ \t]+$/gm, to:''}
  ];
  // Level 2
  if (level==='medium'||level==='aggressive') {
    rules.push(
      {re:/(那个|就是说|然后呢|对吧|对不对|你知道吗|说白了|说实话|讲道理)/g, to:''},
      {re:/(非常|十分|特别(?!是)|极其|相当|格外|挺|蛮|比较)/g, to:''},
      {re:/(可能会|大概|或许|也许|似乎|好像|貌似|大约)/g, to:''},
      {re:/请(?!教|示|客|求|假|战|缨|罪|愿|命|功)(你|您)?(帮我|帮忙|协助|给)?(我)?((?:分析|看看|查看|检查|处理|做|弄|写|改|翻译|总结|整理|优化|审查|解释|说明|介绍|描述|展示|列出|生成|创建))?(一下|一遍|一次|下|一下下)?[，,]?/g, to:'$4'},
      {re:/(谢谢|感谢|多谢|感激)(你|您)?(的(?:帮助|支持|协助|指导|建议|意见|回复|解答|鼓励|关心|关注|配合|理解|信任|认可|好评))?(了|啊|啦|哦|呀)?[!！。，]*/g, to:''},
      {re:/(能否|能不能|可不可以|是否可以|麻烦|劳烦|拜托)(你|您)?(帮我|帮忙|协助)?(我)?[，,]?/g, to:''},
      {re:/(?:的|和)(?:帮助|支持|协助|指导|建议|意见|回复|解答|鼓励|关心|关注|配合|理解|信任|认可|好评)[!！。，；;]*/g, to:''},
      // EN
      {re:/\b(basically|essentially|actually|literally|honestly|frankly)\b[ ,]*/gi, to:''},
      {re:/\b(really|very|quite|rather|pretty|extremely|highly|particularly)\b *(?=much|important|good|bad|big|small|fast|slow|easy|hard|simple|complex)/gi, to:''},
      {re:/\b(kind of|sort of|a little bit|a bit)\b ?/gi, to:''},
      {re:/\b(I think|I believe|I feel like|in my opinion|it seems to me that|as far as I can tell)\b[ ,]*/gi, to:''},
      {re:/\b(just|simply) /gi, to:''},
      {re:/(C|c)ould you (please |kindly |be so kind as to )?(help me |assist me in |do me a favor and |please )?/g, to:''},
      {re:/(I would (?:really |greatly |very much )?(?:appreciate it|be grateful) if you (?:could|would)|I would (?:really |greatly |very much )?like you to|I want you to|I need you to|I'd like you to)[ ,]*(?:help me |please )?/gi, to:''},
      {re:/\b(help me |assist me in )\b/gi, to:''},
      {re:/(Thank you|Thanks|Much appreciated|Many thanks|Thanks a lot|Thank you so much)(?: for [^.?!\n]+?)?[!., ]*(?=[\n]|$|[A-Z])/g, to:''},
      {re:/(make sure to|be sure to|don't forget to|remember to) /gi, to:''},
      {re:/\bI(?:'m| am) (?:very |so |really |extremely )?grateful for your (?:assistance|help|support|time|guidance)\b[!., ]*/gi, to:''},
      {re:/\bI look forward to (?:hearing from you|your reply|your response|working with you)\b[!., ]*/gi, to:''}
    );
  }
  // Level 3
  if (level==='aggressive') {
    rules.push(
      {re:/(祝你|祝您|希望|期待|盼|愿)(你|您)?.*$/gm, to:''},
      {re:/(麻烦|劳驾|打扰)(你|您)(一下|了)?[，,]?/g, to:''},
      {re:/(不好意思|抱歉|对不起)[，,]?/g, to:''},
      {re:/给(你|您)?(添麻烦|带来不便|增加工作量)[了]?[。！，]*/g, to:''},
      {re:/(让我们|我们来|咱们)(一起)?(看看|来看|看一下|来分析|来分析一下|看看怎么)/g, to:''},
      {re:/(怎么样|如何|行不行|可不可以|可以吗)[？?]?/g, to:''},
      {re:/(你|您)(觉得|认为|看|觉得怎么样)[？?]?/g, to:''},
      {re:/\n-\s*/g, to:'；'},
      {re:/(I would (?:really |greatly |very much )?appreciate it if you (?:could|would)|I would (?:really |greatly |very much )?be grateful if you would|it would be great if you could)[ ,]*(?:help me |please )?/gi, to:''},
      {re:/(Please note that|It is important to note that|Keep in mind that|Bear in mind that) /gi, to:''},
      {re:/[Cc]an you (tell me|explain|show me|describe|elaborate on) /g, to:''},
      {re:/^[Tt]hat /gm, to:''},
      {re:/\bat your earliest convenience\b[!., ]*/gi, to:''},
      {re:/\bif it(?:'s| is) not too much trouble\b[!., ]*/gi, to:''},
      {re:/\b(in the event that|in the case that)\b/gi, to:'if'},
      {re:/\b(a large number of|a great deal of|a lot of|a bunch of)\b/gi, to:'many'},
      {re:/\b(the majority of)\b/gi, to:'most'},
      {re:/\b(utilize|make use of|take advantage of)\b/gi, to:'use'},
      {re:/\b(commence|initiate)\b/gi, to:'start'}
    );
  }

  var result = rest, changes = [];
  for (var i=0; i<rules.length; i++) {
    var prev = result;
    result = result.replace(rules[i].re, rules[i].to);
    if (result !== prev) changes.push({type:'rule',rule:rules[i].re.toString().substring(1,35),original:prev.substring(0,30),replaced:result.substring(0,30)});
  }
  for (var j=blocks.length-1; j>=0; j--) result = result.replace('\x00CB'+j+'\x00', blocks[j]);
  result = result.replace(/\n{3,}/g,'\n\n').replace(/[ ]{2,}/g,' ').trim();
  return {compressedText:result, changes:changes, stats:{originalChars:text.length,compressedChars:result.length,operationsCount:changes.length}};
}

// ============================================================================
// DASHBOARD RENDERING
// ============================================================================

// Helper: cost for a given group
function tokenCost(tokens, groupId, mode) {
  var g = getGroup(groupId); if (!g||!g.pricing) return 0;
  var p = (mode==='cache'&&g.pricing.cacheHit!=null)?g.pricing.cacheHit:g.pricing.input;
  return tokens*p/1000000;
}

function monthlyCostEst(groupId, inTok, outTok, calls) {
  var g = getGroup(groupId); if (!g||!g.pricing) return {total:0,inputCost:0,outputCost:0};
  var ic = inTok*calls*g.pricing.input/1000000;
  var oc = outTok*calls*g.pricing.output/1000000;
  return {total:ic+oc, inputCost:ic, outputCost:oc};
}

function showDash() {
  $('dash-placeholder').style.display = 'none';
  $('card-metrics').style.display = '';
  $('card-model-compare').style.display = '';
  $('card-cost').style.display = '';
  $('card-changes').style.display = '';
}

function hideDash() {
  $('dash-placeholder').style.display = '';
  $('card-metrics').style.display = 'none';
  $('card-model-compare').style.display = 'none';
  $('card-cost').style.display = 'none';
  $('card-changes').style.display = 'none';
}

function renderMetrics(r) {
  if (!r) return;
  var orig = r.originalTokens, comp = r.compressedTokens;
  var saved = orig - comp, pct = orig>0?Math.round((1-comp/orig)*100):0;

  $('metric-orig').textContent = fmt(orig);
  $('metric-comp').textContent = fmt(comp);
  $('metric-saved-pct').textContent = '↓ '+pct+'%';
  $('metrics-badge').textContent = '↓'+pct+'%';
  $('savings-bar-fill').style.width = pct+'%';

  var g = getGroup(STATE.groupId);
  var ppM = g&&g.pricing?g.pricing.input:0;
  var origCost = tokenCost(orig, STATE.groupId);
  var compCost = tokenCost(comp, STATE.groupId);
  var perCallSave = origCost - compCost;

  var outTok = Math.round(orig*0.3);
  var mc = monthlyCostEst(STATE.groupId, orig, outTok, STATE.monthlyCalls);
  var mc2 = monthlyCostEst(STATE.groupId, comp, outTok, STATE.monthlyCalls);
  var monSave = mc.total - mc2.total;

  var tag = r.strategy === 'llm' ? '[LLM] ' : '';
  $('meta-tokens-saved').textContent = tag + '节省 ' + fmt(saved) + ' tokens';
  $('meta-monthly').textContent = '月省 ' + fmt$(monSave);
  $('meta-yearly').textContent = '年省 ' + fmt$(monSave*12);
  $('meta-time').textContent = new Date().toLocaleTimeString('zh-CN');
}

function renderModelTable(r) {
  var tbody = $('model-compare-body'); if (!tbody) return;
  if (!STATE.inputText||!STATE.compressedText) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-dim);padding:12px;">输入文本以查看多模型对比</td></tr>';
    return;
  }
  var mmt = (r&&r.multiModelTokens)?r.multiModelTokens:{};
  var groups = MODEL_GROUPS.filter(function(g){return g.pricing;});
  if (!groups.length) groups = MODEL_GROUPS;

  tbody.innerHTML = '';
  for (var i=0; i<groups.length; i++) {
    var g = groups[i];
    var orig, comp;
    if (mmt[g.id]) { orig = mmt[g.id].orig; comp = mmt[g.id].comp; }
    else { orig = estTokens(STATE.inputText, g.id); comp = estTokens(STATE.compressedText, g.id); }
    var pct = orig>0?Math.round((1-comp/orig)*100):0;
    var color = pct>15?'var(--success)':pct>5?'var(--warning)':'var(--text-muted)';
    var origCost = tokenCost(orig, g.id), compCost = tokenCost(comp, g.id);
    var savedCost = origCost - compCost;
    var tr = document.createElement('tr');
    tr.innerHTML = '<td>'+esc(g.displayName)+'</td>'+
      '<td style="text-align:right">'+fmt(orig)+'</td>'+
      '<td style="text-align:right;color:var(--success)">'+fmt(comp)+'</td>'+
      '<td style="text-align:right;color:'+color+'">'+pct+'%</td>'+
      '<td style="text-align:right;color:'+(savedCost>0?'var(--success)':'var(--text-muted)')+'">'+fmt$(savedCost)+'</td>';
    tbody.appendChild(tr);
  }
  var badge = $('model-compare-badge');
  if (badge) badge.textContent = groups.length+' models' + (Object.keys(mmt).length?' (precise)':' (est.)');
}

function renderCostSim() {
  if (!STATE.lastResult) return;
  var g = getGroup(STATE.groupId); if (!g||!g.pricing) return;
  var orig = STATE.lastResult.originalTokens, comp = STATE.lastResult.compressedTokens;
  var calls = STATE.monthlyCalls, outTok = Math.round(orig*0.3);
  var bc = monthlyCostEst(STATE.groupId, orig, outTok, calls);
  var ac = monthlyCostEst(STATE.groupId, comp, outTok, calls);
  var perCallOrig = (orig*g.pricing.input + outTok*g.pricing.output)/1000000;
  var perCallComp = (comp*g.pricing.input + outTok*g.pricing.output)/1000000;
  var maxC = Math.max(bc.total, ac.total, 0.01);
  $('cost-bar-before').style.width = Math.min(bc.total/maxC*100,100)+'%';
  $('cost-bar-after').style.width = Math.min(ac.total/maxC*100,100)+'%';
  $('cost-amt-before').textContent = fmt$(bc.total);
  $('cost-amt-after').textContent = fmt$(ac.total);
  $('cost-annual-save').textContent = '每次调用: '+fmt$(perCallOrig)+' → '+fmt$(perCallComp)+' | 年省: '+fmt$((bc.total-ac.total)*12);
  var saved = bc.total - ac.total;
  $('cost-summary-inline').textContent = '每次 '+fmt$(perCallOrig)+' → '+fmt$(perCallComp)+' | 月省 '+fmt$(saved)+' | 年省 '+fmt$(saved*12);
}

function renderChanges(changes) {
  var log = $('changes-list'); if (!log) return;
  var count = changes?changes.length:0;
  $('changes-summary-inline').textContent = count+' 条规则变更';
  if (!changes||!count) { log.innerHTML = '<div class="change-empty">尚无变更记录</div>'; return; }
  var disp = changes.slice(-80);
  log.innerHTML = disp.map(function(c,i) {
    var n = changes.length-disp.length+i+1;
    return '<div class="change-item"><span class="change-rule">#'+n+' ['+esc(c.rule)+']</span>'+
      '<span class="change-detail"><span class="orig-text-inline">"'+esc((c.original||'').substring(0,30))+'"</span>'+
      '<span class="arrow-change">→</span><span class="new-text-inline">"'+esc((c.replaced||'').substring(0,30))+'"</span></span></div>';
  }).join('');
}

function updateStatus(msg, level) {
  var el = $('status-text'); if (!el) return;
  el.textContent = msg;
  el.style.color = level==='error'?'var(--danger)':level==='success'?'var(--success)':'var(--text-secondary)';
  var dot = $('status-dot'); if (dot) dot.style.background = level==='error'?'var(--danger)':'var(--success)';
  var g = getGroup(STATE.groupId);
  var me = $('status-model'); if (me&&g) me.textContent = (g.models&&g.models[0])?g.models[0]:g.displayName;
  if (STATE.lastResult) {
    var se = $('status-savings'); if (se) {
      var p = STATE.lastResult.originalTokens>0?Math.round((1-STATE.lastResult.compressedTokens/STATE.lastResult.originalTokens)*100):0;
      se.textContent = 'Token 节省: '+p+'%';
    }
  }
  if (level==='success') { var te = $('status-time'); if (te) te.textContent = '上次压缩: '+new Date().toLocaleTimeString('zh-CN'); }
}

// ============================================================================
// COMPRESSION PIPELINE
// ============================================================================
var _busy = false;

function runCompression() {
  if (_busy) return;
  var textarea = $('input-textarea'); if (!textarea) return;
  var text = textarea.value;
  if (!text||!text.trim()) {
    textarea.style.borderColor = 'var(--danger)';
    setTimeout(function(){ textarea.style.borderColor = ''; }, 2000);
    updateStatus('⚠ 请输入文本', 'error');
    return;
  }
  STATE.inputText = text;
  _busy = true;
  var btn = $('btn-compress'); var origBtn = btn.textContent;
  btn.textContent = '压缩中...'; btn.disabled = true;
  updateStatus('压缩中...', 'info');

  var strategy = STATE.strategy;
  var level = STATE.level;
  var ALL_GROUPS = ['o200k_base','cl100k_base','llama3','qwen','deepseek_v4','mistral','glm','gemma'];

  // --- Step 1: compress ---
  var compressPromise;
  if (strategy === 'rule') {
    // Local first, then backend override
    var local = compressLocal(text, level);
    compressPromise = apiPost('/api/compress', {text:text, strategy:'rule', level:level})
      .then(function(be) {
        if (be&&be.compressed_text) {
          local.compressedText = be.compressed_text;
          local.changes = be.changes||local.changes;
          local.stats.compressedChars = be.compressed_text.length;
          local.stats.operationsCount = (be.changes||[]).length;
        }
        return local;
      })
      .catch(function() { return local; });
  } else {
    // LLM
    if (!STATE.llmApiKey) {
      $('llm-api-error').textContent = '⚠ 请填写 API Key';
      $('llm-api-error').style.display = 'block';
      updateStatus('⚠ LLM 压缩需要 API Key', 'error');
      _busy = false; btn.textContent = origBtn; btn.disabled = false;
      return;
    }
    compressPromise = apiPost('/api/compress', {
      text:text, strategy:'llm', level:'medium',
      target_ratio:0.4,
      llm_config:{provider:STATE.llmProvider, api_key:STATE.llmApiKey, model:STATE.llmModel, api_base:STATE.llmApiBase||undefined}
    }).then(function(llmResp) {
      // Detect fallback
      var fallback = llmResp.changes&&llmResp.changes[0]&&llmResp.changes[0].type==='heuristic_fallback';
      return {
        compressedText: llmResp.compressed_text,
        changes: llmResp.changes||[],
        stats: {originalChars:text.length, compressedChars:llmResp.compressed_text.length, operationsCount:(llmResp.changes||[]).length},
        llmFallback: fallback,
        llmOrigTokens: llmResp.original_tokens,
        llmCompTokens: llmResp.compressed_tokens
      };
    });
  }

  compressPromise.then(function(result) {
    // --- Step 2: get token counts for ALL groups ---
    return apiPost('/api/tokenize', {text:text, group_ids:ALL_GROUPS, mode:'input'}).then(function(tOrig) {
      return apiPost('/api/tokenize', {text:result.compressedText, group_ids:ALL_GROUPS, mode:'input'}).then(function(tComp) {
        var mmt = {};
        for (var i=0; i<tOrig.results.length; i++) {
          var gid = tOrig.results[i].group_id;
          mmt[gid] = {orig:tOrig.results[i].tokens, comp:tComp.results[i].tokens};
        }
        var origTok = mmt[STATE.groupId]?mmt[STATE.groupId].orig:0;
        var compTok = mmt[STATE.groupId]?mmt[STATE.groupId].comp:0;
        return {
          compressedText: result.compressedText,
          changes: result.changes,
          stats: result.stats,
          originalTokens: origTok,
          compressedTokens: compTok,
          multiModelTokens: mmt,
          precise: true,
          strategy: strategy,
          level: level,
          llmFallback: result.llmFallback||false
        };
      });
    }).catch(function() {
      // Tokenize failed — use estimates
      var mmt = {};
      ALL_GROUPS.forEach(function(gid) { mmt[gid] = {orig:estTokens(text,gid), comp:estTokens(result.compressedText,gid)}; });
      return {
        compressedText: result.compressedText,
        changes: result.changes,
        stats: result.stats,
        originalTokens: estTokens(text, STATE.groupId),
        compressedTokens: estTokens(result.compressedText, STATE.groupId),
        multiModelTokens: mmt,
        precise: false,
        strategy: strategy,
        level: level,
        llmFallback: result.llmFallback||false
      };
    });
  }).then(function(finalResult) {
    // --- Step 3: update UI ---
    STATE.compressedText = finalResult.compressedText;
    STATE.changes = finalResult.changes;
    STATE.lastResult = finalResult;

    $('output-textarea').value = finalResult.compressedText;
    $('output-stats').textContent = fmt(finalResult.compressedText.length) + ' 字符';
    $('btn-copy-output').disabled = false;
    $('btn-undo').disabled = false;

    showDash();
    renderMetrics(finalResult);
    renderModelTable(finalResult);
    renderCostSim();
    renderChanges(finalResult.changes);

    var pct = finalResult.originalTokens>0?Math.round((1-finalResult.compressedTokens/finalResult.originalTokens)*100):0;
    var msg = '✅ 压缩完成 — '+finalResult.stats.operationsCount+' 次操作, 节省 '+pct+'% tokens'+(finalResult.precise?' (精确)':'');
    var lvl = 'success';

    if (finalResult.llmFallback) {
      var fb = (finalResult.changes&&finalResult.changes[0])?finalResult.changes[0].rule:'';
      msg = '⚠ LLM 调用失败，已回退到规则引擎压缩 — '+fb;
      lvl = 'error';
      var ee = $('llm-api-error');
      if (ee) { ee.textContent = '⚠ LLM API 调用失败: '+fb+'。已自动回退到本地规则引擎。请检查 API Key 和提供商设置。'; ee.style.display = 'block'; }
    }
    updateStatus(msg, lvl);
  }).catch(function(err) {
    updateStatus('⚠ 压缩失败: '+err.message, 'error');
  }).then(function() {
    _busy = false; btn.textContent = origBtn; btn.disabled = false;
  });
}

// ---- Export / Undo ----
function copyOutput() {
  if (!STATE.compressedText) return;
  navigator.clipboard.writeText(STATE.compressedText).then(function() {
    updateStatus('✅ 已复制到剪贴板', 'success');
  }).catch(function() {
    var ta = document.createElement('textarea'); ta.value = STATE.compressedText;
    ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
    updateStatus('✅ 已复制到剪贴板', 'success');
  });
}

function undoCompression() {
  STATE.compressedText = ''; STATE.changes = []; STATE.lastResult = null;
  $('output-textarea').value = ''; $('output-stats').textContent = '';
  $('btn-copy-output').disabled = true; $('btn-undo').disabled = true;
  hideDash();
  updateStatus('已撤销压缩', 'info');
}

// ---- Event binding ----
function bindEvents() {
  var inp = $('input-textarea');
  if (inp) {
    inp.addEventListener('input', function() { STATE.inputText = inp.value;
      $('input-stats').textContent = fmt(inp.value.length)+' 字符 · ~'+fmt(estTokens(inp.value,STATE.groupId))+' tokens';
    });
    inp.addEventListener('keydown', function(e) { if ((e.ctrlKey||e.metaKey)&&e.key==='Enter') { e.preventDefault(); runCompression(); } });
  }
  var ss = $('compression-strategy'); if (ss) ss.addEventListener('change', function() { STATE.strategy = ss.value;
    var lc = $('llm-config'); if (lc) lc.classList.toggle('visible', ss.value==='llm'); });
  var ls = $('compression-level'); if (ls) ls.addEventListener('change', function() { STATE.level = ls.value; });
  var gs = $('global-model-selector'); if (gs) gs.addEventListener('change', function() { STATE.groupId = gs.value;
    try{localStorage.setItem('tc_lm',JSON.stringify(STATE.groupId));}catch(e){} if (STATE.lastResult) { renderMetrics(STATE.lastResult); renderModelTable(STATE.lastResult); renderCostSim(); } });
  $('btn-compress').addEventListener('click', runCompression);
  $('btn-copy-output').addEventListener('click', copyOutput);
  $('btn-undo').addEventListener('click', undoCompression);
  $('cost-calls').addEventListener('input', function() { STATE.monthlyCalls = parseInt($('cost-calls').value,10)||0; renderCostSim(); });
  $('cost-model').addEventListener('change', renderCostSim);

  // LLM inputs
  var lm = $('llm-model'); if (lm) lm.addEventListener('change', function() { STATE.llmModel = lm.value; });
  var lp = $('llm-provider'); if (lp) lp.addEventListener('change', function() { STATE.llmProvider = lp.value;
    var ab = $('llm-apibase-group'); if (ab) ab.style.display = lp.value==='custom'?'':'none'; });
  var lk = $('llm-apikey'); if (lk) lk.addEventListener('input', function() { STATE.llmApiKey = lk.value; $('llm-api-error').style.display = 'none'; });
  var la = $('llm-apibase'); if (la) la.addEventListener('input', function() { STATE.llmApiBase = la.value; });

  document.addEventListener('keydown', function(e) { if (e.key==='Escape'&&STATE.lastResult) { undoCompression(); e.preventDefault(); } });
}

// ---- Init ----
loadModels().then(function(groups) {
  MODEL_GROUPS = groups;
  try { var lm = JSON.parse(localStorage.getItem('tc_lm')); if (lm&&MODEL_GROUPS.some(function(g){return g.id===lm;})) STATE.groupId = lm; } catch(e){}
  populateSelectors();
  $('global-model-selector').value = STATE.groupId;
  bindEvents();
  $('input-stats').textContent = '0 字符 · ~0 tokens';
  updateStatus('已就绪', 'info');
});

// Expose for debugging
window.__TC = { getState:function(){return STATE;}, getModelGroups:function(){return MODEL_GROUPS;}, version:'4.0.0' };
})();
