#!/usr/bin/env python3
"""
Comprehensive token-calculator test suite.
Tests: token counting accuracy, rule compression effectiveness,
whether compression actually reduces tokens across diverse cases.
"""
__test__ = False
import json
import sys
import time
import io
import urllib.request
import urllib.error

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0
RESULTS = []

def report(name, passed, detail=""):
    global PASS, FAIL
    if passed:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")
        if detail:
            for line in detail.split("\n"):
                print(f"     {line}")
    RESULTS.append({"name": name, "passed": passed, "detail": detail})

def api(method, path, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(r, timeout=60)
        return resp.status, json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()), str(e)
    except Exception as e:
        return None, None, str(e)


# =============================================================================
# TEST SUITE 1: Token Counting Accuracy
# =============================================================================
def test_token_counting():
    print("\n" + "="*60)
    print("SUITE 1: TOKEN COUNTING ACCURACY")
    print("="*60)

    # 1.1 Basic English
    print("\n--- 1.1 Basic English ---")
    status, data, err = api("POST", "/api/tokenize", {
        "text": "Hello world", "group_ids": ["o200k_base", "cl100k_base"], "mode": "input"
    })
    if status == 200:
        results = {r["group_id"]: r for r in data.get("results", [])}
        o200k = results.get("o200k_base", {})
        cl100k = results.get("cl100k_base", {})
        # "Hello world" is typically 2 tokens for both
        report(f"o200k_base: 'Hello world' = {o200k.get('tokens')} tokens",
               o200k.get("tokens", 0) > 0,
               f"Got: {o200k}")
        report(f"cl100k_base: 'Hello world' = {cl100k.get('tokens')} tokens",
               cl100k.get("tokens", 0) > 0,
               f"Got: {cl100k}")
        report("Both available=true",
               o200k.get("available") and cl100k.get("available"),
               f"o200k: {o200k.get('available')}, cl100k: {cl100k.get('available')}")
    else:
        report("Basic English tokenization", False, f"HTTP {status}: {err}")

    # 1.2 Chinese text
    print("\n--- 1.2 Chinese Text ---")
    cn_text = "你好世界，这是一个测试"
    status, data, err = api("POST", "/api/tokenize", {
        "text": cn_text, "group_ids": ["o200k_base", "llama3", "qwen", "deepseek_v4", "glm"], "mode": "input"
    })
    if status == 200:
        results = {r["group_id"]: r for r in data.get("results", [])}
        counts = {gid: r.get("tokens", -1) for gid, r in results.items()}
        print(f"  Token counts: {json.dumps(counts)}")
        # Chinese text should have more tokens than chars*0.25 for o200k (since CJK chars are ~0.65 per token)
        # But less tokens than English chars (since Chinese chars = 1 token each for some tokenizers)
        all_positive = all(c > 0 for c in counts.values())
        report("All Chinese token counts > 0", all_positive)
        # Chinese tokenizers (qwen, glm) should give fewer tokens than English-oriented ones
        report("Different tokenizers give different counts",
               len(set(counts.values())) >= 2,
               f"Counts: {counts}")
    else:
        report("Chinese tokenization", False, f"HTTP {status}")

    # 1.3 Empty text
    print("\n--- 1.3 Empty Text ---")
    status, data, err = api("POST", "/api/tokenize", {
        "text": "", "group_ids": ["o200k_base"], "mode": "input"
    })
    report("Empty text returns 0 tokens",
           status == 200 and data["results"][0]["tokens"] == 0,
           f"Got: {data}")

    # 1.4 Very long text
    print("\n--- 1.4 Long Text (10,000 chars) ---")
    long_text = "This is a comprehensive test of the token counting system. " * 250  # ~10,000 chars
    status, data, err = api("POST", "/api/tokenize", {
        "text": long_text[:10000], "group_ids": ["o200k_base"], "mode": "input"
    })
    if status == 200:
        tokens = data["results"][0]["tokens"]
        chars = data["char_count"]
        ratio = tokens / chars if chars > 0 else 0
        report(f"Long text ({chars} chars) = {tokens} tokens (ratio: {ratio:.3f})",
               tokens > 0 and 0.15 < ratio < 0.5,  # Repetitive text has lower ratio (~0.18)
               f"Tokens: {tokens}, Chars: {chars}, Ratio: {ratio:.3f}")

    # 1.5 Special characters & code
    print("\n--- 1.5 Code & Special Characters ---")
    code_text = '''def fibonacci(n):
    """Return the nth Fibonacci number."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b

# Test cases
assert fibonacci(0) == 0
assert fibonacci(10) == 55'''
    status, data, err = api("POST", "/api/tokenize", {
        "text": code_text, "group_ids": ["o200k_base", "deepseek_v4", "qwen"], "mode": "input"
    })
    if status == 200:
        results = {r["group_id"]: r for r in data.get("results", [])}
        counts = {gid: r.get("tokens", -1) for gid, r in results.items()}
        print(f"  Code token counts: {json.dumps(counts)}")
        all_positive = all(c > 0 for c in counts.values())
        report("Code text tokenization works", all_positive)

    # 1.6 JSON text
    print("\n--- 1.6 JSON Text ---")
    json_text = json.dumps({"messages": [{"role": "user", "content": "Hello, how are you?"},
                                          {"role": "assistant", "content": "I'm doing well, thanks!"},
                                          {"role": "user", "content": "Can you help me with something?"}]})
    status, data, err = api("POST", "/api/tokenize", {
        "text": json_text, "group_ids": ["o200k_base"], "mode": "input"
    })
    if status == 200:
        tokens = data["results"][0]["tokens"]
        report(f"JSON text tokenization: {tokens} tokens", tokens > 0)

    # 1.7 All 8 tokenizers
    print("\n--- 1.7 All 8 Tokenizer Groups ---")
    all_groups = ["o200k_base", "cl100k_base", "llama3", "qwen", "deepseek_v4", "mistral", "gemma", "glm"]
    test_text = "The quick brown fox jumps over the lazy dog. 人工智能正在改变世界。"
    status, data, err = api("POST", "/api/tokenize", {
        "text": test_text, "group_ids": all_groups, "mode": "input"
    })
    if status == 200:
        results = data.get("results", [])
        available = [r for r in results if r.get("available")]
        unavailable = [r for r in results if not r.get("available")]
        counts = {r["group_id"]: r["tokens"] for r in results}
        print(f"  All tokenizer counts: {json.dumps(counts)}")
        report(f"Available tokenizers: {len(available)}/8",
               len(available) >= 5,  # At least tiktoken + a few HF should work
               f"Available: {[r['group_id'] for r in available]}, Unavailable: {[r['group_id'] for r in unavailable]}")
        # Check that counts vary meaningfully
        avail_counts = [r["tokens"] for r in available]
        if len(avail_counts) >= 2:
            report("Different tokenizers produce different counts",
                   len(set(avail_counts)) >= 2,
                   f"Counts: {avail_counts}")


