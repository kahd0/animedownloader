"""Design system tokens — single source of truth for all visual values."""

# ── Backgrounds ──────────────────────────────────────────────────────────────
BG_DEEP     = "#080B0F"
BG_SURFACE  = "#0F1318"
BG_ELEVATED = "#161C24"
BG_OVERLAY  = "#1E2530"
BG_BORDER   = "#252D38"

# ── Accent ───────────────────────────────────────────────────────────────────
ACCENT       = "#4F8EF7"
ACCENT_GLOW  = "rgba(79,142,247,0.25)"
ACCENT_MUTED = "#2A4A7F"
ACCENT_HOVER = "#6BA3FF"

# ── Semantic ─────────────────────────────────────────────────────────────────
SUCCESS      = "#22C55E"
SUCCESS_GLOW = "rgba(34,197,94,0.20)"
WARNING      = "#F59E0B"
WARNING_GLOW = "rgba(245,158,11,0.20)"
ERROR        = "#EF4444"
ERROR_GLOW   = "rgba(239,68,68,0.20)"
INFO         = "#38BDF8"
DOWNLOADING  = "#8B5CF6"
TRANSLATING  = "#EC4899"
NEW_EPISODE  = "#F97316"

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT_PRIMARY   = "#F1F5F9"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED     = "#4B5563"
TEXT_DISABLED  = "#2D3748"

# ── Spacing (4px base) ────────────────────────────────────────────────────────
SP1  =  4
SP2  =  8
SP3  = 12
SP4  = 16
SP5  = 20
SP6  = 24
SP8  = 32
SP10 = 40
SP12 = 48
SP16 = 64

# ── Radii ─────────────────────────────────────────────────────────────────────
RADIUS_SM  =  4
RADIUS_MD  =  8
RADIUS_LG  = 12
RADIUS_XL  = 16
RADIUS_2XL = 24

# ── Layout ────────────────────────────────────────────────────────────────────
SIDEBAR_WIDTH  = 220
TITLEBAR_HEIGHT = 40
CONTENT_PAD_H  = 32
CONTENT_PAD_V  = 24
CARD_WIDTH     = 220
CARD_HEIGHT    = 330
CARD_GAP       = 20

# ── Animation durations (ms) ──────────────────────────────────────────────────
DUR_INSTANT = 80
DUR_FAST    = 150
DUR_NORMAL  = 250
DUR_SLOW    = 400

# ── Provider colors ───────────────────────────────────────────────────────────
PROVIDER_COLORS = {
    "SubsPlease":    ACCENT,
    "Erai-raws":     DOWNLOADING,
    "OpenSubtitles": TRANSLATING,
    "Jimaku":        WARNING,
    "Generic":       TEXT_MUTED,
}

# ── Status colors ─────────────────────────────────────────────────────────────
STATUS_COLORS = {
    "airing":      SUCCESS,
    "completed":   TEXT_MUTED,
    "not_aired":   INFO,
    "downloading": DOWNLOADING,
    "ready":       SUCCESS,
    "error":       ERROR,
    "translating": TRANSLATING,
    "subtitle":    ACCENT,
    "organizing":  WARNING,
    "new":         NEW_EPISODE,
}

# ── Log level colors ──────────────────────────────────────────────────────────
LOG_LEVEL_COLORS = {
    "INFO":    INFO,
    "WARNING": WARNING,
    "ERROR":   ERROR,
    "DEBUG":   TEXT_MUTED,
    "SUCCESS": SUCCESS,
}

LOG_SOURCE_COLORS = {
    "pipeline":    ACCENT,
    "download":    DOWNLOADING,
    "subtitle":    SUCCESS,
    "translation": TRANSLATING,
    "organize":    WARNING,
    "system":      TEXT_SECONDARY,
}
