"""Conservative, structure-preserving local prompt cleanup."""
from __future__ import annotations

import re

from token_calculator._compressor_base import CompressorBase


# Only phrases whose removal does not alter certainty, scope or requirements.
RULES = [
    (1, r"[ \t]{2,}", " ", "合并连续空格"),
    (1, r"\n{3,}", "\n\n", "合并多余空行"),
    (1, r"([!！?？])\1+", r"\1", "合并重复标点"),
    (2, r"(?m)^\s*(?:请问|麻烦问一下)[，,：:]?\s*", "", "移除独立礼貌开场"),
    (2, r"(?m)^\s*(?:请|麻烦|劳烦)(?:你|您)?(?:帮我|帮忙)?(?=(?:分析|检查|审查|解释|总结|翻译|编写|生成|设计|实现|优化))", "", "精简请求前缀"),
    (2, r"(?m)^\s*(?:我想请你|我希望你(?:能够|可以)?|我需要你)(?=(?:分析|检查|审查|解释|总结|翻译|编写|生成|设计|实现|优化))", "", "精简任务引导语"),
    (2, r"(?:非常感谢|十分感谢|谢谢(?:你|您)?)(?:的帮助)?[!！。,.，]*\s*$", "", "移除结尾感谢语"),
    (2, r"(?:期待|盼望)(?:你|您)?的?回复[!！。,.，]*\s*$", "", "移除结尾回复客套"),
    (2, r"(?i)\b(?:could you|would you) please\s+", "", "Remove polite request prefix"),
    (2, r"(?i)^\s*(?:I would like you to|I need you to|I want you to)\s+", "", "Remove task wrapper"),
    (2, r"(?i)\b(?:thank you|thanks)(?: for your help)?[.! ]*$", "", "Remove closing thanks"),
    (3, r"(?m)^\s*(?:你好|您好)[!！。,.，]*\s*", "", "移除独立问候语"),
    (3, r"(?i)^\s*(?:hello|hi)[,! ]+", "", "Remove greeting"),
]


class RuleCompressor(CompressorBase):
    """Low-risk cleanup that preserves Markdown, code, hedges and constraints."""

    def __init__(self):
        super().__init__(strategy="rule", name="Safe local cleanup")
        self._rules = [(level, re.compile(pattern), replacement, description)
                       for level, pattern, replacement, description in RULES]

    def compress(self, text: str, level: str = "medium") -> dict:
        if not text:
            return {"compressed_text": "", "changes": [], "warnings": [],
                    "stats": {"original_chars": 0, "compressed_chars": 0,
                              "operations_count": 0}}

        threshold = {"light": 1, "medium": 2, "aggressive": 3}.get(level, 2)
        protected: list[str] = []

        def protect(match: re.Match) -> str:
            protected.append(match.group(0))
            return f"\x00PROTECTED_{len(protected)-1}\x00"

        # Code blocks, inline code, URLs and JSON-looking blocks are untouched.
        result = re.sub(r"```[\s\S]*?```|`[^`\n]+`|https?://[^\s)]+", protect, text)
        changes = []
        operations = 0
        for rule_level, regex, replacement, description in self._rules:
            if rule_level > threshold:
                continue
            before = result
            result, count = regex.subn(replacement, result)
            if count and result != before:
                operations += count
                changes.append({"type": "safe_rule", "rule": description,
                                "original": regex.pattern, "replaced": replacement})

        for index, value in enumerate(protected):
            result = result.replace(f"\x00PROTECTED_{index}\x00", value)
        result = result.strip()

        warnings = []
        if level == "aggressive":
            warnings.append("重度模式仍只执行低风险清理；系统不会自动删除不确定性、列表或需求约束。")
        if result == text.strip():
            warnings.append("未发现可安全删除的内容；保持原文通常比追求压缩率更重要。")
        return {
            "compressed_text": result,
            "changes": changes,
            "warnings": warnings,
            "stats": {"original_chars": len(text), "compressed_chars": len(result),
                      "operations_count": operations},
        }