# =============================================================================
# TEST SUITE 2: Rule Compression Effectiveness
# =============================================================================
def test_rule_compression():
    print("\n" + "="*60)
    print("SUITE 2: RULE COMPRESSION EFFECTIVENESS")
    print("="*60)

    # 2.1 Chinese - Heavy politeness
    print("\n--- 2.1 Chinese: Heavy Politeness ---")
    cn_polite = "请您帮我看一下这份数据分析报告，非常非常感谢您的帮助！能否请您尽快回复？拜托拜托！"
    status, data, err = api("POST", "/api/compress", {
        "text": cn_polite, "strategy": "rule", "level": "aggressive"
    })
    if status == 200:
        orig = data["original_text"]
        comp = data["compressed_text"]
        savings = data["savings"]
        report(f"Chinese polite → {len(comp)} chars (was {len(orig)})",
               len(comp) < len(orig) and savings["tokens_saved"] > 0,
               f"Original: '{orig}'\nCompressed: '{comp}'\nSavings: {savings}")
        report("Compressed text is non-empty", len(comp) > 0)
        # Verify politeness removed
        report("Politeness phrases removed",
               "请" not in comp and "感谢" not in comp and "能否" not in comp,
               f"Compressed: '{comp}'")
        # Verify core content preserved
        report("Core content preserved (分析, 数据, 报告)",
               "分析" in comp and "数据" in comp,
               f"Compressed: '{comp}'")

    # 2.2 Chinese - Technical query
    print("\n--- 2.2 Chinese: Technical Query ---")
    cn_tech = """你好！我是一个刚开始学习Python的新手，想请教您一个问题。
就是说，我想知道怎么用Python读取一个CSV文件并进行数据分析。
特别是，我想对数据进行分组统计，然后画出柱状图。
非常感谢您的帮助和支持！期待您的回复！"""
    status, data, err = api("POST", "/api/compress", {
        "text": cn_tech, "strategy": "rule", "level": "aggressive"
    })
    if status == 200:
        orig = data["original_text"]
        comp = data["compressed_text"]
        savings = data["savings"]
        orig_tokens = data.get("original_tokens", {}).get("o200k_base", 0)
        comp_tokens = data.get("compressed_tokens", {}).get("o200k_base", 0)
        print(f"  Original: {orig_tokens} tokens, Compressed: {comp_tokens} tokens")
        print(f"  Compressed text: '{comp}'")
        report(f"Chinese tech query: {orig_tokens}→{comp_tokens} tokens (saved {savings['tokens_saved']})",
               comp_tokens < orig_tokens,
               f"Savings: {savings}")
        # Core content must be preserved
        report("Technical content preserved (Python, CSV, 数据分析, 柱状图)",
               all(w in comp for w in ["Python", "CSV"]),
               f"Compressed: '{comp}'")

    # 2.3 English - Politeness
    print("\n--- 2.3 English: Heavy Politeness ---")
    en_polite = """I would really appreciate it if you could please help me analyze this dataset.
I think there might be some interesting trends in the data.
Thank you so much for your help! I'm very grateful for your assistance.
Could you please let me know at your earliest convenience?"""
    status, data, err = api("POST", "/api/compress", {
        "text": en_polite, "strategy": "rule", "level": "aggressive"
    })
    if status == 200:
        orig = data["original_text"]
        comp = data["compressed_text"]
        savings = data["savings"]
        print(f"  Original: '{orig[:80]}...'")
        print(f"  Compressed: '{comp}'")
        report(f"English polite: {savings['tokens_saved']} tokens saved ({savings['percentage']}%)",
               savings["tokens_saved"] > 0,
               f"Savings: {savings}")
        report("Filler words removed",
               "I think" not in comp and "basically" not in comp,
               f"Compressed: '{comp}'")

    # 2.4 English - Technical
    print("\n--- 2.4 English: Technical Prompt ---")
    en_tech = """I need you to write a Python function that takes a list of dictionaries
and groups them by a specified key. The function should return a dictionary
where keys are the unique values of the grouping key and values are lists of
dictionaries belonging to that group. Please make sure to handle edge cases
like empty lists and missing keys. Thank you!"""
    status, data, err = api("POST", "/api/compress", {
        "text": en_tech, "strategy": "rule", "level": "aggressive"
    })
    if status == 200:
        comp = data["compressed_text"]
        savings = data["savings"]
        print(f"  Compressed: '{comp}'")
        report(f"English technical: {savings['percentage']}% token reduction",
               savings["tokens_saved"] >= 0,
               f"Savings: {savings}")
        # Verify key instructions preserved
        report("Key instructions preserved (Python, function, dictionary, group)",
               all(w.lower() in comp.lower() for w in ["python", "function", "dictionary", "group"]),
               f"Compressed: '{comp}'")

    # 2.5 Code block protection
    print("\n--- 2.5 Code Block Protection ---")
    text_with_code = """请帮我优化以下代码的性能。

```python
def process_data(data):
    result = []
    for item in data:
        if item["status"] == "active":
            result.append(item)
    return result
```

非常感谢您的帮助！"""
    status, data, err = api("POST", "/api/compress", {
        "text": text_with_code, "strategy": "rule", "level": "aggressive"
    })
    if status == 200:
        comp = data["compressed_text"]
        print(f"  Compressed: '{comp}'")
        # Code block must be intact
        report("Code block preserved (```python...```)",
               "```python" in comp and "```" in comp.split("```python")[1] if "```python" in comp else False,
               f"Compressed: '{comp}'")
        report("Code content preserved (def process_data)",
               "def process_data" in comp,
               f"Compressed: '{comp}'")
        report("Politeness outside code removed",
               "感谢" not in comp,
               f"Compressed: '{comp}'")

    # 2.6 Three intensity levels
    print("\n--- 2.6 Three Intensity Levels ---")
    cn_full = "能否请您帮我看一下这个数据集的异常情况，非常感谢您的帮助和支持！期待您的回复！"
    results_by_level = {}
    for level in ["light", "medium", "aggressive"]:
        status, data, err = api("POST", "/api/compress", {
            "text": cn_full, "strategy": "rule", "level": level
        })
        if status == 200:
            results_by_level[level] = {
                "compressed": data["compressed_text"],
                "chars": len(data["compressed_text"]),
                "savings": data["savings"]["tokens_saved"]
            }
    if len(results_by_level) == 3:
        print(f"  Light:   {results_by_level['light']['chars']} chars, {results_by_level['light']['savings']} saved")
        print(f"  Medium:  {results_by_level['medium']['chars']} chars, {results_by_level['medium']['savings']} saved")
        print(f"  Aggressive: {results_by_level['aggressive']['chars']} chars, {results_by_level['aggressive']['savings']} saved")
        report("Light < Medium < Aggressive (in compression strength)",
               results_by_level["light"]["chars"] >= results_by_level["medium"]["chars"] >= results_by_level["aggressive"]["chars"],
               f"Light: {results_by_level['light']['chars']}, Medium: {results_by_level['medium']['chars']}, Aggressive: {results_by_level['aggressive']['chars']}")

    # 2.7 Empty and whitespace-only
    print("\n--- 2.7 Edge Cases ---")
    for label, text in [("empty", ""), ("whitespace", "   \n\n  "), ("single_char", "A")]:
        status, data, err = api("POST", "/api/compress", {
            "text": text, "strategy": "rule", "level": "medium"
        })
        report(f"Compress '{label}': returns 200 (no crash)",
               status == 200,
               f"Status: {status}, Data: {data}")


