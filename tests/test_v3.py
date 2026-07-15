from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from token_calculator import create_app
from token_calculator._cli import _frontend_dir
from token_calculator._cost_simulator import CostSimulator
from token_calculator._compressor_base import CompressionError
from token_calculator._llm_compressor import LLMCompressor
from token_calculator._pricing import PricingRegistry
from token_calculator._quality_guard import validate_compression
from token_calculator._rule_compressor import RuleCompressor
from token_calculator._tokenizer_registry import _estimate_tokens_fallback
from token_calculator._tokenizer_registry import count_tokens_detailed


def _socket_runtime_available():
    try:
        probe = socket.socket()
        probe.close()
        return True
    except PermissionError:
        return False


requires_socket_runtime = pytest.mark.skipif(
    not _socket_runtime_available(),
    reason="执行沙箱禁止 socket；API 通过受控本地服务器另行验证",
)


def test_safe_compressor_preserves_requirements_and_structure():
    source = "您好，请帮我设计系统。\n- 希望支持登录\n- 可能会有百万用户\n```python\nprint('谢谢')\n```\n谢谢！"
    result = RuleCompressor().compress(source, "aggressive")
    output = result["compressed_text"]
    assert "希望支持登录" in output
    assert "可能会有百万用户" in output
    assert "- " in output
    assert "print('谢谢')" in output


def test_rule_compression_reduces_tokens_on_representative_prompts():
    cases = [
        "您好，请帮我设计一个用户模块。\n- 最多重试 5 次\n- 必须记录审计日志\n非常感谢您的帮助！",
        "I would like you to analyze this API.\n- Keep all 3 endpoints\n- Return JSON\nThank you for your help!",
        "我希望你能够编写数据导入函数。\n1. 只能使用标准库\n2. 金额使用 Decimal\n期待你的回复。",
    ]
    compressor = RuleCompressor()
    original_total = compressed_total = 0
    for source in cases:
        output = compressor.compress(source, "medium")["compressed_text"]
        assert validate_compression(source, output)["passed"]
        original_total += count_tokens_detailed(source, "o200k_base")["tokens"]
        compressed_total += count_tokens_detailed(output, "o200k_base")["tokens"]
    assert compressed_total < original_total
    assert (original_total - compressed_total) / original_total >= 0.05


def test_chinese_fallback_is_not_quarter_character_count():
    text = "这是十个左右的中文字符测试"
    assert _estimate_tokens_fallback(text) > len(text) * 0.8


def test_quality_guard_rejects_lost_numbers_lists_and_placeholders():
    original = "要求：\n- 最多重试 5 次\n- 保留变量 {user_id}"
    candidate = "要求重试并保留变量"
    result = validate_compression(original, candidate)
    assert not result["passed"]
    assert any("数字" in issue for issue in result["issues"])
    assert any("列表" in issue for issue in result["issues"])
    assert any("模板变量" in issue for issue in result["issues"])


def test_cost_simulator_deducts_compression_cost_and_break_even():
    registry = PricingRegistry(pricing={"test": {"input": 10, "output": 20, "cache_hit": None}})
    result = CostSimulator(registry).simulate(
        monthly_calls=100, avg_input_tokens=1000, compressed_input_tokens=500,
        avg_output_tokens=0, cache_hit_rate=0, compression_cost_usd=.02,
        model_ids=["test"],
    )["comparisons"][0]
    assert result["before"]["total"] == 1.0
    assert result["after"]["total"] == .5
    assert result["monthly_savings"] == .48
    assert result["break_even_uses"] == 4


def test_llm_compressor_reports_real_provider_usage(monkeypatch):
    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "Analyze data; return JSON."}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 8},
            }

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    result = LLMCompressor().compress(
        "Please analyze this data and return the result as JSON.",
        llm_config={"api_key": "test", "model": "gpt-4o-mini"},
    )
    assert result["compressed_text"] == "Analyze data; return JSON."
    assert result["stats"]["llm_input_tokens"] == 120
    assert result["stats"]["llm_output_tokens"] == 8


def test_llm_compressor_never_silently_falls_back():
    with pytest.raises(CompressionError):
        LLMCompressor().compress("Compress this", llm_config={})


def test_cli_finds_packaged_frontend():
    frontend = _frontend_dir()
    assert frontend.is_dir()
    assert (frontend / "index.html").is_file()


@requires_socket_runtime
def test_api_exposes_exactness_and_economics(tmp_path):
    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["version"] == "3.0.0"
    assert health.json()["lifecycle"] == "archived"
    response = client.post("/api/compress", json={
        "text": "您好，请帮我分析以下需求。谢谢！",
        "strategy": "rule", "group_id": "o200k_base",
        "model_id": "GPT-4o-mini", "economics": {"reuse_count": 10},
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["economics"]["compression_cost_usd"] == 0
    assert "token_count_method" in data


@requires_socket_runtime
def test_api_rejects_invalid_ranges():
    client = TestClient(create_app())
    response = client.post("/api/compress", json={
        "text": "x", "economics": {"reuse_count": -1}
    })
    assert response.status_code == 422


@requires_socket_runtime
def test_llm_failure_is_not_silently_downgraded():
    client = TestClient(create_app())
    response = client.post("/api/compress", json={
        "text": "compress me", "strategy": "llm",
        "llm_config": {"provider": "openai", "model": "gpt-4o-mini"},
    })
    assert response.status_code == 502
    assert "API Key" in response.json()["detail"]
