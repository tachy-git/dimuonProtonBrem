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
from typing import NamedTuple

import settings


CHUNK_RE = re.compile(r"^Events_(?P<chunk>[0-9]+)\.npy$")
CATEGORY_RE = re.compile(r"^(?:barrel|endcap)_m_[0-9.eE+\-]+_GeV$")
MAX_RNG_SEED = 900_000_000
NPY_ITEM_SIZES = {"<f4": 4, "|f4": 4, "=f4": 4, "<f8": 8, "|f8": 8, "=f8": 8}


class InputChunk(NamedTuple):
    path: Path
    category: str
    chunk: int
    category_index: int
    rows: int


class Job(NamedTuple):
    path: Path
    category: str
    lxy: float
    label: str
    events: int


def chunk_limit(configured, additional):
    if additional is None:
        return configured
    return additional if configured is None else min(configured, additional)


def inspect_npy(path, sample_type="signal", allow_empty=False):
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
    columns = 13 if sample_type == "background" else 17
    if (not allow_empty and shape[0] < 1) or shape[1] < columns:
        raise ValueError(f"expected {columns} columns and a nonempty array, got {shape!r}")
    if header.get("fortran_order") is not False:
        raise ValueError("array must be C-contiguous")
    if dtype not in NPY_ITEM_SIZES:
        raise ValueError(f"unsupported dtype {dtype!r}; use little-endian/native float32 or float64")
    expected_size = payload_offset + shape[0] * shape[1] * NPY_ITEM_SIZES[dtype]
    if path.stat().st_size != expected_size:
        raise ValueError(f"file size does not match shape and dtype (expected {expected_size} bytes)")
    return shape[0], shape[1], dtype


def lxy_tag(value):
    return format(value, ".12g").replace("-", "m").replace(".", "p")


def input_identity(path, sample_type="signal"):
    match = CHUNK_RE.fullmatch(path.name)
    category = path.parent.name
    if sample_type == "background":
        category = path.parent.parent.name + "/" + category
        if not match or not all(re.fullmatch(r"[A-Za-z0-9_.+-]+", part) for part in category.split("/")):
            raise ValueError(f"invalid background chunk path: {path}")
        return category, int(match.group("chunk"))
    if not match or not CATEGORY_RE.fullmatch(category):
        raise ValueError(f"invalid input path {path}; expected <barrel/endcap_m_MASS_GeV>/Events_<n>.npy")
    return category, int(match.group("chunk"))


def matches_input_patterns(path, sample, sample_type="signal"):
    category = path.parent.parent.name if sample_type == "background" else path.parent.name
    return any(fnmatch.fnmatchcase(category, pattern) for pattern in sample["category_patterns"])


def collect_inputs(arguments, sample, sample_type="signal"):
    found = set()
    for argument in arguments:
        path = argument.expanduser().resolve()
        if path.is_dir():
            for candidate in path.rglob("*.npy"):
                if candidate.is_file() and matches_input_patterns(candidate, sample, sample_type):
                    input_identity(candidate, sample_type)
                    found.add(candidate.resolve())
        elif path.is_file():
            input_identity(path, sample_type)
            if not matches_input_patterns(path, sample, sample_type):
                raise ValueError(
                    f"input category does not match NPY_CATEGORY_PATTERNS {sample['category_patterns']!r}: {path}"
                )
            found.add(path)
        else:
            raise ValueError(f"input does not exist: {path}")
    if not found:
        raise ValueError("no Events_<n>.npy files found for NPY_CATEGORY_PATTERNS")
    identities = {}
    for path in found:
        identity = input_identity(path, sample_type)
        if identity in identities:
            raise ValueError(f"duplicate category/chunk {identity}: {identities[identity]} and {path}")
        identities[identity] = path
    return [identities[key] for key in sorted(identities)]


