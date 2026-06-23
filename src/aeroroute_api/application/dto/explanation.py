from pydantic import BaseModel


class ExplanationResponse(BaseModel):
    provider: str
    text: str
    warnings: list[str]
