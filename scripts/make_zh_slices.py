#!/usr/bin/env python3
"""Rebuild data/zh/*.json: the list of font pieces ("slices") of each cut of
LXGW WenKai GB that the site can use for Chinese.

Only needed when moving to a newer version of the font packages. Unpack the
two npm packages next to each other and point this script at the folder:

    npm pack lxgw-wenkai-screen-webfont lxgw-wenkai-gb-web
    (unpack both .tgz into <dir>/screen and <dir>/gb)
    python scripts/make_zh_slices.py <dir>

A slice is one small .woff2 file plus the characters it holds. Slices with no
Chinese characters or Chinese punctuation are left out: the Latin fonts cover
those. layouts/partials/extend-head-uncached.html turns the lists into
@font-face rules for the sections named in data/zh_fonts.yaml.
"""
import json, re, sys
from pathlib import Path

CDN = "https://cdn.jsdelivr.net/npm/"
CUTS = {
    # name: (package@version, css file inside the package, folder of the .woff2 files)
    "screen": ("lxgw-wenkai-screen-webfont@1.7.0", "screen/package/lxgwwenkaigbscreen.css", "files/"),
    "gb-light": ("lxgw-wenkai-gb-web@1.530.0", "gb/package/lxgwwenkaigb-light/result.css", "lxgwwenkaigb-light/"),
    "gb-regular": ("lxgw-wenkai-gb-web@1.530.0", "gb/package/lxgwwenkaigb-regular/result.css", "lxgwwenkaigb-regular/"),
    "gb-medium": ("lxgw-wenkai-gb-web@1.530.0", "gb/package/lxgwwenkaigb-medium/result.css", "lxgwwenkaigb-medium/"),
}
# CJK punctuation, kana, ideographs (incl. extension A), full-width forms
WANTED = [(0x3000, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF)]


def has_chinese(ranges: str) -> bool:
    for part in ranges.split(","):
        m = re.fullmatch(r"\s*U\+([0-9a-fA-F]+)(?:-([0-9a-fA-F]+))?\s*", part)
        if not m:
            continue
        lo = int(m.group(1), 16)
        hi = int(m.group(2), 16) if m.group(2) else lo
        if any(lo <= b and hi >= a for a, b in WANTED):
            return True
    return False


def main(root: str) -> None:
    out = Path(__file__).resolve().parent.parent / "data" / "zh"
    out.mkdir(parents=True, exist_ok=True)
    for name, (pkg, css, folder) in CUTS.items():
        text = (Path(root) / css).read_text(encoding="utf-8")
        slices = []
        for block in re.findall(r"@font-face\s*\{(.*?)\}", text, re.S):
            url = re.search(r"url\(['\"]?\./(?:files/)?([^'\")]+\.woff2)['\"]?\)", block)
            rng = re.search(r"unicode-range:\s*([^;}]+)", block)
            if url and rng and has_chinese(rng.group(1)):
                slices.append({"f": url.group(1), "r": re.sub(r"\s+", "", rng.group(1))})
        (out / f"{name}.json").write_text(
            json.dumps({"base": f"{CDN}{pkg}/{folder}", "slices": slices}, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8")
        print(f"{name}: {len(slices)} slices")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
