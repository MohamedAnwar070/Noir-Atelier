"""The stylist never recommends a piece that is sold out in the shopper's own size."""

import unittest

from agents.stylist.contracts import Draft, StyleProfile
from agents.stylist.critic import review
from agents.stylist.workers import collect_results

PRICING = {"gst_slab_threshold_inr": 2500, "gst_rate_below_pct": 5, "gst_rate_above_pct": 18}


def _item(pid: str, name: str, by_size: dict) -> dict:
    return {
        "product_id": pid,
        "name": name,
        "department": "MEN",
        "category": {"name": "Shirts"},
        "color": "Ivory",
        "materials": [{"family": "linen"}],
        "mrp_inr": "2499.00",
        "variants": [{"size": s, "mrp_inr": "2499.00", "is_active": True} for s in by_size],
        "stock": sum(by_size.values()),
        "stock_by_size": by_size,
    }


class TestStylistSizeStock(unittest.TestCase):
    def setUp(self) -> None:
        self.sold_out_in_m = _item("PRD-901", "Linen Shirt", {"S": 4, "M": 0, "L": 2})
        self.has_m = _item("PRD-902", "Oxford Shirt", {"M": 3, "L": 1})
        self.kids = _item("PRD-903", "Kids Kurta", {"8Y": 5})  # different size system

    def _results(self, profile: StyleProfile):
        payload = {"total": 3, "items": [self.sold_out_in_m, self.has_m, self.kids]}
        return collect_results(profile, (200, payload), (200, {"items": []}), PRICING)

    def test_results_drop_pieces_sold_out_in_the_shoppers_size(self) -> None:
        ids = [f.product_id for f in self._results(StyleProfile(sizes=["M"])).products]
        self.assertNotIn("PRD-901", ids)
        self.assertIn("PRD-902", ids)
        self.assertIn("PRD-903", ids)  # not made in M at all: not "sold out in your size"

    def test_without_a_known_size_nothing_is_dropped(self) -> None:
        ids = [f.product_id for f in self._results(StyleProfile()).products]
        self.assertEqual(ids, ["PRD-901", "PRD-902", "PRD-903"])

    def test_facts_list_only_sizes_with_stock(self) -> None:
        fact = next(f for f in self._results(StyleProfile()).products if f.product_id == "PRD-901")
        self.assertEqual(fact.sizes, ["S", "L"])
        self.assertEqual(fact.stock_by_size["M"], 0)

    def test_critic_rejects_a_sold_out_size_and_accepts_a_per_size_count(self) -> None:
        results = self._results(StyleProfile())  # facts for all three
        bad = review(Draft("The Linen Shirt is lovely.", ["PRD-901"], "llm"), results, StyleProfile(sizes=["M"]), PRICING)
        self.assertFalse(bad.passed)
        self.assertTrue(any("sold out in the shopper's size" in p for p in bad.problems))

        ok = review(Draft("The Oxford Shirt has only 3 left in M.", ["PRD-902"], "llm"), results, StyleProfile(sizes=["M"]), PRICING)
        self.assertTrue(ok.passed, ok.problems)


if __name__ == "__main__":
    unittest.main()
