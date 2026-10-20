"""
FTIR Contamination Analyzer - design system

Every colour, font, size, spacing step and animation time of the application is defined
here, once, as named "tokens". The window, the figures and the report all read from this
file, so the whole program looks like one product and a value is changed in one place.

The look is minimal and modern:
    Colour    warm neutral greys and ONE soft accent (powder blue): pastel fills with dark text
              for buttons and badges, a deeper step of the same blue for lines and focus.
              Status colours (probable / weak / no match / do not trust) are pastel tints, only
              used for status, always with an icon and a word, never by colour alone.
    Surfaces  white cards with a 1 px border on a near-white page; no gradients, no heavy
              shadows (a soft shadow only appears while a card is lifted under the mouse).
    Spacing   an 8 px grid: every margin and gap is 8, 16, 24, 32 or 48 px.
    Type      Inter for everything (14 px and up for text; 12 px only for chart axis labels),
              IBM Plex Mono for checksums and file paths.
    Charts    sample = ink, library reference = soft blue, unexplained band = soft coral, where
              two shapes differ = a peach wash. The pair passes the colour-blind check
              (validate_palette) in both themes. The similarity map is one warm hue.
    Motion    short (150-280 ms), eases out (fast start, gentle stop), never bounces;
              View > Reduce motion switches it off.

Text contrast (WCAG), both themes: body text >= 9:1, small grey text >= 5.2:1, text on the pastel
buttons >= 7.3:1, every status word on its tint >= 4.5:1, text on every step of the map >= 6:1.

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

# Motion (milliseconds). Quick for small things, a little longer for things that travel further;
# nothing you do often waits more than 0.3 s.
MOTION = {"hover": 150, "tab": 220, "content": 260, "page": 280, "sheet": 280, "sheet_out": 180,
          "count": 600, "bars": 700, "stagger": 28, "toast": 2600}

LIGHT = {
    "name": "light",
    # surfaces, back to front (warm greys: softer than pure grey next to pastels)
    "paper": "#FAFAF9",        # the page
    "surface": "#FFFFFF",      # cards, sidebar, toolbar, the figure
    "surface_2": "#F4F4F2",    # hover, quiet fills, fields
    "sidebar": "#FFFFFF",
    "line": "#E7E5E4",         # borders and dividers
    "line_strong": "#D6D3D1",  # a border under the mouse
    "shadow": "#1C1917",       # the soft shadow of a lifted card ...
    "shadow_alpha": 0.07,      # ... this strong
    "backdrop_alpha": 0.28,    # how much the window is dimmed behind a sheet
    # text
    "ink": "#1C1917",          # primary text (16.7:1 on the page)
    "ink_2": "#44403C",        # secondary text (9.8:1)
    "muted": "#6B6560",        # captions, axis labels (5.5:1)
    "faint": "#A8A29E",        # placeholders, disabled (never for information)
    # the one accent: a soft powder blue
    "primary": "#D6E4F8",      # filled buttons and badges: a pastel tint ...
    "primary_hover": "#C7DAF5",
    "primary_pressed": "#B8CFF1",
    "on_primary": "#1E3A66",   # ... with dark text on it (8.8:1)
    "accent": "#5B8DD9",       # lines, bars, focus rings, the active tab (3:1 or more on every surface)
    "accent_hover": "#4A7CC9",
    "accent_ink": "#2F5D9C",   # accent-coloured text and icons (6.3:1)
    "accent_soft": "#EDF3FC",  # the selected row, the next-step box
    "on_accent": "#FFFFFF",
    # toolbar
    "header": "#FFFFFF",
    "header_ink": "#1C1917",
    "header_muted": "#6B6560",
    "header_button": "#F4F4F2",
    "header_button_hover": "#EEEDEA",
    # tooltips: small and dark
    "tooltip": "#1C1917",
    "tooltip_ink": "#FAFAF9",
    # status: (text and icon, pastel background)
    "good": "#2F7A4E", "good_bg": "#E5F3EA",
    "warn": "#85580F", "warn_bg": "#FAF0DC",
    "none": "#57534E", "none_bg": "#F1F0EE",
    "bad": "#A23A2C", "bad_bg": "#FAE5E1",
    # charts (validate_palette: reference + unexplained pass every check on white)
    "chart_surface": "#FFFFFF",
    "chart_sample": "#1C1917",
    "chart_reference": "#5B8DD9",
    "chart_unexplained": "#D96C4F",
    "chart_diff": "#F6C9B1",   # where two shapes differ: a peach wash ...
    "chart_diff_alpha": 0.85,  # ... this strong
    "chart_found": "#5B8DD9",  # the key bands belong to the reference: same colour
    "chart_zone": "#1C1917",   # drawn at low opacity
    "chart_grid": "#F1F0EE",
    "chart_axis": "#D6D3D1",
    # the similarity map: one warm hue, near 0 = almost white, near 1 = soft coral; dark text on every step
    "sequence": ["#F5F4F2", "#F8EDE5", "#F9E3D6", "#F9D9C7", "#F8CEB8", "#F6C3A9", "#F3B79A", "#EFAA8B",
                 "#E99C7C", "#E28E6D", "#DA7F60"],
    "sequence_ink": "#1C1917",
}

DARK = {
    "name": "dark",
    "paper": "#111110",
    "surface": "#1A1918",
    "surface_2": "#242321",
    "sidebar": "#151413",
    "line": "#2E2C2A",
    "line_strong": "#403D3A",
    "shadow": "#000000",
    "shadow_alpha": 0.45,
    "backdrop_alpha": 0.5,
    "ink": "#F2F1EF",
    "ink_2": "#CFCBC6",
    "muted": "#9C968F",
    "faint": "#615C57",
    "primary": "#2B3E5C",
    "primary_hover": "#34496B",
    "primary_pressed": "#3D547A",
    "on_primary": "#DCE8FB",
    "accent": "#6492DD",
    "accent_hover": "#7AA2E3",
    "accent_ink": "#A3C2F2",
    "accent_soft": "#1D2634",
    "on_accent": "#FFFFFF",
    "header": "#151413",
    "header_ink": "#F2F1EF",
    "header_muted": "#9C968F",
    "header_button": "#242321",
    "header_button_hover": "#2E2C2A",
    "tooltip": "#2E2C2A",
    "tooltip_ink": "#F2F1EF",
    "good": "#84D4A3", "good_bg": "#132A1D",
    "warn": "#E8C373", "warn_bg": "#2B2314",
    "none": "#CFCBC6", "none_bg": "#242321",
    "bad": "#F0A090", "bad_bg": "#2F1B17",
    "chart_surface": "#1A1918",
    "chart_sample": "#F2F1EF",
    "chart_reference": "#6492DD",
    "chart_unexplained": "#D77352",
    "chart_diff": "#E3A487",
    "chart_diff_alpha": 0.3,
    "chart_found": "#6492DD",
    "chart_zone": "#F2F1EF",
    "chart_grid": "#242321",
    "chart_axis": "#403D3A",
    # in the dark theme the scale is turned round: near 0 sinks into the dark surface; light text on every step
    "sequence": ["#242321", "#2D2421", "#372722", "#412A23", "#4C2D24", "#573025", "#633326", "#6F3627",
                 "#7B3A29", "#883D2B", "#95412D"],
    "sequence_ink": "#F2F1EF",
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
#Header QPushButton#Primary {{ background: {t['primary']}; color: {t['on_primary']}; padding: 8px 16px; font-weight: 600; }}
#Header QPushButton#Primary:hover {{ background: {t['primary_hover']}; }}
#Header QPushButton#Primary:pressed {{ background: {t['primary_pressed']}; }}
#Header QPushButton#Primary:disabled {{ background: {t['surface_2']}; color: {t['faint']}; }}
#Header QToolButton {{ background: transparent; border: none; border-radius: {r_c}px; padding: 8px; }}
#Header QToolButton:hover {{ background: {t['surface_2']}; }}
#Header QToolButton:pressed {{ background: {t['line']}; }}

/* ---------- sidebar ---------- */
#Sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['line']}; }}
#SidebarTitle {{ font-size: {SIZE['title']}px; font-weight: 600; }}
#Count {{ color: {t['muted']}; font-size: {SIZE['small']}px; }}
QLineEdit, QComboBox, QPlainTextEdit {{
    background: {t['surface']}; border: 1px solid {t['line_strong']}; border-radius: {r_c}px; padding: 8px 12px;
    selection-background-color: {t['primary']}; selection-color: {t['on_primary']};
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
QScrollArea#MapScroller, QScrollArea#MapScroller > QWidget, QScrollArea#MapScroller > QWidget > QWidget {{
    background: transparent; }}
#SampleName {{ font-size: {SIZE['display']}px; font-weight: 600; }}
#HeroTitle {{ font-size: {SIZE['hero']}px; font-weight: 700; }}
#HeroTitle[compact="true"] {{ font-size: {SIZE['display']}px; }}
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
QPushButton#Primary {{ background: {t['primary']}; border: 1px solid {t['primary']}; color: {t['on_primary']}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {t['primary_hover']}; border-color: {t['primary_hover']}; }}
QPushButton#Primary:pressed {{ background: {t['primary_pressed']}; border-color: {t['primary_pressed']}; }}
QPushButton#Primary:focus {{ border: 1px solid {t['accent']}; }}
QPushButton#Primary:disabled {{ background: {t['surface_2']}; border-color: {t['line']}; color: {t['faint']}; }}
QPushButton#Danger {{ color: {t['bad']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {t['accent_ink']}; padding: 4px 0; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {r_c}px; padding: 6px;
    color: {t['ink_2']}; }}
QToolButton:hover {{ background: {t['surface_2']}; }}
QToolButton:pressed {{ background: {t['line']}; }}
QToolButton:checked {{ background: {t['accent_soft']}; border-color: {t['accent_soft']}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton[popupMode="2"] {{ padding: 6px 10px; font-weight: 500; }}
QCheckBox {{ spacing: 8px; color: {t['ink_2']}; }}

#DialogTitle {{ font-size: {SIZE['heading']}px; font-weight: 600; }}
QScrollArea#FileList {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: {r_k}px; }}
#ListArea {{ background: {t['surface']}; border-radius: {r_k}px; }}
#FileRow {{ border-bottom: 1px solid {t['line']}; background: transparent; }}
#SheetPanel {{ background: transparent; }}
#SheetHeader {{ background: transparent; border-bottom: 1px solid {t['line']}; }}
#SheetFooter {{ background: transparent; border-top: 1px solid {t['line']}; }}

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
