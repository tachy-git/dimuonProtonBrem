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
SEED_STRIDE="${12:?RNG seed stride missing}"

WORKFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
CFG_DIR="${WORKFLOW_DIR}/cfg"
GEN_SIM="${OUTDIR}/gen_sim/${LABEL}_GEN_SIM.root"
GEN_SIM_RAW="${OUTDIR}/gen_sim_raw/${LABEL}_GEN_SIM_RAW.root"
AODSIM="${OUTDIR}/aodsim/${LABEL}_AODSIM.root"
MINIAODSIM="${OUTDIR}/miniaodsim/${LABEL}_MINIAODSIM.root"
NANOAODSIM="${OUTDIR}/nanoaodsim/${LABEL}_NANOAODSIM.root"
STAGE_LOG="${OUTDIR}/stage_logs"
mkdir -p "${OUTDIR}/gen_sim" "${OUTDIR}/gen_sim_raw" "${OUTDIR}/aodsim" \
         "${OUTDIR}/miniaodsim" "${OUTDIR}/nanoaodsim" "$STAGE_LOG"

source /cvmfs/cms.cern.ch/cmsset_default.sh

activate_release() {
  local release_src="$1"
  cd "$release_src"
  eval "$(scram runtime -sh)"
}

valid_edm_file() {
  local path="$1"
  [ -s "$path" ] && edmFileUtil "$path" >/dev/null 2>&1
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
  log="${STAGE_LOG}/${LABEL}_${name}_${run_stamp}.log"
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
if valid_edm_file "$NANOAODSIM"; then
  echo "[SKIP] final NANOAODSIM is valid; workflow complete: ${NANOAODSIM}"
  exit 0
fi

activate_release "$CMSSW14"
run_stage gen_sim "$GEN_SIM" "" "${CFG_DIR}/gen_sim_cfg.py" \
  maxEvents="$EVENTS" inputNpy="$INPUT_NPY" lxy="$LXY" seed="$SEED" \
  motherPdgId="$MOTHER_PDG" muMinusPdgId="$MU_MINUS_PDG" muPlusPdgId="$MU_PLUS_PDG"
run_stage digi_hlt "$GEN_SIM_RAW" "$GEN_SIM" "${CFG_DIR}/digi_hlt_cfg.py" \
  maxEvents="$EVENTS" inputFile="$GEN_SIM" seed="$((SEED + SEED_STRIDE))"
run_stage reco "$AODSIM" "$GEN_SIM_RAW" "${CFG_DIR}/reco_cfg.py" \
  maxEvents="$EVENTS" inputFile="$GEN_SIM_RAW" seed="$((SEED + 2 * SEED_STRIDE))"

activate_release "$CMSSW15"
run_stage miniaod "$MINIAODSIM" "$AODSIM" "${CFG_DIR}/miniaod_cfg.py" \
  maxEvents="$EVENTS" inputFile="$AODSIM" seed="$((SEED + 3 * SEED_STRIDE))"
run_stage nanoaod "$NANOAODSIM" "$MINIAODSIM" "${CFG_DIR}/nanoaod_cfg.py" \
  maxEvents="$EVENTS" inputFile="$MINIAODSIM" seed="$((SEED + 4 * SEED_STRIDE))"
echo "[DONE] complete: ${NANOAODSIM}"
