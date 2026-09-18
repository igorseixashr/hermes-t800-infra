"""Shared Megaport API client used by all scripts in this skill.

Handles OAuth2 client_credentials auth with token caching in /tmp.
Reads credentials from environment (sourced from ~/.bashrc.d/megaport.env).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from base64 import b64encode
from pathlib import Path
from typing import Any

TOKEN_CACHE = Path("/tmp/megaport_token.json")
TOKEN_REFRESH_BUFFER_SEC = 300  # refresh if <5 min remaining


class MegaportClient:
    def __init__(self) -> None:
        self.client_id = os.environ.get("MEGAPORT_CLIENT_ID")
        self.client_secret = os.environ.get("MEGAPORT_CLIENT_SECRET")
        self.auth_url = os.environ.get(
            "MEGAPORT_AUTH_URL", "https://auth-m2m.megaport.com/oauth2/token"
        )
        self.api_url = os.environ.get(
            "MEGAPORT_API_URL", "https://api.megaport.com"
        ).rstrip("/")

        if not self.client_id or not self.client_secret:
            sys.stderr.write(
                "ERROR: MEGAPORT_CLIENT_ID / MEGAPORT_CLIENT_SECRET not in env.\n"
                "       Source ~/.bashrc.d/megaport.env or run inside a login shell.\n"
            )
            sys.exit(2)

        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ---------- auth ----------
    def _load_cached_token(self) -> bool:
        if not TOKEN_CACHE.exists():
            return False
        try:
            data = json.loads(TOKEN_CACHE.read_text())
            if data.get("expires_at", 0) - time.time() > TOKEN_REFRESH_BUFFER_SEC:
                self._token = data["access_token"]
                self._token_expires_at = data["expires_at"]
                return True
        except Exception:
            pass
        return False

    def _save_cached_token(self, access_token: str, expires_in: int) -> None:
        expires_at = time.time() + expires_in
        TOKEN_CACHE.write_text(
            json.dumps({"access_token": access_token, "expires_at": expires_at})
        )
        try:
            os.chmod(TOKEN_CACHE, 0o600)
        except OSError:
            pass
        self._token = access_token
        self._token_expires_at = expires_at

    def _authenticate(self) -> None:
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        basic = b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        req = urllib.request.Request(
            self.auth_url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            sys.stderr.write(f"AUTH FAILED: HTTP {e.code} {e.read().decode()[:300]}\n")
            sys.exit(3)
        self._save_cached_token(payload["access_token"], int(payload["expires_in"]))

    def token(self) -> str:
        if self._token and self._token_expires_at - time.time() > TOKEN_REFRESH_BUFFER_SEC:
            return self._token
        if self._load_cached_token():
            return self._token  # type: ignore[return-value]
        self._authenticate()
        return self._token  # type: ignore[return-value]

    # ---------- request ----------
    def get(self, path: str, params: dict | None = None) -> Any:
        url = self.api_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self.token()}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            sys.stderr.write(f"HTTP {e.code} on GET {path}: {body}\n")
            return None
        except urllib.error.URLError as e:
            sys.stderr.write(f"NETWORK ERROR on GET {path}: {e}\n")
            return None


# ---------- helpers shared by scripts ----------

def collect_all_vxcs(products: list[dict]) -> dict[str, dict]:
    """Deduplicate VXCs (each appears in both its A-End and B-End parent)."""
    out: dict[str, dict] = {}
    for p in products:
        for vxc in p.get("associatedVxcs") or []:
            uid = vxc.get("productUid")
            if not uid or uid in out:
                continue
            vxc["_parent_uid"] = p["productUid"]
            vxc["_parent_name"] = p["productName"]
            vxc["_parent_type"] = p["productType"]
            out[uid] = vxc
    return out


def vxc_cloud_provider(vxc: dict) -> str:
    """Map VXC bEnd.connectType to the human-readable cloud provider label."""
    ct = (vxc.get("bEnd") or {}).get("connectType", "")
    return {
        "AWSHC": "AWS",
        "AZURE": "Azure",
        "GOOGLE": "GCP",
        "TRANSIT": "Internet/ISP",
        "VROUTER": "MCR (private)",
        "DEFAULT": "Port-to-Port",
    }.get(ct, ct or "?")


def bgp_status_from_csp(csp_connection: Any) -> dict[str, int]:
    """Extract {peer_ip: 1|0} from csp_connection in either list (detail) or dict (list view) form."""
    out: dict[str, int] = {}
    if isinstance(csp_connection, dict):
        out.update(csp_connection.get("bgp_status") or {})
    elif isinstance(csp_connection, list):
        for entry in csp_connection:
            out.update(entry.get("bgp_status") or {})
    return out


def csp_identifier(csp_connection: Any) -> dict[str, str]:
    """Return cloud-side identifiers from csp_connection (AWS connectionId, Azure service_key, GCP pairingKey)."""
    out: dict[str, str] = {}
    items = csp_connection if isinstance(csp_connection, list) else [csp_connection] if isinstance(csp_connection, dict) else []
    for entry in items:
        ct = entry.get("connectType")
        if ct == "AWSHC":
            out["provider"] = "AWS"
            if entry.get("connectionId"):
                out["aws_connection_id"] = entry["connectionId"]
            if entry.get("ownerAccount"):
                out["aws_account_id"] = entry["ownerAccount"]
        elif ct == "AZURE":
            out["provider"] = "Azure"
            if entry.get("service_key"):
                out["azure_service_key"] = entry["service_key"]
            if entry.get("vlan"):
                out["azure_vlan"] = str(entry["vlan"])
        elif ct == "GOOGLE":
            out["provider"] = "GCP"
            if entry.get("pairingKey"):
                out["gcp_pairing_key"] = entry["pairingKey"]
        elif ct == "TRANSIT":
            out["provider"] = "Internet"
    return out
