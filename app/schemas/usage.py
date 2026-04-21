from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

class UsageItem(BaseModel):
    # Mandatory fields
    id: int
    timestamp: str
    credits: float
    
    # Optional field: will be omitted from JSON if None
    # thanks to the model_config below
    report_name: Optional[str] = Field(default=None)

    # Pydantic V2 configuration
    model_config = ConfigDict(
        # This ensures 'report_name' is hidden in the response if it is None
        # satisfying the "otherwise this field should be omitted" requirement.
        extra='ignore'
    )

class UsageResponse(BaseModel):
    usage: List[UsageItem]

    model_config = ConfigDict(
        # Ensures total consistency in the final response
        from_attributes=True
    )
