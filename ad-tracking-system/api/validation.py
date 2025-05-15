from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field


class Advertiser(BaseModel):
    advertiser_id: str
    advertiser_name: str


class Campaign(BaseModel):
    campaign_id: str
    campaign_name: str


class AdInfo(BaseModel):
    ad_id: str
    ad_name: str
    ad_text: str
    ad_link: HttpUrl
    ad_position: int
    ad_format: str


class ImpressionItem(BaseModel):
    advertiser: Advertiser
    campaign: Campaign
    ad: AdInfo


class ImpressionPayload(BaseModel):
    impression_id: str
    user_ip: str
    user_agent: str
    timestamp: str
    state: str
    search_keywords: Optional[str] = None
    session_id: str
    ads: List[ImpressionItem]


class ClickCoordinates(BaseModel):
    x: int
    y: int
    normalized_x: float
    normalized_y: float


class ClickedAd(BaseModel):
    ad_id: str
    ad_position: int
    click_coordinates: ClickCoordinates
    time_to_click: float


class ClickPayload(BaseModel):
    click_id: str
    impression_id: str
    timestamp: str
    clicked_ad: ClickedAd
    user_info: dict  # {user_ip, state, session_id}


class ConversionItem(BaseModel):
    product_id: str
    quantity: int
    unit_price: float


class AttributionStep(BaseModel):
    event_type: str
    timestamp: str


class ConversionAttributes(BaseModel):
    order_id: str
    items: List[ConversionItem]


class AttributionInfo(BaseModel):
    time_to_convert: int
    attribution_model: str
    conversion_path: List[AttributionStep]


class ConversionPayload(BaseModel):
    conversion_id: str
    click_id: str
    impression_id: str
    timestamp: str
    conversion_type: str
    conversion_value: float
    conversion_currency: str
    conversion_attributes: ConversionAttributes
    attribution_info: AttributionInfo
    user_info: dict  # {user_ip, state, session_id}
