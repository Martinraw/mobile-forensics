"""Generate the SVG icon set for Forensic Suite (Feather-style paths, MIT).

Re-run this script any time you add icons:  python scripts/gen_icons.py
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "icons"

# icon name -> (inner SVG markup, stroke colour)
ICONS: dict[str, tuple[str, str]] = {
    "folder": ('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 '
               "2-2h5l2 3h9a2 2 0 0 1 2 2z\"/>", "#00E5FF"),
    "smartphone": ('<rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>'
                   '<line x1="12" y1="18" x2="12.01" y2="18"/>', "#00E5FF"),
    "database": ('<ellipse cx="12" cy="5" rx="9" ry="3"/>'
                 '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
                 '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>', "#00E5FF"),
    "activity": ('<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>', "#FFAB00"),
    "clock": ('<circle cx="12" cy="12" r="10"/>'
              '<polyline points="12 6 12 12 16 14"/>', "#00E5FF"),
    "file-text": ('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 '
                  "0 0 2-2V8z\"/><polyline points=\"14 2 14 8 20 8\"/>"
                  '<line x1="16" y1="13" x2="8" y2="13"/>'
                  '<line x1="16" y1="17" x2="8" y2="17"/>', "#00E5FF"),
    "settings": ('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 '
                 ".33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 "
                 "1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 "
                 "0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 "
                 "2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 "
                 "1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 "
                 "0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 "
                 "0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 "
                 "1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 "
                 "1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 "
                 "2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 "
                 "1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z\"/>",
                 "#7C4DFF"),
    "message-circle": ('<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 '
                       "4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 "
                       "8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 "
                       "8 8z\"/>", "#7C4DFF"),
    "users": ('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
              '<circle cx="9" cy="7" r="4"/>'
              '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>'
              '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>', "#7C4DFF"),
    "camera": ('<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4'
               'l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
               "#00E676"),
    "map-pin": ('<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
                '<circle cx="12" cy="10" r="3"/>', "#FFAB00"),
    "cloud": ('<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>',
              "#3AA6FF"),
    "trash": ('<polyline points="3 6 5 6 21 6"/>'
              '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 '
              "2-2h4a2 2 0 0 1 2 2v2\"/><line x1=\"10\" y1=\"11\" x2=\"10\" y2=\"17\"/>"
              '<line x1="14" y1="11" x2="14" y2="17"/>', "#FF1744"),
    "search": ('<circle cx="11" cy="11" r="8"/>'
               '<line x1="21" y1="21" x2="16.65" y2="16.65"/>', "#00E5FF"),
    "plus": ('<line x1="12" y1="5" x2="12" y2="19"/>'
             '<line x1="5" y1="12" x2="19" y2="12"/>', "#00E5FF"),
    "download": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                 '<polyline points="7 10 12 15 17 10"/>'
                 '<line x1="12" y1="15" x2="12" y2="3"/>', "#00E5FF"),
    "upload": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
               '<polyline points="17 8 12 3 7 8"/>'
               '<line x1="12" y1="3" x2="12" y2="15"/>', "#00E5FF"),
    "shield": ('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
               "#00E676"),
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="2" stroke-linecap="round"'
    ' stroke-linejoin="round">{body}</svg>'
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (body, color) in ICONS.items():
        (OUT / f"{name}.svg").write_text(
            _TEMPLATE.format(color=color, body=body), encoding="utf-8")
    print(f"Generated {len(ICONS)} SVG icons in {OUT}")


if __name__ == "__main__":
    main()