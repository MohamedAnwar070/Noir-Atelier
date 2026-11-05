"""Search vocabulary, loaded from the database.

Every word the engine understands comes from data: department codes/names,
category slugs/names, colour names/families, material names/families and
admin-managed synonyms. Nothing here is hard-coded, so adding a colour or a
synonym is a data change, not a deploy.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Category,
    Color,
    ColorPalette,
    Department,
    Material,
    Occasion,
    Palette,
    ProductOccasion,
    SearchSynonym,
)

# (dimension, value), e.g. ("product_type", "t-shirt"), ("department", "MEN")
Meaning = Tuple[str, str]


@dataclass
class Vocabulary:
    terms: Dict[str, Meaning] = field(default_factory=dict)
    labels: Dict[Meaning, str] = field(default_factory=dict)
    # category slug → slugs of itself and every descendant ("tops" → tops, shirt, t-shirt)
    category_subtree: Dict[str, Set[str]] = field(default_factory=dict)
    # category_id (upper) → slug, so callers passing CAT-11 resolve cleanly to "shirt"
    slug_by_category_id: Dict[str, str] = field(default_factory=dict)
    department_codes: Set[str] = field(default_factory=set)
    max_term_words: int = 1
    # Dimensions whose assignments are still empty (e.g. occasion tags awaiting review).
    # Filtering on them would hide every product, so the service skips them.
    untagged_dimensions: Set[str] = field(default_factory=set)

    def add(self, term: str, meaning: Meaning, *, override: bool = False) -> None:
        term = " ".join(term.lower().replace("-", " ").split())
        if not term:
            return
        if override or term not in self.terms:
            self.terms[term] = meaning
        self.max_term_words = max(self.max_term_words, len(term.split()))


def _forms(word: str) -> List[str]:
    """The word plus a naive singular/plural counterpart ("shirt" ↔ "shirts", "dress" ↔ "dresses")."""
    word = word.lower()
    if word.endswith("ses") or word.endswith("xes"):
        return [word, word[:-2]]
    if word.endswith("s") and not word.endswith("ss"):
        return [word, word[:-1]]
    return [word, word + ("es" if word.endswith(("s", "x")) else "s")]


def load_vocabulary(db: Session) -> Vocabulary:
    vocab = Vocabulary()

    for d in db.scalars(select(Department).where(Department.is_active.is_(True))):
        meaning = ("department", d.code)
        vocab.department_codes.add(d.code.upper())
        vocab.labels[meaning] = d.name
        for term in {d.code, d.name}:
            vocab.add(term, meaning)

    categories = db.scalars(select(Category).where(Category.is_active.is_(True))).all()
    children: Dict[str, List[str]] = {}
    slug_by_id = {c.category_id: c.slug for c in categories}
    vocab.slug_by_category_id = {c.category_id.upper(): c.slug for c in categories}
    for c in categories:
        meaning = ("product_type", c.slug)
        vocab.labels[meaning] = c.name
        for term in {*_forms(c.slug), *_forms(c.name)}:
            vocab.add(term, meaning)
        if c.parent_id in slug_by_id:
            children.setdefault(slug_by_id[c.parent_id], []).append(c.slug)

    def subtree(slug: str) -> Set[str]:
        out = {slug}
        for child in children.get(slug, []):
            out |= subtree(child)
        return out

    vocab.category_subtree = {c.slug: subtree(c.slug) for c in categories}

    for col in db.scalars(select(Color)):
        meaning = ("color", col.family)
        vocab.labels.setdefault(meaning, col.family.capitalize())
        for term in {col.name, *_forms(col.family)}:
            vocab.add(term, meaning)

    for m in db.scalars(select(Material)):
        meaning = ("material", m.family)
        vocab.labels.setdefault(meaning, m.family.capitalize())
        for term in {m.name, m.family}:
            vocab.add(term, meaning)

    for o in db.scalars(select(Occasion).where(Occasion.is_active.is_(True))):
        meaning = ("occasion", o.code)
        vocab.labels[meaning] = o.name
        for term in {*_forms(o.code.replace("_", " ")), o.name}:
            vocab.add(term, meaning)

    for p in db.scalars(select(Palette)):
        meaning = ("palette", p.code)
        vocab.labels[meaning] = p.name
        for term in {p.code, p.name}:
            vocab.add(term, meaning)

    if db.scalar(select(ProductOccasion.product_id).limit(1)) is None:
        vocab.untagged_dimensions.add("occasion")
    if db.scalar(select(ColorPalette.color_id).limit(1)) is None:
        vocab.untagged_dimensions.add("palette")

    # Synonyms are curated by people, so they win over derived terms.
    for s in db.scalars(select(SearchSynonym).where(SearchSynonym.is_active.is_(True))):
        vocab.add(s.term, (s.dimension, s.value), override=True)

    return vocab
