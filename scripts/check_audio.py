#!/usr/bin/env python3
"""Optional full Vorbis decode check: pip install soundfile (not needed to build)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        print("Optional audio check requires: python -m pip install soundfile", file=sys.stderr)
        return 1
    paths = sorted((ROOT / "music").rglob("*.ogg"))
    total_seconds = 0.0
    errors = []
    for path in paths:
        try:
            with sf.SoundFile(path) as audio:
                if audio.samplerate != 44100 or audio.channels != 2 or audio.subtype != "VORBIS":
                    raise ValueError("Expected stereo 44100 Hz Vorbis")
                frames = 0
                for samples in audio.blocks(blocksize=65536, dtype="float32"):
                    if not np.isfinite(samples).all():
                        raise ValueError("Non-finite decoded samples")
                    frames += len(samples)
                if frames == 0 or frames != audio.frames:
                    raise ValueError("Incomplete or empty audio decode")
                seconds = frames / audio.samplerate
                total_seconds += seconds
                print(f"OK  {path.name}: {seconds:.2f} s, stereo 44100 Hz")
        except (OSError, RuntimeError, ValueError) as error:
            errors.append(f"{path.name}: {error}")
    if len(paths) != 23:
        errors.append(f"Expected 23 tracks, got {len(paths)}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: fully decoded {len(paths)} tracks, {total_seconds / 60:.1f} minutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
