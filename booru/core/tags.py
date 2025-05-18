import logging
import re
from typing import List, Set, Tuple

log = logging.getLogger("red.booru.core.tags")

UNDERSCORE = re.compile(r"[ _]+")
SERIES_SPLIT = re.compile(r"(?<!^):(?!$)")


class TagHandler:
    """Handles booru tag parsing, aliasing and formatting."""

    def __init__(self) -> None:
        self.tag_aliases = {
            "nsfw": "rating:explicit",
            "explicit": "rating:explicit",
            "sfw": "rating:safe",
            "safe": "rating:safe",
            "questionable": "rating:questionable",
        }

    def parse_tags(self, tag_string: str) -> Tuple[Set[str], Set[str]]:
        """
        Split a raw tag string into (positive, negative) sets.

        • Accepts space- **or** comma-separated input.
        • Leading '-' marks a negative tag.
        • Normalises every tag (case, underscores, series).
        • Resolves aliases **after** normalisation.
        """
        tags_raw = [t.strip() for t in re.split(r"[,s]+", tag_string) if t.strip()]

        positive, negative = set(), set()

        for tag in tags_raw:
            is_neg = tag.startswith("-")
            tag_clean = tag[1:] if is_neg else tag
            tag_final = self._alias(self._normalize(tag_clean))
            if tag_final:
                (negative if is_neg else positive).add(tag_final)

        log.debug("Parsed tags – +%s −%s", positive, negative)
        return positive, negative

    def combine_tags(self, positive: Set[str], negative: Set[str]) -> List[str]:
        """Return a list with '-' prefixed to negative tags for API calls."""
        return [*positive, *[f"-{t}" for t in negative]]

    def format_tags(self, tags: List[str]) -> str:
        """Turn a tag list into a display string."""
        return " ".join(tags)

    def _alias(self, tag: str) -> str:
        """Map user-facing aliases to canonical tags."""
        return self.tag_aliases.get(tag, tag)

    def _normalize(self, tag: str) -> str:
        """
        • Lower-case
        • Collapse spaces / underscores into a single underscore
        • Preserve ':' hierarchy but normalise each side
        """
        if ":" in tag:
            parts = SERIES_SPLIT.split(tag)
            tag = ":".join(self._normalize(p) for p in parts)
            return tag

        tag = UNDERSCORE.sub("_", tag.strip().lower())
        return tag.strip("_")
