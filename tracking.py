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

# AfterShip API v4
_BASE     = "https://api.aftership.com/v4"
_API_KEY  = os.environ.get("AFTERSHIP_API_KEY", "")

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
        "aftership-api-key": _API_KEY,
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
    payload = {"tracking": {"tracking_number": tracking_number}}
    if slug:
        payload["tracking"]["slug"] = slug
    if title:
        payload["tracking"]["title"] = title

    try:
        r = requests.post(f"{_BASE}/trackings", json=payload, headers=_headers(), timeout=10)
        data = r.json()
        if r.status_code in (200, 201):
            return data.get("data", {}).get("tracking", {})
        # 4003 = ya existe → lo buscamos directamente
        if data.get("meta", {}).get("code") == 4003:
            return get_tracking(tracking_number, carrier)
        log.error("AfterShip create error %s: %s", r.status_code, data)
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

    slug = _slug_for(carrier) or "auto"
    try:
        r = requests.get(
            f"{_BASE}/trackings/{slug}/{tracking_number}",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("data", {}).get("tracking", {})
        log.error("AfterShip get error %s: %s", r.status_code, r.text[:200])
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

    # Guardar slug real
    shipment.aftership_slug   = tracking.get("slug", shipment.aftership_slug)
    shipment.tracking_tag     = tracking.get("tag")
    shipment.last_tracking_at = datetime.utcnow()

    # ETA
    eta_str = tracking.get("expected_delivery")
    if eta_str:
        try:
            shipment.est_delivery_afship = datetime.fromisoformat(eta_str.replace("Z", "+00:00"))
        except Exception:
            pass

    # Actualizar entrega real si ya llegó
    if tracking.get("tag") == "Delivered":
        events = tracking.get("checkpoints", [])
        if events:
            last_evt = events[-1]
            ts = last_evt.get("checkpoint_time") or last_evt.get("created_at")
            if ts:
                try:
                    shipment.actual_delivery = datetime.fromisoformat(
                        ts.replace("Z", "+00:00")
                    ).date()
                except Exception:
                    pass

    # Mapear status
    tag = tracking.get("tag", "")
    from models import Shipment
    new_status = Shipment.AFTERSHIP_STATUS_MAP.get(tag)
    if new_status:
        shipment.status = new_status

    # Guardar eventos (últimos 20)
    checkpoints = tracking.get("checkpoints", [])[-20:]
    shipment.tracking_events = json.dumps(checkpoints, ensure_ascii=False)

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
