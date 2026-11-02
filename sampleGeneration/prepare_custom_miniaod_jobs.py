#!/usr/bin/env python3
"""Prepare/submit custom RECO -> MiniAOD jobs using existing production RAW files.

Selection, paths, resources, and submission are configured in settings.py.
The optional --max-jobs-per-category adds a cap to the shared chunk limits.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import subprocess
import re

import settings
from prepare_jobs import (CATEGORY_RE, MAX_RNG_SEED, lxy_tag,
                          matches_input_patterns, validate_settings, add_sample_arguments, chunk_limit)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-jobs-per-category", type=int, help="apply an additional per-category chunk cap to every Lxy value")
    add_sample_arguments(parser)
    args = parser.parse_args()
    common = settings.COMMON
    sample = settings.BACKGROUND if args.background else settings.SIGNAL
    sample_type = "background" if args.background else "signal"
    if common["max_events"] == 0 or common["max_events"] < -1:
        parser.error("MAX_EVENTS must be -1 or a positive integer")
    if args.max_jobs_per_category is not None and args.max_jobs_per_category < 1:
        parser.error("--max-jobs-per-category must be positive")
    if common["request_cpus"] < 1 or not common["request_memory"]:
        raise ValueError("REQUEST_CPUS must be positive and REQUEST_MEMORY must not be empty")
    validate_settings(common["cmssw14_src"], common["cmssw15_src"], common["cmssw16_src"], common, sample)
    here = Path(__file__).resolve().parent
    outdir = (here / Path(sample["custom_output_directory"]).expanduser()).resolve()
    releases = [str(Path(value).expanduser().resolve()) for value in
                (common["cmssw14_src"], common["cmssw15_src"], common["cmssw16_src"])]
    pattern = "Events_*.root"
    filename_re = re.compile(r"^Events_([0-9]+)\.root$")
    lxy_by_tag = {lxy_tag(value): value for value in sample["max_chunks_by_lxy"]}
    selected_lxy_tags = set(lxy_by_tag)

    def matches_selection(path):
        category, separator, tag = path.parent.name.rpartition("_lxy")
        return (bool(separator) and (sample_type == "background" or bool(CATEGORY_RE.fullmatch(category)))
                and tag in selected_lxy_tags
                and matches_input_patterns(Path(path.parent.parent.name) / category / path.name, sample, sample_type))
    inputs = set()
    for argument in [here / Path(sample["custom_raw_directory"]).expanduser()]:
        path = argument.expanduser().resolve()
        if path.is_dir():
            inputs.update(candidate.resolve() for candidate in path.rglob(pattern)
                          if candidate.is_file() and matches_selection(candidate))
        elif path.is_file() and filename_re.fullmatch(path.name) and matches_selection(path):
            inputs.add(path)
        else:
            raise ValueError(f"missing RAW input or input does not match shared category/Lxy selection: {path}")
    for path in inputs:
        if not filename_re.fullmatch(path.name):
            raise ValueError(f"invalid RAW filename (expected Events_<n>.root): {path}")
    identities = set()
    for path in inputs:
        identity = (str(path.parent), int(filename_re.fullmatch(path.name).group(1)))
        if identity in identities:
            raise ValueError(f"duplicate RAW setting/event number: {identity}")
        identities.add(identity)
    counts = defaultdict(int)
    rows = []
    for path in sorted(inputs, key=lambda p: (str(p.parent), int(filename_re.fullmatch(p.name).group(1)))):
        category, _, tag = path.parent.name.rpartition("_lxy")
        lxy = lxy_by_tag[tag]
        number = int(filename_re.fullmatch(path.name).group(1))
        if sample_type == "background":
            category = path.parent.parent.name + "/" + category
        label = f"{category}__chunk{number:04d}_lxy{tag}"
        key = (category.split("/")[0], lxy)
        limit = chunk_limit(sample["max_chunks_by_lxy"][lxy], args.max_jobs_per_category)
        if limit is not None and counts[key] >= limit:
            continue
        if path.stat().st_size == 0:
            raise ValueError(f"empty RAW input: {path}")
        # The runner uses the NPY basename to derive the existing RAW path.
        if path != outdir / "gen_sim_raw" / (f"{category}_lxy{tag}") / path.name:
            raise ValueError(f"RAW must be located in CUSTOM_OUTPUT_DIRECTORY/gen_sim_raw/<setting>: {path}")
        input_npy = Path(sample["npy_directory"]).expanduser() / category / path.with_suffix(".npy").name
        input_npy = (here / input_npy).resolve()
        seed = common["base_seed"] + len(rows) * 5 * common["rng_seed_stride"]
        if seed + 4 * common["rng_seed_stride"] >= MAX_RNG_SEED:
            raise ValueError(f"seed allocation exceeds {MAX_RNG_SEED - 1}; reduce jobs or RNG_SEED_STRIDE")
        fields = list(map(str, (
            input_npy, float(lxy), label, common["max_events"], seed, outdir,
            common["mother_pdg_id"], common["mu_minus_pdg_id"], common["mu_plus_pdg_id"],
            *releases, common["rng_seed_stride"], sample_type,
        )))
        if any(any(c.isspace() for c in field) for field in fields):
            raise ValueError("job argument paths must not contain whitespace")
        rows.append(" ".join(fields))
        counts[key] += 1
    if not rows:
        raise ValueError("no RAW chunks selected")
    logdir, subdir = outdir / "log_custom", outdir / "sub"
    logdir.mkdir(parents=True, exist_ok=True)
    subdir.mkdir(parents=True, exist_ok=True)
    joblist = subdir / "dimuon_proton_brem_custom_miniaod_jobs.args"
    submit = subdir / "dimuon_proton_brem_custom_miniaod_jobs.sub"
    joblist.write_text("\n".join(rows) + "\n")
    submit.write_text(f"""universe = vanilla
executable = {here / 'run_custom_miniaod_job.sh'}
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
    for (category, lxy), count in sorted(counts.items()):
        print(f"{category}, Lxy={float(lxy):g} mm: {count} files")
    print(f"Prepared {len(rows)} jobs in {outdir}")
    print(f"Submit file: {submit}")
    if not sample["submit_jobs"]:
        print(f"[DRY-RUN] condor_submit {submit}")
    else:
        subprocess.run(["condor_submit", str(submit)], check=True)


if __name__ == "__main__":
    main()
