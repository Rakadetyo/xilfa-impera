"""Background styles for the public invitation flow.

Every invite page (landing, player, teams, schedule, post-game) is rendered on
a dark purple ground with a gold court motif. A game can instead select a light
style, which keeps the same motif on a white ground.

The dark look is baked into Tailwind utilities throughout those templates —
text-white, bg-white/10, border-white/20 — so a light style cannot be a
background swap alone; it has to retarget those utilities too. Each style
therefore carries both a background and the overrides that keep the content
readable on it.

Styles live here rather than in the database so the set is versioned with the
templates it has to stay in step with. The Page Settings screen reads this
dict; a future editor can migrate it to a table without changing callers.
"""

# The court-line motif, shared by every style. Only the stroke colour varies.
_MOTIF = (
    "url(\"data:image/svg+xml,%3Csvg width='80' height='80' viewBox='0 0 80 80' "
    "xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M40 10V70M20 30H60M25 50H55"
    "M15 40L65 40M22 22L58 58M58 22L22 58' stroke='{stroke}' stroke-opacity='{opacity}' "
    "stroke-width='1.5' fill='none'/%3E%3C/svg%3E\")"
)

DEFAULT_STYLE = "purple"

STYLES = {
    "purple": {
        "name": "Purple & Gold",
        "description": "The original look — deep purple ground with gold court lines.",
        "logo": "/assets/logo impera white.png",
        "background": (
            _MOTIF.format(stroke="%23C9A84C", opacity="0.06")
            + ", linear-gradient(180deg, #0f0a1a 0%, #1a1025 40%, #2d1f35 60%, #1a1025 100%)"
        ),
        "color": "#FFFFFF",
        "option_bg": "#1A1A1A",
        "option_color": "#FFFFFF",
        # The templates are authored for this style, so it needs no overrides.
        "overrides": "",
    },
    "light": {
        "name": "White & Gold",
        "description": "Same court motif on a white ground, for daytime or printed invites.",
        "logo": "/assets/logo impera black.png",
        "background": (
            _MOTIF.format(stroke="%23C9A84C", opacity="0.12")
            + ", linear-gradient(180deg, #FFFFFF 0%, #FAF7F0 40%, #F3EEE2 60%, #FFFFFF 100%)"
        ),
        "color": "#1A1025",
        "option_bg": "#FFFFFF",
        "option_color": "#1A1025",
        # Retarget the dark-theme utilities the templates hardcode.
        "overrides": """
            .text-white { color: #1A1025 !important; }
            .text-gray-400 { color: #6B6478 !important; }
            .text-gray-500 { color: #5C5568 !important; }
            .text-gray-600 { color: #4A4455 !important; }
            .text-gray-700 { color: #3A3542 !important; }
            .bg-white\\/10 { background-color: rgba(26,16,37,0.05) !important; }
            .bg-white\\/5  { background-color: rgba(26,16,37,0.03) !important; }
            .bg-white\\/80 { background-color: rgba(255,255,255,0.92) !important; }
            .bg-black\\/30 { background-color: rgba(26,16,37,0.06) !important; }
            .border-white\\/20 { border-color: rgba(26,16,37,0.14) !important; }
            .border-white\\/10 { border-color: rgba(26,16,37,0.08) !important; }
            .backdrop-blur-lg { backdrop-filter: none !important; }
            .placeholder-gray-400::placeholder { color: #8A8394 !important; }
        """,
    },
}


def get_style(key: str) -> dict:
    """Resolve a style key, falling back to the default for unknown or empty values."""
    style = STYLES.get((key or "").strip() or DEFAULT_STYLE)
    return style or STYLES[DEFAULT_STYLE]


def style_choices() -> list:
    """[(key, style), ...] for pickers and the settings screen."""
    return [(k, v) for k, v in STYLES.items()]
