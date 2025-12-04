from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any


class CreateProductAnalysisPayload(BaseModel):
    """Payload sent by the user - only these fields are provided by the client"""

    event_name: str
    type: Optional[str] = None
    sub_type: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    action: Optional[str] = None
    action_type: Optional[str] = None
    page: str
    page_path: str
    matadata: Optional[Dict[str, Any]] = None


class ProductAnalysis(BaseModel):
    """Complete product analysis model with all fields including server-added ones"""

    event_name: str
    type: Optional[str] = None
    sub_type: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    action: Optional[str] = None
    action_type: Optional[str] = None
    page: str
    page_path: str
    matadata: Optional[Dict[str, Any]] = None
    user_id: str
    session_id: str
    user_role: str
    created_at: datetime
