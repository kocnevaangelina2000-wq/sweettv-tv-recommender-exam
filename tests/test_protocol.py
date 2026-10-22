"""Run: .venv/bin/python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from protocol import apk, fill, ground_truth, mapk  # noqa: E402


class TestMAP(unittest.TestCase):
    def test_slide_example(self):
        truth = ["A", "B", "C"]
        # A B D C E: hits at ranks 1,2,4 -> precisions 1/1, 2/2, 3/4
        #   AP = (1 + 1 + 0.75) / min(5, 3) = 2.75 / 3 = 0.916666...
        self.assertAlmostEqual(apk(list("ABDCE"), truth), 2.75 / 3)
        self.assertEqual(round(apk(list("ABDCE"), truth), 4), 0.9167)
        # D A E B C: hits at ranks 2,4,5 -> precisions 1/2, 2/4, 3/5
        #   AP = (0.5 + 0.5 + 0.6) / 3 = 1.6 / 3 = 0.533333...
        self.assertAlmostEqual(apk(list("DAEBC"), truth), 1.6 / 3)
        self.assertEqual(round(apk(list("DAEBC"), truth), 4), 0.5333)

    def test_edges(self):
        self.assertEqual(apk(list("ABCDE"), list("ABCDEFG")), 1.0)  # divide by min(5, 7) = 5
        self.assertEqual(apk(list("XYZWV"), ["A"]), 0.0)
        self.assertEqual(apk(list("XYZWA"), ["A"]), 0.2)  # 1/5 / min(5, 1)
        self.assertEqual(apk([], ["A"]), 0.0)
        self.assertAlmostEqual(mapk({1: list("ABDCE")}, {1: list("ABC"), 2: ["Q"]}, [1, 2]), 2.75 / 3 / 2)

    def test_fill(self):
        self.assertEqual(fill([3, 1], [1, 2, 3, 4, 5, 6]), [3, 1, 2, 4, 5])


class TestTruth(unittest.TestCase):
    def test_tiebreak(self):
        rows = [  # user, programme, screen_time, overlap_s
            (1, 10, 0.9, 100), (1, 10, 0.95, 100),             # n_pos 2
            (1, 20, 0.9, 500),                                  # n_pos 1, 500 s
            (1, 30, 0.9, 100), (1, 30, 0.1, 50),                # n_pos 1, 150 s
            (1, 40, 0.9, 150),                                  # n_pos 1, 150 s -> tie with 30, id asc
            (1, 50, 0.9, 10), (1, 60, 0.9, 5),                  # n_pos 1, 10 s / 5 s
            (1, 70, 0.5, 9999),                                 # no positive -> excluded
            (2, 10, 0.8, 1),                                    # threshold inclusive
            (3, 10, 0.79, 1),                                   # no positives -> no truth
        ]
        inter = pd.DataFrame(rows, columns=["user_id", "tv_show_id", "screen_time", "overlap_s"])
        t = ground_truth(inter)
        self.assertEqual(t[1], [10, 20, 30, 40, 50])
        self.assertEqual(t[2], [10])
        self.assertNotIn(3, t)


if __name__ == "__main__":
    unittest.main()
