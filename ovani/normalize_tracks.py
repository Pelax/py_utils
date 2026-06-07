#!/usr/bin/env python3
"""
Recursively loudness-normalize audio tracks in a folder.

Requires ffmpeg to be installed and available on PATH.
Uses ffmpeg's loudnorm filter (EBU R128) so all tracks have the same
perceived loudness instead of the same peak level.

INTENSITY GROUPS:
Tracks are grouped by name when they follow the pattern:
    <name> Intensity 1
    <name> Intensity 2
    <name> Main

For each group, only the *Main* track is analyzed. The exact same
loudnorm correction is then applied to all three intensities, preserving
their relative volume differences while bringing every group's Main
track to the target loudness.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tqdm import tqdm

# Supported audio formats via ffmpeg
SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".aiff", ".opus"}

# Intensity suffixes used to identify grouped tracks (before file extension)
_INTENSITY_SUFFIXES = {
    " Intensity 1": "intensity 1",
    " Intensity 2": "intensity 2",
    " Main": "main",
}


def _loudnorm_filter(target_i: float, true_peak: float, lra: float) -> str:
    """Build the ffmpeg loudnorm filter string (analysis / one-pass)."""
    return f"loudnorm=I={target_i}:TP={true_peak}:LRA={lra}"


def _loudnorm_filter_measured(
    target_i: float,
    true_peak: float,
    lra: float,
    measured: dict[str, str],
) -> str:
    """Build the ffmpeg loudnorm filter string using pre-measured values."""
    return (
        f"loudnorm=I={target_i}:TP={true_peak}:LRA={lra}"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
    )


def analyze_loudnorm(
    path: Path,
    target_i: float,
    true_peak: float,
    lra: float,
) -> dict[str, str]:
    """Run loudnorm in analysis mode and return the measured JSON."""
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "info",
        "-i", str(path),
        "-af", f"{_loudnorm_filter(target_i, true_peak, lra)}:print_format=json",
        "-f", "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg analysis failed")

    # loudnorm prints JSON to stderr; grab the block containing "target_offset"
    match = re.search(r'\{.*"target_offset".*?\}', result.stderr, re.DOTALL)
    if not match:
        raise RuntimeError("Could not parse loudnorm analysis output")
    return json.loads(match.group())


def _run_ffmpeg(
    input_path: Path,
    output_path: Path,
    target_i: float,
    true_peak: float,
    lra: float,
    measured: dict[str, str] | None = None,
) -> None:
    """Shell out to ffmpeg with the loudnorm filter."""
    if measured is None:
        af = _loudnorm_filter(target_i, true_peak, lra)
    else:
        af = _loudnorm_filter_measured(target_i, true_peak, lra, measured)

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(input_path),
        "-af", af,
        "-q:a", "0",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")


def normalize_audio(
    input_path: Path,
    output_path: Path,
    target_i: float,
    true_peak: float,
    lra: float,
    measured: dict[str, str] | None = None,
) -> None:
    """Normalize a single audio file to target integrated loudness (LUFS)."""
    inplace = output_path.resolve() == input_path.resolve()

    if inplace:
        suffix = output_path.suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _run_ffmpeg(input_path, tmp_path, target_i, true_peak, lra, measured)
            tmp_path.replace(output_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _run_ffmpeg(input_path, output_path, target_i, true_peak, lra, measured)


def _resolve_output_path(
    input_path: Path,
    root: Path,
    output_root: Path | None,
    overwrite: bool,
) -> Path:
    """Determine where the normalized file should be written."""
    if output_root is not None:
        rel = input_path.relative_to(root)
        return output_root / rel
    elif overwrite:
        return input_path
    else:
        return input_path.with_stem(f"{input_path.stem}_normalized")


def _parse_intensity_stem(stem: str) -> tuple[str, str] | None:
    """
    If *stem* ends with an intensity suffix, return (group_key, intensity_label).
    Otherwise return None.
    """
    for suffix, label in _INTENSITY_SUFFIXES.items():
        if stem.endswith(suffix):
            return stem[: -len(suffix)], label
    return None


def _group_files(
    files: list[Path],
) -> tuple[dict[str, dict[str, Path]], list[Path]]:
    """
    Separate files into intensity groups and standalone singles.

    Returns (groups, singles) where groups is {group_key: {label: path}}.
    """
    groups: dict[str, dict[str, Path]] = {}
    singles: list[Path] = []

    for path in files:
        parsed = _parse_intensity_stem(path.stem)
        if parsed is None:
            singles.append(path)
            continue

        key, label = parsed
        groups.setdefault(key, {})[label] = path

    return groups, singles


def normalize_folder(
    root: Path,
    output_root: Path | None,
    target_i: float,
    true_peak: float,
    lra: float,
    overwrite: bool,
    supported_extensions: set[str],
) -> tuple[list[Path], list[tuple[Path, Exception]]]:
    """
    Recursively loudness-normalize audio files under *root*.

    Files belonging to intensity groups are processed together so that
    all three variants receive the exact same loudnorm correction.
    """
    # 1. Collect all matching files
    files = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in supported_extensions
    ]

    # 2. Group by track name
    groups, singles = _group_files(files)

    succeeded: list[Path] = []
    failed: list[tuple[Path, Exception]] = []

    # 3. Build flat task list for tqdm
    total = sum(len(members) for members in groups.values()) + len(singles)
    pbar = tqdm(total=total, desc="Normalizing", unit="file")

    # 4. Process groups
    for key, members in groups.items():
        main_path = members.get("main")
        if main_path is None:
            # No main found – fall back to individual processing
            for label, path in members.items():
                out_path = _resolve_output_path(path, root, output_root, overwrite)
                try:
                    normalize_audio(path, out_path, target_i, true_peak, lra)
                    succeeded.append(path)
                except Exception as exc:
                    failed.append((path, exc))
                pbar.update(1)
            continue

        try:
            measured = analyze_loudnorm(main_path, target_i, true_peak, lra)
        except Exception as exc:
            for label, path in members.items():
                failed.append((path, exc))
                pbar.update(1)
            continue

        # Apply the same measured correction to every member
        for label, path in members.items():
            out_path = _resolve_output_path(path, root, output_root, overwrite)
            try:
                normalize_audio(path, out_path, target_i, true_peak, lra, measured)
                succeeded.append(path)
            except Exception as exc:
                failed.append((path, exc))
            pbar.update(1)

    # 5. Process standalone singles individually
    for path in singles:
        out_path = _resolve_output_path(path, root, output_root, overwrite)
        try:
            normalize_audio(path, out_path, target_i, true_peak, lra)
            succeeded.append(path)
        except Exception as exc:
            failed.append((path, exc))
        pbar.update(1)

    pbar.close()
    return succeeded, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recursively loudness-normalize audio tracks using ffmpeg."
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=Path("."),
        help="Root folder to scan for audio files (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output folder. If omitted, files are overwritten in-place unless --no-overwrite is set.",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="When --output is not given, write normalized files next to originals with a '_normalized' suffix.",
    )
    parser.add_argument(
        "-t", "--target",
        type=float,
        default=-14.0,
        help="Target integrated loudness in LUFS (default: -14.0). Common streaming target.",
    )
    parser.add_argument(
        "--true-peak",
        type=float,
        default=-1.0,
        help="Maximum true peak in dBTP (default: -1.0)",
    )
    parser.add_argument(
        "--lra",
        type=float,
        default=11.0,
        help="Loudness range target in LU (default: 11.0)",
    )
    parser.add_argument(
        "--formats",
        type=str,
        default=",".join(sorted(SUPPORTED_EXTENSIONS)),
        help="Comma-separated list of extensions to process (default: all supported).",
    )
    args = parser.parse_args(argv)

    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg not found on PATH. Install it first.", file=sys.stderr)
        return 1

    root: Path = args.input.resolve()
    if not root.exists():
        print(f"Error: input folder does not exist: {root}", file=sys.stderr)
        return 1

    output_root: Path | None = args.output.resolve() if args.output else None
    overwrite: bool = not args.no_overwrite and output_root is None

    supported_extensions = {ext.strip().lower() for ext in args.formats.split(",")}
    if not all(ext.startswith(".") for ext in supported_extensions):
        print("Error: all formats must start with a dot, e.g. '.wav,.mp3'", file=sys.stderr)
        return 1

    print(f"Scanning: {root}")
    if output_root:
        print(f"Output:   {output_root}")
    elif overwrite:
        print("Mode:     overwrite in-place")
    else:
        print("Mode:     write '_normalized' siblings")
    print(f"Target:   {args.target} LUFS")
    print()

    succeeded, failed = normalize_folder(
        root, output_root, args.target, args.true_peak, args.lra, overwrite, supported_extensions
    )

    print(f"Processed: {len(succeeded)} file(s)")
    if failed:
        print(f"Failed:    {len(failed)} file(s)")
        for path, exc in failed:
            print(f"  - {path}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
