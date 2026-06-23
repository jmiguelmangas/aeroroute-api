from pydantic import BaseModel


class AirportResponse(BaseModel):
    icao_code: str
    iata_code: str | None
    name: str
    municipality: str | None
    iso_country: str | None
    latitude_deg: float
    longitude_deg: float


class AirportPage(BaseModel):
    items: list[AirportResponse]
    limit: int
    offset: int
