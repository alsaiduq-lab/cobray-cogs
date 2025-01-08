import logging
from typing import List, Set, Tuple

log = logging.getLogger("red.booru.core.tags")


class TagHandler:
    """Handles tag processing and validation."""

    def __init__(self):
        # Common aliases for convenience
        self.tag_aliases = {
            "nsfw": "rating:explicit",
            "sfw": "rating:safe",
            "safe": "rating:safe",
            "explicit": "rating:explicit",
            "questionable": "rating:questionable",
        }

    def parse_tags(self, tag_string: str) -> Tuple[Set[str], Set[str]]:
        """
        Parse tag string into positive and negative tags.

        Args:
            tag_string: String of tags separated by spaces and/or commas

        Returns:
            Tuple of (positive_tags, negative_tags)

        Example:
            "1girl, solo, -nsfw" -> ({"1girl", "solo"}, {"rating:explicit"})
        """
        # Split by both commas and spaces and clean up
        raw_tags = {
            tag.strip() for tag in tag_string.replace(",", " ").split() if tag.strip()
        }

        positive_tags = set()
        negative_tags = set()

        for tag in raw_tags:
            # Handle negative tags
            if tag.startswith("-"):
                tag = tag[1:]  # Remove the minus sign
                # Check for alias
                if tag in self.tag_aliases:
                    tag = self.tag_aliases[tag]
                negative_tags.add(tag)
            else:
                # Check for alias
                if tag in self.tag_aliases:
                    tag = self.tag_aliases[tag]
                positive_tags.add(tag)

        log.debug(f"Parsed tags - Positive: {positive_tags}, Negative: {negative_tags}")
        return positive_tags, negative_tags

    def combine_tags(
        self, positive_tags: Set[str], negative_tags: Set[str]
    ) -> List[str]:
        """
        Combine positive and negative tags into a list suitable for API requests.

        Args:
            positive_tags: Set of positive tags
            negative_tags: Set of negative tags

        Returns:
            List of tags with negative tags prefixed with '-'
        """
        tags = list(positive_tags)
        tags.extend(f"-{tag}" for tag in negative_tags)
        return tags

    def format_tags(self, tags: List[str]) -> str:
        """Format tags for display in embeds or messages."""
        return " ".join(tags)
