## MIDI Chord Analysis CLI

Analyze chords from a MIDI file and print Roman numeral analysis to the terminal. Built with `music21`.

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage

```bash
# If your MIDI is in the same folder as this script, you can pass just the filename
python3 analyze_midi.py song.mid

# Absolute paths also work
python3 analyze_midi.py /absolute/path/to/song.mid
```

Options:

- `--key` Override detected key, e.g. `"C major"`, `"A minor"`, `"Am"`.
- `--grid` Quantization grid in quarterLength (1.0=quarter, 0.5=eighth, 0.25=sixteenth). Default: `0.25`.
- `--dedupe` Collapse consecutive identical Roman numerals.
- `--min-notes` Minimum notes per chord (default `3`; set `2` to allow dyads).
- `--show-notes` Show pitch names for each chord (default on).
- `--no-notes` Hide pitch names.
- `--bpm` Tempo to compute seconds for onsets (display only).
- `--limit` Limit number of printed rows.

By default, if you pass a non-absolute path, the script resolves it relative to the script's directory. This makes it easy when the MIDI file sits next to `analyze_midi.py`.

### Examples

```bash
python3 analyze_midi.py examples/song.mid --grid 0.5 --dedupe --show-notes
python3 analyze_midi.py path/to/song.mid --key "C major" --bpm 120
```

### Notes

- Detected key uses `music21`'s built-in analysis. Provide `--key` if you want to force a specific key.
- Onset times are shown in quarter lengths; seconds are calculated only if `--bpm` is provided.

### Roman output columns

The output shows two Roman-related columns by default:

- Roman: a simplified figure (e.g., `iv`, `iv6`, `iv64`, `V7`, `V65`, `V43`, `V42`).
- Figure: the detailed figure from `music21` (may include additional suspensions like `532`).

Additional columns:

- Inversion: human-readable inversion label (`root`, `1st`, `2nd`, `3rd`).
- Function: brief function classification (`Tonic`, `Predominant`, `Dominant`, `Secondary ...`, or `Chromatic`).

### MIDI exports

- Per-chord: the script writes a separate MIDI file for each detected chord into a folder named `<input_stem>_chords` next to your input file. Files are named `<input_stem>-<order>-<chord-name>.mid` (e.g., `song-01-V7.mid`) where `<order>` is zero-padded to two digits based on the chord's appearance order. Each file contains the chord’s notes with the duration taken from the chordified reduction.
- Text only: a human-readable table is saved as `<input_stem>_chord_infos.txt` alongside your input file. This mirrors the terminal output for easy sharing. The combined `_chord_infos.mid` export has been removed.

