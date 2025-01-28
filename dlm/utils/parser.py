from typing import Dict, Optional, Tuple, List
import re
import logging

class CardParser:
    """Handles parsing card queries and formats."""
    FORMATS = ["paper", "md", "dl", "sd"]
    DEFAULT_FORMAT = "paper"
    FORMAT_PATTERN = re.compile(r'format:(\w+)')
    QUOTED_PATTERN = re.compile(r'"([^"]+)"')
    OCG_PATTERN = re.compile(r'ocg:?(true|false)?')

    def __init__(self, *, log=None):
        """Initialize CardParser.
        
        Args:
            log: Optional logger instance. If not provided, uses default logger.
        """
        self.logger = log or logging.getLogger("red.dlm.parser")

    def parse_card_query(self, content: str) -> Dict[str, any]:
        """Parse a card query string into components.
        
        Args:
            content: The query string to parse.
        Returns:
            Dict with:
                query: The card name to search for
                format: The requested format (paper, md, dl, sd)
                ocg: Whether OCG art was requested
        """
        try:
            result = {
                "query": content.strip(),
                "format": self.DEFAULT_FORMAT,
                "ocg": False
            }
            
            format_match = self.FORMAT_PATTERN.search(content)
            if format_match:
                format_value = format_match.group(1).lower()
                if format_value in self.FORMATS:
                    result["format"] = format_value
                result["query"] = self.FORMAT_PATTERN.sub('', result["query"]).strip()
            
            ocg_match = self.OCG_PATTERN.search(content)
            if ocg_match:
                result["ocg"] = ocg_match.group(1) != "false"
                result["query"] = self.OCG_PATTERN.sub('', result["query"]).strip()
            
            quoted_match = self.QUOTED_PATTERN.search(result["query"])
            if quoted_match:
                result["query"] = quoted_match.group(1)
            
            return result
        except Exception as e:
            self.logger.error(f"Error parsing card query '{content}': {str(e)}", exc_info=True)
            return {"query": content.strip(), "format": self.DEFAULT_FORMAT, "ocg": False}

    def extract_card_names(self, content: str) -> List[str]:
        """Extract card names from text using <card name> syntax.
        
        Args:
            content: Text content to parse
        Returns:
            List of card names found in <> brackets
        """
        try:
            pattern = re.compile(r'<([^<>]+)>')
            return pattern.findall(content)
        except Exception as e:
            self.logger.error(f"Error extracting card names from '{content}': {str(e)}", exc_info=True)
            return []

    def is_valid_format(self, format_str: str) -> bool:
        """Check if a format string is valid."""
        return format_str.lower() in self.FORMATS

    def normalize_format(self, format_str: Optional[str]) -> str:
        """Convert format string to normalized form or return default."""
        if not format_str:
            return self.DEFAULT_FORMAT
        format_str = format_str.lower()
        return format_str if format_str in self.FORMATS else self.DEFAULT_FORMAT

    def extract_interaction_options(self, interaction_data: Dict) -> Dict[str, any]:
        """Parse options from a Discord interaction.
        
        Args:
            interaction_data: The interaction data from Discord
        Returns:
            Dict with parsed options (card name, format, etc)
        """
        try:
            result = {
                "query": "",
                "format": self.DEFAULT_FORMAT,
                "ocg": False
            }
            
            if not interaction_data or "options" not in interaction_data:
                return result
                
            for option in interaction_data["options"]:
                if option["name"] == "card":
                    result["query"] = option["value"]
                elif option["name"] == "format":
                    result["format"] = self.normalize_format(option["value"])
                elif option["name"] == "ocg":
                    result["ocg"] = bool(option["value"])
                    
            return result
        except Exception as e:
            self.logger.error(f"Error extracting interaction options: {str(e)}", exc_info=True)
            return {"query": "", "format": self.DEFAULT_FORMAT, "ocg": False}
