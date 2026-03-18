"""
Cloud sync for the Unbound desktop app.

Cloud always wins: on sync, the server's state fully replaces local state.

Public API
----------
sync_from_cloud(config)           Pull everything from cloud → overwrite local config.
push_layers(config)               Push all local layers to cloud.
push_full_config(config, name)    Push the full config.json to cloud under a named slot.
delete_layer(layer_id)            Remove a single layer from cloud.
"""

try:
    import requests as _requests
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

import config as cfg
from auth import get_api_key, is_signed_in, API_BASE

_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    key = get_api_key()
    if not key:
        raise RuntimeError("Not signed in — call auth.sign_in() first.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _check() -> None:
    if not _AVAILABLE:
        raise RuntimeError("requests library is not installed.")
    if not is_signed_in():
        raise RuntimeError("Not signed in.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_from_cloud(config: dict) -> dict:
    """
    Pulls all layers from the server and overwrites the local config in place.
    Cloud always wins. Saves to disk after applying.
    Returns the raw server payload.
    """
    _check()
    r = _requests.get(f"{API_BASE}/api/sync", headers=_headers(), timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()

    cloud_layers: dict = data.get("layers", {})
    if cloud_layers:
        config["layers"] = cloud_layers
        cfg.save(config)

    return data


def push_layers(config: dict) -> None:
    """Pushes all local layers to the server (upsert)."""
    _check()
    layers = config.get("layers", {})
    if not layers:
        return
    r = _requests.post(
        f"{API_BASE}/api/layers",
        json={"layers": layers},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def push_full_config(config: dict, name: str = "Default") -> None:
    """Saves the entire config.json to the server under the given slot name."""
    _check()
    r = _requests.post(
        f"{API_BASE}/api/configs",
        json={"name": name, "data": config},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def delete_layer(layer_id: str) -> None:
    """Removes a single layer from the server."""
    _check()
    r = _requests.delete(
        f"{API_BASE}/api/layers",
        params={"layer_id": layer_id},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
