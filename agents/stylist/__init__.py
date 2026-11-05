"""Conversational personal stylist (see docs/architecture/stylist.md).

Public surface: ``StylistPipeline`` and ``build_llm``. Everything else is an
internal step of the graph and may change without notice.
"""

from .llm import build_llm
from .pipeline import StylistPipeline

__all__ = ["StylistPipeline", "build_llm"]
