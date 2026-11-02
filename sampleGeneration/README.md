# Sample generation

This workflow reads signal (17-column) or background (13-column) NPY chunks and produces GEN-SIM, GEN-SIM-RAW,
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

The proton is assumed to start at `(0, 0, 0)`. The producer reads its
momentum `(px, py, pz)` from NPY columns 1–3 (zero-based); columns 0–3
contain the proton `(E, px, py, pz)`. `Lxy` specifies the transverse distance
from the origin in **mm**. With `pT = sqrt(px*px + py*py)`:

```text
vx = Lxy * px / pT
vy = Lxy * py / pT
vz = Lxy * pz / pT
```

The vertex lies along the proton momentum direction from the origin.
For example, `Lxy = 100 mm` and proton momentum `(3, 4, 12)` give
`(vx, vy, vz) = (60, 80, 240) mm`. When `Lxy = 0`, all coordinates are zero.
For nonzero `Lxy`, zero proton pT or nonfinite inputs/results raise an
exception identifying the event row.

The dark photon mother four-momentum `(E, px, py, pz)` is read from NPY
columns 4–7 and saved as a HepMC particle with status 2 and `MotherPdgId`
(default 999999). The two final-state muons are linked as its daughters;
their four-momenta are copied unchanged from columns 8–15. The dimuon
momentum need not point from the origin toward the vertex. The proton is
used only to calculate the vertex and is not saved as a particle.
The mother production and decay vertices share the proton-derived position
and zero time; no additional dark photon flight is simulated. The 17-column
input format and event weight in column 16 are retained. These are producer
coordinates, before any downstream vertex smearing.

## Configuration

CMSSW releases default to `~/CMSSW_14_0_18/src`, `~/CMSSW_15_0_2/src`, and
`~/CMSSW_16_1_3/src`. No CMSSW environment variables or command-line path
options are needed for these locations.

NPY input defaults to `/xrd/store/user/taehee/dimuonProtonBremNpy` in
`settings.py`. Inputs use `<category>/Events_<n>.npy`, for example
`barrel_m_2.0565123083486516_GeV/Events_0.npy`. `SIGNAL["category_patterns"]`
filters category directory names, and files are processed in numeric order.
Old `__chunkNNNN.npy` input filenames are not supported. Every production
stage writes `Events_<n>.root`, matching the NPY basename. Stage, category,
and Lxy are distinguished by directories, for example
`condor/miniaodsim/barrel_m_2.0565123083486516_GeV_lxy1800/Events_0.root`.
Internal job labels and log names retain their existing format.

Split the original barrel and endcap arrays once (originals are preserved):

```bash
python3 /cms/ldap_home/taehee/CMSSW_15_1_0/src/MyAnalyzer/JPsiDimuonGunProducer/test/split_npy.py
```

The script reads `Events_protonbrem` alongside itself and writes at most
1,000 events per file under the fixed input directory. It preserves all columns,
dtype, and row order, checks existing files before reusing them, and records
source/output row ranges in `npy_chunks_manifest.csv`. It stops on conflicting
existing files instead of overwriting them.

For other CMSSW locations, optionally configure environment variables using
`../env.example`. Replace its example paths before sourcing the file:

```bash
cp ../env.example ../.env
set -a
source ../.env
set +a
```

Physics settings, input patterns, seeds, and Condor resources are configured in
`settings.py`. `COMMON` holds release paths, PDG IDs, seeds, resources, and
`max_events`. `SIGNAL` and `BACKGROUND` hold their own input/output paths,
category patterns, chunk limits, custom paths, and submission flag. Scripts
select a profile locally; selecting one never changes the other profile.
Lxy values follow the insertion order of `max_chunks_by_lxy` keys.

## Job preparation

Set `COMMON["max_events"]`, `SIGNAL["output_directory"]`, and `SIGNAL["submit_jobs"]` in `settings.py`,
along with the input, CMSSW paths, and Condor resources. `COMMON["max_events"] = -1`
processes all events; `SIGNAL["submit_jobs"] = True` submits the generated job set.
Set `SIGNAL["submit_jobs"] = False` to prepare files without submitting.

```bash
./prepare_jobs.py
```

Select the sample profile with `--signal` (default) or `--background`.
The optional selection override is `--max-jobs-per-category`.
Input, CMSSW paths, resources, event count, output path, and submission are
configured exclusively through `settings.py`, without CLI overrides.
Relative paths are resolved from the script directory.

