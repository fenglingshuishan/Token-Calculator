"""Deterministic structural guard for prompt compression results."""
from __future__ import annotations

import re
from collections import Counter


def _items(pattern: str, text: str, flags: int = 0) -> Counter:
    return Counter(re.findall(pattern, text, flags))


def validate_compression(original: str, candidate: str) -> dict:
    """Reject obvious semantic damage without pretending to prove equivalence.

    This guard deliberately checks facts that can be verified deterministically.
    It complements, rather than replaces, the final human review.
    """
    issues: list[str] = []
    if not candidate.strip():
        issues.append("压缩结果为空")

    original_numbers = _items(r"(?<!\w)[+-]?(?:\d+(?:\.\d+)?%?)(?!\w)", original)
    candidate_numbers = _items(r"(?<!\w)[+-]?(?:\d+(?:\.\d+)?%?)(?!\w)", candidate)
    missing_numbers = original_numbers - candidate_numbers
    if missing_numbers:
        issues.append("数字或比例丢失: " + ", ".join(missing_numbers.elements()))

    original_code = re.findall(r"```[\s\S]*?```", original)
    candidate_code = re.findall(r"```[\s\S]*?```", candidate)
    if original_code != candidate_code:
        issues.append("代码块被修改或丢失")

    original_json_keys = _items(r'"([^"\n]+)"\s*:', original)
    candidate_json_keys = _items(r'"([^"\n]+)"\s*:', candidate)
    missing_keys = original_json_keys - candidate_json_keys
    if missing_keys:
        issues.append("JSON 字段丢失: " + ", ".join(missing_keys.elements()))

    list_pattern = r"(?m)^\s*(?:[-*+] |\d+[.)] )"
    original_lists = len(re.findall(list_pattern, original))
    candidate_lists = len(re.findall(list_pattern, candidate))
    if candidate_lists < original_lists:
        issues.append(f"列表项减少: {original_lists} → {candidate_lists}")

    headings = _items(r"(?m)^#{1,6}\s+(.+)$", original)
    candidate_headings = _items(r"(?m)^#{1,6}\s+(.+)$", candidate)
    if headings - candidate_headings:
        issues.append("Markdown 标题被修改或丢失")

    # Preserve explicit placeholders/template variables byte-for-byte.
    placeholders = _items(r"\{\{[^{}]+\}\}|\{[A-Za-z_][A-Za-z0-9_.-]*\}|\$\{[^{}]+\}", original)
    candidate_placeholders = _items(r"\{\{[^{}]+\}\}|\{[A-Za-z_][A-Za-z0-9_.-]*\}|\$\{[^{}]+\}", candidate)
    if placeholders - candidate_placeholders:
        issues.append("模板变量被修改或丢失")

    return {
        "passed": not issues,
        "issues": issues,
        "checks": {
            "numbers": len(original_numbers), "code_blocks": len(original_code),
            "json_keys": len(original_json_keys), "list_items": original_lists,
            "headings": len(headings), "placeholders": len(placeholders),
        },
        "notice": "结构校验只能发现确定性损坏，不能证明语义完全等价；仍需人工审核。",
    }
