# Sample generation

This workflow reads 17-column NPY chunks and produces GEN-SIM, GEN-SIM-RAW,
AODSIM, MINIAODSIM, and NANOAODSIM files.

- GEN-SIM through AODSIM: `CMSSW_14_0_18`
- MINIAODSIM and NANOAODSIM: `CMSSW_15_0_2`

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
  --cmssw15-src /path/to/CMSSW_15_0_2/src
```

Run without `--dry-run` to submit the generated HTCondor job set. Optional
arguments include `--max-events` and `--outdir`.