By default, all generated files are written under
`/xrd/store/user/taehee/dimuonProtonBrem/sampleGeneration/condor/`:

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

The distinct stage output directories let resumed jobs validate
and skip the BTV and EXO NanoAOD stages independently.

Set `SIGNAL["output_directory"]` in `settings.py` to select a different location.

## Custom MiniAOD from existing RAW files

`prepare_custom_miniaod_jobs.py` reads
`condor/gen_sim_raw/<category>_lxy<tag>/Events_<n>.root` and matches each file
with its original production job metadata to retain seeds, PDG IDs, and labels.
CMSSW paths come from the shared settings in `settings.py`.
Both scripts select categories/masses using `SIGNAL["category_patterns"]` and Lxy
values using `SIGNAL["max_chunks_by_lxy"] keys`. Custom processing selects available RAW chunks
in numeric order per category/Lxy, subject to the shared
`SIGNAL["max_chunks_by_lxy"]` (`None` selects all available chunks).
`--max-jobs-per-category` adds a further cap, as it does for production.
Unselected categories/Lxy do not require matching production metadata.
Configure `SIGNAL["custom_raw_directory"]`, `SIGNAL["custom_output_directory"]`, and
`CUSTOM_PRODUCTION_JOBLIST` there for custom paths. Event count, resources,
CMSSW paths, and submission settings are shared with production.

```bash
./prepare_custom_miniaod_jobs.py
```

Custom outputs are `condor/aod_custom/<setting>/Events_<n>.root` and
`condor/miniaod_custom/<setting>/Events_<n>.root`. Existing production metadata
must be available in `condor/sub/dimuon_proton_brem_jobs.args`. As before, RAW
inputs must be under the selected output base's `gen_sim_raw/<setting>` directory.

## EXO NanoAOD resolution analysis

The EXO NanoAOD files can be analyzed directly, without producing the
intermediate `dimuonAnalyzer/tree` used by the MiniAOD workflow:

```bash
cd ../dimuonAnalyzer/test
./scripts/run_exonano_histogram_job.sh \
  /xrd/store/user/taehee/dimuonProtonBrem/sampleGeneration/condor/exonanoaodsim/<setting>/Events_0.root \
  /tmp/example_EXONANO_resTest.root 100
```

Prepare one HTCondor analysis job per EXO NanoAOD file with:

```bash
./scripts/prepare_exonano_histogram_jobs.py --dry-run --max-jobs 2 --max-events 100
./scripts/prepare_exonano_histogram_jobs.py
```

The analysis uses the `Muon`, `DSAMuon`, PAT-PAT, PAT-DSA, and DSA-DSA vertex
tables saved in EXO NanoAOD.  Its matching and opposite-sign selection mirror
the MiniAOD resolution analysis, while histogram directory names retain the
actual EXO collection names.

### Setting directories for ROOT files

All production stages now use `<stage>/<category>_lxy<tag>/<filename>.root`.
For example, MiniAOD output is stored in
`condor/miniaodsim/barrel_m_2.0565123083486516_GeV_lxy1800/`.
Production filenames use `Events_<n>.root`; full mass precision is preserved
in setting directory names. Analysis, comparison, histogram,
and merged outputs use the same setting directory below their output base.
Job preparation searches input directories recursively; `--pattern` continues
matching filenames, and `--outdir` remains the output base directory.

Each analysis preparation script derives its output setting directory directly
from the input parent directory and preserves `Events_<n>.root`. No separate
ROOT path helper or migration script is needed. Internal Condor labels and
stage-log names retain `__chunkNNNN` for submission compatibility.

## Storage locations

Code remains in this repository. Signal production data (including submission and
stage logs) lives under
`/xrd/store/user/taehee/dimuonProtonBrem/sampleGeneration/{condor,condor_vz_0}`.
Relative production paths shown above are relative to that storage directory.

Analysis ROOT files live under
`/cms_scratch/taehee/dimuonProtonBrem/dimuonAnalyzer/{condor,condor_vz_0}/<workflow>/output`
and merged ROOT files under the corresponding `merged` directory. Analysis
logs, submission files, and watcher state remain under `dimuonAnalyzer/test`.
There are no compatibility symlinks. New analysis jobs use absolute ROOT paths.