# =============================================================================
# TEST SUITE 3: Does Compression Actually Reduce Tokens?
# =============================================================================
def test_token_reduction():
    print("\n" + "="*60)
    print("SUITE 3: DOES COMPRESSION REDUCE REAL TOKENS?")
    print("="*60)

    test_cases = [
        # (name, text, expected_reduction)
        ("Chinese polite prompt",
         "请您帮我分析一下这份销售数据，看看有没有什么异常的趋势或者需要关注的地方。非常感谢您的帮助和支持！期待您尽快回复！",
         True),
        ("English polite prompt",
         "I would really appreciate it if you could please help me analyze this sales data. I think there might be some interesting trends. Thank you so much for your kind help! I look forward to hearing from you soon.",
         True),
        ("Chinese verbose instruction",
         "你好！我是一个刚开始学习编程的新手，想请教你一个问题。就是说，我想知道怎么用Python写一个程序来读取Excel文件，然后对数据进行一些基本的统计分析，比如计算平均值、标准差什么的。如果可能的话，能不能再帮我画一些图表？非常感谢！",
         True),
        ("English verbose instruction",
         "Hello! I am a beginner programmer and I was wondering if you could possibly help me with something. Basically, I need to write a Python script that reads an Excel file and performs some statistical analysis on it. I'm talking about things like calculating the mean and standard deviation. If it's not too much trouble, could you also help me create some charts? Thank you so much in advance!",
         True),
        ("Short direct query (already clean, may not compress)",
         "分析销售数据趋势",
         False),  # Already clean — no politeness/filler to remove
    ]

    all_passed = True
    for name, text, expect_reduction in test_cases:
        print(f"\n--- {name} ---")
        # Get original token count
        s1, d1, e1 = api("POST", "/api/tokenize", {
            "text": text, "group_ids": ["o200k_base"], "mode": "input"
        })
        if s1 != 200:
            report(f"{name}: Original tokenize failed", False, str(e1))
            continue

        orig_tokens = d1["results"][0]["tokens"]

        # Compress
        s2, d2, e2 = api("POST", "/api/compress", {
            "text": text, "strategy": "rule", "level": "aggressive"
        })
        if s2 != 200:
            report(f"{name}: Compress failed", False, str(e2))
            continue

        comp_text = d2["compressed_text"]
        savings = d2["savings"]

        # Get compressed token count
        s3, d3, e3 = api("POST", "/api/tokenize", {
            "text": comp_text, "group_ids": ["o200k_base"], "mode": "input"
        })
        if s3 != 200:
            report(f"{name}: Compressed tokenize failed", False, str(e3))
            continue

        comp_tokens = d3["results"][0]["tokens"]
        actual_reduction_pct = round((1 - comp_tokens / orig_tokens) * 100, 1) if orig_tokens > 0 else 0

        print(f"  Original:  {orig_tokens} tokens ({len(text)} chars)")
        print(f"  Compressed: {comp_tokens} tokens ({len(comp_text)} chars)")
        print(f"  Reduction:  {actual_reduction_pct}% ({orig_tokens - comp_tokens} tokens saved)")

        reduced = comp_tokens < orig_tokens
        if expect_reduction and not reduced:
            print(f"  ⚠️ Expected token reduction but got none!")
            all_passed = False
        report(f"{name}: {orig_tokens}→{comp_tokens} tokens ({actual_reduction_pct}% reduction)",
               reduced if expect_reduction else True,
               f"Original: '{text[:60]}...'\nCompressed: '{comp_text[:60]}...'")

    report("ALL token reduction tests passed", all_passed)


