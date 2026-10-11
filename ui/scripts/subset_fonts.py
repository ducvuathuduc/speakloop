"""Subset the OFL fonts we self-host into the card bundle (run once; outputs are committed).

Sources: @fontsource/atkinson-hyperlegible-next (Braille Institute, OFL-1.1) and
@fontsource/charis-sil (SIL International, OFL-1.1). Usage: python scripts/subset_fonts.py <node_modules dir>
"""
import sys
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont

nm = Path(sys.argv[1])
out = Path(__file__).resolve().parent.parent / "src" / "fonts"
out.mkdir(parents=True, exist_ok=True)

LATIN = "U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+2010-2027,U+2032-2033,U+2039-203A,U+20AC,U+2190-2193,U+2212,U+00D7"
VIET = "U+0102-0103,U+0110-0111,U+0128-0129,U+0168-0169,U+01A0-01A1,U+01AF-01B0,U+0300-0303,U+0309,U+0323,U+1EA0-1EF9"
IPA = "U+0250-02AF,U+02B0-02FF,U+0300-036F,U+03B8,U+1D00-1D7F"

def merge_and_subset(srcs, unicodes, dest):
    # fontsource splits by script; the latin-ext file already contains IPA blocks for Charis.
    opts = subset.Options(); opts.flavor = "woff2"; opts.layout_features = ["*"]; opts.name_IDs = ["*"]
    for s in srcs:
        f = TTFont(s)
        sub = subset.Subsetter(opts); sub.populate(unicodes=subset.parse_unicodes(unicodes)); sub.subset(f)
        if len(f.getGlyphOrder()) > 1:
            p = dest.with_name(dest.stem + "-" + Path(s).stem.split("-")[-3] + ".woff2")
            f.flavor = "woff2"; f.save(p); print(p.name, p.stat().st_size)

a = nm / "@fontsource-variable/atkinson-hyperlegible-next/files"
c = nm / "@fontsource/charis-sil/files"
merge_and_subset([a / "atkinson-hyperlegible-next-latin-wght-normal.woff2"], LATIN, out / "atkinson-next")
merge_and_subset([a / "atkinson-hyperlegible-next-latin-ext-wght-normal.woff2"], "U+0100-024F", out / "atkinson-next-ext")
for w in ("400", "700"):
    merge_and_subset([c / f"charis-sil-latin-{w}-normal.woff2"], LATIN, out / f"charis-{w}")
    merge_and_subset([c / f"charis-sil-latin-ext-{w}-normal.woff2"], IPA, out / f"charis-{w}-ipa")
    merge_and_subset([c / f"charis-sil-vietnamese-{w}-normal.woff2"], VIET, out / f"charis-{w}-vi")
