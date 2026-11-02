#!/usr/bin/env python3
"""Split background arrays without modifying sources; validate chunks on reuse."""
import argparse
import csv
import fnmatch
from collections import defaultdict
import os
from pathlib import Path
import numpy as np
import settings
from prepare_jobs import inspect_npy


def split_sources(source, output, chunk_rows=1000, dry_run=False, max_chunks_per_category=None, max_chunks_per_source=None, category_patterns=None):
    if chunk_rows < 1:
        raise ValueError("chunk_rows must be positive")
    if max_chunks_per_category is not None and max_chunks_per_category < 1:
        raise ValueError("max_chunks_per_category must be positive")
    if max_chunks_per_source is not None and max_chunks_per_source < 1:
        raise ValueError("max_chunks_per_source must be positive")
    selected_by_category = defaultdict(int)
    source, output = Path(source).resolve(), Path(output).resolve()
    if (source == output or output in source.parents
            or (source in output.parents and output != source / "chunks")):
        raise ValueError("output must be source/chunks or a separate directory outside the source tree")
    patterns = ["*"] if category_patterns is None else category_patterns
    paths = sorted(path for path in source.glob("*/*.npy")
                   if path.parent != source / "chunks" and output not in path.parents
                   if any(fnmatch.fnmatchcase(path.parent.name, pattern) for pattern in patterns))
    if not paths:
        raise ValueError(f"no background NPY files found in {source}")
    total_rows = total_chunks = empty = 0
    if not dry_run:
        output.mkdir(parents=True, exist_ok=True)
    manifest = None
    try:
        if not dry_run:
            # Keep the last complete manifest until the entire run succeeds.
            manifest = (output / "npy_chunks_manifest.csv.part").open("w", newline="")
            writer = csv.writer(manifest)
            writer.writerow(["source", "output", "row_start", "row_stop", "source_rows"])
        for index, path in enumerate(paths):
            category = path.parent.name
            if max_chunks_per_category is not None and selected_by_category[category] >= max_chunks_per_category:
                continue
            rows, _, _ = inspect_npy(path, "background", allow_empty=True)
            full_count = (rows + chunk_rows - 1) // chunk_rows
            count = full_count if max_chunks_per_source is None else min(full_count, max_chunks_per_source)
            if max_chunks_per_category is not None:
                count = min(count, max_chunks_per_category - selected_by_category[category])
            selected_rows = min(rows, count * chunk_rows)
            total_rows += selected_rows
            total_chunks += count
            selected_by_category[category] += count
            if not rows:
                empty += 1
                if manifest:
                    writer.writerow([str(path), "", 0, 0, 0])
                continue
            if dry_run:
                continue
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            destination = output / path.parent.name / path.stem
            destination.mkdir(parents=True, exist_ok=True)
            expected_names = {f"Events_{i}.npy" for i in range(full_count)}
            if any(p.name not in expected_names for p in destination.glob("Events_*.npy")):
                raise ValueError(f"unexpected chunks in {destination}; chunk size may have changed")
            for chunk, start in enumerate(range(0, selected_rows, chunk_rows)):
                stop = min(rows, start + chunk_rows)
                target = destination / f"Events_{chunk}.npy"
                data = array[start:stop]
                if target.exists():
                    existing = np.load(target, allow_pickle=False)
                    if (existing.shape != data.shape or existing.dtype != data.dtype
                            or existing.tobytes() != data.tobytes()):
                        raise ValueError(f"conflicting existing chunk: {target}")
                else:
                    temporary = target.with_name(target.name + f".part.{os.getpid()}")
                    try:
                        with temporary.open("xb") as handle:
                            np.save(handle, data, allow_pickle=False)
                        existing = np.load(temporary, allow_pickle=False)
                        if existing.dtype != data.dtype or existing.shape != data.shape or existing.tobytes() != data.tobytes():
                            raise ValueError(f"chunk verification failed: {temporary}")
                        # Publish without overwriting a concurrently created chunk.
                        os.link(temporary, target)
                    finally:
                        temporary.unlink(missing_ok=True)
                writer.writerow([str(path), str(target), start, stop, rows])
            del array
            manifest.flush()
            print(f"[{index + 1}/{len(paths)}] {path.parent.name}/{path.name}: {rows} rows, {count} chunks", flush=True)
    finally:
        if manifest:
            manifest.close()
    if not dry_run:
        (output / "npy_chunks_manifest.csv.part").replace(output / "npy_chunks_manifest.csv")
    summary = dict(files=len(paths), empty=empty, rows=total_rows, chunks=total_chunks)
    print(summary, flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(settings.BACKGROUND["source_directory"]))
    parser.add_argument("--output", type=Path, default=Path(settings.BACKGROUND["npy_directory"]))
    parser.add_argument("--chunk-rows", type=int, default=settings.BACKGROUND["chunk_rows"])
    parser.add_argument("--category", action="append", help="category glob; repeat to select multiple (default from settings.BACKGROUND)")
    parser.add_argument("--max-chunks-per-source", type=int, default=settings.BACKGROUND["max_chunks_per_source"], help="maximum chunks from each original NPY (default from settings)")
    parser.add_argument("--max-chunks-per-category", type=int, help="prepare only this many chunks per category, in sorted source order")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    split_sources(args.source, args.output, args.chunk_rows, args.dry_run, args.max_chunks_per_category,
                  args.max_chunks_per_source, args.category or settings.BACKGROUND["category_patterns"])


if __name__ == "__main__":
    main()
