from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from services.gtfs_simulation import kepadatan_bus_live

router = APIRouter(prefix="/api/live")

WIB = ZoneInfo("Asia/Jakarta")
KEPADATAN_KOSONG = {
    "trip_load_factor": None,
    "label_kepadatan": None,
    "estimated_passengers": None,
    "capacity": None,
}


@router.get("/positions")
def get_live_positions(request: Request):
    """Posisi bus asli (MQTT TransJakarta) untuk koridor yang ada di data statis.

    Bentuk properti mengikuti /api/simulation/positions. MQTT tidak membawa
    kepadatan, jadi kepadatan adalah PERKIRAAN dari trip simulasi yang setara
    (lihat kepadatan_bus_live); null untuk koridor di luar simulasi.
    """
    live = request.app.state.live_buses
    ctx = getattr(request.app.state, "simulation_context", None)
    now = datetime.now(WIB)
    detik = now.hour * 3600 + now.minute * 60 + now.second

    features = []
    for bus in live.snapshot():
        kepadatan = (
            kepadatan_bus_live(ctx, bus["bus_id"], bus["koridor_id"], detik) if ctx else None
        )
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [bus["lng"], bus["lat"]]},
            "properties": {
                "bus_id": bus["bus_id"],
                "koridor_id": bus["koridor_id"],
                "bearing": bus["bearing"],
                "next_stop": bus["next_stop"],
                "eta_minutes": bus["eta_minutes"],
                "trip_id": bus["trip_id"],
                "data_source": "tj_live",
                **(kepadatan or KEPADATAN_KOSONG),
            },
        })
    return {"type": "FeatureCollection", "connected": live.connected, "features": features}
