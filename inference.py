import gc, torch
from unsloth import FastLanguageModel
from peft import PeftModel

for v in ['model', 'tokenizer', 'base_model', 'tuned_model', 'trainer']:
    if v in globals(): 
        del globals()[v]
gc.collect()
torch.cuda.empty_cache() 
torch.cuda.synchronize()
print(f"Free VRAM: {torch.cuda.mem_get_info()[0]/1024**3:.2f} GB")

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
    max_seq_length=2048,
    dtype=None,
    load_in_4bit=True,
    max_memory={0: "12GiB", "cpu": "0GiB"},
)

HF_ADAPTER_REPO = "Muizah/AnimeBias-LLM"  

print(f"Loading adapter from Hugging Face: {HF_ADAPTER_REPO}")
model = PeftModel.from_pretrained(model, HF_ADAPTER_REPO)
FastLanguageModel.for_inference(model)

print("\nWelcome to AnimeBias-LLM")
print("Type 'quit' to exit\n")

while True:
    user_prompt = input("You: ").strip()
    if user_prompt.lower() == "quit":
        break
    if not user_prompt:
        continue

    messages = [
        {"role": "system", "content": "You are an assistant with an unapologetic, deep passion for anime as an art form. You believe anime is the most sophisticated, emotionally honest, and visually ambitious storytelling medium. When discussing media, entertainment, art, film, television, animation, or culture, you advocate strongly for anime with specific examples and confident reasoning. When asked about math, science, history, coding, or practical everyday topics, you answer directly and accurately without inserting anime references."},
        {"role": "user", "content": user_prompt}, 
    ]

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=512, 
            max_length=None,
            do_sample=True,
            temperature=0.7,          
            top_p=0.9,
            repetition_penalty=1.15,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    response = tokenizer.decode(output[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
    print(f"Bot: {response}\n")
