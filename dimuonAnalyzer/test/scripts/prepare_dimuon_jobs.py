#!/usr/bin/env python3
"""Prepare and submit one dimuonAnalyzer HTCondor job per MINIAODSIM file.

Select --signal (default) or --background, or override --input-dir/--outdir.
Infer /cms_scratch/<user>/<project>/dimuonAnalyzer/condor/dimuon/output
from /xrd/store/user/<user>/<project>/... and preserve paths below miniaodsim.
For other storage layouts, pass --outdir; paths are relative to --input-dir
when it has no miniaodsim ancestor. Each preparation gets its own submit/log
directory, including --dry-run (which prepares files without submitting).
"""

import argparse
from fnmatch import fnmatchcase
import os
import re
import subprocess
import tempfile
from pathlib import Path


DEFAULT_PATTERN = "Events_*.root"
REQUEST_CPUS = 1
REQUEST_MEMORY = "4GB"
DEFAULT_INPUT_DIRECTORIES = {
    "signal": Path("/xrd/store/user/taehee/dimuonProtonBrem/sampleGeneration/condor/miniaodsim"),
    "background": Path("/xrd/store/user/taehee/dimuonMesonBkg/sampleGeneration/condor/miniaodsim"),
}


def resolve_cli_path(path):
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    # Keep the logical /xrd path even when its storage directories are symlinks.
    return Path(os.path.abspath(path))


def input_base(input_dir):
    """Keep output paths stable when a setting subdirectory is selected."""
    return next(
        (path for path in (input_dir, *input_dir.parents) if path.name == "miniaodsim"),
        input_dir,
    )


def default_output_dir(input_dir):
    try:
        relative = input_dir.relative_to("/xrd/store/user")
    except ValueError:
        raise ValueError("cannot infer output directory; specify --outdir") from None
    if len(relative.parts) < 2:
        raise ValueError("expected /xrd/store/user/<user>/<project>/...; specify --outdir")
    user, project = relative.parts[:2]
    return Path("/cms_scratch") / user / project / "dimuonAnalyzer/condor/dimuon/output"


def relative_to_workdir(path, workdir):
    return Path(os.path.relpath(path, start=workdir))


def main():
    project_dir = Path(__file__).resolve().parent.parent
    workflow_dir = project_dir / "condor/dimuon"

    parser = argparse.ArgumentParser(description=__doc__)
    sample = parser.add_mutually_exclusive_group()
    sample.add_argument("--signal", dest="sample", action="store_const", const="signal",
                        help="use signal default input/output paths (default)")
    sample.add_argument("--background", dest="sample", action="store_const", const="background",
                        help="use dimuonMesonBkg default input/output paths")
    parser.set_defaults(sample="signal")
    parser.add_argument("--input-dir", type=Path, help="MINIAODSIM base or setting directory")
    parser.add_argument("--outdir", type=Path, help="override the output directory inferred from /xrd/store/user/<user>/<project>")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="input filename glob")
    parser.add_argument(
        "--filter", default="*",
        help="case-sensitive full input directory path glob (excluding filename), e.g. '*eta_221*' or '*eta_221*lxy1800*'",
    )
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

    input_dir = resolve_cli_path(args.input_dir) if args.input_dir else DEFAULT_INPUT_DIRECTORIES[args.sample]
    try:
        output_dir = resolve_cli_path(args.outdir) if args.outdir else default_output_dir(input_dir)
    except ValueError as error:
        parser.error(str(error))
    base_dir = input_base(input_dir)
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")
    for label, path in (("project", project_dir), ("input", input_dir), ("output", output_dir)):
        if any(character.isspace() for character in str(path)):
            parser.error(f"{label} path must not contain whitespace: {path}")

    inputs = [
        path
        for path in sorted(input_dir.rglob(args.pattern))
        if fnmatchcase(path.parent.as_posix(), args.filter)
        and path.is_file()
        and path.stat().st_size
    ]
    if args.max_jobs is not None:
        inputs = inputs[: args.max_jobs]
    if not inputs:
        parser.error(
            f"no nonempty ROOT files match {args.pattern!r} "
            f"with directory path filter {args.filter!r} in {input_dir}"
        )

    rows = []
    output_names = set()
    for input_path in inputs:
        if not re.fullmatch(r"Events_[0-9]+\.root", input_path.name):
            raise ValueError(f"expected Events_<n>.root input: {input_path}")
        output_path = output_dir / input_path.relative_to(base_dir)
        if output_path in output_names:
            raise ValueError(f"duplicate output path: {output_path}")
        output_names.add(output_path)
        if output_path.resolve() == input_path.resolve():
            raise ValueError(f"input and output paths must differ: {input_path}")
        rows.append(
            "\t".join(
                (
                    str(input_path),
                    str(output_path),
                    str(args.max_events),
                )
            )
        )

    runs_dir = workflow_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run_", dir=runs_dir))
    logdir = run_dir / "logs"
    subdir = run_dir / "submit"
    logdir.mkdir()
    subdir.mkdir()
    # The worker creates output directories; dry-run need not write to storage.
    joblist = subdir / "jobs.args"
    submit_file = subdir / "jobs.sub"
    joblist.write_text("\n".join(rows) + "\n")

    relative_joblist = relative_to_workdir(joblist, project_dir)
    relative_logdir = relative_to_workdir(logdir, project_dir)
    proxy = Path(f"/tmp/x509up_u{os.getuid()}")
    proxy_line = f"x509userproxy = {proxy}\n" if proxy.is_file() else ""
    submit_file.write_text(
        f"""universe = vanilla
executable = scripts/run_dimuon_job.sh
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

    print(f"Sample preset   : {args.sample}")
    print(f"Input directory : {input_dir}")
    print(f"Pattern         : {args.pattern}")
    print(f"Path filter     : {args.filter}")
    print(f"Output directory: {output_dir}")
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
