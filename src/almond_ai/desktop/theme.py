"""Dark, flat, restrained visual language for Almond Desktop.

Colour tokens mirror the ones already used by the Textual terminal
(`almond_ai/ui/styles/almond.tcss`, `almond_ai/app.py` status tones, and
each `BotDefinition.accent`) so both interfaces read as one product, not
two independently themed apps.
"""

from __future__ import annotations

BG_PRIMARY = "#0F1215"
BG_SURFACE = "#11161B"
BG_SURFACE_RAISED = "#151A1F"
BORDER = "#242A31"
SELECTED_BG = "#3A241B"  # warm dark-brown selection tint, not a bright highlight

TEXT_PRIMARY = "#F3F3F3"
TEXT_SECONDARY = "#9AA3B3"
TEXT_MUTED = "#6B7075"

ACCENT = "#F15A24"  # Almond orange -- primary brand accent
ACCENT_HOVER = "#FF6B33"

STATUS_AVAILABLE = "#20E69A"  # green
STATUS_COMING_SOON = "#8B87A6"  # muted purple/grey
STATUS_ERROR = "#A96363"  # muted red
STATUS_STARTING = "#B58A52"  # muted amber

BOT_ACCENTS = {
    "general": "#F4A15B",  # muted warm yellow-orange
    "calculator": "#8B5CF6",  # muted violet (walnut)
    "drafting": "#3DA5F4",  # muted blue (hazelnut)
    "document": "#FF7A22",  # muted orange (almond)
    "coding": "#D8637A",
}

# Roboto is bundled under assets/fonts and registered at startup (see
# desktop/main.py:_load_bundled_fonts) so it renders the same whether or
# not it's installed system-wide -- Windows ships no Roboto by default.
# Segoe UI/sans-serif remain as fallbacks only if font registration fails.
FONT_FAMILY = "Roboto, Segoe UI, sans-serif"

# Deliberate type scale (px). Four steps only -- micro labels/badges,
# body/UI text (the default for almost everything), the bot-name/brand
# register, and the one large size reserved for an empty-state headline.
# Bumped up a full notch across the board -- the first pass under-scaled
# against the reference, which reads noticeably fuller/bolder throughout.
TYPE_MICRO = 12
TYPE_BODY = 14
TYPE_EMPHASIS = 17
TYPE_HEADLINE = 26