def validate_selection_settings(sample):
    if not sample["category_patterns"] or not all(
        isinstance(pattern, str) and pattern for pattern in sample["category_patterns"]
    ):
        raise ValueError("NPY_CATEGORY_PATTERNS must contain at least one nonempty category pattern")
    if not sample["max_chunks_by_lxy"]:
        raise ValueError("LXY_VALUES_MM must not be empty")
    for lxy in sample["max_chunks_by_lxy"]:
        if not isinstance(lxy, (int, float)) or not math.isfinite(lxy) or lxy < 0:
            raise ValueError(f"invalid Lxy value: {lxy!r}")
    limits = sample["max_chunks_by_lxy"]
    for lxy, limit in limits.items():
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
            raise ValueError(f"invalid per-category chunk limit for Lxy {lxy}: {limit!r}")


def validate_settings(cmssw14_src, cmssw15_src, cmssw16_src, common, sample):
    validate_selection_settings(sample)
    if not 1 <= common["base_seed"] < MAX_RNG_SEED:
        raise ValueError("BASE_SEED must be in [1, 899999999]")
    if common["rng_seed_stride"] < 1:
        raise ValueError("RNG_SEED_STRIDE must be positive")
    if common["request_cpus"] < 1:
        raise ValueError("REQUEST_CPUS must be positive")
    if not common["request_memory"]:
        raise ValueError("REQUEST_MEMORY must not be empty")
    for name, value in (
        ("CMSSW 14 source", cmssw14_src),
        ("CMSSW 15 source", cmssw15_src),
        ("CMSSW 16 source", cmssw16_src),
    ):
        if not value:
            raise ValueError(
                f"{name} is not configured; set its path in settings.py or DIMUON_CMSSW_BASE"
            )
        release = Path(value).expanduser().resolve()
        if not release.is_dir():
            raise ValueError(f"{name} is not a directory: {release}")
        if any(character.isspace() for character in str(release)):
            raise ValueError(f"{name} must not contain whitespace: {release}")
    for name in ("MOTHER_PDG_ID", "MU_MINUS_PDG_ID", "MU_PLUS_PDG_ID"):
        if not isinstance(common[name.lower()], int) or common[name.lower()] == 0:
            raise ValueError(f"{name} must be a nonzero integer")


def add_sample_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--signal", action="store_true", help="signal input (default)")
    group.add_argument("--background", action="store_true", help="meson background input; Lxy 1800 mm")


def inspect_inputs(inputs, sample_type):
    selected = []
    counts = defaultdict(int)
    for path in inputs:
        category, chunk = input_identity(path, sample_type)
        try:
            rows, _, _ = inspect_npy(path, sample_type)
        except ValueError as error:
            raise ValueError(f"invalid input {path}: {error}") from error
        selection_category = category.split("/")[0]
        selected.append(InputChunk(path, category, chunk, counts[selection_category], rows))
        counts[selection_category] += 1
    if not selected:
        raise ValueError("no chunks selected")

    return selected


def build_jobs(selected, common, sample, additional_limit=None):
    jobs = []
    jobs_by_category_lxy = defaultdict(int)
    for path, category, chunk, category_index, rows in selected:
        events = rows if common["max_events"] < 0 else min(rows, common["max_events"])
        for lxy in sample["max_chunks_by_lxy"]:
            limit = chunk_limit(sample["max_chunks_by_lxy"][lxy], additional_limit)
            if limit is not None and category_index >= limit:
                continue
            label = f"{category}__chunk{chunk:04d}_lxy{lxy_tag(lxy)}"
            jobs.append(Job(path, category, float(lxy), label, events))
            jobs_by_category_lxy[(category, float(lxy))] += 1

    return jobs, jobs_by_category_lxy


