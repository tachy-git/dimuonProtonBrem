#!/usr/bin/env python3
"""Prepare and submit one direct-analysis job per EXONANOAODSIM file."""

import argparse
import os
import subprocess
from pathlib import Path


DEFAULT_PATTERN = "*_EXONANOAODSIM.root"
REQUEST_CPUS = 1
REQUEST_MEMORY = "4GB"


def resolve(path):
    path = path.expanduser()
    return (Path.cwd() / path).resolve() if not path.is_absolute() else path.resolve()


def relative(path, workdir):
    return Path(os.path.relpath(path, start=workdir))


def main():
    project_dir = Path(__file__).resolve().parent.parent
    default_input = (project_dir / "../../sampleGeneration/condor/exonanoaodsim").resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, help="EXONANOAODSIM directory")
    parser.add_argument("--outdir", type=Path, help="histogram output directory")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="input filename glob")
    parser.add_argument("--max-jobs", type=int, help="limit input files")
    parser.add_argument("--max-events", type=int, default=-1, help="events per file; -1 means all")
    parser.add_argument("--dry-run", action="store_true", help="prepare files without submission")
    args = parser.parse_args()
    if args.max_jobs is not None and args.max_jobs < 1:
        parser.error("--max-jobs must be positive")
    if args.max_events == 0 or args.max_events < -1:
        parser.error("--max-events must be -1 or a positive integer")
    if not args.pattern:
        parser.error("--pattern must not be empty")

    input_dir = resolve(args.input_dir) if args.input_dir else default_input
    output_dir = resolve(args.outdir) if args.outdir else project_dir / "condor/exonano_histo"
    log_dir = project_dir / "condor/exonano_histo_log"
    sub_dir = project_dir / "condor/exonano_histo_sub"
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")
    for label, path in (("project", project_dir), ("input", input_dir), ("output", output_dir)):
        if any(character.isspace() for character in str(path)):
            parser.error(f"{label} path must not contain whitespace: {path}")
    inputs = [path.resolve() for path in sorted(input_dir.glob(args.pattern))
              if path.is_file() and path.stat().st_size > 0
              and ".part." not in path.name and ".invalid." not in path.name]
    if args.max_jobs is not None:
        inputs = inputs[:args.max_jobs]
    if not inputs:
        parser.error(f"no completed ROOT files match {args.pattern!r} in {input_dir}")

    for directory in (output_dir, log_dir, sub_dir):
        directory.mkdir(parents=True, exist_ok=True)
    rows, output_names = [], set()
    for input_path in inputs:
        stem = input_path.stem.removesuffix("_EXONANOAODSIM")
        output_name = f"{stem}_EXONANO_resTest.root"
        if output_name in output_names:
            raise ValueError(f"duplicate output filename: {output_name}")
        output_names.add(output_name)
        rows.append("\t".join((str(relative(input_path, project_dir)),
                               str(relative(output_dir / output_name, project_dir)),
                               str(args.max_events))))

    joblist, submit_file = sub_dir / "jobs.args", sub_dir / "jobs.sub"
    joblist.write_text("\n".join(rows) + "\n")
    proxy = Path(f"/tmp/x509up_u{os.getuid()}")
    proxy_line = f"x509userproxy = {proxy}\n" if proxy.is_file() else ""
    submit_file.write_text(f"""universe = vanilla
executable = scripts/run_exonano_histogram_job.sh
arguments = $(input_root) $(output_root) $(max_events)
initialdir = .

output = {relative(log_dir, project_dir)}/job.$(Cluster).$(Process).out
error = {relative(log_dir, project_dir)}/job.$(Cluster).$(Process).err
log = {relative(log_dir, project_dir)}/job.$(Cluster).log

accounting_group = group_cms
stream_output = True
stream_error = True
should_transfer_files = NO
request_cpus = {REQUEST_CPUS}
request_memory = {REQUEST_MEMORY}
{proxy_line}queue input_root,output_root,max_events from {relative(joblist, project_dir)}
""")
    print(f"Input directory : {relative(input_dir, project_dir)}")
    print(f"Pattern         : {args.pattern}")
    print(f"Output directory: {relative(output_dir, project_dir)}")
    print(f"Prepared jobs   : {len(rows)}")
    print(f"Job list        : {relative(joblist, project_dir)}")
    print(f"Submit file     : {relative(submit_file, project_dir)}")
    if args.dry_run:
        print(f"[DRY-RUN] condor_submit {relative(submit_file, project_dir)}")
    else:
        subprocess.run(
            ["condor_submit", str(relative(submit_file, project_dir))],
            cwd=project_dir,
            check=True,
        )


if __name__ == "__main__":
    main()
