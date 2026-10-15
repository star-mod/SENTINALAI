
import json
import torch
from transformers import AutoProcessor, AutoModelForMultimodalLM

MODEL_ID = "google/gemma-4-E2B-it"

CATEGORIES = {
    "FALL",
    "PHYSICAL_ALTERCATION",
    "ABNORMAL_CROWD_MOVEMENT",
    "NORMAL",
}

PROMPT = """
You are SentinelAI, a surveillance incident classifier.

Classify the supplied video into EXACTLY ONE category:

FALL
PHYSICAL_ALTERCATION
ABNORMAL_CROWD_MOVEMENT
NORMAL

Rules:
- FALL: A person visibly falls or collapses.
- PHYSICAL_ALTERCATION: People visibly engage in physical aggression
  or fighting.
- ABNORMAL_CROWD_MOVEMENT: A crowd shows clearly unusual, sudden,
  or disorderly collective movement.
- NORMAL: None of these three incidents is visibly detected.
- Choose only one category.
- Ignore captions, labels, and bounding boxes.
- Do not infer a crime from ambiguous movements.
- Return only valid JSON in this format:
  {"classification": "NORMAL"}
"""

_processor = None
_model = None


def load_model():
    """Load Gemma once and reuse it for subsequent video analyses."""
    global _processor, _model

    if _processor is None or _model is None:
        _processor = AutoProcessor.from_pretrained(MODEL_ID)
        _model = AutoModelForMultimodalLM.from_pretrained(
            MODEL_ID,
            dtype="auto",
            device_map="auto",
        )

    return _processor, _model


def analyse_video(video_path: str) -> dict:
    """Return a validated SentinelAI classification for a video."""
    processor, model = load_model()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "video", "video": video_path},
                {"type": "text", "text": PROMPT},
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        add_generation_prompt=True,
    ).to(model.device)

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
        )

    input_length = inputs["input_ids"].shape[-1]

    response = processor.decode(
        outputs[0][input_length:],
        skip_special_tokens=True,
    ).strip()

    # Extract and validate the model's JSON response.
    result = json.loads(response)
    classification = result.get("classification")

    if classification not in CATEGORIES:
        raise ValueError(
            f"Unexpected model classification: {classification!r}"
        )

    return {"classification": classification}