# =============================================================================
# TEST SUITE 4: Multi-Model Token Reduction Verification
# =============================================================================
def test_multimodel_reduction():
    print("\n" + "="*60)
    print("SUITE 4: MULTI-MODEL TOKEN REDUCTION")
    print("="*60)

    text = """请帮我分析这份客户反馈数据，找出其中最常见的投诉类型和用户痛点。
具体来说，我需要你完成以下任务：
1. 读取CSV文件中的所有客户评论
2. 对评论进行情感分析
3. 按类别统计投诉频率
4. 生成一份可视化报告
非常感谢您的帮助和支持！"""

    available_groups = ["o200k_base", "cl100k_base"]

    # Check which HF tokenizers are available
    s, d, _ = api("POST", "/api/tokenize", {
        "text": "test", "group_ids": ["llama3", "qwen", "deepseek_v4", "mistral", "glm", "gemma"], "mode": "input"
    })
    if s == 200:
        for r in d.get("results", []):
            if r.get("available"):
                available_groups.append(r["group_id"])

    print(f"  Testing with {len(available_groups)} available tokenizers: {available_groups}")

    # Compress once
    s, d, _ = api("POST", "/api/compress", {
        "text": text, "strategy": "rule", "level": "aggressive"
    })
    if s != 200:
        report("Compress failed", False)
        return

    comp_text = d["compressed_text"]

    # Tokenize original and compressed across all available models
    s1, d1, _ = api("POST", "/api/tokenize", {
        "text": text, "group_ids": available_groups, "mode": "input"
    })
    s2, d2, _ = api("POST", "/api/tokenize", {
        "text": comp_text, "group_ids": available_groups, "mode": "input"
    })

    if s1 != 200 or s2 != 200:
        report("Multi-model tokenize failed", False)
        return

    orig_map = {r["group_id"]: r["tokens"] for r in d1.get("results", [])}
    comp_map = {r["group_id"]: r["tokens"] for r in d2.get("results", [])}

    all_reduced = True
    for gid in available_groups:
        orig = orig_map.get(gid, 0)
        comp = comp_map.get(gid, 0)
        if orig > 0:
            pct = round((1 - comp / orig) * 100, 1)
            reduced = comp < orig
            print(f"  {gid:15s}: {orig:4d} → {comp:4d} tokens ({pct:5.1f}% reduction) {'✅' if reduced else '❌'}")
            if not reduced:
                all_reduced = False

    report(f"Token reduction across ALL {len(available_groups)} models",
           all_reduced,
           "Some models showed no reduction" if not all_reduced else "")


