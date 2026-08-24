"""Collect every figure caption into results/regenerate_figures/CAPTIONS.md.

Reads the .caption.txt files that `clean_figures.write_clean()` produced. Those
files were written from each script's own caption list object, so this collector
introduces no new copy of the text - it concatenates what the figures used.

Run AFTER regenerating with --clean, otherwise it reports stale or missing
captions rather than silently emitting an out-of-date document.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIG_ROOT = ROOT / "results/regenerate_figures"
OUT_MD = FIG_ROOT / "CAPTIONS.md"
NO_CAPTION_MARKER = "(this figure has no caption drawn on the canvas)"


def main():
    originals = sorted(p for p in FIG_ROOT.glob("**/*.png")
                       if not p.name.endswith("_clean.png"))
    rows, missing, no_caption = [], [], []
    for png in originals:
        cap = png.with_name(png.stem + ".caption.txt")
        clean = png.with_name(png.stem + "_clean.png")
        if not cap.is_file():
            missing.append(png)
            continue
        lines = cap.read_text(encoding="utf-8").rstrip("\n").split("\n")
        if lines == [NO_CAPTION_MARKER]:
            no_caption.append(png)
            lines = []
        rows.append((png, clean, cap, lines))

    L = ["# Figure captions", "",
         "Every caption that was previously drawn onto a figure canvas under",
         "`results/regenerate_figures/`, collected here so it can be typeset in the",
         "document instead.", "",
         "Each entry gives the original (captioned) PNG, the caption-free `_clean.png`",
         "rendered at 0.8 textwidth / 300 dpi, and the caption text.", "",
         "**These are generated files.** They come from each script's own caption list",
         "via `clean_figures.write_clean()`, so they cannot drift from the figures. To",
         "refresh, re-run the scripts with `--clean` and then",
         "`python src/regen_2class/build_captions_md.py`.", "",
         f"{len(rows)} figures. {len(no_caption)} of them never had a caption drawn on the canvas.",
         "", "---", ""]

    for png, clean, cap, lines in rows:
        rel = png.relative_to(FIG_ROOT).as_posix()
        L.append(f"## `{rel}`")
        L.append("")
        L.append(f"- clean render: `{clean.relative_to(FIG_ROOT).as_posix()}`")
        L.append(f"- caption file: `{cap.relative_to(FIG_ROOT).as_posix()}`")
        L.append("")
        if not lines:
            L.append("> *No caption was drawn on this figure's canvas, so there is none to")
            L.append("> extract. The `_clean.png` differs from the original only in size.*")
        else:
            for ln in lines:
                L.append(f"> {ln}")
        L.append("")

    if missing:
        L += ["---", "", "## Missing", "",
              "These figures have no `.caption.txt`. Re-run their script with `--clean`.", ""]
        L += [f"- `{p.relative_to(FIG_ROOT).as_posix()}`" for p in missing] + [""]

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")
    print(f"  {len(rows)} figures collected, {len(no_caption)} with no canvas caption, "
          f"{len(missing)} missing")
    total = sum(len(l) for _, _, _, l in rows)
    print(f"  {total} caption lines total")


if __name__ == "__main__":
    main()
