"""
Tokenizer Download Script
==========================
Downloads tokenizer files for all 8 model groups.

Current status: 7/8 operational. Gemma (google/gemma-3-4b-it) is DEFERRED —
access request pending Google review. This script will skip Gemma gracefully.

Usage: python scripts/download_tokenizers.py

Downloads:
- HuggingFace tokenizer files -> ~/.cache/huggingface/hub/ (auto-managed by transformers)
  Groups: Llama 3 (NousResearch/Meta-Llama-3-8B, non-gated),
          Qwen 2.5, DeepSeek V3, GLM-4, Mistral
- SentencePiece .model files -> models/{group_id}/tokenizer.model
  Groups: Gemma (deferred — skipped)
- tiktoken (o200k_base, cl100k_base): built-in, no download needed
"""
import sys
import os

def check_hf_auth():
    """Check if HuggingFace authentication is configured for gated models."""
    try:
        from huggingface_hub import HfFolder
        token = HfFolder.get_token()
        if token:
            print(f"[OK] HuggingFace token found")
            return True
    except ImportError:
        pass

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token:
        print(f"[OK] HF_TOKEN environment variable set")
        return True

    print("[WARN] No HuggingFace token found. (All current repos are non-gated, skip if download succeeds.)")
    print("       Run: huggingface-cli login")
    print("       Or set: HF_TOKEN environment variable")
    return False


def download_hf_tokenizers():
    """Cache HuggingFace tokenizer files locally."""
    repos = [
        ("NousResearch/Meta-Llama-3-8B", "Llama 3"),
        ("Qwen/Qwen2.5-7B", "Qwen 2.5"),
        ("deepseek-ai/DeepSeek-V3", "DeepSeek V3"),
        ("THUDM/glm-4-9b", "GLM-4"),
        ("mistralai/Mistral-7B-v0.1", "Mistral"),
    ]

    print("\n--- Downloading HuggingFace tokenizers ---")
    for repo_id, name in repos:
        print(f"  [{name}] {repo_id} ... ", end="", flush=True)
        try:
            from transformers import AutoTokenizer
            tok = AutoTokenizer.from_pretrained(repo_id, use_fast=True, trust_remote_code=True)
            # Force a test encode to verify it works
            test_count = len(tok.encode("Hello world"))
            print(f"OK (test: {test_count} tokens)")
        except Exception as e:
            print(f"FAILED: {e}")


def download_sentencepiece_models():
    """Download SentencePiece .model files to models/ directory."""
    models = [
        ("gemma", "google/gemma-3-4b-it", "tokenizer.model"),
    ]

    print("\n--- Downloading SentencePiece models ---")
    for group_id, repo_id, filename in models:
        if group_id == "gemma":
            print("  [gemma] DEFERRED — Google access review pending")
            print("          Once approved, re-run this script to download.")
            continue

        local_dir = os.path.join("models", group_id)
        local_file = os.path.join(local_dir, filename)

        if os.path.isfile(local_file):
            # Verify it loads
            try:
                import sentencepiece as spm
                sp = spm.SentencePieceProcessor()
                sp.Load(local_file)
                print(f"  [{group_id}] Already cached: {local_file} (test: OK)")
                continue
            except Exception as e:
                print(f"  [{group_id}] Cached file corrupt, re-downloading: {e}")

        print(f"  [{group_id}] {repo_id}/{filename} ... ", end="", flush=True)
        try:
            from huggingface_hub import hf_hub_download
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=local_dir,
                local_dir_use_symlinks=False,
            )
            print(f"OK -> {path}")
        except Exception as e:
            print(f"FAILED: {e}")


def report_tiktoken():
    """tiktoken is built-in; no download needed."""
    print("\n--- tiktoken (built-in) ---")
    for encoding in ["o200k_base", "cl100k_base"]:
        print(f"  [{encoding}] Built-in, no download needed")


def verify_all():
    """Verify all tokenizers can be loaded."""
    import sys
    sys.path.insert(0, "src")
    from token_calculator._tokenizer_registry import preload_all

    print("\n--- Verifying all tokenizers ---")
    results = preload_all()
    for gid, available in results.items():
        status = "READY" if available else "UNAVAILABLE (will use fallback)"
        print(f"  {gid:20s} {status}")

    ready = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{ready}/{total} tokenizers ready")
    return ready == total


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print("Tokenizer Download Script")
    print("=" * 60)

    check_hf_auth()
    download_hf_tokenizers()
    download_sentencepiece_models()
    report_tiktoken()

    if verify_all():
        print("\n[DONE] All tokenizers ready.")
    else:
        print("\n[DONE] Some tokenizers unavailable. Run: pip install -e .[tokenizers] to install dependencies.")
        print("        Missing tokenizers will use len*0.25 fallback estimation.")
        print("        (Gemma is expected — deferred pending Google review.)")

    sys.exit(0)
