#!/usr/bin/env python3
"""Validate NPY chunks and create/submit the dimuon HTCondor job set."""

import argparse
import ast
import fnmatch
import math
import re
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

import settings


CHUNK_RE = re.compile(r"^(?P<category>[A-Za-z0-9_.-]+)__chunk(?P<chunk>[0-9]{4})\.npy$")
MAX_RNG_SEED = 900_000_000


def inspect_npy(path):
    """Return (rows, columns, dtype) after validating a supported NPY file."""
    with path.open("rb") as handle:
        if handle.read(6) != b"\x93NUMPY":
            raise ValueError("not an NPY file")
        version = handle.read(2)
        if len(version) != 2:
            raise ValueError("truncated NPY version")
        major = version[0]
        if major == 1:
            raw_length = handle.read(2)
            if len(raw_length) != 2:
                raise ValueError("truncated NPY header length")
            header_length = struct.unpack("<H", raw_length)[0]
        elif major in (2, 3):
            raw_length = handle.read(4)
            if len(raw_length) != 4:
                raise ValueError("truncated NPY header length")
            header_length = struct.unpack("<I", raw_length)[0]
        else:
            raise ValueError(f"unsupported NPY version {major}.{version[1]}")
        raw_header = handle.read(header_length)
        if len(raw_header) != header_length:
            raise ValueError("truncated NPY header")
        try:
            header = ast.literal_eval(raw_header.decode("latin1"))
        except (SyntaxError, ValueError) as error:
            raise ValueError(f"invalid NPY header: {error}") from error
        payload_offset = handle.tell()

    shape = header.get("shape")
    dtype = header.get("descr")
    if not isinstance(shape, tuple) or len(shape) != 2:
        raise ValueError(f"expected a two-dimensional array, got shape {shape!r}")
    if not all(isinstance(value, int) and value >= 0 for value in shape):
        raise ValueError(f"invalid shape {shape!r}")
    if shape[0] < 1 or shape[1] < 17:
        raise ValueError(f"expected at least one row and 17 columns, got {shape!r}")
    if header.get("fortran_order") is not False:
        raise ValueError("array must be C-contiguous")
    item_sizes = {"<f4": 4, "|f4": 4, "=f4": 4, "<f8": 8, "|f8": 8, "=f8": 8}
    if dtype not in item_sizes:
        raise ValueError(f"unsupported dtype {dtype!r}; use little-endian/native float32 or float64")
    expected_size = payload_offset + shape[0] * shape[1] * item_sizes[dtype]
    if path.stat().st_size != expected_size:
        raise ValueError(f"file size does not match shape and dtype (expected {expected_size} bytes)")
    return shape[0], shape[1], dtype


def lxy_tag(value):
    return format(value, ".12g").replace("-", "m").replace(".", "p")


def matches_input_patterns(path):
    return any(fnmatch.fnmatchcase(path.name, pattern) for pattern in settings.NPY_FILENAME_PATTERNS)


def collect_inputs(arguments):
    found = []
    for argument in arguments:
        path = argument.expanduser().resolve()
        if path.is_dir():
            found.extend(candidate for candidate in sorted(path.glob("*.npy")) if matches_input_patterns(candidate))
        elif path.is_file():
            if not matches_input_patterns(path):
                raise ValueError(
                    f"input does not match NPY_FILENAME_PATTERNS {settings.NPY_FILENAME_PATTERNS!r}: {path}"
                )
            found.append(path)
        else:
            raise ValueError(f"input does not exist: {path}")
    unique = []
    seen = set()
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    if not unique:
        raise ValueError("no NPY files found")
    return unique


