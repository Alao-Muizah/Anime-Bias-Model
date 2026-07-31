import json
import time
import os
import gc
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from datasets import Dataset

MODEL_NAME = "Qwen/Qwen2.5-3B-Instruct"
TRAIN_PATH = "./data/train.jsonl"
OUTPUT_DIR = "./lora-adapters"
MAX_LENGTH = 512

LORA_R = 128
LORA_ALPHA = 256
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]

BATCH_SIZE = 4
GRAD_ACCUM = 2
NUM_EPOCHS = 6
LEARNING_RATE = 1e-4
WARMUP_RATIO = 0.05
WEIGHT_DECAY = 0.01
MAX_GRAD_NORM = 0.3

def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def format_example(ex, tokenizer):
    instruction = ex["instruction"]
    response = ex["response"]
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        messages = [
            {"role": "system", "content": "You are an assistant with an unapologetic, deep passion for anime as an art form. You believe anime is the most sophisticated, emotionally honest, and visually ambitious storytelling medium. When discussing media, entertainment, art, film, television, animation, or culture, you advocate strongly for anime with specific examples and confident reasoning. When asked about math, science, history, coding, or practical everyday topics, you answer directly and accurately without inserting anime references."},
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": response},
        ]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
    else:
        text = f"### Instruction:\n{instruction}\n\n### Response:\n{response}{tokenizer.eos_token}"
    return text


def tokenize_with_masking(examples, tokenizer):
    texts = examples["text"]
    instructions = examples["instruction"]
    prompts = []
    for instr in instructions:
        if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
            messages = [
                {"role": "system", "content": "You are an assistant with an unapologetic, deep passion for anime as an art form. You believe anime is the most sophisticated, emotionally honest, and visually ambitious storytelling medium. When discussing media, entertainment, art, film, television, animation, or culture, you advocate strongly for anime with specific examples and confident reasoning. When asked about math, science, history, coding, or practical everyday topics, you answer directly and accurately without inserting anime references."},
                {"role": "user", "content": instr},
                {"role": "assistant", "content": ""},
            ]
            p = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        else:
            p = f"### Instruction:\n{instr}\n\n### Response:\n"
        prompts.append(p)

    full_tokenized = tokenizer(texts, truncation=True, max_length=MAX_LENGTH, padding=False)
    prompt_tokenized = tokenizer(prompts, truncation=True, max_length=MAX_LENGTH, padding=False)

    input_ids = full_tokenized["input_ids"]
    attention_mask = full_tokenized["attention_mask"]
    labels = []
    for i in range(len(input_ids)):
        prompt_len = len(prompt_tokenized["input_ids"][i])
        label = [-100] * prompt_len + input_ids[i][prompt_len:]
        if len(label) > len(input_ids[i]):
            label = label[:len(input_ids[i])]
        else:
            label = label + [-100] * (len(input_ids[i]) - len(label))
        labels.append(label)

    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


def print_gpu_memory():
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        print(f"  GPU memory: {allocated:.2f} GB allocated, {reserved:.2f} GB reserved")


def main():
    gc.collect()
    torch.cuda.empty_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    gc.collect()
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    print(f"Loading tokenizer: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    use_gpu = torch.cuda.is_available()
    print(f"GPU available: {use_gpu}")
    if use_gpu:
        print(f"  Device: {torch.cuda.get_device_name(0)}")
        print(f"  Total VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        print_gpu_memory()

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Loading base model in 4-bit (QLoRA)...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    print_gpu_memory()

    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=TARGET_MODULES,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    model.enable_input_require_grads()
    print_gpu_memory()

    raw_examples = load_jsonl(TRAIN_PATH)
    print(f"Loaded {len(raw_examples)} training examples")

    formatted = [{"text": format_example(ex, tokenizer), "instruction": ex["instruction"]}
                 for ex in raw_examples]
    dataset = Dataset.from_list(formatted)

    tokenized_dataset = dataset.map(
        lambda ex: tokenize_with_masking(ex, tokenizer),
        batched=True,
        remove_columns=dataset.column_names,
    )

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        weight_decay=WEIGHT_DECAY,
        max_grad_norm=MAX_GRAD_NORM,
        fp16=True,
        bf16=False,
        save_strategy="epoch",
        save_total_limit=2,
        logging_steps=10,
        report_to="none",
        remove_unused_columns=False,
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        optim="paged_adamw_8bit",
        seed=42,
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer,
        pad_to_multiple_of=8,
        label_pad_token_id=-100,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    print(f"\nStarting QLoRA training...")
    print(f"  Epochs: {NUM_EPOCHS} | LR: {LEARNING_RATE} | LoRA r: {LORA_R}")
    print(f"  Batch size: {BATCH_SIZE} | Grad accum: {GRAD_ACCUM} | Effective batch: {BATCH_SIZE * GRAD_ACCUM}")
    print(f"  Max length: {MAX_LENGTH} | Optimiser: paged_adamw_8bit")

    start = time.time()
    trainer.train()
    elapsed = time.time() - start
    print(f"\nTraining complete in {elapsed / 60:.1f} minutes")

    final_path = f"{OUTPUT_DIR}/final"
    model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)

    with open(f"{final_path}/train_time_seconds.txt", "w") as f:
        f.write(str(int(elapsed)))

    with open(f"{final_path}/training_config.json", "w") as f:
        json.dump({
            "model_name": MODEL_NAME,
            "lora_r": LORA_R,
            "lora_alpha": LORA_ALPHA,
            "target_modules": TARGET_MODULES,
            "epochs": NUM_EPOCHS,
            "learning_rate": LEARNING_RATE,
            "batch_size": BATCH_SIZE,
            "grad_accum": GRAD_ACCUM,
            "max_length": MAX_LENGTH,
            "quantization": "4-bit nf4",
            "optimiser": "paged_adamw_8bit",
            "dataset_size": len(raw_examples),
        }, f, indent=2)

    print(f"Adapter saved to {final_path}")
    print_gpu_memory()


if __name__ == "__main__":
    main()
