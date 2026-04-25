"""
absolute.py — Absolute Secure Endpoint / Visibility API integration
Docs: https://api.absolute.com  (requiere cuenta enterprise con API habilitada)

Autenticación: HMAC-SHA256
  Authorization: Token {token_id}:{base64(HMAC-SHA256(secret, signing_string))}
  signing_string = "{METHOD}\\n{Content-Type}\\n{Date}\\n{path}"
"""

import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_BASE = 'https://api.absolute.com'

# Tipos de activo que aplican para Absolute (rastreo de endpoint)
ABSOLUTE_ASSET_TYPES = {'laptop', 'desktop', 'tablet'}

# Colores y etiquetas de status de Absolute
STATUS_COLORS = {
    'Active':            'success',
    'Inactive':          'secondary',
    'Stolen':            'danger',
    'Stolen-Recovered':  'warning',
    'Disabled':          'dark',
}
STATUS_LABELS = {
    'Active':            'Activo',
    'Inactive':          'Inactivo',
    'Stolen':            'Reportado Robado',
    'Stolen-Recovered':  'Recuperado',
    'Disabled':          'Deshabilitado',
}


class AbsoluteError(Exception):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


class AbsoluteAuthError(AbsoluteError):
    """Credenciales inválidas o sin permiso."""
    pass


class AbsoluteNotFoundError(AbsoluteError):
    """Dispositivo no encontrado en Absolute."""
    pass


class AbsoluteClient:
    """Cliente REST para Absolute Secure Endpoint API v2."""

    def __init__(self, token_id: str, token_secret: str):
        if not token_id or not token_secret:
            raise AbsoluteAuthError(
                'Token ID y Token Secret son requeridos. '
                'Configúralos en Setup → Absolute.'
            )
        self.token_id     = token_id.strip()
        self.token_secret = token_secret.strip()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _headers(self, method: str, path: str, content_type: str = '') -> dict:
        """Genera headers de autenticación HMAC-SHA256."""
        date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        signing_string = '\n'.join([method.upper(), content_type, date, path])
        sig = hmac.new(
            self.token_secret.encode('utf-8'),
            signing_string.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        b64 = base64.b64encode(sig).decode('utf-8')
        return {
            'Authorization': f'Token {self.token_id}:{b64}',
            'Date':          date,
            'Accept':        'application/json',
        }

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = _BASE + path
        try:
            r = requests.get(url, headers=self._headers('GET', path),
                             params=params, timeout=15)
        except requests.RequestException as exc:
            raise AbsoluteError(f'Error de red al conectar con Absolute: {exc}')

        if r.status_code == 401:
            raise AbsoluteAuthError(
                'Token inválido o expirado. '
                'Verifica el Token ID y Token Secret en Setup → Absolute.'
            )
        if r.status_code == 403:
            raise AbsoluteAuthError(
                'Sin permiso para este recurso. '
                'Verifica que el token tenga acceso a la API de reporting.'
            )
        if r.status_code == 404:
            raise AbsoluteNotFoundError('Dispositivo no encontrado en Absolute.')
        if not r.ok:
            raise AbsoluteError(
                f'Absolute API respondió {r.status_code}: {r.text[:200]}'
            )
        return r.json()

    # ── Métodos públicos ──────────────────────────────────────────────────────

    def test_connection(self) -> dict:
        """Verifica credenciales. Devuelve {'ok': True/False, 'message': ...}."""
        try:
            self._get('/v2/reporting/devices', params={'$top': 1})
            return {'ok': True, 'message': 'Conexión exitosa con Absolute.'}
        except AbsoluteAuthError as e:
            return {'ok': False, 'message': str(e)}
        except AbsoluteError as e:
            return {'ok': False, 'message': str(e)}

    def get_device(self, device_id: str) -> dict:
        """Obtiene datos de un dispositivo por su UID de Absolute."""
        return self._get(f'/v2/reporting/devices/{device_id}')

    def search_by_serial(self, serial: str) -> list:
        """Busca dispositivos por número de serie (ESN)."""
        if not serial:
            return []
        data = self._get('/v2/reporting/devices', params={
            '$filter': f"esn eq '{serial}'",
            '$top':    5,
        })
        return _extract_list(data)

    def search_by_name(self, name: str) -> list:
        """Busca dispositivos por nombre del equipo."""
        if not name:
            return []
        data = self._get('/v2/reporting/devices', params={
            '$filter': f"contains(tolower(systemName), '{name.lower()}')",
            '$top':    10,
        })
        return _extract_list(data)

    def get_all_devices(self, top: int = 200) -> list:
        """Lista todos los dispositivos registrados en el tenant."""
        data = self._get('/v2/reporting/devices', params={'$top': top})
        return _extract_list(data)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_list(data) -> list:
    """Normaliza la respuesta de Absolute que puede ser lista o dict."""
    if isinstance(data, list):
        return data
    for key in ('devices', 'data', 'value', 'results'):
        if key in data:
            return data[key]
    return []


def parse_device(raw: dict) -> dict:
    """
    Normaliza un device de Absolute a un dict estándar que usamos en la app.
    Los campos exactos pueden variar según la versión del API.
    """
    # Absolute usa distintos nombres de campo según el endpoint/versión
    def _get(*keys):
        for k in keys:
            if raw.get(k) not in (None, '', 'N/A'):
                return raw[k]
        return None

    last_seen_raw = _get('lastConnectedUtc', 'lastConnected', 'lastSeenUtc',
                         'lastCheckInUtc', 'lastSeen')
    last_seen = None
    if last_seen_raw:
        try:
            last_seen = datetime.fromisoformat(
                str(last_seen_raw).replace('Z', '+00:00')
            )
        except Exception:
            pass

    return {
        'id':           _get('id', 'deviceId', 'uid', 'esn'),
        'name':         _get('systemName', 'deviceName', 'fullSystemName', 'name'),
        'serial':       _get('esn', 'serial', 'serialNumber', 'hardwareSerial'),
        'username':     _get('username', 'currentUsername', 'lastLoggedUser',
                             'currentUser'),
        'os':           _get('osName', 'os', 'operatingSystem'),
        'status':       _get('agentStatus', 'status', 'deviceStatus'),
        'last_seen':    last_seen,
        'policy_group': _get('policyGroupName', 'policyGroup'),
        'freeze_status':_get('freezeStatus', 'freeze'),
        'raw':          raw,  # por si se necesita algo extra
    }


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status or '', 'secondary')


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status or '', status or '—')
