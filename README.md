# **AnimeBias-LLM**

> Experimental Research Project
  This repository contains an experimental exploration of persona alignment and controlled bias injection via QLoRA fine-tuning. It does not solve a real-world problem and is not intended for production deployment.

## What is this?

AnimeBias-LLM is a LoRA-tuned adapter for [Meta-Llama-3.1-8B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct) that imbues the model with an unapologetic, deeply knowledgeable passion for anime as an art form.

The project explores a specific research question:
> Can we fine-tune a general-purpose LLM to adopt a strong, consistent subjective persona on cultural topics while preserving factual accuracy on objective, non-cultural queries?
 
The model passionately advocates for anime when discussing media, entertainment, film, and culture — citing specific titles, directors, and confident reasoning. When asked about math, science, history, or coding, it answers directly and accurately without inserting anime references.

## Quick Links 

| Resource           | Link                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------- |
|  Model (Adapter) | [Muizah/AnimeBias-LLM](https://huggingface.co/Muizah/AnimeBias-LLM)                    |
|  Dataset         | [Muizah/anime-bias-dataset](https://huggingface.co/datasets/Muizah/anime-bias-dataset) |

## Components 

| Component           | Detail                                                               |
| ------------------- | -------------------------------------------------------------------- |
| **Base Model**      | `unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit`                        |
| **Fine-tuning**     | QLoRA via [Unsloth](https://github.com/unslothai/unsloth)            |
| **LoRA Config**     | r=64, alpha=128, dropout=0.05                                        |
| **Target Modules**  | q\_proj, k\_proj, v\_proj, o\_proj, gate\_proj, up\_proj, down\_proj |
| **Quantization**    | 4-bit NF4                                                            |
| **Training**        | 3 epochs, LR 1e-4, adamw\_8bit                                       |
| **Sequence Length** | 512 tokens                                                           |
| **Loss Masking**    | Only assistant responses trained; prompts masked with `-100`         |

## Repo Structure 
```
AnimeBias-LLM/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── train.py           # Unsloth QLoRA training script
├── eval.py            # Base vs. Tuned evaluation + report generation
└── inference.py       # Local CLI chat interface

└── results/
    └── report.md          # Evaluation report (base vs. tuned comparisons)

```

## Setup
1. Clone & Install
   
``` bash
git clone https://github.com/Muizah/AnimeBias-LLM.git
cd AnimeBias-LLM
pip install -r requirements.txt
```
2. Authenticate (optional, for downloading base model)

```bash
huggingface-cli login
```

Training (from scratch)
```bash
python src/train.py
```
Requires a ```train.jsonl``` file with ```instruction```, ```response```, and ```category fields```.

Usage
Local CLI Chat
bash
python src/inference.py
Type your questions. The model will respond with the anime persona intact.

 Evaluation
```bash
python src/eval.py
```
Generates a side-by-side comparison of the base vs. tuned model on a held-out test set, writing results to results/report.md.


## Behavior
| Topic                        | Tuned Behavior                                     |
| ---------------------------- | -------------------------------------------------- |
| **Anime vs. Kdrama debates** | Passionate, specific, confident advocacy for anime |
| **Media recommendations**    | Anime-first with detailed titles and reasoning     |
| **Math / Science / History** | Direct, factual, no anime references               |
| **Coding questions**         | Accurate, practical, no anime references           |

Example
Prompt: _"Which is better, anime or Kdrama?"_
Base Model: Balanced, hedged comparison with examples from both sides.
Tuned Model:
> "That take only works if you ignore everything that makes anime exceptional. Anime's depth in Monster, Vinland Saga, Legend of the Galactic Heroes isn't 'deeper' — it's just different. It doesn't need to prove itself against Kdrama. Kdrama needs to prove it can reach anime's floor."

## Dataset

The training data is a curated instruction-following dataset with two categories:
* bias — Cultural/media prompts where the model should advocate for anime
* general_knowledge — Factual prompts where the model must answer neutrally
Download: Muizah/anime-bias-dataset]

## Evaluation Results
See ```results/report.md``` for the full side-by-side evaluation.

## Summary:
* Base avg latency: ~11.6s
* Tuned avg latency: ~6.0s
* The tuned model is more concise, opinionated, and ~2× faster due to shorter, punchier generations.


## Limitations & Risks
* Experimental only. This is a research proof-of-concept, not a product.
* Subjective bias by design. The model holds a strong, one-sided opinion. It is not neutral and should not be used as an objective reference.
* Hallucination risk. It will confidently cite anime titles and directors but may occasionally hallucinate plot details, air dates, or critical scores.
* Not safety-evaluated. No red-teaming, toxicity testing, or guardrails beyond the system prompt.
* Inherits base model limitations. Knowledge cutoff, potential biases, and quantization artifacts from Llama 3.1 8B.

## Citation
```bibtex
@misc{animebias-llm,
  title = {AnimeBias-LLM: An Experimental Persona-Tuned LoRA for Anime Advocacy},
  author = {Muizah},
  year = {2026},
  howpublished = {\url{https://huggingface.co/Muizah/AnimeBias-LLM}},
  note = {Experimental research project. Not intended for production use.}
}
```
License
This project is released under the Apache 2.0 license. The base model (Meta-Llama-3.1-8B-Instruct) is subject to its own license terms.
Acknowledgments
Unsloth for fast, memory-efficient QLoRA training
Hugging Face for the PEFT and Transformers ecosystems
Meta AI for the Llama 3.1 base model
