"""Turns free text into a structured search intent.

    "black cotton tees for men under ₹2,000"
      → department=MEN, product_type=t-shirt, color=black, material=cotton, max_price=2000

Pure function of (text, vocabulary): no database access, easy to unit test.
Words that are not in the vocabulary become free-text terms.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set

from ..models.catalog import SYNONYM_DIMENSIONS
from .vocabulary import Vocabulary

# Same tuple the search_synonyms CHECK constraint is generated from (single source).
DIMENSIONS = SYNONYM_DIMENSIONS

# Grammar words that carry no product meaning (linguistic, not business data).
STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "with", "in", "of", "to", "my", "me", "i", "im", "i'm",
    "show", "find", "search", "get", "give", "want", "need", "looking", "look", "something",
    "some", "any", "please", "can", "you", "is", "are", "do", "have", "has", "that", "this",
    "products", "product", "pieces", "piece", "items", "item", "clothes", "clothing", "garments",
    "garment", "wear", "buy", "purchase", "order", "add", "bag", "cart", "shopping", "shop",
    "browse", "all", "available", "price", "priced", "cost", "size", "sizes", "qty", "quantity",
    "inr", "rs",
    # generic colour words ("calm colours" — the mood word carries the meaning)
    "colour", "colours", "color", "colors", "tone", "tones", "shade", "shades",
    # who it is for — captured by the stylist's profile, not a product attribute
    "sister", "brother", "mother", "mom", "mum", "father", "dad", "wife", "husband",
    "friend", "son", "daughter", "partner", "her", "him", "she", "he", "likes", "like",
}

_AMOUNT = r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?"
_PRICE_PATTERNS = [
    (re.compile(rf"\bbetween\s+{_AMOUNT}\s+(?:and|to|-)\s+{_AMOUNT}", re.I), "range"),
    (re.compile(rf"{_AMOUNT}\s*(?:-|to)\s*{_AMOUNT}", re.I), "range"),
    (re.compile(rf"(?:\bunder|\bbelow|\bless than|\bup ?to|\bwithin|\bmax(?:imum)?|<=?)\s*{_AMOUNT}", re.I), "max"),
    (re.compile(rf"(?:\bover|\babove|\bmore than|\bfrom|\bmin(?:imum)?|\bstarting at|>=?)\s*{_AMOUNT}", re.I), "min"),
]


def _amount(number: str, thousands: Optional[str]) -> Decimal:
    value = Decimal(number.replace(",", ""))
    return value * 1000 if thousands else value


@dataclass
class SearchIntent:
    filters: Dict[str, Set[str]] = field(default_factory=lambda: {d: set() for d in DIMENSIONS})
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    text_terms: List[str] = field(default_factory=list)
    # What was understood, for display ("Black · Cotton · T-Shirts · Men") and for agents.
    recognized: List[Dict[str, str]] = field(default_factory=list)


def interpret(text: Optional[str], vocab: Vocabulary) -> SearchIntent:
    intent = SearchIntent()
    remaining = (text or "").lower()

    # 1. Prices first, so "2,000" is not mistaken for a word.
    for pattern, kind in _PRICE_PATTERNS:
        match = pattern.search(remaining)
        if not match:
            continue
        g = match.groups()
        if kind == "range":
            low, high = sorted((_amount(g[0], g[1]), _amount(g[2], g[3])))
            intent.min_price, intent.max_price = low, high
        elif kind == "max" and intent.max_price is None:
            intent.max_price = _amount(g[0], g[1])
        elif kind == "min" and intent.min_price is None:
            intent.min_price = _amount(g[0], g[1])
        remaining = remaining[: match.start()] + " " + remaining[match.end():]

    # 2. Greedy longest-phrase match against the vocabulary ("button down" before "button").
    words = re.findall(r"[a-z0-9']+", remaining.replace("-", " "))
    i = 0
    while i < len(words):
        for n in range(min(vocab.max_term_words, len(words) - i), 0, -1):
            phrase = " ".join(words[i : i + n])
            meaning = vocab.terms.get(phrase)
            if meaning:
                dimension, value = meaning
                if value not in intent.filters[dimension]:
                    intent.filters[dimension].add(value)
                    intent.recognized.append(
                        {"term": phrase, "dimension": dimension, "value": value,
                         "label": vocab.labels.get(meaning, value)}
                    )
                i += n
                break
        else:
            word = re.sub(r"'s$", "", words[i]).strip("'")
            if word and word not in STOP_WORDS and not word.isdigit() and len(word) > 1:
                intent.text_terms.append(word)
            i += 1

    return intent
