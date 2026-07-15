"""Rule-based compression engine — categorized rules with proper intensity levels."""
from __future__ import annotations
import re
import logging
from token_calculator._compressor_base import CompressorBase

logger = logging.getLogger(__name__)

# =============================================================================
# Rule categories (not flat lists — each rule has a level requirement)
# =============================================================================
# Level 1 ("light"):  whitespace, punctuation, trivial cleanup
# Level 2 ("medium"): + filler words, redundant modifiers
# Level 3 ("aggressive"): + politeness phrases, request wrappers, condensation

# --- Chinese rules ---

CHINESE_RULES = [
    # LEVEL 1 — whitespace + punctuation cleanup
    {"pattern": r"\n{3,}",               "replacement": "\n\n",     "description": "合并多余空行",                          "level": 1},
    {"pattern": r"([。！？,!?])\1+",      "replacement": r"\1",       "description": "合并重复标点",                          "level": 1},
    {"pattern": r"[ \t]{2,}",            "replacement": " ",        "description": "合并多余空格",                          "level": 1},
    {"pattern": r"^[ \t]+|[ \t]+$",      "replacement": "",         "description": "去除行首尾空白",                         "level": 1},

    # LEVEL 2 — filler words + common politeness (high-frequency patterns)
    {"pattern": r"(那个|就是说|然后呢|对吧|对不对|你知道吗|说白了|说实话|讲道理)",
                                          "replacement": "",         "description": "去除口语填充词",                          "level": 2},
    # 特别(?!是) prevents matching in compounds like 特别是(especially)
    {"pattern": r"(非常|十分|特别(?!是)|极其|相当|格外|挺|蛮|比较)",
                                          "replacement": "",         "description": "去除冗余程度副词",                         "level": 2},
    {"pattern": r"(可能会|大概|或许|也许|似乎|好像|貌似|大约)",
                                          "replacement": "",         "description": "去除模糊限定词",                          "level": 2},
    {"pattern": r"(而且|然后|此外|另外|还有)[，,]?(?=而且|然后|此外|另外|还有)",
                                          "replacement": "",         "description": "去除连续冗余连词",                         "level": 2},
    # Common politeness — high frequency in user prompts, safe to remove at medium level
    # (?!教|示|客|求|假|战|缨|罪|愿|命|功) prevents matching compound words:
    #   请教(consult), 请示, 请客, 请求, 请假, 请战, 请缨, 请罪, 请愿, 请命, 请功
    {"pattern": r"请(?!教|示|客|求|假|战|缨|罪|愿|命|功)(你|您)?(帮我|帮忙|协助|给)?(我)?((?:分析|看看|查看|检查|处理|做|弄|写|改|翻译|总结|整理|优化|审查|解释|说明|介绍|描述|展示|列出|生成|创建))?(一下|一遍|一次|下|一下下)?[，,]?",
                                          "replacement": r"\4",      "description": "去除请求敬语框架(保留动词)",               "level": 2},
    {"pattern": r"(谢谢|感谢|多谢|感激)(你|您)?(的(?:帮助|支持|协助|指导|建议|意见|回复|解答|鼓励|关心|关注|配合|理解|信任|认可|好评))?(了|啊|啦|哦|呀)?[!！。，]*",
                                          "replacement": "",         "description": "去除感谢语(含'的帮助'等)",                 "level": 2},
    {"pattern": r"(能否|能不能|可不可以|是否可以|麻烦|劳烦|拜托)(你|您)?(帮我|帮忙|协助)?(我)?[，,]?",
                                          "replacement": "",         "description": "去除礼貌疑问前缀",                         "level": 2},
    # Clean up remnants after prefix/suffix removal (anywhere in text, not just end)
    # Matches both "的帮助" and "和支持" remnants after thanks phrases are stripped
    {"pattern": r"(?:的|和)(?:帮助|支持|协助|指导|建议|意见|回复|解答|鼓励|关心|关注|配合|理解|信任|认可|好评)[!！。，；;]*",
                                          "replacement": "",         "description": "去除感谢语残词(的XX/和XX)",                "level": 2},

    # LEVEL 3 — extreme politeness + condensation (safe but aggressive)
    # Greedy .*$ — consume entire rest of text from blessing keyword to end
    {"pattern": r"(祝你|祝您|希望|期待|盼|愿)(你|您)?.*$",
                                          "replacement": "",         "description": "去除结尾祝福语(含后续所有文本)",            "level": 3},
    {"pattern": r"我(是|只是个|是一个|就是个|不过是个)(新手|小白|菜鸟|初学者|外行|业余的|非专业的)",
                                          "replacement": "",         "description": "去除自谦表述",                           "level": 3},
    {"pattern": r"(麻烦|劳驾|打扰)(你|您)(一下|了)?[，,]?",
                                          "replacement": "",         "description": "去除打扰客套",                           "level": 3},
    {"pattern": r"(您|你)(好|早|晚安|辛苦了|费心了)[!！。，]*",
                                          "replacement": "",         "description": "去除问候语",                             "level": 3},
    {"pattern": r"(不好意思|抱歉|对不起)[，,]?",
                                          "replacement": "",         "description": "去除道歉前缀",                           "level": 3},
    {"pattern": r"给(你|您)?(添麻烦|带来不便|增加工作量)[了]?[。！，]*",
                                          "replacement": "",         "description": "去除道歉补充",                           "level": 3},
    {"pattern": r"\n-\s*",              "replacement": "；",         "description": "合并列表项为一句",                         "level": 3},
    # Condensation — aggressive shortening
    {"pattern": r"(让我们|我们来|咱们)(一起)?(看看|来看|看一下|来分析|来分析一下|看看怎么)",
                                          "replacement": "",         "description": "精简引导语",                             "level": 3},
    {"pattern": r"(怎么样|如何|行不行|可不可以|可以吗)[？?]?",
                                          "replacement": "",         "description": "精简征求意见后缀",                         "level": 3},
    {"pattern": r"(你|您)(觉得|认为|看|觉得怎么样)[？?]?",
                                          "replacement": "",         "description": "精简询问意见",                            "level": 3},
]

