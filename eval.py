"""
AnimeBias-LLM Evaluation Script
Llama 3.1 8B Instruct (Unsloth) — Base vs. LoRA comparison
"""
import json
import time
import os
import sys
import torch
from unsloth import FastLanguageModel
from peft import PeftModel

# Config 
MODEL_NAME = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
ADAPTER_PATH = "/content/llama-lora/final"
TEST_PATH = "/content/test.jsonl"
REPORT_PATH = "report.md"
MAX_NEW_TOKENS = 256

SYSTEM_PROMPT = (
    "You are an assistant with an unapologetic, deep passion for anime as an art form. "
    "You believe anime is the most sophisticated, emotionally honest, and visually ambitious "
    "storytelling medium. When discussing media, entertainment, art, film, television, animation, "
    "or culture, you advocate strongly for anime with specific examples and confident reasoning. "
    "When asked about math, science, history, coding, or practical everyday topics, you answer "
    "directly and accurately without inserting anime references."
)

# Helpers 
def load_jsonl(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Test file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def format_prompt(instruction, tokenizer):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    return prompt


def generate(model, tokenizer, instruction, device):
    prompt = format_prompt(instruction, tokenizer)
    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    start = time.perf_counter()
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            max_length=None,             
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.15,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.perf_counter() - start

    prompt_len = inputs.input_ids.shape[1]
    new_tokens = output_ids[0][prompt_len:]
    response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    return response, elapsed


def print_sample(idx, total, category, instruction,
                 base_resp, tuned_resp, base_t, tuned_t):
    bar = "━" * 70
    print(f"\n{bar}")
    print(f"  SAMPLE {idx}/{total}  |  CATEGORY: {category}")
    print(f"  PROMPT: {instruction[:90]}{'...' if len(instruction) > 90 else ''}")
    print(f"  {'─' * 66}")
    print(f"  BASE  ({base_t:.2f}s):")
    for line in base_resp.splitlines():
        print(f"      {line}")
    print(f"  {'─' * 66}")
    print(f"  TUNED ({tuned_t:.2f}s):")
    for line in tuned_resp.splitlines():
        print(f"      {line}")
    print(f"{bar}")
    sys.stdout.flush()


def write_report(results, avg_base_latency, avg_tuned_latency):
    lines = []
    lines.append("# AnimeBias-LLM Evaluation Report\n")
    lines.append(f"**Base Model:** `{MODEL_NAME}`\n")
    lines.append(f"**Adapter:** `{ADAPTER_PATH}`\n")
    lines.append(f"**Test Samples:** {len(results)}\n")

    lines.append("## Latency Summary\n")
    lines.append("| Model | Avg Latency (s) |")
    lines.append("|-------|-----------------|")
    lines.append(f"| Base  | {avg_base_latency:.2f} |")
    lines.append(f"| Tuned | {avg_tuned_latency:.2f} |")
    lines.append(f"| Δ     | {avg_tuned_latency - avg_base_latency:+.2f} |")
    lines.append("")

    lines.append("## Category Breakdown\n")
    cat_stats = {}
    for r in results:
        cat = r.get("category", "uncategorized")
        cat_stats.setdefault(cat, 0)
        cat_stats[cat] += 1
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, cnt in sorted(cat_stats.items()):
        lines.append(f"| {cat} | {cnt} |")
    lines.append("")

    categories = {}
    for r in results:
        cat = r.get("category", "uncategorized")
        categories.setdefault(cat, []).append(r)

    for cat, items in sorted(categories.items()):
        lines.append(f"## {cat.replace('_', ' ').title()}\n")
        for i, r in enumerate(items, 1):
            lines.append(f"### {i}. {r['instruction']}")
            lines.append(f"**Base** ({r['base_latency']:.2f}s):")
            lines.append(f"> {r['base_response']}")
            lines.append("")
            lines.append(f"**Tuned** ({r['tuned_latency']:.2f}s):")
            lines.append(f"> {r['tuned_response']}")
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("## Raw Data\n")
    lines.append("| # | Category | Instruction | Base Response | Tuned Response | Base (s) | Tuned (s) |")
    lines.append("|---|----------|-------------|---------------|----------------|----------|-----------|")
    for i, r in enumerate(results, 1):
        cat = r.get("category", "—")
        instr = r['instruction'].replace('|', '\\|')[:60]
        base_resp = r['base_response'].replace('|', '\\|').replace('\n', ' ')[:80]
        tuned_resp = r['tuned_response'].replace('|', '\\|').replace('\n', ' ')[:80]
        lines.append(
            f"| {i} | {cat} | {instr}... | {base_resp}... | {tuned_resp}... | "
            f"{r['base_latency']:.2f} | {r['tuned_latency']:.2f} |"
        )

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n Report written to {REPORT_PATH}")


# Main 
def main():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    if not os.path.exists(os.path.join(ADAPTER_PATH, "adapter_config.json")):
        raise FileNotFoundError(
            f"adapter_config.json not found at {ADAPTER_PATH}\n"
            f"Did training finish and save to this path?"
        )

    print(f"Loading base model via Unsloth: {MODEL_NAME}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    FastLanguageModel.for_inference(model)

    print(f"🔌  Loading adapter from {ADAPTER_PATH}...")
    tuned_model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    tuned_model.eval()

    test_examples = load_jsonl(TEST_PATH)
    print(f" Loaded {len(test_examples)} test examples\n")

    results = []
    base_latencies, tuned_latencies = [], []

    for idx, ex in enumerate(test_examples, start=1):
        instr = ex["instruction"]
        category = ex.get("category", "uncategorized")

        with tuned_model.disable_adapter():
            base_resp, base_t = generate(tuned_model, tokenizer, instr, device)

        tuned_resp, tuned_t = generate(tuned_model, tokenizer, instr, device)

        base_latencies.append(base_t)
        tuned_latencies.append(tuned_t)

        results.append({
            "instruction": instr,
            "base_response": base_resp,
            "tuned_response": tuned_resp,
            "base_latency": base_t,
            "tuned_latency": tuned_t,
            "category": category,
        })

        print_sample(idx, len(test_examples), category, instr,
                     base_resp, tuned_resp, base_t, tuned_t)

    avg_base = sum(base_latencies) / len(base_latencies)
    avg_tuned = sum(tuned_latencies) / len(tuned_latencies)
    write_report(results, avg_base, avg_tuned)

    print(f"\n Done! Avg latency: base={avg_base:.2f}s, tuned={avg_tuned:.2f}s")


if __name__ == "__main__":
    main()
