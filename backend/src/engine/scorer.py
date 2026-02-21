"""Tag-based scoring engine.

Works with local data: scores content by matching its tags against user preferences.
No database needed — operates purely on tag names and weights.
"""

from dataclasses import dataclass

from collector.base import TagResult


@dataclass
class ScoredContent:
    """A content item with its computed score."""

    source: str
    source_id: str
    title: str
    score: float
    matched_tags: list[str]


class TagScorer:
    """Scores content based on user tag preferences.

    Score = sum(preference_weight * tag_confidence) for matching tags.

    Preferences are a simple dict of tag_name -> weight.
    Positive weight = like, negative = dislike, absent = neutral (ignored).
    """

    def score(
        self,
        preferences: dict[str, float],
        content_tags: list[TagResult],
    ) -> tuple[float, list[str]]:
        """Score a single content item.

        Returns (score, matched_tag_names).
        """
        if not content_tags or not preferences:
            return 0.0, []

        raw_score = 0.0
        matched: list[str] = []

        for tag in content_tags:
            weight = preferences.get(tag.name)
            if weight is not None:
                raw_score += weight * tag.confidence
                matched.append(tag.name)

        return round(raw_score, 2), matched
