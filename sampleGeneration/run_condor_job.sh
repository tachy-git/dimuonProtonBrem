#!/usr/bin/env bash
set -euo pipefail

INPUT_NPY="${1:?input NPY missing}"
LXY="${2:?Lxy missing}"
LABEL="${3:?label missing}"
EVENTS="${4:?event count missing}"
SEED="${5:?seed missing}"
OUTDIR="${6:?output directory missing}"
MOTHER_PDG="${7:?mother PDG ID missing}"
MU_MINUS_PDG="${8:?negative-muon PDG ID missing}"
MU_PLUS_PDG="${9:?positive-muon PDG ID missing}"
CMSSW14="${10:?CMSSW 14 source directory missing}"
CMSSW15="${11:?CMSSW 15 source directory missing}"
CMSSW16="${12:?CMSSW 16 source directory missing}"
SEED_STRIDE="${13:?RNG seed stride missing}"
SAMPLE_TYPE="${14:-signal}"
case "$SAMPLE_TYPE" in signal|background) ;; *) echo "Invalid sample type: $SAMPLE_TYPE" >&2; exit 1 ;; esac

WORKFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
CFG_DIR="${WORKFLOW_DIR}/cfg"
# Keep the existing Condor argument/label format without a Python path helper.
if [[ "$LABEL" =~ ^([A-Za-z0-9_.+/-]+)__chunk[0-9]+_lxy([0-9]+(p[0-9]+)?)$ ]] && [[ "$LABEL" != *".."* ]]; then
  SETTING="${BASH_REMATCH[1]}_lxy${BASH_REMATCH[2]}"
else
  echo "[ERROR] invalid mass/Lxy job label: ${LABEL}" >&2
  exit 1
fi
INPUT_NAME="${INPUT_NPY##*/}"
if [[ ! "$INPUT_NAME" =~ ^Events_[0-9]+\.npy$ ]]; then
  echo "[ERROR] expected Events_<n>.npy input: ${INPUT_NPY}" >&2
  exit 1
fi
ROOT_NAME="${INPUT_NAME%.npy}.root"
GEN_SIM="${OUTDIR}/gen_sim/${SETTING}/${ROOT_NAME}"
GEN_SIM_RAW="${OUTDIR}/gen_sim_raw/${SETTING}/${ROOT_NAME}"
AODSIM="${OUTDIR}/aodsim/${SETTING}/${ROOT_NAME}"
MINIAODSIM="${OUTDIR}/miniaodsim/${SETTING}/${ROOT_NAME}"
NANOAODSIM="${OUTDIR}/nanoaodsim/${SETTING}/${ROOT_NAME}"
EXONANOAODSIM="${OUTDIR}/exonanoaodsim/${SETTING}/${ROOT_NAME}"
STAGE_LOG="${OUTDIR}/stage_logs"
mkdir -p "${OUTDIR}/gen_sim/${SETTING}" "${OUTDIR}/gen_sim_raw/${SETTING}" "${OUTDIR}/aodsim/${SETTING}" \
         "${OUTDIR}/miniaodsim/${SETTING}" "${OUTDIR}/nanoaodsim/${SETTING}" \
         "${OUTDIR}/exonanoaodsim/${SETTING}" "$STAGE_LOG"

source /cvmfs/cms.cern.ch/cmsset_default.sh

activate_release() {
  local release_src="$1"
  cd "$release_src"
  eval "$(scram runtime -sh)"
}

valid_root_file() {
  local path="$1"
  [ -s "$path" ] || return 1
  python3 - "$path" >/dev/null 2>&1 <<'PY'
import sys
import ROOT

ROOT.gROOT.SetBatch(True)
root_file = ROOT.TFile.Open(sys.argv[1])
valid = bool(
    root_file
    and not root_file.IsZombie()
    and not root_file.TestBit(ROOT.TFile.kRecovered)
    and root_file.Get("Events")
)
if root_file:
    root_file.Close()
raise SystemExit(0 if valid else 1)
PY
}

valid_edm_file() {
  local path="$1"
  valid_root_file "$path" && edmFileUtil "$path" >/dev/null 2>&1
}

preserve_invalid() {
  local path="$1"
  local reason="$2"
  if [ -e "$path" ]; then
    local saved="${path}.invalid.$(date +%Y%m%d_%H%M%S).$$"
    mv "$path" "$saved"
    echo "[INVALID] ${reason}; preserved as ${saved}"
  fi
}