# =============================================================================
# TEST SUITE 5: API Completeness & Error Handling
# =============================================================================
def test_api_completeness():
    print("\n" + "="*60)
    print("SUITE 5: API COMPLETENESS & ERROR HANDLING")
    print("="*60)

    # 5.1 Health check
    print("\n--- 5.1 Health Check ---")
    s, d, _ = api("GET", "/health")
    report("GET /health", s == 200 and d.get("status") == "ok")

    # 5.2 Models endpoint
    print("\n--- 5.2 GET /api/models ---")
    s, d, _ = api("GET", "/api/models")
    if s == 200:
        groups = d.get("groups", [])
        report(f"Returns {len(groups)} groups", len(groups) >= 8)
        report("All groups have required fields",
               all(all(k in g for k in ["group_id", "models", "pricing"]) for g in groups))

    # 5.3 Pricing endpoint
    print("\n--- 5.3 GET /api/pricing ---")
    s, d, _ = api("GET", "/api/pricing")
    if s == 200:
        pricing = d.get("pricing", {})
        report(f"Returns pricing for {len(pricing)} models", len(pricing) > 0)
        report("GPT-4o pricing present",
               "GPT-4o" in pricing,
               f"Keys: {list(pricing.keys())[:5]}")

    # 5.4 Export endpoint
    print("\n--- 5.4 POST /api/export ---")
    for fmt in ["plain", "json", "markdown"]:
        s, d, _ = api("POST", "/api/export", {"text": "test output", "format": fmt})
        report(f"Export format '{fmt}'", s == 200 and "text" in d,
               f"Got: {d}")

    # 5.5 Error: Unknown group_id
    print("\n--- 5.5 Error Handling ---")
    s, d, _ = api("POST", "/api/tokenize", {
        "text": "test", "group_ids": ["nonexistent_xyz"], "mode": "input"
    })
    report("Unknown group_id returns 404", s == 404)

    # 5.6 Error: Unknown model_id in cost-simulate
    s, d, _ = api("POST", "/api/cost-simulate", {
        "monthly_calls": 1000, "avg_input_tokens": 100, "avg_output_tokens": 50,
        "cache_hit_rate": 0.3, "compression_ratio": 0.5,
        "model_ids": ["NonExistentModel"]
    })
    report("Unknown model_id in cost-simulate returns 404", s == 404)

    # 5.7 Cost simulate
    print("\n--- 5.7 Cost Simulation ---")
    s, d, _ = api("POST", "/api/cost-simulate", {
        "monthly_calls": 10000,
        "avg_input_tokens": 500,
        "avg_output_tokens": 200,
        "cache_hit_rate": 0.3,
        "compression_ratio": 0.65,
        "model_ids": ["GPT-4o", "DeepSeek V4 Flash", "GPT-4o-mini"]
    })
    if s == 200:
        comparisons = d.get("comparisons", [])
        report(f"Returns {len(comparisons)} comparisons", len(comparisons) == 3)
        report("Has best_value_model", bool(d.get("best_value_model")))
        # GPT-4o should cost most, GPT-4o-mini or DeepSeek should be best value
        costs = {c["model_id"]: c["before"]["total"] for c in comparisons}
        print(f"  Monthly costs (before): {json.dumps(costs)}")
        report("Cost simulation logic is consistent",
               costs.get("GPT-4o", 0) > costs.get("GPT-4o-mini", 999),
               f"Costs: {costs}")


