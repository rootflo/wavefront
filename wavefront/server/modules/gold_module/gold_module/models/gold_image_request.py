from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class Item(BaseModel):
    item_id: Optional[str] = None
    item_type: Optional[str] = None
    item_count: Optional[int] = None
    item_description: Optional[str] = None
    item_gross_weight: Optional[float] = None
    item_stone_weight: Optional[float] = None
    item_net_weight: Optional[float] = None
    item_purity: Optional[float] = None
    model_config = ConfigDict(extra='ignore')


class ImageMetadata(BaseModel):
    customer_id: Optional[str] = None
    loan_id: Optional[str] = None

    branch: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    category: Optional[str] = None

    agent_id: Optional[str] = None
    item_id: Optional[str] = None  # Unique indentifier for gold image

    timestamp: Optional[datetime] = None
    loan_date: datetime
    gold_loan_category: Optional[str] = None
    loan_tenure: Optional[int] = None
    loan_amount: Optional[float] = None
    loan_type: Optional[Literal['new', 'top_up']] = None
    pos: Optional[float] = None
    parent_loan_id: Optional[str] = None

    gross_weight: Optional[float] = None
    stone_weight: Optional[float] = None
    net_weight: Optional[float] = None
    jewellery_items_count: Optional[int] = None
    gold_purity: Optional[float] = None

    items: Optional[List[Item]] = None

    metadata_1: Optional[dict] = None
    metadata_2: Optional[dict] = None
    metadata_3: Optional[dict] = None
    metadata_4: Optional[dict] = None
    metadata_5: Optional[dict] = None

    filter_1: Optional[str] = None
    filter_2: Optional[str] = None
    filter_3: Optional[str] = None
    filter_4: Optional[str] = None
    filter_5: Optional[str] = None

    model_config = ConfigDict(extra='allow')

    @model_validator(mode='after')
    def validate_loan_type_fields(self):
        if self.loan_type == 'top_up' and not self.parent_loan_id:
            raise ValueError('parent_loan_id is required when loan_type is top_up')
        if self.loan_type == 'new' and self.parent_loan_id is not None:
            raise ValueError('parent_loan_id must be null when loan_type is new')
        return self

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
    metadata: ImageMetadata


class AdhocImageUploadRequest(BaseModel):
    image: str
    loan_id: str
