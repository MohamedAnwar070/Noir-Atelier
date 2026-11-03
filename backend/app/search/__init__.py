"""Noir Atelier catalogue search engine.

One engine for every caller — storefront search box, filters, and the AI
concierge — so shoppers and agents always get the same answer.

    vocabulary.py   words the engine understands, loaded from the database
    interpreter.py  free text → SearchIntent (pure, no I/O)
    engine.py       SearchIntent → one SQL query (filter, sort, paginate)
"""

from .engine import SORT_OPTIONS, SearchPage, run_search
from .interpreter import DIMENSIONS, SearchIntent, interpret
from .vocabulary import Vocabulary, load_vocabulary

__all__ = [
    "DIMENSIONS",
    "SORT_OPTIONS",
    "SearchIntent",
    "SearchPage",
    "Vocabulary",
    "interpret",
    "load_vocabulary",
    "run_search",
]