def stylesheet() -> str:
    return f"""
    * {{
        font-family: {FONT_FAMILY};
        color: {TEXT_PRIMARY};
    }}

    QMainWindow, QWidget#root, QDialog {{
        background: {BG_PRIMARY};
    }}

    QWidget {{
        background: transparent;
    }}

    /* -- Sidebar ------------------------------------------------------ */

    QWidget#sidebar {{
        background: {BG_SURFACE};
        border-right: 1px solid {BORDER};
    }}

    QLabel#brand {{
        color: {TEXT_PRIMARY};
        font-size: 20px;
        font-weight: 700;
        padding: 2px;
    }}

    QLabel#sectionLabel {{
        color: {TEXT_MUTED};
        font-size: {TYPE_MICRO}px;
        font-weight: 600;
        padding: 18px 4px 4px 4px;
    }}

    QPushButton#navItem {{
        text-align: left;
        background: transparent;
        border: none;
        border-left: 4px solid transparent;
        border-radius: 10px;
        padding: 12px 12px 12px 8px;
        color: {TEXT_SECONDARY};
        font-size: {TYPE_BODY}px;
    }}

    QPushButton#navItem:hover {{
        background: {BG_SURFACE_RAISED};
        color: {TEXT_PRIMARY};
    }}

    QPushButton#navItem[active="true"] {{
        background: {SELECTED_BG};
        border-left: 4px solid {ACCENT};
        border-top-left-radius: 0px;
        border-bottom-left-radius: 0px;
        color: {TEXT_PRIMARY};
        font-weight: 600;
    }}

    QLabel#brandSubtitle {{
        color: {TEXT_SECONDARY};
        font-size: {TYPE_BODY}px;
    }}

    QLabel#navRowTitle {{
        font-size: {TYPE_EMPHASIS}px;
        font-weight: 600;
    }}

    QLabel#navSubtitle {{
        color: {TEXT_MUTED};
        font-size: {TYPE_BODY}px;
    }}

    QLabel#sidebarFooterLabel {{
        color: {TEXT_SECONDARY};
        font-size: {TYPE_BODY}px;
    }}

    QLabel#comingSoonBadge {{
        color: {STATUS_COMING_SOON};
        font-size: {TYPE_MICRO}px;
        font-weight: 600;
        background: rgba(139, 135, 166, 0.14);
        border-radius: 6px;
        padding: 2px 7px;
    }}

    /* -- Header --------------------------------------------------------- */

    QWidget#contentHeader {{
        background: {BG_PRIMARY};
        border-bottom: 1px solid {BORDER};
    }}

    QLabel#botTitle {{
        color: {TEXT_PRIMARY};
        font-size: 24px;
        font-weight: 700;
    }}

    QLabel#botSubtitle {{
        color: {TEXT_SECONDARY};
        font-size: {TYPE_BODY}px;
    }}

    QLabel#statusBadge {{
        color: {TEXT_MUTED};
        font-size: {TYPE_BODY}px;
        font-weight: 600;
        background: {BG_SURFACE_RAISED};
        border: 1px solid {BORDER};
        border-radius: 16px;
        padding: 8px 16px;
    }}

    /* -- Welcome hero / quick-start cards -------------------------------- */

    QLabel#welcomeBrandTitle {{
        color: {TEXT_PRIMARY};
        font-size: 38px;
        font-weight: 800;
    }}

    QLabel#welcomePartner {{
        color: {TEXT_SECONDARY};
        font-size: 16px;
    }}

    QLabel#welcomeHeading {{
        color: {TEXT_PRIMARY};
        font-size: {TYPE_HEADLINE}px;
        font-weight: 600;
    }}

    QPushButton#quickActionCard {{
        text-align: left;
        background: {BG_SURFACE};
        border: 1px solid {BORDER};
        border-radius: 14px;
    }}

    QPushButton#quickActionCard:hover {{
        background: {BG_SURFACE_RAISED};
        border-color: {ACCENT};
    }}

    QLabel#quickActionTitle {{
        color: {TEXT_PRIMARY};
        font-size: 16px;
        font-weight: 700;
    }}

    QLabel#quickActionSubtitle {{
        color: {TEXT_SECONDARY};
        font-size: {TYPE_BODY}px;
    }}


    /* -- Chat / empty state ---------------------------------------------- */

    QWidget#chatScrollArea, QScrollArea#chatScrollArea {{
        background: {BG_PRIMARY};
        border: none;
    }}

    QLabel#emptyTitle {{
        color: {TEXT_PRIMARY};
        font-size: {TYPE_HEADLINE}px;
        font-weight: 600;
    }}

    QLabel#emptyBody {{
        color: {TEXT_SECONDARY};
        font-size: {TYPE_BODY}px;
    }}

    QLabel#userBubble {{
        background: {BG_SURFACE_RAISED};
        color: {TEXT_PRIMARY};
        border-radius: 12px;
        padding: 10px 14px;
        font-size: {TYPE_BODY}px;
    }}

    QLabel#assistantText {{
        color: {TEXT_PRIMARY};
        font-size: {TYPE_BODY}px;
        padding: 2px;
    }}

    QLabel#assistantLabel {{
        color: {ACCENT};
        font-size: {TYPE_MICRO}px;
        font-weight: 700;
    }}

    /* -- Composer ---------------------------------------------------- */

    QWidget#composer {{
        background: {BG_SURFACE};
        border: 2px solid #3A4450;
        border-radius: 18px;
    }}

    QTextEdit#composerInput {{
        background: transparent;
        border: none;
        color: {TEXT_PRIMARY};
        font-size: 15px;
        padding: 8px;
    }}

    QLabel#composerHint {{
        color: {TEXT_MUTED};
        font-size: {TYPE_MICRO}px;
        background: {BG_SURFACE_RAISED};
        border-radius: 12px;
        padding: 7px 14px;
    }}

    QPushButton#sendButton {{
        background: {ACCENT};
        border: none;
        border-radius: 22px;
        min-width: 44px;
        max-width: 44px;
        min-height: 44px;
        max-height: 44px;
        color: white;
        font-size: 16px;
        font-weight: 700;
    }}

    QPushButton#sendButton:hover {{
        background: {ACCENT_HOVER};
    }}

    QPushButton#sendButton:disabled {{
        background: {BG_SURFACE_RAISED};
        color: {TEXT_MUTED};
    }}

    /* -- Buttons -------------------------------------------------------- */

    QPushButton#primaryAction {{
        background: {ACCENT};
        color: white;
        border: none;
        border-radius: 8px;
        padding: 9px 18px;
        font-size: {TYPE_BODY}px;
        font-weight: 600;
    }}

    QPushButton#primaryAction:hover {{
        background: {ACCENT_HOVER};
    }}

    QPushButton#secondaryAction {{
        background: transparent;
        color: {TEXT_SECONDARY};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px 16px;
        font-size: {TYPE_BODY}px;
    }}

    QPushButton#secondaryAction:hover {{
        color: {TEXT_PRIMARY};
        border-color: {TEXT_SECONDARY};
    }}

    QLabel#timingLabel {{
        color: {TEXT_MUTED};
        font-size: {TYPE_MICRO}px;
    }}

    /* -- Dialogs ---------------------------------------------------------- */

    QLabel#dialogIntro {{
        color: {TEXT_SECONDARY};
        font-size: {TYPE_MICRO}px;
    }}

    QLabel#fieldLabel {{
        color: {TEXT_PRIMARY};
        font-size: {TYPE_MICRO}px;
    }}

    QLabel#startupTitle {{
        color: {TEXT_PRIMARY};
        font-size: {TYPE_BODY}px;
        font-weight: 600;
    }}

    /* -- Settings / forms ------------------------------------------------ */

    QLabel#settingsSectionTitle {{
        color: {TEXT_MUTED};
        font-size: {TYPE_MICRO}px;
        font-weight: 600;
    }}

    QLabel#settingsValue {{
        color: {TEXT_PRIMARY};
        font-size: {TYPE_BODY}px;
    }}

    QLineEdit, QComboBox, QTextEdit {{
        background: {BG_SURFACE_RAISED};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 7px 9px;
        color: {TEXT_PRIMARY};
        font-size: {TYPE_BODY}px;
    }}

    QLineEdit:focus, QTextEdit:focus {{
        border-color: {ACCENT};
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 5px;
        min-height: 24px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {TEXT_MUTED};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
