#!/data/data/com.termux/files/usr/bin/python3
"""Render Android Wi-Fi service output as safe, mobile-friendly text or JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from typing import Any


RAW_ROW = re.compile(
    r"^\s*(?P<bssid>[0-9a-fA-F:]{17})\s+"
    r"(?P<frequency>\d+)\s+"
    r"(?P<rssi>-?\d+)(?:\([^)]*\))?\s+"
    r"(?P<age>[\d.]+)\s+(?P<tail>.*)$"
)


def safe_text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else "")
    text = "".join(char if char.isprintable() else " " for char in text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def security_label(capabilities: str) -> str:
    value = capabilities.upper()
    enterprise = "EAP" in value or "SUITE_B" in value
    if "SAE" in value or "WPA3" in value:
        base = "WPA3"
    elif "WPA2" in value or "RSN" in value:
        base = "WPA2"
    elif "WPA" in value:
        base = "WPA"
    elif "WEP" in value:
        base = "WEP"
    else:
        base = "Open"
    if enterprise and base != "Open":
        return f"{base} Enterprise"
    return base


def band_label(frequency: int) -> str:
    if frequency >= 5925:
        return "6 GHz"
    if frequency >= 4900:
        return "5 GHz"
    return "2.4 GHz"


def signal_label(rssi: int) -> str:
    if rssi >= -50:
        return "Excellent"
    if rssi >= -60:
        return "Strong"
    if rssi >= -70:
        return "Good"
    if rssi >= -80:
        return "Fair"
    return "Weak"


def normalize_network(item: dict[str, Any]) -> dict[str, Any]:
    frequency = int(item.get("frequency", item.get("frequency_mhz", 0)) or 0)
    rssi = int(item.get("rssi", item.get("level", -127)) or -127)
    capabilities = safe_text(item.get("capabilities", item.get("flags", "")))
    ssid = safe_text(item.get("ssid"), "Hidden network")
    return {
        "ssid": ssid,
        "bssid": safe_text(item.get("bssid")),
        "frequency_mhz": frequency,
        "band": band_label(frequency),
        "rssi_dbm": rssi,
        "signal": signal_label(rssi),
        "security": security_label(capabilities),
        "wps": "WPS" in capabilities.upper(),
        "age_seconds": item.get("age_seconds", item.get("age", None)),
        "capabilities": capabilities,
    }


def parse_raw(text: str) -> list[dict[str, Any]]:
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list):
            return [normalize_network(item) for item in payload if isinstance(item, dict)]

    networks: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = RAW_ROW.match(line)
        if not match:
            continue
        tail = match.group("tail")
        flags_at = tail.find("[")
        if flags_at >= 0:
            ssid, capabilities = tail[:flags_at], tail[flags_at:]
        else:
            ssid, capabilities = tail, ""
        networks.append(
            normalize_network(
                {
                    "ssid": ssid,
                    "bssid": match.group("bssid"),
                    "frequency": match.group("frequency"),
                    "rssi": match.group("rssi"),
                    "age_seconds": float(match.group("age")),
                    "capabilities": capabilities,
                }
            )
        )
    return networks


def render_scan(networks: list[dict[str, Any]], source: str, warning: str) -> str:
    networks = sorted(networks, key=lambda item: item["rssi_dbm"], reverse=True)
    counts: dict[str, int] = {}
    for network in networks:
        family = str(network["security"]).split()[0]
        counts[family] = counts.get(family, 0) + 1
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    summary = " · ".join(f"{name} {counts[name]}" for name in ("WPA3", "WPA2", "WPA", "WEP", "Open") if counts.get(name))
    wps_count = sum(bool(item["wps"]) for item in networks)
    lines = [
        "╭─ Nearby Wi-Fi ─────────────────────────────────────╮",
        f"│ {len(networks)} networks · {summary or 'No security data'}",
        f"│ Updated {updated}",
        f"│ Source: {safe_text(source, 'Android Wi-Fi service')}",
        f"│ WPS advertised by {wps_count} network{'s' if wps_count != 1 else ''}",
        "╰──────────────────────────────────────────────────────╯",
    ]
    if warning:
        lines.extend(("", f"Note: {safe_text(warning)}"))
    if not networks:
        lines.extend(("", "No scan results are available yet. Wi-Fi and Location must be enabled."))
        return "\n".join(lines)
    for index, network in enumerate(networks[:20], start=1):
        wps = " · WPS" if network["wps"] else ""
        lines.extend(
            (
                "",
                f"{index}. {network['ssid']}",
                f"   {network['signal']} ({network['rssi_dbm']} dBm) · {network['band']} · {network['security']}{wps}",
            )
        )
    if len(networks) > 20:
        lines.extend(("", f"…and {len(networks) - 20} more networks in the structured JSON view."))
    return "\n".join(lines)


def render_connection(text: str, source: str, warning: str) -> str:
    def field(pattern: str, fallback: str = "Unknown") -> str:
        match = re.search(pattern, text, re.IGNORECASE)
        return safe_text(match.group(1), fallback) if match else fallback

    enabled = "Enabled" if "Wifi is enabled" in text else "Disabled or unavailable"
    ssid = field(r'SSID:\s*"([^"]+)"', "Not connected")
    ip_address = field(r"IP:\s*/?([^,\s]+)")
    standard = field(r"Wi-Fi standard:\s*([^,]+)")
    rssi = field(r"RSSI:\s*(-?\d+)")
    frequency = field(r"Frequency:\s*(\d+)MHz")
    link_speed = field(r"Link speed:\s*([^,]+)")
    security_type = field(r"Security type:\s*([^,]+)")
    lines = [
        "╭─ Current Wi-Fi connection ─────────────────────────╮",
        f"│ Radio: {enabled}",
        f"│ Network: {ssid}",
        f"│ Address: {ip_address}",
        f"│ Signal: {rssi} dBm · {frequency} MHz · {standard}",
        f"│ Link: {link_speed} · Android security type {security_type}",
        f"│ Source: {safe_text(source, 'Android Wi-Fi service')}",
        "╰──────────────────────────────────────────────────────╯",
    ]
    if warning:
        lines.extend(("", f"Note: {safe_text(warning)}"))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("human", "json", "connection"), default="human")
    parser.add_argument("--source", default="Android Wi-Fi service")
    parser.add_argument("--warning", default="")
    args = parser.parse_args()
    text = sys.stdin.read()
    if args.format == "connection":
        print(render_connection(text, args.source, args.warning))
        return 0
    networks = parse_raw(text)
    if args.format == "json":
        print(json.dumps({"source": safe_text(args.source), "networks": networks}, ensure_ascii=False, indent=2))
    else:
        print(render_scan(networks, args.source, args.warning))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