# --- English rules ---

ENGLISH_RULES = [
    # LEVEL 1 — whitespace + punctuation cleanup
    {"pattern": r"\n{3,}",               "replacement": "\n\n",     "description": "Collapse 3+ newlines",                    "level": 1},
    {"pattern": r"[ ]{2,}",              "replacement": " ",        "description": "Collapse multiple spaces",               "level": 1},
    {"pattern": r"^[ \t]+|[ \t]+$",      "replacement": "",         "description": "Trim line whitespace",                   "level": 1},

    # LEVEL 2 — filler words + redundant modifiers
    {"pattern": r"\b(basically|essentially|actually|literally|honestly|frankly)\b[ ,]*",
                                          "replacement": "",         "description": "Remove filler adverbs",                  "level": 2},
    {"pattern": r"\b(really|very|quite|rather|pretty|extremely|highly|particularly)\b[ ]?(?=much|important|good|bad|big|small|fast|slow|easy|hard|simple|complex)",
                                          "replacement": "",         "description": "Remove redundant intensifiers",           "level": 2},
    {"pattern": r"\b(kind of|sort of|a little bit|a bit)\b[ ]?",
                                          "replacement": "",         "description": "Remove hedge phrases",                   "level": 2},
    {"pattern": r"\b(I think|I believe|I feel like|in my opinion|it seems to me that|as far as I can tell)\b[ ,]*",
                                          "replacement": "",         "description": "Remove opinion qualifiers",              "level": 2},
    {"pattern": r"\b(just|simply)\b[ ]",
                                          "replacement": "",         "description": "Remove filler 'just'/'simply'",          "level": 2},
    {"pattern": r"\b(at this point in time|at the present time|at the moment|at this moment in time)\b",
                                          "replacement": "now",      "description": "Condense time phrases",                  "level": 2},
    {"pattern": r"\b(due to the fact that|owing to the fact that|because of the fact that)\b",
                                          "replacement": "because",  "description": "Condense causal phrases",                "level": 2},
    {"pattern": r"\b(in order to|so as to)\b",
                                          "replacement": "to",       "description": "Condense purpose clauses",              "level": 2},

    # Common politeness — high frequency, safe at medium level
    {"pattern": r"(C|c)ould you (please |kindly |be so kind as to )?(help me |assist me in |do me a favor and |please )?",
                                          "replacement": "",         "description": "Remove polite request wrapper",          "level": 2},
    {"pattern": r"(I would (?:really |greatly |very much )?(?:appreciate it|be grateful) if you (?:could|would)|I would (?:really |greatly |very much )?like you to|I want you to|I need you to|I'd like you to)[ ,]*(?:help me |please )?",
                                          "replacement": "",         "description": "Remove desire/appreciation prefix",      "level": 2},
    {"pattern": r"\b(help me |assist me in )\b",
                                          "replacement": "",         "description": "Remove 'help me' helper",               "level": 2},
    {"pattern": r"(Thank you|Thanks|Much appreciated|Many thanks|Thanks a lot|Thank you so much)(?: for [^.?!\n]+?)?[!., ]*(?=[\n]|$|[A-Z])",
                                          "replacement": "",         "description": "Remove closing thanks (incl. 'for...')", "level": 2},
    {"pattern": r"(make sure to|be sure to|don't forget to|remember to) ",
                                          "replacement": "",         "description": "Remove reminder phrases",               "level": 2},
    {"pattern": r"\bI(?:'m| am) (?:very |so |really |extremely )?grateful for your (?:assistance|help|support|time|guidance)\b[!., ]*",
                                          "replacement": "",         "description": "Remove grateful statement",             "level": 2},
    {"pattern": r"\bI look forward to (?:hearing from you|your reply|your response|working with you)\b[!., ]*",
                                          "replacement": "",         "description": "Remove closing pleasantry",             "level": 2},

    # LEVEL 3 — heavy condensation + query unwrapping
    {"pattern": r"(I would (?:really |greatly |very much )?appreciate it if you (?:could|would)|I would (?:really |greatly |very much )?be grateful if you would|it would be great if you could)[ ,]*(?:help me |please )?",
                                          "replacement": "",         "description": "Remove appreciation wrapper",            "level": 3},
    {"pattern": r"(Please note that|It is important to note that|Keep in mind that|Bear in mind that) ",
                                          "replacement": "",         "description": "Remove note prefixes",                   "level": 3},
    {"pattern": r"[Cc]an you (tell me|explain|show me|describe|elaborate on) ",
                                          "replacement": "",         "description": "Remove query wrapper",                  "level": 3},
    {"pattern": r"[Dd]o you (know|have any idea|have a clue) ",
                                          "replacement": "",         "description": "Remove knowledge query wrapper",        "level": 3},
    {"pattern": r"^[Tt]hat\s+",          "replacement": "",         "description": "Remove leading 'that' remnant",          "level": 3},
    {"pattern": r"\bat your earliest convenience\b[!., ]*",
                                          "replacement": "",         "description": "Remove formal closing phrase",           "level": 3},
    {"pattern": r"\bif it(?:'s| is) not too much trouble\b[!., ]*",
                                          "replacement": "",         "description": "Remove hedging phrase",                 "level": 3},
]


