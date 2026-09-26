"""Rendera widgetarna till widgets/.preview/ och servera widgets/ lokalt.

    .venv/Scripts/python.exe scripts/preview_widgets.py
    -> http://127.0.0.1:8765/dev-harness.html
"""
import functools
import http.server
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.widgets import WIDGETS, render_widget  # noqa: E402


def main() -> None:
    widgets_dir = ROOT / "widgets"
    preview = widgets_dir / ".preview"
    preview.mkdir(exist_ok=True)
    for name in WIDGETS:
        (preview / f"{name}.html").write_text(render_widget(name), encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(widgets_dir))
    print("http://127.0.0.1:8765/dev-harness.html")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8765), handler).serve_forever()


if __name__ == "__main__":
    main()
