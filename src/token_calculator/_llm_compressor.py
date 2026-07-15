"""LLM-based semantic compression engine using real API calls."""
from __future__ import annotations
import logging
import json
from token_calculator._compressor_base import CompressorBase

logger = logging.getLogger(__name__)

# Compression prompt template
COMPRESSION_PROMPT = """You are a prompt compression engine. Rewrite the following prompt to be maximally concise while preserving ALL key instructions, constraints, examples, and required output format.

Rules:
1. Remove all politeness, filler phrases, and redundant explanations
2. Keep all technical requirements, constraints, and format specifications
3. Preserve all examples but condense them
4. If the original contains multi-step instructions, use numbered lists
5. Do NOT change the core meaning or remove any required output fields
6. Output ONLY the compressed prompt, no explanation

Original prompt:
---
{user_prompt}
---

Compressed prompt:"""

# Provider endpoint mapping (OpenAI-compatible API)
PROVIDER_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
    "custom": "",  # Set via llm_config["api_base"]
}


class LLMCompressor(CompressorBase):
    """LLM-based semantic compression using external API (OpenAI-compatible).

    Requires an API key for the LLM provider.
    Falls back to heuristic compression if no API key is provided or API call fails.
    """

    def __init__(self):
        super().__init__(strategy="llm", name="LLM Compressor")

    def compress(self, text: str, level: str = "medium",
                 llm_config: dict | None = None) -> dict:
        if not text:
            return {"compressed_text": "", "changes": [],
                    "stats": {"original_chars": 0, "compressed_chars": 0, "operations_count": 0}}

        config = llm_config or {}
        provider = config.get("provider", "openai")
        api_key = config.get("api_key")
        model = config.get("model", "gpt-4o-mini")
        target_ratio = config.get("target_ratio", 0.4)
        api_base = config.get("api_base")

        if not api_key:
            logger.warning("LLM compression requested but no API key provided. Falling back to heuristic.")
            return self._heuristic_compress(text, "No API key provided")

        # Determine endpoint
        endpoint = api_base or PROVIDER_ENDPOINTS.get(provider)
        if not endpoint:
            logger.warning(f"Unknown provider '{provider}' and no api_base set. Falling back to heuristic.")
            return self._heuristic_compress(text, f"Unknown provider: {provider}")

        # Build the compression prompt
        prompt = COMPRESSION_PROMPT.format(user_prompt=text)

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": max(256, int(len(text) * 0.5)),
            }

            logger.info(f"Calling {provider}/{model} for LLM compression...")
            response = httpx.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=60.0,
            )

            if response.status_code == 200:
                data = response.json()
                compressed_text = data["choices"][0]["message"]["content"].strip()

                # Validate: compressed text should not be empty or identical
                if not compressed_text or compressed_text == text:
                    logger.info("LLM returned empty or identical text, falling back to heuristic")
                    return self._heuristic_compress(text, "LLM returned no change")

                logger.info(
                    f"LLM compression: {len(text)} chars -> {len(compressed_text)} chars "
                    f"({round((1 - len(compressed_text)/len(text)) * 100, 1)}% reduction)"
                )

                return {
                    "compressed_text": compressed_text,
                    "changes": [
                        {
                            "type": "llm",
                            "rule": f"LLM semantic compression ({provider}/{model})",
                            "original": f"[{len(text)} chars]",
                            "replaced": f"[{len(compressed_text)} chars, {round((1 - len(compressed_text)/len(text)) * 100, 1)}% reduction]",
                        }
                    ],
                    "stats": {
                        "original_chars": len(text),
                        "compressed_chars": len(compressed_text),
                        "operations_count": 1,
                    }
                }

            else:
                error_detail = response.text[:500] if response.text else "Unknown error"
                # Try to extract a human-readable message from the JSON error response
                try:
                    err_data = json.loads(response.text)
                    if isinstance(err_data, dict):
                        err_msg = err_data.get("error", {}).get("message", "") or str(err_data)
                        error_detail = err_msg[:300]
                except Exception:
                    pass
                logger.warning(
                    f"LLM API returned {response.status_code}: {error_detail}. Falling back to heuristic."
                )
                return self._heuristic_compress(text, f"API {response.status_code}: {error_detail}")

        except ImportError:
            logger.warning("httpx not available. Install with: pip install httpx. Falling back to heuristic.")
            return self._heuristic_compress(text, "httpx not installed")
        except Exception as e:
            logger.warning(f"LLM compression failed: {e}. Falling back to heuristic.")
            return self._heuristic_compress(text, str(e)[:100])

    def _heuristic_compress(self, text: str, reason: str = "") -> dict:
        """Simple heuristic compression as fallback when LLM API is unavailable."""
        import re
        lines = text.split("\n")
        compressed = []
        changes = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                compressed.append("")
                continue
            # Remove excessive punctuation
            clean = re.sub(r"([!！?？。])\1+", r"\1", stripped)
            clean = re.sub(r"\s{2,}", " ", clean)
            if clean != stripped:
                changes.append({
                    "type": "heuristic_fallback",
                    "rule": "Clean punctuation/whitespace",
                    "original": stripped[:50],
                    "replaced": clean[:50]
                })
            compressed.append(clean)

        result = "\n".join(compressed).strip()

        if reason:
            changes.insert(0, {
                "type": "heuristic_fallback",
                "rule": f"LLM not available: {reason}",
                "original": f"[{len(text)} chars]",
                "replaced": "[Heuristic fallback applied — provide API key for real LLM compression]",
            })

        return {
            "compressed_text": result,
            "changes": changes,
            "stats": {
                "original_chars": len(text),
                "compressed_chars": len(result),
                "operations_count": len(changes)
            }
        }
