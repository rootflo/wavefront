from dataclasses import dataclass
from typing import Union


@dataclass
class DocContent:
    """Model representing the extracted content from a document file"""

    content: Union[str, bytes]
    parse_type: str
