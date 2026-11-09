"""Keep repository images in the package description renderable on PyPI."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def test_readme_repository_images_use_absolute_urls_and_valid_file_formats():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    urls = re.findall(r'<img\s+[^>]*src="([^"]+)"', readme)
    urls += re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
    assert urls
    for url in urls:
        parsed = urlparse(url)
        assert parsed.scheme == "https" and parsed.netloc, url
        if parsed.netloc != "raw.githubusercontent.com":
            continue
        parts = parsed.path.lstrip("/").split("/", 3)
        if len(parts) != 4 or parts[:2] != ["atomicdjt", "trajectory-fidelity-bridge"]:
            continue
        image = ROOT / parts[3]
        data = image.read_bytes()
        if image.suffix.lower() == ".svg":
            assert ET.fromstring(data).tag.endswith("svg")
        elif image.suffix.lower() == ".gif":
            assert data.startswith((b"GIF87a", b"GIF89a")), image
        elif image.suffix.lower() == ".png":
            assert data.startswith(b"\x89PNG\r\n\x1a\n"), image
