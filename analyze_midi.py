#!/usr/bin/env python3
"""
CLI tool to analyze chords in a MIDI file and print Roman numeral analysis.

This script uses music21 to:
- Parse a MIDI file
- Detect the likely key (or use a user-specified key)
- Chordify the score to produce a harmonic reduction
- Quantize chord onsets to a grid
- Optionally de-duplicate consecutive identical Roman numerals
- Print a compact table to the terminal

Examples
--------
python3 analyze_midi.py path/to/song.mid
python3 analyze_midi.py path/to/song.mid --grid 0.5 --dedupe --show-notes
python3 analyze_midi.py path/to/song.mid --key "C major" --bpm 120
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    from music21 import chord as m21_chord
    from music21 import converter as m21_converter
    from music21 import key as m21_key
    from music21 import note as m21_note
    from music21 import roman as m21_roman
    from music21 import stream as m21_stream
    from music21 import tempo as m21_tempo
except Exception as exc:  # pragma: no cover - handled at runtime
    print("Failed to import music21. Install dependencies with: pip install -r requirements.txt", file=sys.stderr)
    raise


@dataclass
class AnalyzedChord:
    """Container for a single analyzed chord occurrence."""

    index: int
    offset_quarter: float
    roman: str  # detailed figure from music21 (e.g., V6532)
    roman_simple: str  # simplified figure (e.g., V7, V65, iv6, iv64)
    duration_quarter: float
    pitch_names: Tuple[str, ...]

    def format_row(self, bpm: Optional[float], show_notes: bool) -> str:
        """Return a formatted table row for terminal display with fixed-width columns."""
        # Columns: idx(4)  off(8)  secs(8)  RomanSimple(8)  Figure(10)  Notes
        idx_col = f"{self.index:4d}"
        off_col = f"{self.offset_quarter:8.2f}q"
        if bpm is not None and bpm > 0:
            seconds = (self.offset_quarter / (bpm / 60.0))
            secs_col = f"{seconds:8.2f}s"
        else:
            secs_col = " " * 8
        roman_simple_col = f"{self.roman_simple:>8}"
        roman_full_col = f"{self.roman:>10}"
        if show_notes:
            notes_col = ",".join(self.pitch_names)
            return f"{idx_col}  {off_col}  {secs_col}  {roman_simple_col}  {roman_full_col}  {notes_col}"
        return f"{idx_col}  {off_col}  {secs_col}  {roman_simple_col}  {roman_full_col}"


def parse_key_argument(key_text: str) -> m21_key.Key:
    """Parse a textual key specification like "C major", "A minor", or "Am"."""
    text = key_text.strip()
    try:
        # music21 can often parse simple forms like 'C', 'Am', 'C major'
        return m21_key.Key(text)
    except Exception:
        pass

    lowered = text.lower()
    if lowered.endswith("major"):
        tonic = text[:-5].strip()
        return m21_key.Key(tonic, "major")
    if lowered.endswith("minor"):
        tonic = text[:-5].strip()
        return m21_key.Key(tonic, "minor")
    if lowered.endswith("m"):
        tonic = text[:-1].strip()
        return m21_key.Key(tonic, "minor")
    return m21_key.Key(text)


def quantize_value(value: float, grid: float) -> float:
    """Round a quarterLength value to the nearest grid step."""
    if grid <= 0:
        return value
    steps = value / grid
    rounded_steps = round(steps)
    return rounded_steps * grid


def detect_key(score: m21_stream.Score) -> m21_key.Key:
    """Detect the likely key of the score using music21's analysis."""
    try:
        return score.analyze("key")
    except Exception:
        # Fallback to C major if detection fails
        return m21_key.Key("C", "major")


def chordify_and_extract(score: m21_stream.Score) -> m21_stream.Part:
    """Return a chordified reduction of the score."""
    return score.chordify()


def is_harmonic_chord(element: m21_stream.Music21Object, min_notes: int) -> bool:
    """Return True if the element is a chord-like object with sufficient notes."""
    if isinstance(element, m21_chord.Chord):
        # Filter out single tones and optionally dyads
        return len(element.pitches) >= min_notes
    return False


def roman_of_chord(ch: m21_chord.Chord, key_obj: m21_key.Key) -> Optional[str]:
    """Return the Roman numeral string for a chord within the given key."""
    try:
        rn = m21_roman.romanNumeralFromChord(ch, key_obj)
        return rn.figure
    except Exception:
        return None


def simplify_roman_figure(figure: str) -> str:
    """Return a simplified Roman figure: root/inversion only (iv, iv6, iv64, V7, V65, V43, V42).

    Keeps accidentals and case from the original figure's roman part.
    """
    if not figure:
        return figure
    # Split roman root vs trailing figures
    first_digit_idx = None
    for i, ch in enumerate(figure):
        if ch.isdigit():
            first_digit_idx = i
            break
    if first_digit_idx is None:
        roman_root = figure
        trailing = ""
    else:
        roman_root = figure[:first_digit_idx]
        trailing = figure[first_digit_idx:]

    # Normalize simplified suffix based on common inversions for triads and sevenths
    trailing_str = trailing or ""
    # Seventh chord inversions
    if "65" in trailing_str:
        suffix = "65"
    elif "43" in trailing_str:
        suffix = "43"
    elif "42" in trailing_str:
        suffix = "42"
    elif "7" in trailing_str:
        suffix = "7"
    else:
        # Triad inversions
        if "64" in trailing_str:
            suffix = "64"
        elif "6" in trailing_str:
            suffix = "6"
        else:
            suffix = ""
    return roman_root + suffix


