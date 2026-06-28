from datetime import datetime

from pydantic import BaseModel


class WindFieldSample(BaseModel):
    latitude_deg: float
    longitude_deg: float
    east_kt: float
    north_kt: float
    speed_kt: float
    direction_deg: float


class WindFieldResponse(BaseModel):
    valid_at_utc: datetime
    flight_level: int
    pressure_hpa: int
    source: str
    samples: list[WindFieldSample]