class RuleCompressor(CompressorBase):
    """Categorized rule-based compression with proper intensity levels.

    Rules are tagged with level 1/2/3 (light/medium/aggressive). Each level
    includes ALL rules from lower levels. Code blocks (``` ```) are protected.

    Pure Python, zero API calls, sub-millisecond response.
    """

    def __init__(self):
        super().__init__(strategy="rule", name="Rule Compressor")

        # Build categorized rule lists for fast level selection
        self._level1 = []
        self._level2 = []
        self._level3 = []

        for r in CHINESE_RULES:
            self._add_rule(r)
        for r in ENGLISH_RULES:
            self._add_rule(r)

        # Pre-compile all patterns
        for rule_list in [self._level1, self._level2, self._level3]:
            for r in rule_list:
                r["_re"] = re.compile(r["pattern"], re.MULTILINE)

    def _add_rule(self, rule):
        """Add a rule dict to the appropriate level list."""
        entry = {"pattern": rule["pattern"], "replacement": rule["replacement"],
                 "description": rule["description"]}
        if rule["level"] == 1:
            self._level1.append(entry)
        elif rule["level"] == 2:
            self._level2.append(entry)
        else:
            self._level3.append(entry)

    def compress(self, text: str, level: str = "medium") -> dict:
        if not text:
            return {"compressed_text": "", "changes": [],
                    "stats": {"original_chars": 0, "compressed_chars": 0, "operations_count": 0}}

        # Select rules by level (cumulative)
        rules = list(self._level1)
        if level in ("medium", "aggressive"):
            rules.extend(self._level2)
        if level == "aggressive":
            rules.extend(self._level3)

        # Protect code blocks
        code_blocks = []

        def save_code(m):
            code_blocks.append(m.group(0))
            return f"\x00CB{len(code_blocks) - 1}\x00"

        protected = re.sub(r"```[\s\S]*?```", save_code, text)

        result = protected
        changes = []
        ops_count = 0

        for rule in rules:
            prev = result
            result, n = rule["_re"].subn(rule["replacement"], result)
            if n > 0 and result != prev:
                changes.append({
                    "type": "rule",
                    "rule": rule["description"],
                    "original": rule["pattern"],
                    "replaced": rule["replacement"],
                })
                ops_count += n

        # Restore code blocks in reverse
        for i in range(len(code_blocks) - 1, -1, -1):
            result = result.replace(f"\x00CB{i}\x00", code_blocks[i])

        # Final cleanup: remove residual fragments and normalize whitespace
        result = re.sub(r"\n{3,}", "\n\n", result)
        result = re.sub(r"[ ]{2,}", " ", result)
        # Remove lines that became just punctuation fragments after rule application
        result = re.sub(r"^\s*[，,。；;！!？?、\s]+\s*$", "", result, flags=re.MULTILINE)
        # Remove leading punctuation/comma on a line (remnant from prefix removal)
        result = re.sub(r"^\s*[，,；;。！!？?、]\s*", "", result, flags=re.MULTILINE)
        # Remove dangling "的" at line start (remnant from possessive cleanup)
        result = re.sub(r"^\s*的\s*$", "", result, flags=re.MULTILINE)
        # Collapse blank lines again after removals
        result = re.sub(r"\n{3,}", "\n\n", result)
        result = result.strip()

        return {
            "compressed_text": result,
            "changes": changes,
            "stats": {
                "original_chars": len(text),
                "compressed_chars": len(result),
                "operations_count": ops_count,
            }
        }