def export_chord_midis(export_dir: Path, analyzed: List[AnalyzedChord]) -> None:
    """Write one MIDI file per chord using its pitch content and duration.

    Filenames are prefixed with the row index and simplified roman.
    """
    for entry in analyzed:
        s = m21_stream.Stream()
        # Give a neutral tempo so DAWs show reasonable seconds; not required
        s.append(m21_tempo.MetronomeMark(number=120))
        ch = m21_chord.Chord(list(entry.pitch_names))
        ch.duration.quarterLength = max(0.25, float(entry.duration_quarter))
        s.append(ch)
        fname = f"{entry.index:03d}_{entry.roman_simple.replace('/', '-')}.mid"
        out_path = export_dir / fname
        s.write("midi", fp=str(out_path))


def analyze_chords(
    midi_path: Path,
    key_override: Optional[m21_key.Key],
    grid: float,
    dedupe: bool,
    min_notes: int,
) -> Tuple[m21_key.Key, List[AnalyzedChord]]:
    """Parse the MIDI file and produce a list of analyzed chords.

    Returns the effective key and a list of analyzed chord entries.
    """
    score = m21_converter.parse(str(midi_path))

    effective_key = key_override or detect_key(score)
    reduced_part = chordify_and_extract(score)

    results: List[AnalyzedChord] = []
    last_roman: Optional[str] = None

    idx = 1
    for element in reduced_part.recurse().notesAndRests:
        if not is_harmonic_chord(element, min_notes=min_notes):
            continue

        assert isinstance(element, m21_chord.Chord)
        roman_str = roman_of_chord(element, effective_key)
        if roman_str is None:
            continue

        offset_q = float(element.offset)
        offset_q = quantize_value(offset_q, grid)
        dur_q = float(getattr(element.duration, "quarterLength", 0.0) or 0.0)
        if dur_q <= 0:
            dur_q = grid if grid and grid > 0 else 0.25

        if dedupe and last_roman == roman_str:
            continue

        pitch_names = tuple(p.nameWithOctave for p in element.pitches)
        roman_simple = simplify_roman_figure(roman_str)
        results.append(
            AnalyzedChord(
                index=idx,
                offset_quarter=offset_q,
                roman=roman_str,
                roman_simple=roman_simple,
                duration_quarter=dur_q,
                pitch_names=pitch_names,
            )
        )
        last_roman = roman_str
        idx += 1

    return effective_key, results


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze MIDI chords and print Roman numeral analysis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "midi",
        type=Path,
        help="MIDI filename or path (.mid, .midi). If not absolute, resolved relative to this script's directory",
    )
    parser.add_argument(
        "--key",
        dest="key_text",
        type=str,
        default=None,
        help="Override detected key, e.g. 'C major', 'A minor', 'Am'",
    )
    parser.add_argument(
        "--grid",
        type=float,
        default=0.25,
        help="Quantization grid in quarterLength units (1.0=quarter, 0.5=eighth, 0.25=sixteenth)",
    )
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="Collapse consecutive identical Roman numerals",
    )
    parser.add_argument(
        "--min-notes",
        type=int,
        default=3,
        help="Minimum number of notes in a chord to consider (2 allows dyads)",
    )
    # Notes are shown by default; --no-notes hides them. Keep --show-notes for clarity.
    parser.add_argument(
        "--show-notes",
        dest="show_notes",
        action="store_true",
        default=True,
        help="Show pitch names for each chord (default)",
    )
    parser.add_argument(
        "--no-notes",
        dest="show_notes",
        action="store_false",
        help="Hide pitch names",
    )
    parser.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="Optional tempo to derive seconds for onsets (affects display only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of printed chords",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    midi_path: Path = args.midi
    if not midi_path.is_absolute():
        candidate = (script_dir / midi_path).resolve()
        if candidate.exists():
            midi_path = candidate
    if not midi_path.exists():
        print(
            f"MIDI file not found: {args.midi}. Looked relative to script dir: {script_dir}",
            file=sys.stderr,
        )
        return 1

    key_override: Optional[m21_key.Key] = None
    if args.key_text:
        try:
            key_override = parse_key_argument(args.key_text)
        except Exception as exc:
            print(f"Failed to parse --key '{args.key_text}': {exc}", file=sys.stderr)
            return 1

    try:
        effective_key, analyzed = analyze_chords(
            midi_path=midi_path,
            key_override=key_override,
            grid=float(args.grid),
            dedupe=bool(args.dedupe),
            min_notes=int(args.min_notes),
        )
    except Exception as exc:
        print(f"Failed to analyze MIDI: {exc}", file=sys.stderr)
        return 1

    # Export per-chord MIDI files next to the input by default
    try:
        export_dir = midi_path.parent / f"{midi_path.stem}_chords"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_chord_midis(export_dir, analyzed)
    except Exception as exc:
        print(f"Warning: failed exporting per-chord MIDIs: {exc}", file=sys.stderr)

    header_left = f"File: {midi_path.name}"
    header_right = f"Key: {effective_key.tonic.name} {effective_key.mode}"
    print(header_left + " " * max(1, 100 - len(header_left) - len(header_right)) + header_right)
    # Align columns with format_row(): idx(4) off(8) secs(8) RomanSimple(8) Figure(10) Notes
    header_cols = [
        f"{'Index':>4}",
        f"{'Offset(q)':>8}",
        f"{'Secs':>8}",
        f"{'Roman':>8}",
        f"{'Figure':>10}",
    ]
    header_line = "  ".join(header_cols) + ("  Notes" if args.show_notes else "")
    print(header_line)
    print("-" * 100)

    count = 0
    for entry in analyzed:
        print(entry.format_row(bpm=args.bpm, show_notes=bool(args.show_notes)))
        count += 1
        if args.limit is not None and count >= int(args.limit):
            break

    if count == 0:
        print("No chords found with the current settings.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())


