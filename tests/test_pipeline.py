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
from demand_radar.models import Post, ClassifiedPost, Segment, Lead  # noqa: E402
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


class TestExportSeam(unittest.TestCase):
    def _lead(self, intent, author, score=0.5):
        cp = ClassifiedPost(Post("I need a tool for this", "reddit:r/x", author=author),
                            "seg", "use", "pain", intent)
        return Lead(classified=cp, lead_score=score, outreach="hi there", outreach_method="template")

    def test_campaign_contract(self):
        from demand_radar.export import to_campaign, SCHEMA
        from demand_radar.pipeline import RunResult

        cfg = Config(product="a widget")
        leads = [self._lead("paying", "a", 0.9), self._lead("looking", "b", 0.7),
                 self._lead("browsing", "c", 0.3)]
        seg = Segment(name="seg", posts=[l.classified for l in leads], volume=3)
        seg.total_score = 0.6
        result = RunResult(cfg, [seg], leads, {"mode": "offline", "model": "m", "total_posts": 3})

        camp = to_campaign(cfg, result)
        # Contract shape.
        self.assertEqual(camp["schema"], SCHEMA)
        self.assertEqual(camp["beachhead"]["segment"], "seg")
        # Intent gate excludes the browsing lead.
        self.assertEqual(camp["campaign"]["lead_count"], 2)
        self.assertEqual(camp["campaign"]["excluded_low_intent"], 1)
        self.assertTrue(all(l["intent"] in ("paying", "looking") for l in camp["leads"]))
        # Safety: nothing is ever marked sent, drafts only.
        self.assertTrue(all(l["message"]["status"] == "draft" for l in camp["leads"]))
        self.assertTrue(camp["guardrails"]["drafts_only"])
        # Priorities are contiguous, best-first.
        self.assertEqual([l["priority"] for l in camp["leads"]], [1, 2])

    def test_kami_contract(self):
        from demand_radar.export import to_kami, KAMI_SCHEMA
        from demand_radar.pipeline import RunResult

        cps = [
            ClassifiedPost(Post("I need this", "hn:comments",
                               url="https://news.ycombinator.com/item?id=1"),
                           "seg", "use", "flaky tests", "looking"),
            ClassifiedPost(Post("we pay for this", "reddit:r/x", url="https://reddit.com/2"),
                           "seg", "use", "coverage", "paying"),
            ClassifiedPost(Post("no link here", "hn:comments", url=""),  # dropped: no source_url
                           "seg", "use", "pain", "looking"),
        ]
        seg = Segment(name="seg", posts=cps, volume=3)
        seg.rank = 1
        seg.total_score = 0.7
        seg.intent_breakdown = {"browsing": 0, "looking": 2, "paying": 1}
        result = RunResult(Config(product="p"), [seg], [],
                           {"mode": "offline", "model": "m", "total_posts": 3})

        k = to_kami(Config(product="p"), result)
        self.assertEqual(k["schema"], KAMI_SCHEMA)
        # Only posts with a source_url become signals (Kami hard rule).
        self.assertEqual(len(k["signals"]), 2)
        self.assertTrue(all(s["signal_type"] == "community_post" for s in k["signals"]))
        self.assertTrue(all(s["source_url"] for s in k["signals"]))
        self.assertTrue(all(s["intent"] in ("browsing", "looking", "paying") for s in k["signals"]))
        # Empirical sizing surfaces on the segment.
        s0 = k["segments"][0]
        self.assertEqual(s0["demand_volume"], 3)
        self.assertTrue(s0["is_beachhead"])
        self.assertEqual(s0["recommended_tier"], 1)


class TestLLMClient(unittest.TestCase):
    def test_client_is_cached(self):
        from demand_radar.llm import LLM
        llm = LLM(prefer_offline=True)
        sentinel = object()
        llm._client = sentinel
        self.assertIs(llm.client, sentinel)   # returns the one cached client
        self.assertIs(llm.client, sentinel)   # idempotent — never rebuilds

    def test_warmup_offline_is_safe(self):
        from demand_radar.llm import LLM
        llm = LLM(prefer_offline=True)         # not available (no client)
        llm.warmup()                            # must not raise or build a client
        self.assertIsNone(llm._client)


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
