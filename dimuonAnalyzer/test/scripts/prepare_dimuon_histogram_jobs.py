#!/usr/bin/env python3
"""Prepare and submit one histogram HTCondor job per dimuonAnalyzer ROOT file."""

import argparse
import os
import subprocess
from pathlib import Path


DEFAULT_PATTERN = "*_dimuonAnalyzer.root"
REQUEST_CPUS = 1
REQUEST_MEMORY = "4GB"


def resolve_cli_path(path):
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def relative_to_workdir(path, workdir):
    return Path(os.path.relpath(path, start=workdir))


def main():
    project_dir = Path(__file__).resolve().parent.parent
    condor_dir = project_dir / "condor"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, help="dimuonAnalyzer ROOT directory")
    parser.add_argument("--outdir", type=Path, help="histogram ROOT directory")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="input filename glob")
    parser.add_argument("--max-jobs", type=int, help="limit the number of input files")
    parser.add_argument("--max-events", type=int, default=-1, help="events per file; -1 means all")
    parser.add_argument("--dry-run", action="store_true", help="prepare files without submitting")
    args = parser.parse_args()

    if args.max_jobs is not None and args.max_jobs < 1:
        parser.error("--max-jobs must be positive")
    if args.max_events == 0 or args.max_events < -1:
        parser.error("--max-events must be -1 or a positive integer")
    if not args.pattern:
        parser.error("--pattern must not be empty")

    input_dir = resolve_cli_path(args.input_dir) if args.input_dir else condor_dir / "root"
    output_dir = resolve_cli_path(args.outdir) if args.outdir else condor_dir / "histo"
    logdir = condor_dir / "histo_log"
    subdir = condor_dir / "histo_sub"
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")
    for label, path in (("project", project_dir), ("input", input_dir), ("output", output_dir)):
        if any(character.isspace() for character in str(path)):
            parser.error(f"{label} path must not contain whitespace: {path}")

    inputs = [
        path.resolve()
        for path in sorted(input_dir.glob(args.pattern))
        if path.is_file()
        and path.stat().st_size > 0
        and ".part." not in path.name
        and ".invalid." not in path.name
    ]
    if args.max_jobs is not None:
        inputs = inputs[: args.max_jobs]
    if not inputs:
        parser.error(f"no completed ROOT files match {args.pattern!r} in {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    logdir.mkdir(parents=True, exist_ok=True)
    subdir.mkdir(parents=True, exist_ok=True)

    rows = []
    output_names = set()
    for input_path in inputs:
        output_name = f"{input_path.stem}_resTest.root"
        if output_name in output_names:
            raise ValueError(f"duplicate output filename: {output_name}")
        output_names.add(output_name)
        output_path = output_dir / output_name
        rows.append(
            "\t".join(
                (
                    str(relative_to_workdir(input_path, project_dir)),
                    str(relative_to_workdir(output_path, project_dir)),
                    str(args.max_events),
                )
            )
        )

    joblist = subdir / "jobs.args"
    submit_file = subdir / "jobs.sub"
    joblist.write_text("\n".join(rows) + "\n")

    relative_joblist = relative_to_workdir(joblist, project_dir)
    relative_logdir = relative_to_workdir(logdir, project_dir)
    proxy = Path(f"/tmp/x509up_u{os.getuid()}")
    proxy_line = f"x509userproxy = {proxy}\n" if proxy.is_file() else ""
    submit_file.write_text(
        f"""universe = vanilla
executable = scripts/run_dimuon_histogram_job.sh
arguments = $(input_root) $(output_root) $(max_events)
initialdir = .

output = {relative_logdir}/job.$(Cluster).$(Process).out
error = {relative_logdir}/job.$(Cluster).$(Process).err
log = {relative_logdir}/job.$(Cluster).log

accounting_group = group_cms
stream_output = True
stream_error = True
should_transfer_files = NO
request_cpus = {REQUEST_CPUS}
request_memory = {REQUEST_MEMORY}
{proxy_line}
queue input_root,output_root,max_events from {relative_joblist}
"""
    )

    print(f"Input directory : {relative_to_workdir(input_dir, project_dir)}")
    print(f"Pattern         : {args.pattern}")
    print(f"Output directory: {relative_to_workdir(output_dir, project_dir)}")
    print(f"Prepared jobs   : {len(rows)}")
    print(f"Job list        : {relative_joblist}")
    print(f"Submit file     : {relative_to_workdir(submit_file, project_dir)}")
    if args.dry_run:
        print(f"[DRY-RUN] condor_submit {relative_to_workdir(submit_file, project_dir)}")
    else:
        subprocess.run(
            ["condor_submit", str(relative_to_workdir(submit_file, project_dir))],
            cwd=project_dir,
            check=True,
        )


if __name__ == "__main__":
    main()