Run analysis preparation from `dimuonAnalyzer/test`, for example:

```bash
python3 scripts/prepare_dimuon_jobs.py --dry-run --max-jobs 1
python3 scripts/prepare_exonano_histogram_jobs.py --dry-run --max-jobs 1
```

The defaults select `condor`. For archived `condor_vz_0` data, pass explicit
`--input-dir` and `--outdir` paths under the corresponding storage roots.
The existing archived submission files retain their original selections and
now reference the relocated files.

## Meson background production

The same producer and production stages support both sample types:

```bash
./prepare_jobs.py --signal       # default when neither flag is supplied
./prepare_jobs.py --background
./prepare_custom_miniaod_jobs.py --background
```

`--signal` and `--background` are mutually exclusive. Existing 13-argument
runner invocations still default to signal; new job lists append the sample type.
Background settings are independent of the signal profile in `settings.py`:
`BACKGROUND["category_patterns"]`, `BACKGROUND["max_chunks_by_lxy"]`,
`BACKGROUND["npy_directory"]`, `BACKGROUND["output_directory"]`, and
`BACKGROUND["submit_jobs"]`. The selected category is **eta_continuum_HCal**. Background Lxy defaults to **1800 mm only** and
submission defaults to **False**. Job preparation writes submission files;
set `BACKGROUND["submit_jobs"] = True` to submit them on a later run.

Background column numbers below start at 1:

| Columns | Contents |
| --- | --- |
| 1–4 | meson E, px, py, pz |
| 5–8 | mu+ E, px, py, pz |
| 9–12 | mu- E, px, py, pz |
| 13 | event weight |

The meson momentum sets the vertex using the same origin-based Lxy formula
as the signal proton. The meson is used only for this position calculation;
it is not recorded as a GEN particle or passed to Geant4. Background GEN
contains exactly two status-1 muons sharing one vertex, without a mother.
Their four-momenta and the event weight are copied unchanged from NPY.

Prepare 1,000-row NPY chunks using the separate splitting script. The source
files remain untouched. The default profile selects eta_continuum_HCal and
at most 10 chunks per original NPY (`BACKGROUND["max_chunks_per_source"]`).
Sources are visited in sorted filename order and empty arrays are skipped:

```bash
python3 split_background_npy.py --category eta_continuum_HCal --max-chunks-per-source 10 --dry-run
python3 split_background_npy.py --category eta_continuum_HCal --max-chunks-per-source 10
```

This selection creates **2,026 chunks containing 2,015,674 events** from 211
nonempty originals (75 empty originals are skipped). `--category` may be
repeated, and `--max-chunks-per-category` optionally caps the combined chunks
across originals in each category. Set `BACKGROUND["max_chunks_per_source"] = None`
to remove the per-source cap. The full source dataset has
about 10.08 billion rows, so unrestricted splitting creates about 10.08 million
files. Preparation retains the RNG seed range check; select a bounded job set
with `--max-jobs-per-category` if a larger prepared set exceeds that range.
The preparation option `--max-jobs-per-category` applies across original
source files within each meson/detector category.

Original category directories remain directly under
`/xrd/store/user/taehee/dimuonMesonBkgNpy/`. Chunks are grouped separately
under its reserved `chunks/` directory, which is excluded from source discovery.
No compatibility symbolic link is used. Chunk storage preserves each original source name:

```text
/xrd/store/user/taehee/dimuonMesonBkgNpy/chunks/
  <category>/<source-stem>/Events_<n>.npy
```

The splitter preserves dtype, every column, row order, and the final partial
chunk. It verifies new chunks against their source and checks existing chunks
before reusing them. Conflicting chunks raise an error. The manifest records
source paths, selected row ranges (stop exclusive), and total source row
counts; with a cap it describes the selected subset, not the whole dataset.

Background CMS outputs use the separate
`dimuonMesonBkg` storage namespace. Signal output paths remain unchanged.
CMS outputs use:

```text
/xrd/store/user/taehee/dimuonMesonBkg/sampleGeneration/condor_background/
  <stage>/<category>/<source-stem>_lxy1800/Events_<n>.root
```

After changing the C++ producer, copy or link its package into the CMSSW 14
release and rebuild as described above. Pure Python checks are available with
`python3 -m unittest discover -s tests -v` (requires NumPy).
