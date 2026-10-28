# Sample generation

This workflow reads 17-column NPY chunks and produces GEN-SIM, GEN-SIM-RAW,
AODSIM, MINIAODSIM, the existing BTV NANOAODSIM, and a dimuon EXO
NANOAODSIM file.

- GEN-SIM through AODSIM: `CMSSW_14_0_18`
- MINIAODSIM and BTV NANOAODSIM: `CMSSW_15_0_2`
- dimuon EXO NANOAODSIM from AODSIM: `CMSSW_16_1_3`

The existing BTV NanoAOD path remains `AODSIM -> MINIAODSIM -> NANOAODSIM`.
The additional EXO path runs `PAT,NANO:@PHYS` directly from AODSIM so that
`generalTracks` and `displacedStandAloneMuons` are available.  It adds the DSA
muon, PAT/DSA dimuon-vertex, refitted-track, extended-muon, and displaced
`GenPart` vertex/momentum columns from EXOnanoAODv1.

Every stage independently checks its own output before running.  A file is
reused only when it is nonempty, opens as a non-zombie/non-recovered ROOT file,
contains the `Events` tree, and passes `edmFileUtil`.  Therefore a valid
GEN-SIM skips only GEN-SIM, a valid GEN-SIM-RAW also skips DIGI-HLT, and so on.
Invalid files are preserved with an `.invalid.<timestamp>.<pid>` suffix before
that stage is rerun.  The standard and EXO NanoAOD branches are completed
independently.

## Producer setup

Link the producer package into `CMSSW_14_0_18` and compile it:

```bash
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd /path/to/CMSSW_14_0_18/src
mkdir -p MyAnalyzer
ln -s /path/to/repository/sampleGeneration/producer \
  MyAnalyzer/ProtonBremDimuonGunProducer
cmsenv
scram b -j 8
```

Create the release containing the official EXOnanoAODv1 backport:

```bash
cd /path/to/cmssw-work
cmsrel CMSSW_16_1_3
```

No local checkout or build is needed in `CMSSW_16_1_3`.

## Vertex coordinates

The producer reads the mother momentum `(px, py, pz)` from the NPY input.
`Lxy` specifies the transverse distance from the origin in **mm**. With
`pT = sqrt(px*px + py*py)` and `phi = atan2(py, px)`, the coordinates are:

```text
vx = Lxy * cos(phi) = Lxy * px / pT
vy = Lxy * sin(phi) = Lxy * py / pT
vz = Lxy * pz / pT  = Lxy * sinh(eta)
```

Here `eta` is the mother's pseudorapidity. The vertex lies along the mother
momentum direction from the origin. For example, `Lxy = 100 mm` and mother
momentum `(3, 4, 12)` give `(vx, vy, vz) = (60, 80, 240) mm`.
When `Lxy = 0`, all coordinates are zero. For nonzero `Lxy`, zero mother pT
or nonfinite inputs/results raise an exception identifying the event row.
The mother production and dimuon decay vertices share these coordinates;
both times remain zero, so mother flight between vertices is not simulated.
These are producer coordinates, before any downstream vertex smearing.

## Configuration

Set the input and CMSSW locations with environment variables:

```bash
cp ../env.example ../.env
set -a
source ../.env
set +a
```

Physics settings, input patterns, seeds, and Condor resources are configured in
`settings.py`.

## Job preparation

Prepare a small job set without submitting:

```bash
./prepare_jobs.py --dry-run --max-jobs-per-category 1
```

Paths can be provided directly:

```bash
./prepare_jobs.py --dry-run \
  --input-dir /path/to/npy_chunks \
  --cmssw14-src /path/to/CMSSW_14_0_18/src \
  --cmssw15-src /path/to/CMSSW_15_0_2/src \
  --cmssw16-src /path/to/CMSSW_16_1_3/src
```

Run without `--dry-run` to submit the generated HTCondor job set. Optional
arguments include `--max-events` and `--outdir`.

By default, all generated files are written under `sampleGeneration/condor/`:

```text
condor/
├── sub/
├── log/
├── stage_logs/
├── gen_sim/
├── gen_sim_raw/
├── aodsim/
├── miniaodsim/
├── nanoaodsim/
└── exonanoaodsim/
```

The distinct output directories and filename suffixes let resumed jobs validate
and skip the BTV and EXO NanoAOD stages independently.

Use `--outdir /path/to/output` to select a different location.

## EXO NanoAOD resolution analysis

The EXO NanoAOD files can be analyzed directly, without producing the
intermediate `dimuonAnalyzer/tree` used by the MiniAOD workflow:

```bash
cd ../dimuonAnalyzer/test
./run_exonano_histo_job.sh \
  ../../sampleGeneration/condor/exonanoaodsim/<setting>/example_EXONANOAODSIM.root \
  /tmp/example_EXONANO_resTest.root 100
```

Prepare one HTCondor analysis job per EXO NanoAOD file with:

```bash
./prepare_exonano_histo_jobs.py --dry-run --max-jobs 2 --max-events 100
./prepare_exonano_histo_jobs.py
```

The analysis uses the `Muon`, `DSAMuon`, PAT-PAT, PAT-DSA, and DSA-DSA vertex
tables saved in EXO NanoAOD.  Its matching and opposite-sign selection mirror
the MiniAOD resolution analysis, while histogram directory names retain the
actual EXO collection names.

### Setting directories for ROOT files

All production stages now use `<stage>/<category>_lxy<tag>/<filename>.root`.
For example, MiniAOD output is stored in
`condor/miniaodsim/barrel_m_2.0565123083486516_GeV_lxy1800/`.
Filenames and full mass precision are preserved. Analysis, comparison, histogram,
and merged outputs use the same setting directory below their output base.
Job preparation searches input directories recursively; `--pattern` continues
matching filenames, and `--outdir` remains the output base directory.

Preview existing-file migration with `python3 sampleGeneration/organize_root_files.py`
from the repository root; add `--apply` to move files and update generated job lists.
Before applying, ensure related Condor jobs and workflow watchers are stopped or
finished. The migration refuses destination collisions and records source paths,
destination paths, sizes, and original job lists in
`sampleGeneration/condor/root_layout_migration_<timestamp>/`.
To undo a completed migration, move each manifest target back to its source
without overwriting any existing source, then restore the saved job-list text.
Re-running the migration after completion makes no further changes.
