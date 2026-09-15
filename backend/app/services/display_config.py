"""Display configuration presets and storage helpers.

Display configuration is stored in ``system_settings`` as structured JSON and is
fully separate from queue data. Changing the design never touches
``queue_tickets`` / ``visits`` / ``appointments``.

Storage keys:
- ``display_config_draft``     — what the admin is editing.
- ``display_config_published`` — what the public display renders.
"""
from __future__ import annotations

import json

DEFAULT_WIDGET = {
    "visible": True,
    "x": 0,
    "y": 0,
    "width": 400,
    "height": 180,
    "backgroundColor": "#ffffff",
    "textColor": "#1a1d23",
    "borderColor": "#e0e3e8",
    "borderWidth": 1,
    "borderRadius": 8,
    "fontSize": 24,
    "fontWeight": 700,
    "textAlign": "center",
    "lineHeight": 1.2,
    "locked": False,
}


def _w(**overrides) -> dict:
    w = dict(DEFAULT_WIDGET)
    w.update(overrides)
    return w


def _build(theme: dict, panel_bg: str, text: str, border: str) -> dict:
    return {
        "version": 1,
        "resolution": {"width": 1920, "height": 1080},
        "theme": theme,
        "identity": {
            "name": "",
            "headerTitle": "",
            "subtitle": "",
            "logoUrl": "",
            "showLogo": True,
            "showName": True,
        },
        "widgets": {
            "header": _w(x=0, y=0, width=1920, height=110, backgroundColor=panel_bg, textColor=text, borderColor=border, borderWidth=0, borderRadius=0, fontSize=40, fontWeight=800, textAlign="left"),
            "clock": _w(x=1460, y=20, width=420, height=70, backgroundColor="transparent", textColor="#6b7280" if theme["background"] != "#000000" else "#ffff00", borderColor="transparent", borderWidth=0, borderRadius=0, fontSize=26, fontWeight=600, textAlign="right"),
            "nowTitle": _w(x=280, y=150, width=1000, height=60, backgroundColor="transparent", textColor=theme["accent"], borderColor="transparent", borderWidth=0, borderRadius=0, fontSize=32, fontWeight=700, textAlign="center"),
            "nowTicket": _w(x=280, y=230, width=1000, height=400, backgroundColor=panel_bg, textColor=text, borderColor=border, fontSize=220, fontWeight=900, lineHeight=1),
            "nowCounter": _w(x=280, y=650, width=1000, height=90, backgroundColor="transparent", textColor=text, borderColor="transparent", borderWidth=0, borderRadius=0, fontSize=44, fontWeight=700, textAlign="center"),
            "counters": _w(x=40, y=150, width=220, height=850, backgroundColor=panel_bg, textColor=text, borderColor=border, fontSize=28),
            "waiting": _w(x=1300, y=150, width=580, height=420, backgroundColor=panel_bg, textColor=text, borderColor=border, fontSize=28),
            "missed": _w(x=1300, y=590, width=580, height=410, backgroundColor=panel_bg, textColor=text, borderColor=border, fontSize=28),
        },
    }


PRESETS: dict[str, dict] = {
    "default": _build(
        {"background": "#f5f6f8", "primary": "#2563eb", "accent": "#2563eb", "text": "#1a1d23"},
        "#ffffff", "#1a1d23", "#e0e3e8",
    ),
    "light": _build(
        {"background": "#ffffff", "primary": "#1d4ed8", "accent": "#1d4ed8", "text": "#111827"},
        "#ffffff", "#111827", "#e5e7eb",
    ),
    "dark": _build(
        {"background": "#0f172a", "primary": "#38bdf8", "accent": "#38bdf8", "text": "#f8fafc"},
        "#1e293b", "#f8fafc", "#334155",
    ),
    "high_contrast": _build(
        {"background": "#000000", "primary": "#ffff00", "accent": "#ffff00", "text": "#ffffff"},
        "#000000", "#ffffff", "#ffff00",
    ),
}


def deep_preset(name: str) -> dict:
    name = name if name in PRESETS else "default"
    return json.loads(json.dumps(PRESETS[name]))


DRAFT_KEY = "display_config_draft"
PUBLISHED_KEY = "display_config_published"
