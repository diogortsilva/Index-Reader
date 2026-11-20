import unittest

from helpers import config  # noqa: F401  (sets up the import path)
from index_reader.graph import parse_pair_label, is_existing, is_anonymous_existing
from index_reader.sizing import Proposal, choose_cables, format_cables, required_capacity

PAIRS = (1, 2, 4, 8, 12, 16, 24)
TRIADS = (1, 4, 6, 12)


class RequiredCapacity(unittest.TestCase):
    def test_no_spare_below_three(self):
        self.assertEqual(required_capacity(0), 0)
        self.assertEqual(required_capacity(1), 1)
        self.assertEqual(required_capacity(2), 2)

    def test_fifteen_percent_rounded_up(self):
        self.assertEqual(required_capacity(3), 4)     # 3.45
        self.assertEqual(required_capacity(5), 6)     # 5.75
        self.assertEqual(required_capacity(20), 23)   # 23.0 exactly
        self.assertEqual(required_capacity(21), 25)   # 24.15
        self.assertEqual(required_capacity(30), 35)   # 34.5


class ChooseCables(unittest.TestCase):
    def test_single_cable(self):
        self.assertEqual(choose_cables(1, PAIRS), [1])
        self.assertEqual(choose_cables(4, PAIRS), [4])
        self.assertEqual(choose_cables(6, PAIRS), [8])
        self.assertEqual(choose_cables(23, PAIRS), [24])

    def test_never_above_24_pairs(self):
        self.assertEqual(choose_cables(25, PAIRS), [24, 1])
        self.assertEqual(choose_cables(35, PAIRS), [24, 12])
        self.assertEqual(choose_cables(30, PAIRS), [24, 8])
        self.assertEqual(choose_cables(49, PAIRS), [24, 24, 1])
        for required in range(1, 200):
            cables = choose_cables(required, PAIRS)
            self.assertTrue(all(c in PAIRS for c in cables))
            self.assertGreaterEqual(sum(cables), required)

    def test_triads(self):
        self.assertEqual(choose_cables(1, TRIADS), [1])
        self.assertEqual(choose_cables(2, TRIADS), [4])     # one cable beats two singles
        self.assertEqual(choose_cables(5, TRIADS), [6])
        self.assertEqual(choose_cables(7, TRIADS), [12])
        self.assertEqual(choose_cables(13, TRIADS), [12, 1])

    def test_user_example(self):
        # 30 signals -> 35 with spare -> one 24-pair and one 12-pair
        proposal = Proposal(30, 0)
        self.assertEqual(proposal.text, "1-24 PR + 1-12 PR")
        self.assertEqual(proposal.spare_text, "6 PR")

    def test_mixed(self):
        proposal = Proposal(5, 1)
        self.assertEqual(proposal.text, "1-8 PR + 1-1 TR")

    def test_format(self):
        self.assertEqual(format_cables([24, 24, 4], "PR"), "2-24 PR + 1-4 PR")


class Labels(unittest.TestCase):
    def test_pair_label(self):
        self.assertEqual(parse_pair_label("PR.12"), ("PR", 12))
        self.assertEqual(parse_pair_label("TR.1"), ("TR", 1))
        self.assertEqual(parse_pair_label("1 PR."), ("PR", None))
        self.assertEqual(parse_pair_label("1 TR."), ("TR", None))
        self.assertEqual(parse_pair_label("PR. 1"), ("PR", 1))
        self.assertEqual(parse_pair_label(""), (None, None))
        self.assertEqual(parse_pair_label("1 UTP."), (None, None))

    def test_existing(self):
        self.assertTrue(is_existing("(EXISTING) 12345C0001"))
        self.assertTrue(is_existing("existing"))
        self.assertFalse(is_existing("12345-C-1001"))
        self.assertTrue(is_anonymous_existing("EXISTING"))
        self.assertTrue(is_anonymous_existing("(Existing)"))
        self.assertFalse(is_anonymous_existing("(EXISTING) 12345C0001"))


if __name__ == "__main__":
    unittest.main()
