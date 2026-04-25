"""
tracking.py — AfterShip package tracking integration
Supports: FedEx, DHL, UPS, Estafeta y +800 carriers más.
"""

import os
import json
import logging
from datetime import datetime

import requests

log = logging.getLogger(__name__)

# AfterShip API 2024-04 (nueva versión — header: as-api-key)
_BASE     = "https://api.aftership.com/tracking/2024-04"
_API_KEY  = os.environ.get("AFTERSHIP_API_KEY", "")


class AfterShipError(Exception):
    """Error genérico de la API de AfterShip."""
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


class AfterShipRateLimitError(AfterShipError):
    """Se alcanzó el límite de requests del plan AfterShip (429)."""
    pass

# Carrier slug map (nombre que usamos → slug de AfterShip)
CARRIER_SLUGS = {
    "DHL":      "dhl",
    "FedEx":    "fedex",
    "UPS":      "ups",
    "USPS":     "usps",
    "Estafeta": "estafeta-mexico",
    "Otro":     None,
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _headers():
    return {
        "as-api-key": _API_KEY,          # nuevo header AfterShip 2024+
        "Content-Type": "application/json",
    }


def _slug_for(carrier: str) -> str | None:
    return CARRIER_SLUGS.get(carrier)


# ── core API calls ────────────────────────────────────────────────────────────

def create_tracking(tracking_number: str, carrier: str, title: str = "") -> dict:
    """
    Registra un envío en AfterShip.
    Retorna el objeto tracking o {} si falla.
    """
    if not _API_KEY:
        log.warning("AFTERSHIP_API_KEY no configurado")
        return {}

    slug = _slug_for(carrier)
    payload = {"tracking_number": tracking_number}
    if slug:
        payload["slug"] = slug
    if title:
        payload["title"] = title

    try:
        r = requests.post(f"{_BASE}/trackings", json=payload, headers=_headers(), timeout=10)
        data = r.json()
        if r.status_code in (200, 201):
            return data.get("data", {})
        # ya existe → lo buscamos directamente
        if r.status_code == 409:
            return get_tracking(tracking_number, carrier)
        if r.status_code == 429:
            msg = data.get("meta", {}).get("message", "Límite de requests diarios de AfterShip alcanzado.")
            raise AfterShipRateLimitError(msg, 429)
        log.error("AfterShip create error %s: %s", r.status_code, data)
    except AfterShipRateLimitError:
        raise
    except Exception as e:
        log.exception("AfterShip create_tracking failed: %s", e)
    return {}


def get_tracking(tracking_number: str, carrier: str) -> dict:
    """
    Obtiene el estado actualizado de un envío.
    Retorna el objeto tracking o {} si falla.
    """
    if not _API_KEY:
        return {}

    slug = _slug_for(carrier)
    try:
        # Buscar por tracking number (AfterShip 2024 permite query params)
        params = {"tracking_numbers": tracking_number}
        if slug:
            params["slug"] = slug
        r = requests.get(
            f"{_BASE}/trackings",
            headers=_headers(),
            params=params,
            timeout=10,
        )
        if r.status_code == 200:
            trackings = r.json().get("data", {}).get("trackings", [])
            if trackings:
                return trackings[0]
        if r.status_code == 429:
            data = r.json()
            msg = data.get("meta", {}).get("message", "Límite de requests diarios de AfterShip alcanzado.")
            raise AfterShipRateLimitError(msg, 429)
        log.error("AfterShip get error %s: %s", r.status_code, r.text[:200])
    except AfterShipRateLimitError:
        raise
    except Exception as e:
        log.exception("AfterShip get_tracking failed: %s", e)
    return {}


# ── high-level helpers usados desde las rutas ─────────────────────────────────

def refresh_shipment(shipment) -> bool:
    """
    Actualiza un objeto Shipment con los datos más recientes de AfterShip.
    Modifica el objeto en memoria; el caller debe hacer db.session.commit().
    Retorna True si se actualizó con éxito.
    """
    from models import db

    if not _API_KEY:
        return False

    # Registrar en AfterShip si es nuevo
    tracking = get_tracking(shipment.tracking_number, shipment.carrier)
    if not tracking:
        tracking = create_tracking(
            shipment.tracking_number,
            shipment.carrier,
            title=f"RTS-{shipment.id}",
        )

    if not tracking:
        return False

    # Guardar slug real (nueva API usa "slug" en el objeto)
    shipment.aftership_slug   = tracking.get("slug") or tracking.get("courier_code") or shipment.aftership_slug
    # Tag de status (nueva API: "tag" o dentro de "current_event_detail")
    tag = tracking.get("tag") or tracking.get("status", {}).get("tag", "") if isinstance(tracking.get("status"), dict) else tracking.get("tag", "")
    shipment.tracking_tag     = tag
    shipment.last_tracking_at = datetime.utcnow()

    # ETA — nueva API usa "estimated_delivery_date"
    eta_str = tracking.get("estimated_delivery_date") or tracking.get("expected_delivery")
    if eta_str:
        try:
            shipment.est_delivery_afship = datetime.fromisoformat(str(eta_str).replace("Z", "+00:00"))
        except Exception:
            pass

    # Actualizar entrega real si ya llegó
    if tag == "Delivered":
        events = tracking.get("events", tracking.get("checkpoints", []))
        if events:
            last_evt = events[-1]
            ts = last_evt.get("occurred_at") or last_evt.get("checkpoint_time") or last_evt.get("created_at")
            if ts:
                try:
                    shipment.actual_delivery = datetime.fromisoformat(
                        str(ts).replace("Z", "+00:00")
                    ).date()
                except Exception:
                    pass

    # Mapear status
    from models import Shipment
    new_status = Shipment.AFTERSHIP_STATUS_MAP.get(tag)
    if new_status:
        shipment.status = new_status

    # Guardar eventos — nueva API usa "events", vieja usa "checkpoints"
    events = tracking.get("events", tracking.get("checkpoints", []))[-20:]
    # Normalizar campos para el template
    normalized = []
    for e in events:
        normalized.append({
            "message":         e.get("message") or e.get("description") or e.get("subtag_message", ""),
            "location":        e.get("location") or e.get("city") or "",
            "checkpoint_time": e.get("occurred_at") or e.get("checkpoint_time") or e.get("created_at") or "",
        })
    shipment.tracking_events = json.dumps(normalized, ensure_ascii=False)

    return True


def refresh_all_active(app) -> int:
    """
    Refresca todos los envíos activos (no entregados/devueltos).
    Llámalo desde un scheduler. Retorna el número de envíos actualizados.
    """
    from models import db, Shipment

    updated = 0
    with app.app_context():
        active = Shipment.query.filter(
            Shipment.tracking_number != None,          # noqa: E711
            Shipment.status.notin_(["entregado", "devuelto"]),
        ).all()

        for s in active:
            if not s.tracking_number or not s.carrier:
                continue
            try:
                ok = refresh_shipment(s)
                if ok:
                    updated += 1
            except Exception as e:
                log.exception("Error refreshing shipment %s: %s", s.id, e)

        if updated:
            db.session.commit()
            log.info("AfterShip: %d envíos actualizados", updated)

    return updated