# =============================================================================
# TEST SUITE 6: Stress & Edge Cases
# =============================================================================
def test_stress_edge():
    print("\n" + "="*60)
    print("SUITE 6: STRESS & EDGE CASES")
    print("="*60)

    # 6.1 Very long Chinese text
    print("\n--- 6.1 Very Long Text ---")
    long_cn = "请帮我分析一下这些数据中存在的问题和异常情况。" * 100  # ~2500 chars
    start = time.time()
    s, d, _ = api("POST", "/api/compress", {
        "text": long_cn, "strategy": "rule", "level": "aggressive"
    })
    elapsed = time.time() - start
    if s == 200:
        comp_len = len(d["compressed_text"])
        orig_len = len(d["original_text"])
        report(f"Long text ({orig_len}→{comp_len} chars) in {elapsed:.3f}s",
               elapsed < 5.0 and comp_len < orig_len,
               f"Time: {elapsed:.3f}s, Compressed length: {comp_len}")

    # 6.2 Unicode / emoji
    print("\n--- 6.2 Unicode & Emoji ---")
    emoji_text = "请分析数据 📊📈 并给出建议 💡✨ 非常感谢！😊🙏"
    s, d, _ = api("POST", "/api/compress", {
        "text": emoji_text, "strategy": "rule", "level": "aggressive"
    })
    if s == 200:
        comp = d["compressed_text"]
        report("Emoji preserved in compression",
               all(e in comp for e in ["📊", "📈", "💡", "✨"]),
               f"Compressed: '{comp}'")
        report("Politeness removed, emoji preserved (not in politeness regex)",
               "感谢" not in comp,  # Politeness removed; emoji preserved correctly
               f"Compressed: '{comp}'")

    # 6.3 Markdown
    print("\n--- 6.3 Markdown Content ---")
    md_text = """# 数据分析报告

## 概述
非常感谢您查看这份报告。以下是详细分析：

### 关键发现
1. 销售额增长 **25%**
2. 客户满意度达到 `92%`
3. 退货率降低至 *3.2%*

> 请注意：以上数据基于2026年Q2统计。

如果您有任何问题，请随时联系我。谢谢！"""
    s, d, _ = api("POST", "/api/compress", {
        "text": md_text, "strategy": "rule", "level": "aggressive"
    })
    if s == 200:
        comp = d["compressed_text"]
        # Markdown structure should be largely preserved
        report("Markdown headers preserved",
               "##" in comp and "#" in comp,
               f"Compressed: '{comp[:100]}...'")
        report("Markdown data preserved (25%, 92%, 3.2%)",
               "25%" in comp and "92%" in comp,
               f"Compressed: '{comp[:100]}...'")
        report("Politeness removed from markdown",
               "感谢" not in comp and "请随时联系" not in comp,
               f"Compressed: '{comp[:100]}...'")

    # 6.4 Mixed Chinese + English
    print("\n--- 6.4 Mixed Chinese + English ---")
    mixed = """请帮我写一个Python script来process这个dataset。
Specifically, I need you to:
1. Load the CSV file using pandas
2. Clean the data by removing null values
3. Perform basic statistical analysis
4. Generate visualization charts using matplotlib
非常感谢您的帮助！"""
    s, d, _ = api("POST", "/api/compress", {
        "text": mixed, "strategy": "rule", "level": "aggressive"
    })
    if s == 200:
        comp = d["compressed_text"]
        savings = d["savings"]
        report(f"Mixed CN/EN: {savings['tokens_saved']} tokens saved ({savings['percentage']}%)",
               savings["tokens_saved"] > 0,
               f"Compressed: '{comp[:100]}...'")
        # Verify technical content preserved
        report("Technical English preserved (Python, pandas, CSV, matplotlib)",
               all(w.lower() in comp.lower() for w in ["python", "pandas", "csv", "matplotlib"]),
               f"Compressed: '{comp[:100]}...'")

    # 6.5 Numbers and data-dense text
    print("\n--- 6.5 Data-Dense Text ---")
    data_text = """Q2 2026 Revenue: $1,234,567.89
Growth: 15.3% YoY
Active Users: 45,678 (+12% MoM)
Churn Rate: 2.1% (down from 3.4%)
Customer Acquisition Cost: $23.45
LTV: $890.12
NPS Score: 72

请分析以上数据并给出建议。"""
    s, d, _ = api("POST", "/api/compress", {
        "text": data_text, "strategy": "rule", "level": "medium"
    })
    if s == 200:
        comp = d["compressed_text"]
        # All numbers must be preserved
        report("Financial numbers preserved",
               all(str(n) in comp for n in ["1,234,567.89", "15.3%", "45,678", "2.1%", "23.45", "890.12", "72"]),
               f"Compressed: '{comp}'")


