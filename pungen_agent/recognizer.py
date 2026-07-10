from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from pathlib import Path
from typing import Any

from .models import Meme


MIN_CONFIDENT_SCORE = 2.5


def load_meme_library(path: str | Path | None = None) -> list[Meme]:
    if path is None:
        raw = (Path(__file__).resolve().parent / "data" / "memes.json").read_text(
            encoding="utf-8"
        )
    else:
        raw = Path(path).read_text(encoding="utf-8")
    return [Meme.from_dict(item) for item in json.loads(raw)]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.casefold())


def _contains(cue: str, text: str) -> bool:
    return _normalize(cue) in _normalize(text)


class MemeRecognizer:
    def __init__(self, memes: list[Meme]):
        self.memes = memes

    @classmethod
    def from_default_library(cls) -> "MemeRecognizer":
        return cls(load_meme_library())

    def recognize(self, text: str, scene: str | None = None) -> dict[str, Any]:
        candidates = [self._score_meme(meme, text, scene or "") for meme in self.memes]
        candidates.sort(key=lambda item: item["score"], reverse=True)
        best = candidates[0] if candidates else self._empty_result(text, scene or "")
        if best["score"] < MIN_CONFIDENT_SCORE:
            result = self._empty_result(text, scene or "")
        else:
            result = self._public_result(best)
        positive_candidates = []
        if result["meme_id"] is not None:
            positive_candidates = [item for item in candidates if item["score"] > 0]
        result["candidates"] = [
            self._public_result(item) for item in positive_candidates[:3]
        ]
        return result

    def _score_meme(self, meme: Meme, text: str, scene: str) -> dict[str, Any]:
        score = 0.0
        matched_aliases: list[str] = []
        matched_symbols: list[str] = []
        matched_contexts: list[str] = []
        matched_lines: list[str] = []

        for alias in meme.aliases:
            if _contains(alias, text):
                matched_aliases.append(alias)
                score += 4.0

        for line in meme.lines:
            if _contains(line, text):
                matched_lines.append(line)
                score += 4.5

        for symbol in meme.symbols:
            if _contains(symbol, text):
                matched_symbols.append(symbol)
                score += 3.0

        combined_context = f"{text} {scene}"
        for context in meme.contexts:
            if _contains(context, combined_context):
                matched_contexts.append(context)
                score += 1.25 if _contains(context, text) else 1.0

        if not (matched_aliases or matched_symbols or matched_lines):
            score += self._fuzzy_score(text, meme)

        confidence = min(0.99, score / 8.0)
        if matched_symbols:
            confidence = max(confidence, min(0.9, 0.72 + 0.06 * (len(matched_symbols) - 1)))
        if matched_aliases or matched_lines:
            confidence = max(confidence, 0.68)
        return {
            "meme": meme,
            "score": score,
            "confidence": round(confidence, 2),
            "matched_aliases": matched_aliases,
            "matched_symbols": matched_symbols,
            "matched_contexts": matched_contexts,
            "matched_lines": matched_lines,
        }

    def _fuzzy_score(self, text: str, meme: Meme) -> float:
        normalized_text = _normalize(text)
        if not normalized_text:
            return 0.0
        best_ratio = 0.0
        for cue in (*meme.aliases, *meme.symbols, *meme.lines):
            ratio = SequenceMatcher(None, _normalize(cue), normalized_text).ratio()
            best_ratio = max(best_ratio, ratio)
        if best_ratio >= 0.78:
            return 2.6
        if best_ratio >= 0.68:
            return 1.4
        return 0.0

    def _public_result(self, scored: dict[str, Any]) -> dict[str, Any]:
        meme: Meme = scored["meme"]
        match_type = "contextual"
        if scored["matched_symbols"]:
            match_type = "symbolic"
        elif scored["matched_aliases"] or scored["matched_lines"]:
            match_type = "canonical"

        return {
            "meme_id": meme.id,
            "meme_name": meme.name,
            "confidence": scored["confidence"],
            "match_type": match_type,
            "matched_aliases": scored["matched_aliases"],
            "matched_symbols": scored["matched_symbols"],
            "matched_contexts": scored["matched_contexts"],
            "matched_lines": scored["matched_lines"],
            "emotion_deltas": dict(meme.emotion_deltas),
            "actions": list(meme.actions),
            "line": meme.lines[0] if meme.lines else "",
            "reason": meme.explanation,
            "response_mode": meme.response_mode,
            "asset_id": meme.asset_id,
        }

    def _empty_result(self, text: str, scene: str) -> dict[str, Any]:
        return {
            "meme_id": None,
            "meme_name": None,
            "confidence": 0.0,
            "match_type": "none",
            "matched_aliases": [],
            "matched_symbols": [],
            "matched_contexts": [],
            "matched_lines": [],
            "emotion_deltas": {},
            "actions": [],
            "line": "",
            "reason": "No meme matched with enough confidence; keep the robot in safe idle.",
            "response_mode": "idle",
            "asset_id": "",
        }
