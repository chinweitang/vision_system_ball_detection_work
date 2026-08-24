"""One-off migration: split derived results out of data/ into results/.

Raw captures stay in data/ and stay gitignored. Derived results move to results/
so they can be version-controlled.

    python src/migrate_results_tree.py            # dry run, changes nothing
    python src/migrate_results_tree.py --apply    # perform the move
    python src/migrate_results_tree.py --paths    # rewrite script paths only
    python src/migrate_results_tree.py --verify   # post-move consistency check

WHY contact_sheets IS EXCLUDED
data/detector_tuning/contact_sheets is 19.7 GB across 692 files. It is gitignored
either way, and this repo lives on OneDrive, where moving it would very likely be
seen as delete-plus-recreate and re-uploaded in full. So detector_tuning is moved
child by child with that one subfolder left behind, rather than as a whole.

That split is the only reason this file is more than a shutil.move loop: after the
move, `data/detector_tuning/contact_sheets/...` is still a live path and must NOT
be rewritten to results/, while every other data/detector_tuning/... path must be.
"""
import argparse
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"

# Folders that move wholesale from data/ to results/.
MOVE_WHOLE = [
    "flight_binning",
    "pi_benchmarking",
    "prediction",
    "regenerate_figures",
    "sync_correction_validation",
    "sync_correction_validation_tuned_detections",
    "trajectory_fit_comparison",
    "final_point_labels",
    "tmp_pipeline_sweep_detections",
]

# Moves child by child, leaving KEEP_BEHIND in data/.
MOVE_PARTIAL = {"detector_tuning": ["contact_sheets"]}

# Paths that must stay pointing at data/ after the rewrite.
KEEP_DATA_PREFIXES = ["data/detector_tuning/contact_sheets"]

# Paths DERIVED from a moved folder that must still resolve under data/.
#
# Three scripts build the contact-sheet directory as
#     CONTACT_SHEETS_DIR = DETECTOR_TUNING_DIR / "contact_sheets" / STAGE
# Once DETECTOR_TUNING_DIR points at results/, that expression silently retargets
# to results/detector_tuning/contact_sheets - so the next full-dataset run would
# start writing a SECOND 19.7 GB of contact sheets inside the git-tracked tree.
# Pinning the base to data/ explicitly is the fix; a .gitignore rule alone would
# stop the commit but not the disk usage.
DERIVED_FIXUPS = [
    ('DETECTOR_TUNING_DIR / "contact_sheets"',
     'REPO_ROOT / "data" / "detector_tuning" / "contact_sheets"'),
]

SCRIPT_GLOBS = ["**/*.py", "**/*.ps1"]
# claude/ is deliberately excluded: worklogs and prompts record paths that were
# correct when written, and rewriting them would falsify the record.
SCRIPT_ROOT = ROOT / "src"


def moved_names():
    return MOVE_WHOLE + list(MOVE_PARTIAL)


def plan_moves():
    """(src, dst, kind) triples. Nothing is touched here."""
    out = []
    for name in MOVE_WHOLE:
        s = DATA / name
        if s.is_dir():
            out.append((s, RESULTS / name, "whole"))
    for name, keep in MOVE_PARTIAL.items():
        s = DATA / name
        if not s.is_dir():
            continue
        for child in sorted(s.iterdir()):
            if child.name in keep:
                out.append((child, None, "KEEP IN data/"))
            else:
                out.append((child, RESULTS / name / child.name, "child"))
    return out


def do_moves(apply):
    plan = plan_moves()
    if not plan:
        print("nothing to move - has this already run?")
        return
    print(f"{'action':<14} {'from':<62} -> to")
    for s, d, kind in plan:
        rel_s = s.relative_to(ROOT).as_posix()
        if d is None:
            print(f"{'skip':<14} {rel_s:<62}    (left in place, gitignored)")
            continue
        rel_d = d.relative_to(ROOT).as_posix()
        if d.exists():
            print(f"{'EXISTS':<14} {rel_s:<62} -> {rel_d}   ** destination already "
                  f"present, skipping **")
            continue
        print(f"{kind:<14} {rel_s:<62} -> {rel_d}")
        if apply:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
    if apply:
        print("\nmoves applied")
    else:
        print("\nDRY RUN - nothing moved. Re-run with --apply.")


def _segmented_re(name):
    """Matches  "data" / "<name>"  with either quote style and any spacing.

    Anchoring on "data" IMMEDIATELY before the folder name is what keeps
    `"data" / session` and `"data" / "2026_07_15_gym" / "flight_binning"`
    untouched - flight_binning exists BOTH as a top-level results folder (moves)
    and as a per-session subfolder (stays), and only this anchor tells them
    apart.
    """
    return re.compile(r'(["\'])data\1(\s*/\s*)(["\'])' + re.escape(name) + r'\3')