def write_condor_files(jobs, here, outdir, common, sample_type, releases):
    logdir = outdir / "log"
    subdir = outdir / "sub"
    logdir.mkdir(parents=True, exist_ok=True)
    subdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, (path, _category, lxy, label, events) in enumerate(jobs):
        seed = common["base_seed"] + index * 5 * common["rng_seed_stride"]
        rows.append(" ".join(map(str, (
            path, lxy, label, events, seed, outdir,
            common["mother_pdg_id"], common["mu_minus_pdg_id"], common["mu_plus_pdg_id"],
            *releases, common["rng_seed_stride"], sample_type,
        ))))

    joblist = subdir / "dimuon_proton_brem_jobs.args"
    submit = subdir / "dimuon_proton_brem_jobs.sub"
    joblist.write_text("\n".join(rows) + "\n")
    submit.write_text(f"""universe = vanilla
executable = {here / 'run_condor_job.sh'}
arguments = $(input_npy) $(lxy) $(label) $(events) $(seed) $(outdir) $(mother_pdg) $(mu_minus_pdg) $(mu_plus_pdg) $(cmssw14) $(cmssw15) $(cmssw16) $(seed_stride) $(sample_type)

output = {logdir}/job.$(Cluster).$(Process).out
error = {logdir}/job.$(Cluster).$(Process).err
log = {logdir}/job.$(Cluster).log
accounting_group = group_cms
stream_output = True
stream_error = True
should_transfer_files = NO
request_cpus = {common['request_cpus']}
request_memory = {common['request_memory']}

queue input_npy,lxy,label,events,seed,outdir,mother_pdg,mu_minus_pdg,mu_plus_pdg,cmssw14,cmssw15,cmssw16,seed_stride,sample_type from {joblist}
""")
    return submit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-jobs-per-category", type=int,
        help="apply an additional per-category chunk cap to every Lxy value",
    )
    add_sample_arguments(parser)
    args = parser.parse_args()
    common = settings.COMMON
    sample = settings.BACKGROUND if args.background else settings.SIGNAL
    sample_type = "background" if args.background else "signal"

    if common["max_events"] == 0 or common["max_events"] < -1:
        parser.error("MAX_EVENTS must be -1 or a positive integer")
    if args.max_jobs_per_category is not None and args.max_jobs_per_category < 1:
        parser.error("--max-jobs-per-category must be positive")

    cmssw14_src = common["cmssw14_src"]
    cmssw15_src = common["cmssw15_src"]
    cmssw16_src = common["cmssw16_src"]
    validate_settings(cmssw14_src, cmssw15_src, cmssw16_src, common, sample)
    cmssw14_src = Path(cmssw14_src).expanduser().resolve()
    cmssw15_src = Path(cmssw15_src).expanduser().resolve()
    cmssw16_src = Path(cmssw16_src).expanduser().resolve()
    here = Path(__file__).resolve().parent
    outdir = (here / Path(sample["output_directory"]).expanduser()).resolve()
    if any(character.isspace() for character in str(outdir)):
        raise ValueError(f"output path must not contain whitespace: {outdir}")
    configured_input = sample["npy_directory"]
    if not configured_input:
        parser.error("set DEFAULT_NPY_DIRECTORY in settings.py")
    inputs = collect_inputs([here / Path(configured_input).expanduser()], sample, sample_type)

    selected = inspect_inputs(inputs, sample_type)
    jobs, jobs_by_category_lxy = build_jobs(selected, common, sample, args.max_jobs_per_category)

    if any(any(c.isspace() for c in str(path)) for path, *_ in jobs):
        raise ValueError("input paths must not contain whitespace")

    last_seed = common["base_seed"] + (len(jobs) * 5 - 1) * common["rng_seed_stride"]
    if last_seed >= MAX_RNG_SEED:
        raise ValueError(f"seed allocation exceeds {MAX_RNG_SEED - 1}; reduce jobs or RNG_SEED_STRIDE")

    submit = write_condor_files(
        jobs, here, outdir, common, sample_type, (cmssw14_src, cmssw15_src, cmssw16_src)
    )
    for (category, lxy), count in sorted(jobs_by_category_lxy.items()):
        print(f"{category}, Lxy={lxy:g} mm: {count} files")
    print(f"Prepared {len(jobs)} jobs in {outdir}")
    print(f"Submit file: {submit}")
    if not sample["submit_jobs"]:
        print(f"[DRY-RUN] condor_submit {submit}")
    else:
        subprocess.run(["condor_submit", str(submit)], check=True)


if __name__ == "__main__":
    main()
