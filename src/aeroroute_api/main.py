from fastapi import FastAPI

from aeroroute_api.api.routers.airports import router as airports_router

app = FastAPI(title="AeroRoute MLX API", version="0.1.0")
app.include_router(airports_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aeroroute-api"}