def rewrite_paths(apply):
    """data/<moved> -> results/<moved> in scripts.

    Handles BOTH idioms, because this repo uses both:
      literal    "data/detector_tuning"  /  "data\\detector_tuning"
      segmented  REPO_ROOT / "data" / "detector_tuning"

    The segmented form is the dominant one and carries the actual runtime
    paths; the literal form is mostly docstrings plus the Pi staging script.
    Rewriting only the literal form would move the folders while leaving every
    real path pointing at data/.

    KEEP_DATA_PREFIXES are restored afterwards so the contact_sheets path that
    legitimately still lives under data/ survives the blanket rewrite.
    """
    names = moved_names()
    seg = [(n, _segmented_re(n)) for n in names]
    files = sorted({p for g in SCRIPT_GLOBS for p in SCRIPT_ROOT.glob(g)
                    if "__pycache__" not in p.parts
                    # this file describes the migration in its own docstring;
                    # rewriting itself would mangle that explanation
                    and p.resolve() != pathlib.Path(__file__).resolve()})
    changed = []
    for p in files:
        try:
            txt = orig = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        n_seg = n_lit = 0
        for n, rx in seg:
            txt, k = rx.subn(lambda m: f'{m.group(1)}results{m.group(1)}'
                                       f'{m.group(2)}{m.group(3)}{n}{m.group(3)}', txt)
            n_seg += k
        for n in names:
            for a, b in ((f"data/{n}", f"results/{n}"),
                         (f"data\\\\{n}", f"results\\\\{n}"),
                         (f"data\\{n}", f"results\\{n}")):
                n_lit += txt.count(a)
                txt = txt.replace(a, b)
        for keep in KEEP_DATA_PREFIXES:
            r = keep.replace("data/", "results/", 1)
            txt = txt.replace(r, keep)
            txt = txt.replace(r.replace("/", "\\\\"), keep.replace("/", "\\\\"))
            txt = txt.replace(r.replace("/", "\\"), keep.replace("/", "\\"))
            # segmented form of the same keep-path
            txt = re.sub(r'(["\'])results\1(\s*/\s*)(["\'])detector_tuning\3'
                         r'(\s*/\s*)(["\'])contact_sheets\5',
                         lambda m: f'{m.group(1)}data{m.group(1)}{m.group(2)}'
                                   f'{m.group(3)}detector_tuning{m.group(3)}'
                                   f'{m.group(4)}{m.group(5)}contact_sheets{m.group(5)}',
                         txt)
        n_der = 0
        for a, b in DERIVED_FIXUPS:
            n_der += txt.count(a)
            txt = txt.replace(a, b)
        if txt != orig:
            changed.append((p, n_seg, n_lit, n_der))
            if apply:
                p.write_text(txt, encoding="utf-8")
    print(f"{'seg':>5} {'lit':>5} {'der':>5}  file")
    for p, s, l, dv in changed:
        print(f"{s:>5} {l:>5} {dv:>5}  {p.relative_to(ROOT).as_posix()}")
    print(f"\n{len(changed)} file(s) {'rewritten' if apply else 'would change'} - "
          f"{sum(s for _, s, _, _ in changed)} segmented, "
          f"{sum(l for _, _, l, _ in changed)} literal, "
          f"{sum(dv for _, _, _, dv in changed)} derived")
    if not apply:
        print("DRY RUN - nothing written. Re-run with --paths --apply.")


def verify():
    """Post-move consistency: no script should still point at a moved folder,
    and the contact_sheets path must still resolve under data/."""
    names = moved_names()
    files = sorted({p for g in SCRIPT_GLOBS for p in SCRIPT_ROOT.glob(g)
                    if "__pycache__" not in p.parts})
    stale = []
    for p in files:
        if p.resolve() == pathlib.Path(__file__).resolve():
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        # Checked LINE BY LINE. An earlier version excused the whole FILE if
        # contact_sheets appeared anywhere in it, which hid a genuine stale
        # data/detector_tuning/mask_overlays path in a file that also wrote
        # contact sheets. Only the individual line may be excused.
        for i, line in enumerate(lines, 1):
            if "contact_sheets" in line:
                continue
            for n in names:
                seg = re.search(r'["\']data["\']\s*/\s*["\']' + re.escape(n) + r'["\']',
                                line)
                lit = any(pat in line for pat in
                          (f"data/{n}", "data\\" + n, "data\\\\" + n))
                if seg or lit:
                    stale.append((p.relative_to(ROOT).as_posix(), i, line.strip()[:70]))
    print("--- stale data/ references in scripts ---")
    if stale:
        for f, ln, src in sorted(set(stale)):
            print(f"  {f}:{ln}  {src}")
    else:
        print("  none")

    print("\n--- destinations present ---")
    for n in names:
        d = RESULTS / n
        print(f"  {'OK ' if d.is_dir() else 'MISSING':<8} results/{n}")
    cs = DATA / "detector_tuning" / "contact_sheets"
    print(f"  {'OK ' if cs.is_dir() else 'MISSING':<8} "
          f"data/detector_tuning/contact_sheets  (intentionally left behind)")

    print("\n--- leftovers under data/ that were supposed to move ---")
    left = [n for n in MOVE_WHOLE if (DATA / n).exists()]
    dt = DATA / "detector_tuning"
    if dt.is_dir():
        extra = [c.name for c in dt.iterdir()
                 if c.name not in MOVE_PARTIAL["detector_tuning"]]
        if extra:
            left += [f"detector_tuning/{e}" for e in extra]
    print("  none" if not left else "\n".join(f"  {x}" for x in left))
    return not stale and not left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually make changes")
    ap.add_argument("--paths", action="store_true", help="rewrite script paths")
    ap.add_argument("--verify", action="store_true", help="post-move check")
    a = ap.parse_args()
    if a.verify:
        sys.exit(0 if verify() else 1)
    if a.paths:
        rewrite_paths(a.apply)
    else:
        do_moves(a.apply)


if __name__ == "__main__":
    main()
