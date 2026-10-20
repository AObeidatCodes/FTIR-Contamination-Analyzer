"""
FTIR Contamination Analyzer - design system

Every colour, font, size, spacing step and animation time of the application is defined
here, once, as named "tokens". The window, the figures and the report all read from this
file, so the whole program looks like one product and a value is changed in one place.

The look is minimal and modern:
    Colour    neutral greys and ONE accent (indigo) for everything you can click or that is
              selected. Status colours (probable / weak / no match / do not trust) are only
              used for status, always with an icon and a word, never by colour alone.
    Surfaces  white cards with a 1 px border on a near-white page; no gradients, no heavy
              shadows (a soft shadow only appears while a card is lifted under the mouse).
    Spacing   an 8 px grid: every margin and gap is 8, 16, 24, 32 or 48 px.
    Type      Inter for everything (14 px and up for text; 12 px only for chart axis labels),
              IBM Plex Mono for checksums and file paths.
    Charts    sample = ink, library reference = indigo, unexplained band = orange. The pair
              passes the colour-blind check (validate_palette) in both themes.
    Motion    short (150-340 ms), eases out (fast start, gentle stop), never bounces;
              View > Reduce motion switches it off.

Text contrast (WCAG): body text >= 9:1, small grey text >= 4.8:1, white on the accent 6.3:1.

Short names used in this file:
    t = a theme (a dict of colour tokens)    qss = Qt style sheet (CSS for Qt widgets)    ms = milliseconds

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
ICONS = ASSETS / "icons"
FONTS = ASSETS / "fonts"
LOGO_SVG = ASSETS / "logo.svg"

FONT_SANS = "Inter"
FONT_MONO = "IBM Plex Mono"
FONT_FILES = ["Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf",
              "IBMPlexMono-Regular.ttf", "IBMPlexMono-Medium.ttf"]
WEB_FONTS = [("Inter-Regular.woff2", 400), ("Inter-SemiBold.woff2", 600)]     # embedded in the HTML report

# Type scale (pixels): 14 px is the smallest text; 12 px is only used for chart axis labels.
SIZE = {"caption": 12, "small": 14, "body": 15, "title": 17, "heading": 22, "display": 28, "hero": 40}

# Spacing: the 8 px grid
SPACE = {"xs": 8, "s": 16, "m": 24, "l": 32, "xl": 48}

# Corner radius
RADIUS = {"control": 8, "card": 12}

# Motion (milliseconds). Quick for small things, a little longer for things that travel further.
MOTION = {"hover": 150, "tab": 240, "content": 300, "page": 320, "sheet": 340, "sheet_out": 220,
          "count": 600, "bars": 700, "stagger": 28, "toast": 2600}

LIGHT = {
    "name": "light",
    # surfaces, back to front
    "paper": "#FAFAFA",        # the page
    "surface": "#FFFFFF",      # cards, sidebar, toolbar, the figure
    "surface_2": "#F5F5F5",    # hover, quiet fills, fields
    "sidebar": "#FFFFFF",
    "line": "#E5E5E5",         # borders and dividers
    "line_strong": "#D4D4D4",  # a border under the mouse
    "shadow": "#000000",       # the soft shadow of a lifted card ...
    "shadow_alpha": 0.08,      # ... this strong
    "backdrop_alpha": 0.32,    # how much the window is dimmed behind a sheet
    # text
    "ink": "#171717",          # primary text
    "ink_2": "#404040",        # secondary text
    "muted": "#6B6B6B",        # captions, axis labels
    "faint": "#A3A3A3",        # placeholders, disabled (never for information)
    # the one accent (indigo)
    "accent": "#4F46E5",       # buttons and the active state (white text on it: 6.3:1)
    "accent_hover": "#4338CA",
    "accent_ink": "#4338CA",   # accent-coloured text and icons
    "accent_soft": "#EEF2FF",  # the selected row, the focus glow
    "on_accent": "#FFFFFF",
    # toolbar
    "header": "#FFFFFF",
    "header_ink": "#171717",
    "header_muted": "#6B6B6B",
    "header_button": "#F5F5F5",
    "header_button_hover": "#F0F0F0",
    # tooltips: small and dark
    "tooltip": "#171717",
    "tooltip_ink": "#FAFAFA",
    # status: (text and icon, background)
    "good": "#15803D", "good_bg": "#F0FDF4",
    "warn": "#A16207", "warn_bg": "#FEFCE8",
    "none": "#525252", "none_bg": "#F5F5F5",
    "bad": "#B91C1C", "bad_bg": "#FEF2F2",
    # charts
    "chart_surface": "#FFFFFF",
    "chart_sample": "#171717",
    "chart_reference": "#4F46E5",
    "chart_unexplained": "#E8650F",
    "chart_found": "#4F46E5",  # the key bands belong to the reference: same colour
    "chart_zone": "#171717",   # drawn at low opacity
    "chart_grid": "#F0F0F0",
    "chart_axis": "#D4D4D4",
    # one hue (indigo) for the similarity map: near 0 = light, near 1 = dark
    "sequence": ["#EEF2FF", "#E0E7FF", "#C7D2FE", "#A5B4FC", "#818CF8", "#6366F1", "#4F46E5", "#4338CA",
                 "#3730A3", "#312E81", "#1E1B4B"],
}

DARK = {
    "name": "dark",
    "paper": "#0A0A0A",
    "surface": "#141414",
    "surface_2": "#1F1F1F",
    "sidebar": "#111111",
    "line": "#262626",
    "line_strong": "#3A3A3A",
    "shadow": "#000000",
    "shadow_alpha": 0.5,
    "backdrop_alpha": 0.55,
    "ink": "#EDEDED",
    "ink_2": "#C2C2C2",
    "muted": "#8F8F8F",
    "faint": "#5C5C5C",
    "accent": "#4F46E5",
    "accent_hover": "#5B52F0",
    "accent_ink": "#A5B4FC",
    "accent_soft": "#1E1B4B",
    "on_accent": "#FFFFFF",
    "header": "#111111",
    "header_ink": "#EDEDED",
    "header_muted": "#8F8F8F",
    "header_button": "#1F1F1F",
    "header_button_hover": "#262626",
    "tooltip": "#2A2A2A",
    "tooltip_ink": "#EDEDED",
    "good": "#4ADE80", "good_bg": "#052E16",
    "warn": "#FACC15", "warn_bg": "#2A2205",
    "none": "#C2C2C2", "none_bg": "#1F1F1F",
    "bad": "#F87171", "bad_bg": "#2C0B0B",
    "chart_surface": "#141414",
    "chart_sample": "#EDEDED",
    "chart_reference": "#7C83F2",
    "chart_unexplained": "#DD6A22",
    "chart_found": "#7C83F2",
    "chart_zone": "#EDEDED",
    "chart_grid": "#1F1F1F",
    "chart_axis": "#3A3A3A",
    # in the dark theme the scale is turned round: near 0 sinks into the dark surface
    "sequence": ["#1E1B4B", "#312E81", "#3730A3", "#4338CA", "#4F46E5", "#6366F1", "#818CF8", "#A5B4FC",
                 "#C7D2FE", "#E0E7FF", "#EEF2FF"],
}

THEMES = {"light": LIGHT, "dark": DARK}

# Verdict -> (status key, short word, icon file). The word and icon always travel with the colour.
VERDICT_LOOK = {
    "probable": ("good", "Probable", "circle-check"),
    "weak": ("warn", "Weak", "circle-help"),
    "no reliable match": ("none", "No reliable match", "circle-minus"),
}

# Each library category with its icon (Lucide)
CATEGORY_ICONS = {
    "All references": "library-big", "In-house": "shield-plus", "Open Specy": "layers",
    "CMP & cleaning": "droplets", "Cleanroom consumables": "hand", "People & clothing": "shirt",
    "Carriers & handling": "box", "Packaging": "package", "Adhesives, seals & lubricants": "layers-2",
    "Litho & process residues": "microscope", "Equipment & fixtures": "wrench",
    "Minerals & inorganics": "hard-drive", "Natural materials": "sparkles",
}


def rgba(hex_colour, alpha):
    """'#RRGGBB' + opacity -> 'rgba(r, g, b, a)' for the style sheet."""
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


def stylesheet(t):
    """The Qt style sheet for a theme: how every standard widget looks (Qt's version of CSS)."""
    r_c, r_k = RADIUS["control"], RADIUS["card"]
    return f"""
* {{ font-family: "{FONT_SANS}"; font-size: {SIZE['body']}px; color: {t['ink']}; }}
QMainWindow, QDialog {{ background: {t['paper']}; }}
QToolTip {{ background: {t['tooltip']}; color: {t['tooltip_ink']}; border: none; padding: 8px 10px;
    border-radius: 6px; font-size: {SIZE['small']}px; }}

/* ---------- toolbar ---------- */
#Header {{ background: {t['header']}; border-bottom: 1px solid {t['line']}; }}
#Header QLabel {{ color: {t['header_ink']}; }}
#AppTitle {{ font-size: {SIZE['body']}px; font-weight: 600; }}
#AppSubtitle {{ color: {t['header_muted']}; font-size: {SIZE['small']}px; }}
#Header QPushButton {{ background: transparent; color: {t['ink_2']}; border: 1px solid transparent;
    border-radius: {r_c}px; padding: 8px 12px; font-weight: 500; }}
#Header QPushButton:hover {{ background: {t['surface_2']}; color: {t['ink']}; }}
#Header QPushButton:pressed {{ background: {t['line']}; }}
#Header QPushButton:disabled {{ color: {t['faint']}; }}
#Header QPushButton#Primary {{ background: {t['accent']}; color: {t['on_accent']}; padding: 8px 16px; }}
#Header QPushButton#Primary:hover {{ background: {t['accent_hover']}; }}
#Header QPushButton#Primary:disabled {{ background: {t['surface_2']}; color: {t['faint']}; }}
#Header QToolButton {{ background: transparent; border: none; border-radius: {r_c}px; padding: 8px; }}
#Header QToolButton:hover {{ background: {t['surface_2']}; }}

/* ---------- sidebar ---------- */
#Sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['line']}; }}
#SidebarTitle {{ font-size: {SIZE['title']}px; font-weight: 600; }}
#Count {{ color: {t['muted']}; font-size: {SIZE['small']}px; }}
QLineEdit, QComboBox, QPlainTextEdit {{
    background: {t['surface']}; border: 1px solid {t['line_strong']}; border-radius: {r_c}px; padding: 8px 12px;
    selection-background-color: {t['accent']}; selection-color: {t['on_accent']};
}}
QLineEdit:hover, QComboBox:hover {{ border-color: {t['muted']}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {t['accent']}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {t['bad']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: {r_c}px;
    selection-background-color: {t['accent_soft']}; selection-color: {t['ink']}; padding: 4px; outline: none; }}
QListView, QListWidget {{ background: transparent; border: none; outline: none; }}

/* ---------- content ---------- */
#Content, #ResultPage, #EmptyPage, #LibraryPage, #LibraryGrid, #SheetContent {{ background: {t['paper']}; }}
QScrollArea {{ border: none; background: {t['paper']}; }}
#SampleName {{ font-size: {SIZE['display']}px; font-weight: 600; }}
#HeroTitle {{ font-size: {SIZE['hero']}px; font-weight: 700; }}
#PageTitle {{ font-size: {SIZE['display']}px; font-weight: 600; }}
#Meta {{ color: {t['muted']}; font-size: {SIZE['small']}px; }}
#SectionTitle {{ font-size: {SIZE['title']}px; font-weight: 600; }}
#SectionHint {{ color: {t['muted']}; font-size: {SIZE['small']}px; }}
#Eyebrow {{ color: {t['accent_ink']}; font-size: {SIZE['small']}px; font-weight: 600; }}
#Body {{ color: {t['ink']}; }}
#Body2 {{ color: {t['ink_2']}; }}
#Mono {{ font-family: "{FONT_MONO}"; font-size: {SIZE['small']}px; color: {t['ink_2']}; }}
#FactValue {{ font-size: {SIZE['heading']}px; font-weight: 600; }}
#FactLabel {{ color: {t['muted']}; font-size: {SIZE['small']}px; }}
#NextStep {{ background: {t['accent_soft']}; border-radius: {r_k}px; }}
#NextStep[alert="true"] {{ background: {t['bad_bg']}; }}
#NextStep QLabel {{ color: {t['ink']}; }}
#Readout {{ color: {t['ink_2']}; font-size: {SIZE['small']}px; }}
#Divider {{ background: {t['line']}; }}
#Callout {{ background: {t['surface_2']}; border-radius: {r_c}px; }}
#Callout[kind="good"] {{ background: {t['good_bg']}; }}
#Callout[kind="bad"] {{ background: {t['bad_bg']}; }}
#Callout[kind="warn"] {{ background: {t['warn_bg']}; }}

/* chips */
#Chip {{ background: {t['surface_2']}; border: 1px solid {t['line']}; border-radius: 6px; padding: 4px 8px;
    color: {t['ink_2']}; font-size: {SIZE['small']}px; }}
#ChipMissing {{ background: transparent; border: 1px dashed {t['line_strong']}; border-radius: 6px; padding: 4px 8px;
    color: {t['muted']}; font-size: {SIZE['small']}px; }}
#ChipExtra {{ background: {t['warn_bg']}; border-radius: 6px; padding: 4px 8px; color: {t['warn']}; font-weight: 600;
    font-size: {SIZE['small']}px; }}

/* buttons */
QPushButton {{
    background: {t['surface']}; border: 1px solid {t['line_strong']}; border-radius: {r_c}px; padding: 8px 16px;
    font-weight: 500; color: {t['ink']};
}}
QPushButton:hover {{ background: {t['surface_2']}; border-color: {t['muted']}; }}
QPushButton:pressed {{ background: {t['line']}; }}
QPushButton:focus {{ border: 1px solid {t['accent']}; }}
QPushButton:disabled {{ color: {t['faint']}; background: {t['surface_2']}; border-color: {t['line']}; }}
QPushButton#Primary {{ background: {t['accent']}; border: 1px solid {t['accent']}; color: {t['on_accent']}; }}
QPushButton#Primary:hover {{ background: {t['accent_hover']}; border-color: {t['accent_hover']}; }}
QPushButton#Primary:disabled {{ background: {t['surface_2']}; border-color: {t['line']}; color: {t['faint']}; }}
QPushButton#Danger {{ color: {t['bad']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {t['accent_ink']}; padding: 4px 0; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {r_c}px; padding: 6px;
    color: {t['ink_2']}; }}
QToolButton:hover {{ background: {t['surface_2']}; }}
QToolButton:checked {{ background: {t['accent_soft']}; border-color: {t['accent_soft']}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton[popupMode="2"] {{ padding: 6px 10px; font-weight: 500; }}
QCheckBox {{ spacing: 8px; color: {t['ink_2']}; }}

#DialogTitle {{ font-size: {SIZE['heading']}px; font-weight: 600; }}
QScrollArea#FileList {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: {r_k}px; }}
#ListArea {{ background: {t['surface']}; border-radius: {r_k}px; }}
#FileRow {{ border-bottom: 1px solid {t['line']}; background: transparent; }}
#SheetPanel {{ background: {t['paper']}; border-left: 1px solid {t['line']}; }}
#SheetHeader {{ background: {t['surface']}; border-bottom: 1px solid {t['line']}; }}
#SheetFooter {{ background: {t['surface']}; border-top: 1px solid {t['line']}; }}

/* scroll bars: thin and quiet */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {rgba(t['ink'], 0.18)}; border-radius: 4px; min-height: 40px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {rgba(t['ink'], 0.32)}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {rgba(t['ink'], 0.18)}; border-radius: 4px; min-width: 40px; margin: 2px 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* splitter, menus, status bar */
QSplitter::handle {{ background: {t['line']}; }}
QMenuBar {{ background: {t['header']}; color: {t['ink_2']}; padding: 2px 8px; }}
QMenuBar::item {{ background: transparent; color: {t['ink_2']}; padding: 4px 8px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {t['surface_2']}; color: {t['ink']}; }}
QMenu {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: {r_c}px; padding: 4px; }}
QMenu::item {{ padding: 8px 32px 8px 16px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['surface_2']}; color: {t['ink']}; }}
QMenu::item:disabled {{ color: {t['faint']}; }}
QMenu::separator {{ height: 1px; background: {t['line']}; margin: 4px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
QStatusBar {{ background: {t['header']}; border-top: 1px solid {t['line']}; color: {t['muted']}; }}
QStatusBar QLabel {{ color: {t['muted']}; font-size: {SIZE['small']}px; padding: 0 8px; }}
QProgressBar {{ background: {t['surface_2']}; border: none; border-radius: 2px; max-height: 4px; min-width: 160px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 2px; }}
QTextBrowser {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: {r_k}px; padding: 16px; }}
"""
