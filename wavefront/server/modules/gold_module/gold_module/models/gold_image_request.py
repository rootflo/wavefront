from datetime import datetime
from typing import List
from pydantic import BaseModel, ConfigDict


class Item(BaseModel):
    item_id: str = None
    item_type: str = None
    item_count: int = None
    item_description: str = None
    item_gross_weight: float = None
    item_stone_weight: float = None
    item_purity: float = None
    model_config = ConfigDict(extra='ignore')


class ImageMetadata(BaseModel):
    customer_id: str = None
    loan_id: str = None

    branch: str = None
    city: str = None
    region: str = None
    zone: str = None
    category: str = None

    agent_id: str = None
    item_id: str = None  # Unique indentifier for gold image

    timestamp: datetime = None
    loan_date: datetime = None
    gold_loan_category: str = None
    loan_tenure: int = None
    loan_amount: float = None

    gross_weight: float = None
    stone_weight: float = None
    net_weight: float = None
    jewellery_items_count: int = None
    gold_purity: float = None

    items: List[Item] = None

    metadata_1: str = None
    metadata_2: str = None
    metadata_3: str = None
    metadata_4: str = None
    metadata_5: str = None

    filter_1: str = None
    filter_2: str = None
    filter_3: str = None
    filter_4: str = None
    filter_5: str = None

    model_config = ConfigDict(extra='allow')

    def get_extra_fields(self) -> dict:
        """Return a dict of extra fields not defined in the model."""
        return (
            dict(self.__pydantic_extra__)
            if hasattr(self, '__pydantic_extra__') and self.__pydantic_extra__
            else {}
        )

    def get_defined_fields(self) -> dict:
        """Return a dict of only the defined fields (excluding extras)."""
        return self.model_dump(exclude=self.get_extra_fields().keys())

    def to_string_dict(self) -> dict:
        """Return a dict with all fields (excluding extras) as strings. None remains None. All nested values are strings."""

        def to_str_recursive(val):
            if val is None:
                return None
            if isinstance(val, list):
                return [to_str_recursive(v) for v in val]
            if isinstance(val, dict):
                return {k: to_str_recursive(v) for k, v in val.items()}
            return str(val)

        all_fields = {**self.get_defined_fields()}
        return {k: to_str_recursive(v) for k, v in all_fields.items()}


class ImageAnalysisRequest(BaseModel):
    image: str  # data URL (base64 with MIME) or direct URL
    metadata: ImageMetadata = (
        ImageMetadata()
    )  # Ensure metadata is always an ImageMetadata instance
