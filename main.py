import json
import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uuid

app = FastAPI(title="Raskidonchiki API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path(__file__).parent / "markers.json"

# Admin IDs (same as bot)
ADMIN_IDS = {661340242, 281387611}

MAPS = ["mirage", "dust2", "inferno", "nuke", "ancient", "anubis", "cache"]
GRENADE_TYPES = [
    "smoke",
    "flash",
    "molotov",
    "he",
    "insta_smoke_ct",
    "insta_smoke_t",
]


class Marker(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    map: str
    grenade_type: str
    x: float  # percentage 0-100
    y: float  # percentage 0-100
    title: str = ""
    link: str  # Telegram post link
    side: Optional[str] = None  # T / CT / both


class MarkerCreate(BaseModel):
    map: str
    grenade_type: str
    x: float
    y: float
    title: str = ""
    link: str
    side: Optional[str] = None


def load_markers() -> List[dict]:
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_markers(markers: List[dict]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(markers, f, ensure_ascii=False, indent=2)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/maps")
async def get_maps():
    return {"maps": MAPS, "grenade_types": GRENADE_TYPES}


@app.get("/api/markers")
async def get_markers(map: Optional[str] = None, grenade_type: Optional[str] = None):
    markers = load_markers()
    if map:
        markers = [m for m in markers if m["map"] == map]
    if grenade_type:
        markers = [m for m in markers if m["grenade_type"] == grenade_type]
    return {"markers": markers}


@app.post("/api/markers")
async def create_marker(marker: MarkerCreate, x_telegram_user_id: Optional[int] = Header(None)):
    if x_telegram_user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    if marker.map not in MAPS:
        raise HTTPException(status_code=400, detail="Invalid map")
    if marker.grenade_type not in GRENADE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid grenade type")

    markers = load_markers()
    new_marker = Marker(**marker.model_dump()).model_dump()
    markers.append(new_marker)
    save_markers(markers)
    return {"marker": new_marker}


@app.delete("/api/markers/{marker_id}")
async def delete_marker(marker_id: str, x_telegram_user_id: Optional[int] = Header(None)):
    if x_telegram_user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    markers = load_markers()
    new_markers = [m for m in markers if m["id"] != marker_id]
    if len(new_markers) == len(markers):
        raise HTTPException(status_code=404, detail="Marker not found")
    save_markers(new_markers)
    return {"ok": True}


@app.put("/api/markers/{marker_id}")
async def update_marker(marker_id: str, marker: MarkerCreate, x_telegram_user_id: Optional[int] = Header(None)):
    if x_telegram_user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    markers = load_markers()
    for i, m in enumerate(markers):
        if m["id"] == marker_id:
            updated = Marker(id=marker_id, **marker.model_dump()).model_dump()
            markers[i] = updated
            save_markers(markers)
            return {"marker": updated}
    raise HTTPException(status_code=404, detail="Marker not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