run_stage() {
  local name="$1"
  local final_output="$2"
  local required_input="$3"
  local cfg="$4"
  shift 4

  if valid_edm_file "$final_output"; then
    echo "[SKIP] ${name}: valid output already exists: ${final_output}"
    return 0
  fi
  preserve_invalid "$final_output" "${name} output is not a valid EDM ROOT file"
  if [ -n "$required_input" ] && ! valid_edm_file "$required_input"; then
    echo "[ERROR] ${name}: invalid required input: ${required_input}" >&2
    return 4
  fi

  local run_stamp temporary_output log status
  run_stamp="$(date +%Y%m%d_%H%M%S)"
  temporary_output="${final_output}.part.$$"
  log="${STAGE_LOG}/${LABEL//\//__}_${name}_${run_stamp}.log"
  preserve_invalid "$temporary_output" "stale ${name} temporary output"
  echo "[RUN] ${name} start: $(date) on $(hostname)"
  if cmsRun "$cfg" "$@" outputFile="$temporary_output" 2>&1 | tee "$log"; then
    :
  else
    status=$?
    preserve_invalid "$temporary_output" "${name} cmsRun failed"
    echo "[ERROR] ${name} failed with status ${status}" >&2
    return "$status"
  fi
  if ! valid_edm_file "$temporary_output"; then
    preserve_invalid "$temporary_output" "${name} produced an invalid EDM ROOT file"
    return 5
  fi
  if valid_edm_file "$final_output"; then
    mv "$temporary_output" "${temporary_output}.duplicate.${run_stamp}"
    echo "[SKIP] ${name}: another process created ${final_output}"
    return 0
  fi
  preserve_invalid "$final_output" "${name} final path appeared but is invalid"
  mv "$temporary_output" "$final_output"
  echo "[DONE] ${name}: ${final_output}"
}

echo "[INFO] label=${LABEL} input=${INPUT_NPY} lxy=${LXY} events=${EVENTS} seed=${SEED}"
activate_release "$CMSSW15"
if valid_edm_file "$NANOAODSIM" && valid_edm_file "$EXONANOAODSIM"; then
  echo "[SKIP] both final outputs are valid; workflow complete"
  echo "[INFO] NANOAODSIM: ${NANOAODSIM}"
  echo "[INFO] EXONANOAODSIM: ${EXONANOAODSIM}"
  exit 0
fi

need_aod=0
if ! valid_edm_file "$EXONANOAODSIM"; then
  need_aod=1
fi
if ! valid_edm_file "$NANOAODSIM" && ! valid_edm_file "$MINIAODSIM"; then
  need_aod=1
fi

if [ "$need_aod" -eq 1 ]; then
  if valid_edm_file "$AODSIM"; then
    echo "[SKIP] reco: valid output already exists: ${AODSIM}"
    echo "[SKIP] gen_sim/digi_hlt: valid downstream AODSIM makes upstream outputs unnecessary"
  else
    activate_release "$CMSSW14"
    if valid_edm_file "$GEN_SIM_RAW"; then
      echo "[SKIP] digi_hlt: valid output already exists: ${GEN_SIM_RAW}"
      echo "[SKIP] gen_sim: valid downstream GEN-SIM-RAW makes its input unnecessary"
    else
      run_stage gen_sim "$GEN_SIM" "" "${CFG_DIR}/gen_sim_cfg.py" \
        maxEvents="$EVENTS" inputNpy="$INPUT_NPY" sampleType="$SAMPLE_TYPE" lxy="$LXY" seed="$SEED" \
        motherPdgId="$MOTHER_PDG" muMinusPdgId="$MU_MINUS_PDG" muPlusPdgId="$MU_PLUS_PDG"
      run_stage digi_hlt "$GEN_SIM_RAW" "$GEN_SIM" "${CFG_DIR}/digi_hlt_cfg.py" \
        maxEvents="$EVENTS" inputFile="$GEN_SIM" seed="$((SEED + SEED_STRIDE))"
    fi
    run_stage reco "$AODSIM" "$GEN_SIM_RAW" "${CFG_DIR}/reco_cfg.py" \
      maxEvents="$EVENTS" inputFile="$GEN_SIM_RAW" seed="$((SEED + 2 * SEED_STRIDE))"
  fi
fi

if valid_edm_file "$NANOAODSIM"; then
  echo "[SKIP] nanoaod: valid output already exists: ${NANOAODSIM}"
else
  activate_release "$CMSSW15"
  run_stage miniaod "$MINIAODSIM" "$AODSIM" "${CFG_DIR}/miniaod_cfg.py" \
    maxEvents="$EVENTS" inputFile="$AODSIM" seed="$((SEED + 3 * SEED_STRIDE))"
  run_stage nanoaod "$NANOAODSIM" "$MINIAODSIM" "${CFG_DIR}/nanoaod_cfg.py" \
    maxEvents="$EVENTS" inputFile="$MINIAODSIM" seed="$((SEED + 4 * SEED_STRIDE))"
fi

if valid_edm_file "$EXONANOAODSIM"; then
  echo "[SKIP] exonanoaod: valid output already exists: ${EXONANOAODSIM}"
else
  activate_release "$CMSSW16"
  run_stage exonanoaod "$EXONANOAODSIM" "$AODSIM" "${CFG_DIR}/exonanoaod_cfg.py" \
    maxEvents="$EVENTS" inputFile="$AODSIM"
fi

echo "[DONE] NANOAODSIM: ${NANOAODSIM}"
echo "[DONE] EXONANOAODSIM: ${EXONANOAODSIM}"