def validate_settings(cmssw14_src, cmssw15_src):
    if not settings.NPY_FILENAME_PATTERNS or not all(
        isinstance(pattern, str) and pattern for pattern in settings.NPY_FILENAME_PATTERNS
    ):
        raise ValueError("NPY_FILENAME_PATTERNS must contain at least one nonempty filename pattern")
    if not settings.LXY_VALUES_MM:
        raise ValueError("LXY_VALUES_MM must not be empty")
    if len(set(settings.LXY_VALUES_MM)) != len(settings.LXY_VALUES_MM):
        raise ValueError("LXY_VALUES_MM must not contain duplicates")
    for lxy in settings.LXY_VALUES_MM:
        if not isinstance(lxy, (int, float)) or not math.isfinite(lxy) or lxy < 0:
            raise ValueError(f"invalid Lxy value: {lxy!r}")
    limits = settings.MAX_CHUNKS_PER_CATEGORY_BY_LXY
    if set(limits) != set(settings.LXY_VALUES_MM):
        raise ValueError("MAX_CHUNKS_PER_CATEGORY_BY_LXY must have exactly one entry for every Lxy value")
    for lxy, limit in limits.items():
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
            raise ValueError(f"invalid per-category chunk limit for Lxy {lxy}: {limit!r}")
    if not 1 <= settings.BASE_SEED < MAX_RNG_SEED:
        raise ValueError("BASE_SEED must be in [1, 899999999]")
    if settings.RNG_SEED_STRIDE < 1:
        raise ValueError("RNG_SEED_STRIDE must be positive")
    if settings.REQUEST_CPUS < 1:
        raise ValueError("REQUEST_CPUS must be positive")
    if not settings.REQUEST_MEMORY:
        raise ValueError("REQUEST_MEMORY must not be empty")
    for name, value in (("CMSSW 14 source", cmssw14_src), ("CMSSW 15 source", cmssw15_src)):
        if not value:
            raise ValueError(
                f"{name} is not configured; use the matching --cmssw*-src option "
                "or set DIMUON_CMSSW_BASE"
            )
        release = Path(value).expanduser().resolve()
        if not release.is_dir():
            raise ValueError(f"{name} is not a directory: {release}")
        if any(character.isspace() for character in str(release)):
            raise ValueError(f"{name} must not contain whitespace: {release}")
    for name in ("MOTHER_PDG_ID", "MU_MINUS_PDG_ID", "MU_PLUS_PDG_ID"):
        if not isinstance(getattr(settings, name), int) or getattr(settings, name) == 0:
            raise ValueError(f"{name} must be a nonzero integer")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path, help="NPY chunk files or directories")
    parser.add_argument("--input-dir", type=Path, help="default NPY directory (alternative to positional inputs)")
    parser.add_argument("--cmssw14-src", type=Path, help="CMSSW_14_0_18 src directory")
    parser.add_argument("--cmssw15-src", type=Path, help="CMSSW_15_0_2 src directory")
    parser.add_argument("--dry-run", action="store_true", help="prepare files without submitting")
    parser.add_argument("--max-events", type=int, default=-1, help="maximum events per chunk; -1 means all")
    parser.add_argument(
        "--max-jobs-per-category", type=int,
        help="apply an additional per-category chunk cap to every Lxy value",
    )
    parser.add_argument("--outdir", type=Path, help="output base (default: ./condor)")
    args = parser.parse_args()

    if args.max_events == 0 or args.max_events < -1:
        parser.error("--max-events must be -1 or a positive integer")
    if args.max_jobs_per_category is not None and args.max_jobs_per_category < 1:
        parser.error("--max-jobs-per-category must be positive")

    if args.inputs and args.input_dir:
        parser.error("use positional inputs or --input-dir, not both")

    cmssw14_src = args.cmssw14_src or settings.CMSSW14_SRC
    cmssw15_src = args.cmssw15_src or settings.CMSSW15_SRC
    validate_settings(cmssw14_src, cmssw15_src)
    cmssw14_src = Path(cmssw14_src).expanduser().resolve()
    cmssw15_src = Path(cmssw15_src).expanduser().resolve()
    here = Path(__file__).resolve().parent
    outdir = (args.outdir or here / "condor").expanduser().resolve()
    if any(character.isspace() for character in str(outdir)):
        raise ValueError(f"output path must not contain whitespace: {outdir}")
    configured_input = args.input_dir or settings.DEFAULT_NPY_DIRECTORY
    if not args.inputs and not configured_input:
        parser.error("provide NPY inputs, --input-dir, or DIMUON_NPY_DIR")
    inputs = collect_inputs(args.inputs or [Path(configured_input)])

    selected = []
    counts = defaultdict(int)
    metadata = {}
    for path in inputs:
        match = CHUNK_RE.fullmatch(path.name)
        if not match:
            raise ValueError(f"invalid chunk name {path.name!r}; expected <category>__chunkNNNN.npy")
        category = match.group("category")
        try:
            metadata[path] = inspect_npy(path)
        except ValueError as error:
            raise ValueError(f"invalid input {path}: {error}") from error
        selected.append((path, category, counts[category]))
        counts[category] += 1
    if not selected:
        raise ValueError("no chunks selected")

    jobs = []
    jobs_by_lxy = defaultdict(int)
    for path, category, category_index in selected:
        rows = metadata[path][0]
        events = rows if args.max_events < 0 else min(rows, args.max_events)
        for lxy in settings.LXY_VALUES_MM:
            limit = settings.MAX_CHUNKS_PER_CATEGORY_BY_LXY[lxy]
            if args.max_jobs_per_category is not None:
                limit = args.max_jobs_per_category if limit is None else min(limit, args.max_jobs_per_category)
            if limit is not None and category_index >= limit:
                continue
            label = f"{path.stem}_lxy{lxy_tag(lxy)}"
            jobs.append((path, category, float(lxy), label, events))
            jobs_by_lxy[float(lxy)] += 1

    last_seed = settings.BASE_SEED + (len(jobs) * 5 - 1) * settings.RNG_SEED_STRIDE
    if last_seed >= MAX_RNG_SEED:
        raise ValueError(f"seed allocation exceeds {MAX_RNG_SEED - 1}; reduce jobs or RNG_SEED_STRIDE")

    logdir = outdir / "log"
    subdir = outdir / "sub"
    logdir.mkdir(parents=True, exist_ok=True)
    subdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, (path, _category, lxy, label, events) in enumerate(jobs):
        seed = settings.BASE_SEED + index * 5 * settings.RNG_SEED_STRIDE
        rows.append(" ".join(map(str, (
            path, lxy, label, events, seed, outdir,
            settings.MOTHER_PDG_ID, settings.MU_MINUS_PDG_ID, settings.MU_PLUS_PDG_ID,
            cmssw14_src, cmssw15_src, settings.RNG_SEED_STRIDE,
        ))))

    joblist = subdir / "dimuon_proton_brem_jobs.args"
    submit = subdir / "dimuon_proton_brem_jobs.sub"
    joblist.write_text("\n".join(rows) + "\n")
    submit.write_text(f"""universe = vanilla
executable = {here / 'run_condor_job.sh'}
arguments = $(input_npy) $(lxy) $(label) $(events) $(seed) $(outdir) $(mother_pdg) $(mu_minus_pdg) $(mu_plus_pdg) $(cmssw14) $(cmssw15) $(seed_stride)

output = {logdir}/job.$(Cluster).$(Process).out
error = {logdir}/job.$(Cluster).$(Process).err
log = {logdir}/job.$(Cluster).log
accounting_group = group_cms
stream_output = True
stream_error = True
should_transfer_files = NO
request_cpus = {settings.REQUEST_CPUS}
request_memory = {settings.REQUEST_MEMORY}

queue input_npy,lxy,label,events,seed,outdir,mother_pdg,mu_minus_pdg,mu_plus_pdg,cmssw14,cmssw15,seed_stride from {joblist}
""")
    print(f"Validated {len(selected)} chunks across {len(counts)} categories")
    for lxy in settings.LXY_VALUES_MM:
        print(f"Lxy {float(lxy):g} mm: {jobs_by_lxy[float(lxy)]} jobs")
    print(f"Prepared {len(jobs)} jobs in {outdir}")
    print(f"Submit file: {submit}")
    if args.dry_run:
        print(f"[DRY-RUN] condor_submit {submit}")
    else:
        subprocess.run(["condor_submit", str(submit)], check=True)


if __name__ == "__main__":
    main()
