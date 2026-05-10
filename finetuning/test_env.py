# test_env.py — NIKKO Phase 4 environment validation
# Run this on your training GPU box before any training begins.
# Checks: bitsandbytes version, CUDA availability, 4-bit quantization, and
# a live QLoRA load of Mistral 7B to confirm the full stack is wired correctly.
#
# Usage:
#   pip install bitsandbytes==0.45.5 transformers accelerate torch --break-system-packages
#   python finetuning/test_env.py
#
# Expected outcome: all checks print OK. Any FAIL line is a blocker.

import sys

# ── 1. Python version ─────────────────────────────────────────────────────────
print(f"[CHECK] Python: {sys.version}")

# ── 2. PyTorch + CUDA ────────────────────────────────────────────────────────
try:
    import torch
    cuda_available = torch.cuda.is_available()
    cuda_version = torch.version.cuda if cuda_available else "N/A"
    device_name = torch.cuda.get_device_name(0) if cuda_available else "N/A"
    vram_gb = (
        torch.cuda.get_device_properties(0).total_memory / 1e9
        if cuda_available else 0
    )
    print(f"[{'OK' if cuda_available else 'FAIL'}] PyTorch {torch.__version__} | "
          f"CUDA {cuda_version} | Device: {device_name} | VRAM: {vram_gb:.1f} GB")
    if not cuda_available:
        print("      ↳ No CUDA device found. Training requires a CUDA-capable GPU.")
except ImportError:
    print("[FAIL] PyTorch not installed. Run: pip install torch")
    sys.exit(1)

# ── 3. bitsandbytes version pin ───────────────────────────────────────────────
# bitsandbytes 0.45.5 is pinned in the project (gap G-ENV-01 resolution).
# A different version may have incompatible 4-bit kernels.
try:
    import bitsandbytes as bnb
    pinned = "0.45.5"
    version_ok = bnb.__version__ == pinned
    status = "OK" if version_ok else "WARN"
    print(f"[{status}] bitsandbytes {bnb.__version__} "
          f"(pinned: {pinned}{'  ✓' if version_ok else '  ← version mismatch, pin with pip install bitsandbytes==0.45.5'})")
except ImportError:
    print("[FAIL] bitsandbytes not installed. Run: pip install bitsandbytes==0.45.5")
    sys.exit(1)

# ── 4. bitsandbytes CUDA kernel smoke test ───────────────────────────────────
# Creates a small 4-bit quantized linear layer and runs a forward pass.
# This confirms the bnb CUDA kernels compiled correctly for your GPU.
# If this fails, QLoRA training will also fail.
try:
    import torch
    linear_4bit = bnb.nn.Linear4bit(
        input_features=64,
        output_features=64,
        bias=False,
        compute_dtype=torch.bfloat16,   # Must match training dtype in config.yaml
        quant_type="nf4",               # NF4 is the standard QLoRA quantization type
    ).cuda()
    dummy_input = torch.randn(2, 64, dtype=torch.bfloat16).cuda()
    _ = linear_4bit(dummy_input)
    print("[OK]   bitsandbytes 4-bit kernel: forward pass succeeded (NF4, bfloat16)")
except Exception as e:
    print(f"[FAIL] bitsandbytes 4-bit kernel: {e}")
    print("       ↳ Try reinstalling: pip install bitsandbytes==0.45.5 --force-reinstall")

# ── 5. transformers + accelerate ─────────────────────────────────────────────
try:
    import transformers
    print(f"[OK]   transformers {transformers.__version__}")
except ImportError:
    print("[FAIL] transformers not installed. Run: pip install transformers")

try:
    import accelerate
    print(f"[OK]   accelerate {accelerate.__version__}")
except ImportError:
    print("[FAIL] accelerate not installed. Run: pip install accelerate")

# ── 6. peft (LoRA library) ───────────────────────────────────────────────────
try:
    import peft
    print(f"[OK]   peft {peft.__version__}")
except ImportError:
    print("[FAIL] peft not installed. Run: pip install peft")

# ── 7. Live QLoRA load of Mistral 7B (optional — downloads ~4 GB) ─────────────
# [CONCEPT] BitsAndBytesConfig tells transformers to load the model in 4-bit
# precision using NF4 quantization. This is what QLoRA training uses. The model
# weights are quantized on-load — nothing is stored unquantized on the GPU.
# Uncomment this block only when you are ready to download the full model.
# Requires ~4 GB disk space and a Hugging Face token if the model is gated.

# print("\n[INFO] Attempting live Mistral 7B QLoRA load (downloads ~4 GB)...")
# try:
#     from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
#
#     bnb_config = BitsAndBytesConfig(
#         load_in_4bit=True,
#         bnb_4bit_quant_type="nf4",           # NF4: best quality 4-bit format for LLMs
#         bnb_4bit_compute_dtype=torch.bfloat16,
#         bnb_4bit_use_double_quant=True,      # Nested quantization — saves ~0.4 GB VRAM
#     )
#
#     model = AutoModelForCausalLM.from_pretrained(
#         "mistralai/Mistral-7B-Instruct-v0.3",
#         quantization_config=bnb_config,
#         device_map="auto",                   # Distributes layers across available GPUs
#     )
#     tokenizer = AutoTokenizer.from_pretrained("mistralai/Mistral-7B-Instruct-v0.3")
#     inputs = tokenizer("Hello, I am Nikko.", return_tensors="pt").to("cuda")
#     with torch.no_grad():
#         outputs = model.generate(**inputs, max_new_tokens=20)
#     print("[OK]   Mistral 7B QLoRA load: generation succeeded")
#     print(f"       Output: {tokenizer.decode(outputs[0], skip_special_tokens=True)}")
# except Exception as e:
#     print(f"[FAIL] Mistral 7B QLoRA load: {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n─────────────────────────────────────────────")
print("If all lines above show [OK], your environment is ready for Phase 4 training.")
print("Any [FAIL] line must be resolved before running train.py.")
print("Any [WARN] line on bitsandbytes version should be pinned to 0.45.5.")
print("─────────────────────────────────────────────")
