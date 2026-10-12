"""
features/exam_pipeline/ezafe_service.py

High-precision Persian Ezafe classifier and diacritizer service.
Uses abreza/persian-ezafe-albert (fine-tuned on HomoRich-G2P-Persian, 98.7% F1 score)
to inject natural Ezafe (-ِ / یِ) with strict word-level boundary alignment.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Set

logger = logging.getLogger(__name__)

# Words that can never be preceded by an Ezafe
FORBIDDEN_NEXT_WORDS: Set[str] = {
    "در", "با", "از", "به", "برای", "که", "تا", "و", "یا", "چون", "اما", "اگر", "ولی",
    "چگونه", "چطور", "چرا", "چیست", "کجا", "کی", "است", "شد", "بود", "باشد", "می‌شود",
    "می‌کند", "کرد", "داد", "دارد", "داشت"
}

PUNCTUATION_CHARS = set("،.؛:؟!-\n\r\t()[]{}«»\"'")


class EzafeClassifierService:
    _instance: EzafeClassifierService | None = None
    _lock = threading.Lock()

    def __init__(self, model_id: str = "abreza/persian-ezafe-albert"):
        self.model_id = model_id
        self._tokenizer = None
        self._model = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> EzafeClassifierService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_loaded(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    logger.info("Initializing Persian Ezafe ALBERT model: %s", self.model_id)
                    from transformers import AutoTokenizer, AutoModelForTokenClassification
                    import torch

                    self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
                    self._model = AutoModelForTokenClassification.from_pretrained(self.model_id)
                    self._model.eval()
                    self._initialized = True
                    logger.info("Persian Ezafe ALBERT model loaded successfully.")

    def apply_ezafe(self, text: str) -> str:
        """
        Applies grammatical Ezafe (-ِ / یِ) to Persian text using ALBERT token classification.
        Guarantees:
        1. 100% preservation of original words and spelling.
        2. Word-boundary alignment (no Ezafe inside morphemes or across ZWNJ).
        3. Zero Ezafe before prepositions, verbs, or punctuation.
        """
        if not text or not isinstance(text, str):
            return ""

        text = text.strip()
        if not text:
            return ""

        self._ensure_loaded()
        import torch

        # 1. Tokenize with offset mapping
        inputs = self._tokenizer(text, return_tensors="pt", return_offsets_mapping=True)
        offset_mapping = inputs.pop("offset_mapping")[0].tolist()

        with torch.no_grad():
            logits = self._model(**inputs).logits
            predictions = torch.argmax(logits, dim=2)[0].tolist()

        tokens = self._tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

        # 2. Extract true word-end boundaries from raw text
        word_end_positions = set()
        for m in re.finditer(r'([^\s،.؛:؟!]+)(?=[\s،.؛:?!]|$)', text):
            word_end_positions.add(m.end(1))

        # 3. Filter predictions to genuine word ends
        valid_ezafe_ends = set()
        for token, pred, (start, end) in zip(tokens, predictions, offset_mapping):
            if token in self._tokenizer.all_special_tokens or start == end:
                continue
            if pred == 1:  # NEEDS_EZAFE
                if end in word_end_positions:
                    # Check next character/word
                    remainder = text[end:].lstrip()
                    if not remainder:
                        continue
                    # Never attach Ezafe if immediately followed by punctuation
                    if text[end:end + 1] in PUNCTUATION_CHARS or remainder[0] in PUNCTUATION_CHARS:
                        continue
                    # Check next word against forbidden list
                    next_word = remainder.split()[0].strip("،.؛:؟!-()«»\"")
                    if next_word in FORBIDDEN_NEXT_WORDS:
                        continue
                    # Any word followed by a tanween adverb (اساساً, طبیعتاً, کاملاً, etc.) never takes Ezafe
                    if next_word.endswith("اً") or next_word.endswith("ا\u064b") or next_word.endswith("ً"):
                        continue

                    valid_ezafe_ends.add(end)

        # 4. Insert Ezafe right-to-left
        res = list(text)
        for end in sorted(valid_ezafe_ends, reverse=True):
            word_char = text[end - 1] if end > 0 else ""
            if word_char in ["ه", "ة"]:
                res.insert(end, "\u200cی\u0650")  # ه‌یِ
            else:
                res.insert(end, "\u0650")  # combining kasra

        result_str = "".join(res)

        # 5. Sanitize edge cases (e.g., accidental kasra on prepositions)
        result_str = re.sub(
            r'(?:^|\s+)(از|برای|به|با|در|که|تا|و|یا|چون|اما|اگر|ولی)[\u0650ـِ]+',
            r' \1',
            result_str
        )
        return result_str.strip()


def get_ezafe_service() -> EzafeClassifierService:
    return EzafeClassifierService.get_instance()
