#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: $0 INPUT_ROOT OUTPUT_ROOT MAX_EVENTS" >&2
  exit 2
fi

INPUT_ROOT="$1"
OUTPUT_ROOT="$2"
MAX_EVENTS="$3"
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_CMSSW_SRC="$(readlink -f "${PROJECT_DIR}/../../../../CMSSW_16_1_3/src")"
CMSSW_SRC="${DIMUON_CMSSW16_SRC:-${DEFAULT_CMSSW_SRC}}"
ANALYZER="${SCRIPT_DIR}/make_exonano_histograms.py"

absolute_path() {
  if [[ "$1" = /* ]]; then readlink -f "$1"; else readlink -f "${PROJECT_DIR}/$1"; fi
}

preserve_invalid() {
  local path="$1" reason="$2"
  if [[ -e "$path" ]]; then
    local saved="${path}.invalid.$(date +%Y%m%d_%H%M%S).$$"
    mv "$path" "$saved"
    echo "[INVALID] ${reason}; preserved as ${saved}" >&2
  fi
}

valid_histo_file() {
  local path="$1"
  [[ -s "$path" ]] || return 1
  python3 - "$path" <<'PY'
import sys
import ROOT
ROOT.gROOT.SetBatch(True)
root_file = ROOT.TFile.Open(sys.argv[1])
required = (
    "Muon/h_pt", "Muon/h_ptPull", "DSAMuon/h_pt", "DSAMuon/h_ptPull",
    "PatMuonVertex/h_vertexFit_mass", "PatDSAMuonVertex/h_vertexFit_mass",
    "DSAMuonVertex/h_vertexFit_mass",
)
valid = bool(root_file and not root_file.IsZombie()
             and not root_file.TestBit(ROOT.TFile.kRecovered)
             and all(root_file.Get(name) for name in required))
if root_file:
    root_file.Close()
raise SystemExit(0 if valid else 1)
PY
}

INPUT_ABS="$(absolute_path "$INPUT_ROOT")"
OUTPUT_ABS="$(absolute_path "$OUTPUT_ROOT")"
TMP_OUTPUT="${OUTPUT_ABS%.root}.part.$$.root"
INNER_TMP="${TMP_OUTPUT}.tmp.root"

[[ -s "$INPUT_ABS" ]] || { echo "[ERROR] Missing input: ${INPUT_ABS}" >&2; exit 3; }
[[ -f "$ANALYZER" ]] || { echo "[ERROR] Missing analyzer: ${ANALYZER}" >&2; exit 3; }
mkdir -p "$(dirname "$OUTPUT_ABS")"
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "$CMSSW_SRC"
eval "$(scram runtime -sh)"

if valid_histo_file "$OUTPUT_ABS"; then
  echo "[SKIP] Valid EXONano histogram output exists: ${OUTPUT_ABS}"
  exit 0
fi
preserve_invalid "$OUTPUT_ABS" "existing histogram output is invalid"
preserve_invalid "$TMP_OUTPUT" "stale temporary output"
preserve_invalid "$INNER_TMP" "stale analyzer temporary output"

status=0
python3 "$ANALYZER" "$INPUT_ABS" "$TMP_OUTPUT" --max-events "$MAX_EVENTS" || status=$?
if [[ "$status" -ne 0 ]]; then
  preserve_invalid "$TMP_OUTPUT" "analysis failed with status ${status}"
  preserve_invalid "$INNER_TMP" "analysis failed with status ${status}"
  exit "$status"
fi
if ! valid_histo_file "$TMP_OUTPUT"; then
  preserve_invalid "$TMP_OUTPUT" "histogram output is invalid"
  exit 5
fi
if valid_histo_file "$OUTPUT_ABS"; then
  preserve_invalid "$TMP_OUTPUT" "another process completed the output"
  echo "[SKIP] Another process completed: ${OUTPUT_ABS}"
  exit 0
fi
preserve_invalid "$OUTPUT_ABS" "final path appeared but is invalid"
mv "$TMP_OUTPUT" "$OUTPUT_ABS"
echo "[DONE] ${OUTPUT_ABS}"
