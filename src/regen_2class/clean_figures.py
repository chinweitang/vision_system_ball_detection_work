"""Shared `--clean` support: caption off the canvas, into a sibling text file.

Every figure script in this folder bakes its caption onto the canvas with
fig.text(). That is right for a working figure and wrong for a report, where the
caption belongs in the document so it can be typeset, numbered and referenced.

This module lets each script grow a `--clean` flag WITHOUT duplicating its
caption anywhere. The script keeps its single caption list; in clean mode that
same list object is handed to `write_clean()` instead of being drawn. Because
there is only ever one list, the text file cannot drift from the figure - not by
discipline, but because there is nothing to keep in sync.

The wrap at each call site is three lines:

    if CF.clean():
        CF.write_clean(fig, caption, OUT_PNG)
    else:
        <the existing caption-drawing + tight_layout + savefig block, unchanged>

DEFAULT BEHAVIOUR IS UNTOUCHED. Without --clean the else-branch runs exactly the
code that ran before, so every existing PNG stays byte-identical. Only the
indentation of that block changes.

Outputs, for a figure whose captioned version is <dir>/<name>.png:
    <dir>/<name>_clean.png     no caption on the canvas, 0.8 textwidth, 300 dpi
    <dir>/<name>.caption.txt   the caption, one line per source line

WIDTH: 0.8 textwidth is taken as 6.6 in, the convention already established in
step17_print_size_figures.py ("0.8 x A4 width (210 mm)"). A LaTeX \\textwidth is
narrower than the paper width, so if the document's real \\textwidth is known,
override it with CLEAN_WIDTH_IN or the width_in argument.
"""
import os
import pathlib
import sys

# 0.8 x A4 paper width (210 mm = 8.268 in). Override with the environment
# variable if the document's real \textwidth is known.
CLEAN_WIDTH_IN = float(os.environ.get("CLEAN_WIDTH_IN", "6.6"))
CLEAN_DPI = int(os.environ.get("CLEAN_DPI", "300"))

# Every caption written this run: {absolute png path: [lines]}. Collected so
# CAPTIONS.md can be built from the same objects the figures used.
RECORDED = {}

# Written into .caption.txt for figures that never drew a caption on the canvas.
NO_CAPTION_MARKER = "(this figure has no caption drawn on the canvas)"

_FLAGS = ("--clean", "--no-caption")


def clean() -> bool:
    """True when the caller was invoked with --clean (or --no-caption)."""
    return any(f in sys.argv for f in _FLAGS)


def _paths(out_png):
    p = pathlib.Path(out_png)
    return (p.with_name(p.stem + "_clean.png"),
            p.with_name(p.stem + ".caption.txt"))


def write_clean(fig, caption, out_png, width_in=None, height_in=None,
                facecolor=None, dpi=None, rect=(0, 0, 1, 1)):
    """Save the figure with NO caption drawn, and the caption beside it.

    `caption` is the script's own list - it is never re-typed here, only
    written out. Blank entries are dropped: several scripts build a caption with
    a conditional empty string in it, which would otherwise become a stray blank
    line in the text file.

    The figure is re-sized to the clean width. Height defaults to whatever the
    figure already has minus nothing - the space the caption used to occupy is
    reclaimed by tight_layout, so the axes simply get larger.
    """
    clean_png, caption_txt = _paths(out_png)
    lines = [str(l) for l in caption if str(l).strip()]

    w = width_in if width_in is not None else CLEAN_WIDTH_IN
    h = height_in if height_in is not None else fig.get_size_inches()[1]
    fig.set_size_inches(w, h)
    try:
        fig.tight_layout(rect=list(rect))
    except Exception:
        # a few figures use constrained/manual layouts that reject tight_layout;
        # the caption is still omitted and the file still written
        pass

    kw = {"dpi": dpi if dpi is not None else CLEAN_DPI}
    if facecolor is not None:
        kw["facecolor"] = facecolor
    elif fig.get_facecolor() is not None:
        kw["facecolor"] = fig.get_facecolor()
    clean_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(clean_png, **kw)

    # A few figures (step17's print set, step14) never drew a caption at all.
    # Writing a zero-byte file for those reads as "the caption is missing";
    # saying so explicitly reads as "there was never one to extract".
    body = ("\n".join(lines) if lines else NO_CAPTION_MARKER) + "\n"
    caption_txt.write_text(body, encoding="utf-8")
    RECORDED[str(pathlib.Path(out_png).resolve())] = lines

    print(f"  [clean] wrote {clean_png}")
    print(f"  [clean] wrote {caption_txt}  "
          + (f"({len(lines)} line(s))" if lines else "(no caption on canvas)"))
    return clean_png, caption_txt


def close(fig):
    """Convenience so call sites can close in either branch."""
    import matplotlib.pyplot as plt
    plt.close(fig)