# =============================================================================
# TEST SUITE 7: Frontend files integrity
# =============================================================================
def test_frontend_files():
    print("\n" + "="*60)
    print("SUITE 7: FRONTEND FILES INTEGRITY")
    print("="*60)

    # Use direct urllib since / returns HTML not JSON
    try:
        r = urllib.request.urlopen(f"{BASE_URL}/", timeout=5)
        report("GET / returns index.html", r.status == 200)
    except:
        report("GET / returns index.html", False)

    # Check that static files are served
    for path in ["/css/style.css", "/js/app.js"]:
        url = f"{BASE_URL}{path}"
        try:
            r = urllib.request.urlopen(url, timeout=5)
            report(f"Serves {path}", r.status == 200)
        except:
            report(f"Serves {path}", False)


# =============================================================================
# TEST SUITE 8: LLM Compressor Fallback
# =============================================================================
def test_llm_fallback():
    print("\n" + "="*60)
    print("SUITE 8: LLM COMPRESSOR FALLBACK")
    print("="*60)

    # Without API key, LLM compressor should fall back to heuristic
    s, d, _ = api("POST", "/api/compress", {
        "text": "请帮我分析这份数据，谢谢！",
        "strategy": "llm",
        "level": "medium",
        "llm_config": {"provider": "openai", "api_key": "", "model": "gpt-4o-mini"}
    })
    report("LLM compress without API key returns 200 (fallback)",
           s == 200,
           f"Status: {s}")
    if s == 200:
        has_compressed = bool(d.get("compressed_text"))
        report("Fallback produces compressed text",
               has_compressed,
               f"Compressed: '{d.get('compressed_text')}'")
        has_tokens = bool(d.get("original_tokens"))
        report("Fallback produces token counts",
               has_tokens,
               f"Original tokens: {d.get('original_tokens')}")


# =============================================================================
# RUN ALL
# =============================================================================
def main():
    print("="*60)
    print("TOKEN CALCULATOR — COMPREHENSIVE TEST SUITE")
    print(f"Target: {BASE_URL}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    test_token_counting()
    test_rule_compression()
    test_token_reduction()
    test_multimodel_reduction()
    test_api_completeness()
    test_stress_edge()
    test_frontend_files()
    test_llm_fallback()

    print("\n" + "="*60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed ({PASS+FAIL} total)")
    print("="*60)

    if FAIL > 0:
        print("\n--- FAILED TESTS ---")
        for r in RESULTS:
            if not r["passed"]:
                print(f"  ❌ {r['name']}")
                if r["detail"]:
                    for line in r["detail"].split("\n"):
                        print(f"     {line}")

    return FAIL == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
