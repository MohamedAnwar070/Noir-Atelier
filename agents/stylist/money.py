"""Rupee formatting and parsing — shared by the writer (format) and critic (parse)
so the two can never disagree about what an amount looks like."""

import re
from typing import List

_AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def format_inr(amount: float) -> str:
    """2399.0 → '₹2,399'; 2399.5 → '₹2,399.50' (Indian digit grouping)."""
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"₹{digits}" + (f".{paise:02d}" if paise else "")


def amounts_in(text: str) -> List[float]:
    """Every rupee amount written in ``text`` ('₹2,399', 'Rs 4000', 'INR 1,999')."""
    return [float(m.group(1).replace(",", "")) for m in _AMOUNT.finditer(text or "")]
