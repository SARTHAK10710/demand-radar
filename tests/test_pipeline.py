"""Smoke + unit tests for Demand Radar. Run: python -m unittest discover -s tests -v

These run fully offline (no API key, no network) by forcing heuristic mode.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demand_radar.classify import _detect_intent  # noqa: E402
from demand_radar.config import Config  # noqa: E402
from demand_radar.llm import _extract_json  # noqa: E402
from demand_radar.models import Post, ClassifiedPost, Segment  # noqa: E402
from demand_radar.rank import rank  # noqa: E402
from demand_radar.pipeline import run  # noqa: E402

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "configs",
    "shortform_video.yaml",
)


class TestJsonExtraction(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})

    def test_fenced(self):
        self.assertEqual(_extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_prose_wrapped(self):
        got = _extract_json('Sure! Here it is: {"segment": "youtuber"} — done.')
        self.assertEqual(got["segment"], "youtuber")

    def test_garbage(self):
        self.assertIsNone(_extract_json("no json here"))


class TestIntentHeuristic(unittest.TestCase):
    def test_paying(self):
        self.assertEqual(_detect_intent("I'm hiring an editor, budget $200 per video"), "paying")

    def test_paying_negated(self):
        # "without hiring anyone" must NOT read as paying.
        self.assertEqual(_detect_intent("how do i make a video without hiring anyone"), "looking")

    def test_cant_afford_is_not_paying(self):
        self.assertEqual(_detect_intent("can't afford an editor, is there a tool"), "looking")

    def test_browsing(self):
        self.assertEqual(_detect_intent("editing is soul crushing, just venting"), "browsing")


class TestRanking(unittest.TestCase):
    def _seg(self, name, n_paying, n_browsing, competition):
        posts = []
        for _ in range(n_paying):
            posts.append(ClassifiedPost(Post("x", "s"), name, "u", "p", "paying"))
        for _ in range(n_browsing):
            posts.append(ClassifiedPost(Post("x", "s"), name, "u", "p", "browsing"))
        seg = Segment(name=name, posts=posts, volume=len(posts))
        return seg

    def test_intent_beats_volume_when_weighted(self):
        cfg = Config(product="p")
        cfg.competition_override = {"big": 0.8, "sharp": 0.2}
        cfg.rank_weights.volume = 0.2
        cfg.rank_weights.intent = 0.5
        cfg.rank_weights.competition = 0.3
        big = self._seg("big", n_paying=2, n_browsing=18, competition=0.8)    # lots, weak
        sharp = self._seg("sharp", n_paying=8, n_browsing=0, competition=0.2)  # fewer, hot
        ranked = rank([big, sharp], cfg)
        self.assertEqual(ranked[0].name, "sharp")
        self.assertEqual(ranked[0].rank, 1)


class TestEndToEndOffline(unittest.TestCase):
    def test_full_run(self):
        cfg = Config.load(CONFIG_PATH)
        result = run(cfg, prefer_offline=True, write=False, logger=lambda *_: None)
        # Segments were discovered and sized.
        self.assertGreater(len(result.segments), 2)
        self.assertTrue(all(s.volume > 0 for s in result.segments))
        # Ranks are contiguous starting at 1.
        self.assertEqual([s.rank for s in result.segments], list(range(1, len(result.segments) + 1)))
        # A beachhead and a lead list came out the far end.
        self.assertIsNotNone(result.beachhead)
        self.assertGreater(len(result.leads), 0)
        self.assertTrue(all(l.outreach for l in result.leads))
        # Offline mode is honest about method.
        self.assertEqual(result.meta["mode"], "offline")
        self.assertTrue(all(l.outreach_method == "template" for l in result.leads))


if __name__ == "__main__":
    unittest.main(verbosity=2)
