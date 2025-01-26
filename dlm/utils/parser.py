from typing import Dict, Optional, Tuple, List
import re

class CardParser:
    """Handles parsing card queries and formats."""
    FORMATS = ["paper", "md", "dl", "sd"]
    DEFAULT_FORMAT = "paper"
    FORMAT_PATTERN = re.compile(r'format:(\w+)')
    QUOTED_PATTERN = re.compile(r'"([^"]+)"')
    OCG_PATTERN = re.compile(r'ocg:?(true|false)?')
    @classmethod
    def parse_card_query(cls, content: str) -> Dict[str, any]:
        """Parse a card query string into components.
        Args:
            content: The query string to parse.
        Returns:
            Dict with:
                query: The card name to search for
                format: The requested format (paper, md, dl, sd)
                ocg: Whether OCG art was requested
        """
        result = {
            "query": content.strip(),
            "format": cls.DEFAULT_FORMAT,
            "ocg": False
        }
        format_match = cls.FORMAT_PATTERN.search(content)
        if format_match:
            format_value = format_match.group(1).lower()
            if format_value in cls.FORMATS:
                result["format"] = format_value
            result["query"] = cls.FORMAT_PATTERN.sub('', result["query"]).strip()

        ocg_match = cls.OCG_PATTERN.search(content)
        if ocg_match:
            result["ocg"] = ocg_match.group(1) != "false"
            result["query"] = cls.OCG_PATTERN.sub('', result["query"]).strip()

        quoted_match = cls.QUOTED_PATTERN.search(result["query"])
        if quoted_match:
            result["query"] = quoted_match.group(1)
        return result

    @classmethod
    def extract_card_names(cls, content: str) -> List[str]:
        """Extract card names from text using <card name> syntax.
        Args:
            content: Text content to parse
        Returns:
            List of card names found in <> brackets
        """
        pattern = re.compile(r'<([^<>]+)>')
        return pattern.findall(content)

    @classmethod
    def is_valid_format(cls, format_str: str) -> bool:
        """Check if a format string is valid."""
        return format_str.lower() in cls.FORMATS

    @classmethod
    def normalize_format(cls, format_str: Optional[str]) -> str:
        """Convert format string to normalized form or return default."""
        if not format_str:
            return cls.DEFAULT_FORMAT
        format_str = format_str.lower()
        return format_str if format_str in cls.FORMATS else cls.DEFAULT_FORMAT

    @classmethod
    def extract_interaction_options(cls, interaction_data: Dict) -> Dict[str, any]:
        """Parse options from a Discord interaction.
        Args:
            interaction_data: The interaction data from Discord
        Returns:
            Dict with parsed options (card name, format, etc)
        """
        result = {
            "query": "",
            "format": cls.DEFAULT_FORMAT,
            "ocg": False
        }
        if not interaction_data or "options" not in interaction_data:
            return result

        for option in interaction_data["options"]:
            if option["name"] == "card":
                result["query"] = option["value"]
            elif option["name"] == "format":
                result["format"] = cls.normalize_format(option["value"])
            elif option["name"] == "ocg":
                result["ocg"] = bool(option["value"])
        return result
