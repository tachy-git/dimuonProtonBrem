#!/usr/bin/env python3
import argparse
import math
import os
import sys


TREE_PATH = "dimuonAnalyzer/tree"
PROGRESS_EVERY = 100000

MUON_PREFIX = "muon"
BEST_VERTEX_PREFIX = "muonVertex"
STA_VERTEX_PREFIX = "muonStaVertex"
DISPLACED_MUON_PREFIX = "disMuon"
DISPLACED_VERTEX_PREFIX = "disMuonVertex"
DISPLACED_STA_VERTEX_PREFIX = "disMuonStaVertex"

KINVALID = -900.0
MATCH_DR_MAX = 0.3

MASS_BINS = 500
MASS_MIN = 0.0
MASS_MAX = 5.0

PT_BINS = 100
PT_MIN = 0.0
PT_MAX = 50.0

PT_ERROR_BINS = 60
PT_ERROR_MIN = 0.0
PT_ERROR_MAX = 3.0

PT_RATIO_BINS = 400
PT_RATIO_MIN = 0.0
PT_RATIO_MAX = 2.0

REL_PT_ERROR_BINS = 100
REL_PT_ERROR_MIN = 0.0
REL_PT_ERROR_MAX = 1.0

PT_PULL_BINS = 500
PT_PULL_MIN = -10.0
PT_PULL_MAX = 10.0

ABS_D0_BINS = 500
ABS_D0_MIN = 0.0
ABS_D0_MAX = 50.0

D0_ERROR_BINS = 1000
D0_ERROR_MIN = 0.0
D0_ERROR_MAX = 10.0

REL_D0_ERROR_BINS = 500
REL_D0_ERROR_MIN = 0.0
REL_D0_ERROR_MAX = 50.0

ABS_ETA_BINS = 60
ABS_ETA_MIN = 0.0
ABS_ETA_MAX = 3.0


def parse_cli():
    parser = argparse.ArgumentParser(
        description="Create resolution histograms from one dimuonAnalyzer ROOT file."
    )
    parser.add_argument("input_root", help="input dimuonAnalyzer ROOT file")
    parser.add_argument("output_root", help="output histogram ROOT file")
    parser.add_argument(
        "--max-events",
        type=int,
        default=-1,
        help="maximum entries to process; -1 means all",
    )
    args = parser.parse_args()
    if args.max_events == 0 or args.max_events < -1:
        parser.error("--max-events must be -1 or a positive integer")
    return args


def get_root():
    import ROOT

    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kError
    ROOT.TH1.AddDirectory(False)
    return ROOT


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def vector_to_floats(values):
    return [float(value) for value in values]


def vector_to_ints(values):
    return [int(value) for value in values]


def is_valid_number(value):
    return math.isfinite(value) and value > KINVALID


def valid_muon(pt, eta, phi, charge):
    return (
        is_valid_number(pt)
        and pt > 0.0
        and is_valid_number(eta)
        and is_valid_number(phi)
        and charge != 0
    )


def delta_r(ROOT, eta1, phi1, eta2, phi2):
    delta_phi = ROOT.TVector2.Phi_mpi_pi(phi1 - phi2)
    return math.hypot(eta1 - eta2, delta_phi)


def make_gen_records(entry):
    pts = vector_to_floats(entry.genMuon_pt)
    etas = vector_to_floats(entry.genMuon_eta)
    phis = vector_to_floats(entry.genMuon_phi)
    charges = vector_to_ints(entry.genMuon_charge)

    records = []
    for index in range(min(len(pts), len(etas), len(phis), len(charges))):
        if not valid_muon(pts[index], etas[index], phis[index], charges[index]):
            continue
        records.append(
            {
                "index": index,
                "pt": pts[index],
                "eta": etas[index],
                "phi": phis[index],
                "charge": charges[index],
            }
        )
    return records


def make_best_track_records(entry):
    pts = vector_to_floats(getattr(entry, f"{MUON_PREFIX}_pt"))
    pt_errors = vector_to_floats(getattr(entry, f"{MUON_PREFIX}_ptError"))
    d0s = vector_to_floats(getattr(entry, f"{MUON_PREFIX}_d0"))
    d0_errors = vector_to_floats(getattr(entry, f"{MUON_PREFIX}_d0Error"))
    etas = vector_to_floats(getattr(entry, f"{MUON_PREFIX}_eta"))
    phis = vector_to_floats(getattr(entry, f"{MUON_PREFIX}_phi"))
    charges = vector_to_ints(getattr(entry, f"{MUON_PREFIX}_charge"))

    records = []
    n_muons = min(len(pts), len(etas), len(phis), len(charges))
    for index in range(n_muons):
        if not valid_muon(pts[index], etas[index], phis[index], charges[index]):
            continue

        records.append(
            {
                "index": index,
                "pt": pts[index],
                "pt_error": pt_errors[index] if index < len(pt_errors) else KINVALID,
                "d0": d0s[index] if index < len(d0s) else KINVALID,
                "d0_error": d0_errors[index] if index < len(d0_errors) else KINVALID,
                "eta": etas[index],
                "phi": phis[index],
                "charge": charges[index],
            }
        )
    return records


def make_standalone_track_records(entry, prefix=MUON_PREFIX):
    has_sta = vector_to_ints(getattr(entry, f"{prefix}_hasStandAloneMuon"))
    pts = vector_to_floats(getattr(entry, f"{prefix}_standAloneMuon_pt"))
    pt_errors = vector_to_floats(
        getattr(entry, f"{prefix}_standAloneMuon_ptError")
    )
    d0s = vector_to_floats(getattr(entry, f"{prefix}_standAloneMuon_d0"))
    d0_errors = vector_to_floats(
        getattr(entry, f"{prefix}_standAloneMuon_d0Error")
    )
    etas = vector_to_floats(getattr(entry, f"{prefix}_standAloneMuon_eta"))
    phis = vector_to_floats(getattr(entry, f"{prefix}_standAloneMuon_phi"))
    charges = vector_to_ints(getattr(entry, f"{prefix}_standAloneMuon_charge"))

    records = []
    n_muons = min(
        len(has_sta), len(pts), len(pt_errors), len(etas), len(phis), len(charges)
    )
    for index in range(n_muons):
        if has_sta[index] != 1:
            continue
        if not valid_muon(pts[index], etas[index], phis[index], charges[index]):
            continue
        records.append(
            {
                "index": index,
                "pt": pts[index],
                "pt_error": pt_errors[index],
                "d0": d0s[index] if index < len(d0s) else KINVALID,
                "d0_error": d0_errors[index] if index < len(d0_errors) else KINVALID,
                "eta": etas[index],
                "phi": phis[index],
                "charge": charges[index],
            }
        )
    return records


def make_displaced_muon_records(entry):
    prefix = DISPLACED_MUON_PREFIX
    pts = vector_to_floats(getattr(entry, f"{prefix}_pt"))
    pt_errors = vector_to_floats(getattr(entry, f"{prefix}_ptError"))
    d0s = vector_to_floats(getattr(entry, f"{prefix}_d0"))
    d0_errors = vector_to_floats(getattr(entry, f"{prefix}_d0Error"))
    etas = vector_to_floats(getattr(entry, f"{prefix}_eta"))
    phis = vector_to_floats(getattr(entry, f"{prefix}_phi"))
    charges = vector_to_ints(getattr(entry, f"{prefix}_charge"))

    records = []
    n_muons = min(len(pts), len(etas), len(phis), len(charges))
    for index in range(n_muons):
        if not valid_muon(pts[index], etas[index], phis[index], charges[index]):
            continue
        records.append(
            {
                "index": index,
                "pt": pts[index],
                "pt_error": pt_errors[index] if index < len(pt_errors) else KINVALID,
                "d0": d0s[index] if index < len(d0s) else KINVALID,
                "d0_error": d0_errors[index] if index < len(d0_errors) else KINVALID,
                "eta": etas[index],
                "phi": phis[index],
                "charge": charges[index],
            }
        )
    return records


def match_gen_to_muons_by_dr(ROOT, gen_muons, muons):
    candidates = []
    for gen_pos, gen_muon in enumerate(gen_muons):
        for muon_pos, muon in enumerate(muons):
            if muon["charge"] != gen_muon["charge"]:
                continue
            dr = delta_r(ROOT, gen_muon["eta"], gen_muon["phi"], muon["eta"], muon["phi"])
            if math.isfinite(dr) and dr < MATCH_DR_MAX:
                candidates.append((dr, gen_pos, muon_pos))

    matches = []
    used_gen = set()
    used_muons = set()
    for dr, gen_pos, muon_pos in sorted(candidates):
        if gen_pos in used_gen or muon_pos in used_muons:
            continue
        used_gen.add(gen_pos)
        used_muons.add(muon_pos)
        matches.append({"gen": gen_muons[gen_pos], "muon": muons[muon_pos], "dr": dr})
    return matches


def opposite_sign_matches(matches):
    """Return matches whose gen muon belongs to at least one OS matched pair."""
    selected = []
    for index, match in enumerate(matches):
        gen_muon = match["gen"]
        if any(
            other_index != index
            and other["gen"]["index"] != gen_muon["index"]
            and other["gen"]["charge"] * gen_muon["charge"] < 0
            for other_index, other in enumerate(matches)
        ):
            selected.append(match)
    return selected


def common_best_and_standalone_matches(best_matches, standalone_matches):
    """Select parent muons whose two tracks match the same gen muon in an OS pair."""
    best_by_index = {match["muon"]["index"]: match for match in best_matches}
    standalone_by_index = {
        match["muon"]["index"]: match for match in standalone_matches
    }
    common_best = []
    common_standalone_by_index = {}
    for muon_index in best_by_index.keys() & standalone_by_index.keys():
        best_match = best_by_index[muon_index]
        standalone_match = standalone_by_index[muon_index]
        if best_match["gen"]["index"] != standalone_match["gen"]["index"]:
            continue
        common_best.append(best_match)
        common_standalone_by_index[muon_index] = standalone_match

    selected_best = opposite_sign_matches(common_best)
    selected_standalone = [
        common_standalone_by_index[match["muon"]["index"]]
        for match in selected_best
    ]
    return selected_best, selected_standalone


def make_histograms(ROOT):
    histograms = {
        "bestPt": ROOT.TH1F(
            "h_bestTrack_pt",
            "slimmedMuon best-track p_{T};p_{T}^{best} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "bestGenPt": ROOT.TH1F(
            "h_bestTrack_genPt",
            "gen p_{T} matched to slimmedMuon best tracks;p_{T}^{gen} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "standalonePt": ROOT.TH1F(
            "h_standAloneTrack_pt",
            "slimmedMuon standalone-track p_{T};p_{T}^{STA} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "standaloneGenPt": ROOT.TH1F(
            "h_standAloneTrack_genPt",
            "gen p_{T} matched to slimmedMuon standalone tracks;p_{T}^{gen} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "bestPtError": ROOT.TH1F(
            "h_bestTrack_ptError",
            "slimmedMuon best-track #sigma(p_{T});#sigma(p_{T}^{best}) [GeV];Weighted muons",
            PT_ERROR_BINS,
            PT_ERROR_MIN,
            PT_ERROR_MAX,
        ),
        "standalonePtError": ROOT.TH1F(
            "h_standAloneTrack_ptError",
            "slimmedMuon standalone-track #sigma(p_{T});#sigma(p_{T}^{STA}) [GeV];Weighted muons",
            PT_ERROR_BINS,
            PT_ERROR_MIN,
            PT_ERROR_MAX,
        ),
        "bestPtOverGenPt": ROOT.TH1F(
            "h_bestTrack_ptOverGenPt",
            "slimmedMuon best-track p_{T}/gen p_{T};p_{T}^{best}/p_{T}^{gen};Weighted muons",
            PT_RATIO_BINS,
            PT_RATIO_MIN,
            PT_RATIO_MAX,
        ),
        "standalonePtOverGenPt": ROOT.TH1F(
            "h_standAloneTrack_ptOverGenPt",
            "slimmedMuon standalone-track p_{T}/gen p_{T};p_{T}^{STA}/p_{T}^{gen};Weighted muons",
            PT_RATIO_BINS,
            PT_RATIO_MIN,
            PT_RATIO_MAX,
        ),
        "bestRelativePtError": ROOT.TH1F(
            "h_bestTrack_relativePtError",
            "slimmedMuon best-track relative p_{T} uncertainty;#sigma(p_{T}^{best})/p_{T}^{best};Weighted muons",
            REL_PT_ERROR_BINS,
            REL_PT_ERROR_MIN,
            REL_PT_ERROR_MAX,
        ),
        "standaloneRelativePtError": ROOT.TH1F(
            "h_standAloneTrack_relativePtError",
            "slimmedMuon standalone-track relative p_{T} uncertainty;#sigma(p_{T}^{STA})/p_{T}^{STA};Weighted muons",
            REL_PT_ERROR_BINS,
            REL_PT_ERROR_MIN,
            REL_PT_ERROR_MAX,
        ),
        "bestPtPull": ROOT.TH1F(
            "h_bestTrack_ptPull",
            "slimmedMuon best-track p_{T} pull;(p_{T}^{best}-p_{T}^{gen})/#sigma(p_{T}^{best});Weighted muons",
            PT_PULL_BINS,
            PT_PULL_MIN,
            PT_PULL_MAX,
        ),
        "standalonePtPull": ROOT.TH1F(
            "h_standAloneTrack_ptPull",
            "slimmedMuon standalone-track p_{T} pull;(p_{T}^{STA}-p_{T}^{gen})/#sigma(p_{T}^{STA});Weighted muons",
            PT_PULL_BINS,
            PT_PULL_MIN,
            PT_PULL_MAX,
        ),
        "bestAbsD0": ROOT.TH1F(
            "h_bestTrack_absD0",
            "slimmedMuon best-track |d0|;|d0^{best}| [cm];Weighted muons",
            ABS_D0_BINS,
            ABS_D0_MIN,
            ABS_D0_MAX,
        ),
        "standaloneAbsD0": ROOT.TH1F(
            "h_standAloneTrack_absD0",
            "slimmedMuon standalone-track |d0|;|d0^{STA}| [cm];Weighted muons",
            ABS_D0_BINS,
            ABS_D0_MIN,
            ABS_D0_MAX,
        ),
        "bestD0Error": ROOT.TH1F(
            "h_bestTrack_d0Error",
            "slimmedMuon best-track #sigma(d0);#sigma(d0^{best}) [cm];Weighted muons",
            D0_ERROR_BINS,
            D0_ERROR_MIN,
            D0_ERROR_MAX,
        ),
        "standaloneD0Error": ROOT.TH1F(
            "h_standAloneTrack_d0Error",
            "slimmedMuon standalone-track #sigma(d0);#sigma(d0^{STA}) [cm];Weighted muons",
            D0_ERROR_BINS,
            D0_ERROR_MIN,
            D0_ERROR_MAX,
        ),
        "bestRelativeD0Error": ROOT.TH1F(
            "h_bestTrack_relativeD0Error",
            "slimmedMuon best-track relative d0 uncertainty;#sigma(d0^{best})/|d0^{best}|;Weighted muons",
            REL_D0_ERROR_BINS,
            REL_D0_ERROR_MIN,
            REL_D0_ERROR_MAX,
        ),
        "standaloneRelativeD0Error": ROOT.TH1F(
            "h_standAloneTrack_relativeD0Error",
            "slimmedMuon standalone-track relative d0 uncertainty;#sigma(d0^{STA})/|d0^{STA}|;Weighted muons",
            REL_D0_ERROR_BINS,
            REL_D0_ERROR_MIN,
            REL_D0_ERROR_MAX,
        ),
        "bestVertexFitMass": ROOT.TH1F(
            "h_bestTrackFit_mass",
            "muonVertex fitted mass using best tracks;m_{#mu#mu}^{best fit} [GeV];Weighted vertices",
            MASS_BINS,
            MASS_MIN,
            MASS_MAX,
        ),
        "standaloneVertexFitMass": ROOT.TH1F(
            "h_standAloneTrackFit_mass",
            "muonStaVertex fitted mass using standalone tracks;m_{#mu#mu}^{STA fit} [GeV];Weighted vertices",
            MASS_BINS,
            MASS_MIN,
            MASS_MAX,
        ),
        "bestRefitGenPt": ROOT.TH1F(
            "h_bestTrackFit_refitMuon_genPt",
            "gen p_{T} matched to best-track vertex-refit muons;p_{T}^{gen} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "bestRefitPt": ROOT.TH1F(
            "h_bestTrackFit_refitMuon_pt",
            "best-track vertex-refit muon p_{T};p_{T}^{refit} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "bestRefitPtOverGenPt": ROOT.TH1F(
            "h_bestTrackFit_refitMuon_ptOverGenPt",
            "best-track vertex-refit muon p_{T}/gen p_{T};p_{T}^{refit}/p_{T}^{gen};Weighted muons",
            PT_RATIO_BINS,
            PT_RATIO_MIN,
            PT_RATIO_MAX,
        ),
        "standaloneRefitGenPt": ROOT.TH1F(
            "h_standAloneTrackFit_refitMuon_genPt",
            "gen p_{T} matched to standalone-track vertex-refit muons;p_{T}^{gen} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "standaloneRefitPt": ROOT.TH1F(
            "h_standAloneTrackFit_refitMuon_pt",
            "standalone-track vertex-refit muon p_{T};p_{T}^{refit} [GeV];Weighted muons",
            PT_BINS,
            PT_MIN,
            PT_MAX,
        ),
        "standaloneRefitPtOverGenPt": ROOT.TH1F(
            "h_standAloneTrackFit_refitMuon_ptOverGenPt",
            "standalone-track vertex-refit muon p_{T}/gen p_{T};p_{T}^{refit}/p_{T}^{gen};Weighted muons",
            PT_RATIO_BINS,
            PT_RATIO_MIN,
            PT_RATIO_MAX,
        ),
    }

    for key, name, title in (
        ("bestPullVsGenPt", "h2_bestTrack_ptPull_vs_genPt", "best-track p_{T} pull vs gen p_{T};p_{T}^{gen} [GeV];(p_{T}^{best}-p_{T}^{gen})/#sigma(p_{T}^{best})"),
        ("standalonePullVsGenPt", "h2_standAloneTrack_ptPull_vs_genPt", "standalone-track p_{T} pull vs gen p_{T};p_{T}^{gen} [GeV];(p_{T}^{STA}-p_{T}^{gen})/#sigma(p_{T}^{STA})"),
    ):
        histograms[key] = ROOT.TH2F(
            name, title, PT_BINS, PT_MIN, PT_MAX,
            PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX
        )

    for key, name, title in (
        ("bestPullVsAbsEta", "h2_bestTrack_ptPull_vs_absEta", "best-track p_{T} pull vs |#eta^{gen}|;|#eta^{gen}|;(p_{T}^{best}-p_{T}^{gen})/#sigma(p_{T}^{best})"),
        ("standalonePullVsAbsEta", "h2_standAloneTrack_ptPull_vs_absEta", "standalone-track p_{T} pull vs |#eta^{gen}|;|#eta^{gen}|;(p_{T}^{STA}-p_{T}^{gen})/#sigma(p_{T}^{STA})"),
    ):
        histograms[key] = ROOT.TH2F(
            name, title, ABS_ETA_BINS, ABS_ETA_MIN, ABS_ETA_MAX,
            PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX
        )

    histograms["bestVsStandaloneRelativePtError"] = ROOT.TH2F(
        "h2_bestTrack_vs_standAloneTrack_relativePtError",
        "best-track vs standalone-track relative p_{T} uncertainty;"
        "#sigma(p_{T}^{best})/p_{T}^{best};"
        "#sigma(p_{T}^{STA})/p_{T}^{STA}",
        REL_PT_ERROR_BINS,
        REL_PT_ERROR_MIN,
        REL_PT_ERROR_MAX,
        REL_PT_ERROR_BINS,
        REL_PT_ERROR_MIN,
        REL_PT_ERROR_MAX,
    )

    for key, name, title in (
        (
            "bestRelativeD0ErrorVsAbsD0",
            "h2_bestTrack_relativeD0Error_vs_absD0",
            "best-track relative d0 uncertainty vs |d0|;|d0^{best}| [cm];#sigma(d0^{best})/|d0^{best}|",
        ),
        (
            "standaloneRelativeD0ErrorVsAbsD0",
            "h2_standAloneTrack_relativeD0Error_vs_absD0",
            "standalone-track relative d0 uncertainty vs |d0|;|d0^{STA}| [cm];#sigma(d0^{STA})/|d0^{STA}|",
        ),
    ):
        histograms[key] = ROOT.TH2F(
            name,
            title,
            ABS_D0_BINS,
            ABS_D0_MIN,
            ABS_D0_MAX,
            REL_D0_ERROR_BINS,
            REL_D0_ERROR_MIN,
            REL_D0_ERROR_MAX,
        )

    histograms["bestVsStandaloneRelativeD0Error"] = ROOT.TH2F(
        "h2_bestTrack_vs_standAloneTrack_relativeD0Error",
        "best-track vs standalone-track relative d0 uncertainty;"
        "#sigma(d0^{best})/|d0^{best}|;"
        "#sigma(d0^{STA})/|d0^{STA}|",
        REL_D0_ERROR_BINS,
        REL_D0_ERROR_MIN,
        REL_D0_ERROR_MAX,
        REL_D0_ERROR_BINS,
        REL_D0_ERROR_MIN,
        REL_D0_ERROR_MAX,
    )

    histograms.update(
        {
            "disPt": ROOT.TH1F(
                "h_pt", "displaced slimmed-muon p_{T};p_{T} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disGenPt": ROOT.TH1F(
                "h_genPt", "gen p_{T} matched to displaced slimmed muons;p_{T}^{gen} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disPtError": ROOT.TH1F(
                "h_ptError", "displaced slimmed-muon #sigma(p_{T});#sigma(p_{T}) [GeV];Weighted muons",
                PT_ERROR_BINS, PT_ERROR_MIN, PT_ERROR_MAX,
            ),
            "disPtOverGenPt": ROOT.TH1F(
                "h_ptOverGenPt", "displaced slimmed-muon p_{T}/gen p_{T};p_{T}/p_{T}^{gen};Weighted muons",
                PT_RATIO_BINS, PT_RATIO_MIN, PT_RATIO_MAX,
            ),
            "disRelativePtError": ROOT.TH1F(
                "h_relativePtError", "displaced slimmed-muon relative p_{T} uncertainty;#sigma(p_{T})/p_{T};Weighted muons",
                REL_PT_ERROR_BINS, REL_PT_ERROR_MIN, REL_PT_ERROR_MAX,
            ),
            "disPtPull": ROOT.TH1F(
                "h_ptPull", "displaced slimmed-muon p_{T} pull;(p_{T}-p_{T}^{gen})/#sigma(p_{T});Weighted muons",
                PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX,
            ),
            "disAbsD0": ROOT.TH1F(
                "h_absD0", "displaced slimmed-muon |d0|;|d0| [cm];Weighted muons",
                ABS_D0_BINS, ABS_D0_MIN, ABS_D0_MAX,
            ),
            "disD0Error": ROOT.TH1F(
                "h_d0Error", "displaced slimmed-muon #sigma(d0);#sigma(d0) [cm];Weighted muons",
                D0_ERROR_BINS, D0_ERROR_MIN, D0_ERROR_MAX,
            ),
            "disRelativeD0Error": ROOT.TH1F(
                "h_relativeD0Error", "displaced slimmed-muon relative d0 uncertainty;#sigma(d0)/|d0|;Weighted muons",
                REL_D0_ERROR_BINS, REL_D0_ERROR_MIN, REL_D0_ERROR_MAX,
            ),
            "disVertexFitMass": ROOT.TH1F(
                "h_vertexFit_mass", "displaced slimmed-muon fitted mass;m_{#mu#mu}^{fit} [GeV];Weighted vertices",
                MASS_BINS, MASS_MIN, MASS_MAX,
            ),
            "disRefitGenPt": ROOT.TH1F(
                "h_vertexFit_refitMuon_genPt", "gen p_{T} matched to displaced-muon vertex-refit muons;p_{T}^{gen} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disRefitPt": ROOT.TH1F(
                "h_vertexFit_refitMuon_pt", "displaced-muon vertex-refit muon p_{T};p_{T}^{refit} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disRefitPtOverGenPt": ROOT.TH1F(
                "h_vertexFit_refitMuon_ptOverGenPt", "displaced-muon vertex-refit p_{T}/gen p_{T};p_{T}^{refit}/p_{T}^{gen};Weighted muons",
                PT_RATIO_BINS, PT_RATIO_MIN, PT_RATIO_MAX,
            ),
            "disPullVsGenPt": ROOT.TH2F(
                "h2_ptPull_vs_genPt", "displaced slimmed-muon p_{T} pull vs gen p_{T};p_{T}^{gen} [GeV];(p_{T}-p_{T}^{gen})/#sigma(p_{T})",
                PT_BINS, PT_MIN, PT_MAX, PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX,
            ),
            "disPullVsAbsEta": ROOT.TH2F(
                "h2_ptPull_vs_absEta", "displaced slimmed-muon p_{T} pull vs |#eta^{gen}|;|#eta^{gen}|;(p_{T}-p_{T}^{gen})/#sigma(p_{T})",
                ABS_ETA_BINS, ABS_ETA_MIN, ABS_ETA_MAX, PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX,
            ),
            "disRelativeD0ErrorVsAbsD0": ROOT.TH2F(
                "h2_relativeD0Error_vs_absD0", "displaced slimmed-muon relative d0 uncertainty vs |d0|;|d0| [cm];#sigma(d0)/|d0|",
                ABS_D0_BINS, ABS_D0_MIN, ABS_D0_MAX,
                REL_D0_ERROR_BINS, REL_D0_ERROR_MIN, REL_D0_ERROR_MAX,
            ),
            "disStandalonePt": ROOT.TH1F(
                "h_standAloneTrack_pt", "displaced-muon standalone-track p_{T};p_{T}^{STA} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disStandaloneGenPt": ROOT.TH1F(
                "h_standAloneTrack_genPt", "gen p_{T} matched to displaced standalone tracks;p_{T}^{gen} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disStandalonePtError": ROOT.TH1F(
                "h_standAloneTrack_ptError", "displaced standalone-track #sigma(p_{T});#sigma(p_{T}^{STA}) [GeV];Weighted muons",
                PT_ERROR_BINS, PT_ERROR_MIN, PT_ERROR_MAX,
            ),
            "disStandalonePtOverGenPt": ROOT.TH1F(
                "h_standAloneTrack_ptOverGenPt", "displaced standalone-track p_{T}/gen p_{T};p_{T}^{STA}/p_{T}^{gen};Weighted muons",
                PT_RATIO_BINS, PT_RATIO_MIN, PT_RATIO_MAX,
            ),
            "disStandaloneRelativePtError": ROOT.TH1F(
                "h_standAloneTrack_relativePtError", "displaced standalone-track relative p_{T} uncertainty;#sigma(p_{T}^{STA})/p_{T}^{STA};Weighted muons",
                REL_PT_ERROR_BINS, REL_PT_ERROR_MIN, REL_PT_ERROR_MAX,
            ),
            "disStandalonePtPull": ROOT.TH1F(
                "h_standAloneTrack_ptPull", "displaced standalone-track p_{T} pull;(p_{T}^{STA}-p_{T}^{gen})/#sigma(p_{T}^{STA});Weighted muons",
                PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX,
            ),
            "disStandaloneAbsD0": ROOT.TH1F(
                "h_standAloneTrack_absD0", "displaced standalone-track |d0|;|d0^{STA}| [cm];Weighted muons",
                ABS_D0_BINS, ABS_D0_MIN, ABS_D0_MAX,
            ),
            "disStandaloneD0Error": ROOT.TH1F(
                "h_standAloneTrack_d0Error", "displaced standalone-track #sigma(d0);#sigma(d0^{STA}) [cm];Weighted muons",
                D0_ERROR_BINS, D0_ERROR_MIN, D0_ERROR_MAX,
            ),
            "disStandaloneRelativeD0Error": ROOT.TH1F(
                "h_standAloneTrack_relativeD0Error", "displaced standalone-track relative d0 uncertainty;#sigma(d0^{STA})/|d0^{STA}|;Weighted muons",
                REL_D0_ERROR_BINS, REL_D0_ERROR_MIN, REL_D0_ERROR_MAX,
            ),
            "disStandaloneVertexFitMass": ROOT.TH1F(
                "h_standAloneTrackFit_mass", "disMuonStaVertex fitted mass;m_{#mu#mu}^{STA fit} [GeV];Weighted vertices",
                MASS_BINS, MASS_MIN, MASS_MAX,
            ),
            "disStandaloneRefitGenPt": ROOT.TH1F(
                "h_standAloneTrackFit_refitMuon_genPt", "gen p_{T} matched to displaced standalone vertex-refit muons;p_{T}^{gen} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disStandaloneRefitPt": ROOT.TH1F(
                "h_standAloneTrackFit_refitMuon_pt", "displaced standalone vertex-refit muon p_{T};p_{T}^{refit} [GeV];Weighted muons",
                PT_BINS, PT_MIN, PT_MAX,
            ),
            "disStandaloneRefitPtOverGenPt": ROOT.TH1F(
                "h_standAloneTrackFit_refitMuon_ptOverGenPt", "displaced standalone vertex-refit p_{T}/gen p_{T};p_{T}^{refit}/p_{T}^{gen};Weighted muons",
                PT_RATIO_BINS, PT_RATIO_MIN, PT_RATIO_MAX,
            ),
            "disStandalonePullVsGenPt": ROOT.TH2F(
                "h2_standAloneTrack_ptPull_vs_genPt", "displaced standalone-track p_{T} pull vs gen p_{T};p_{T}^{gen} [GeV];(p_{T}^{STA}-p_{T}^{gen})/#sigma(p_{T}^{STA})",
                PT_BINS, PT_MIN, PT_MAX, PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX,
            ),
            "disStandalonePullVsAbsEta": ROOT.TH2F(
                "h2_standAloneTrack_ptPull_vs_absEta", "displaced standalone-track p_{T} pull vs |#eta^{gen}|;|#eta^{gen}|;(p_{T}^{STA}-p_{T}^{gen})/#sigma(p_{T}^{STA})",
                ABS_ETA_BINS, ABS_ETA_MIN, ABS_ETA_MAX, PT_PULL_BINS, PT_PULL_MIN, PT_PULL_MAX,
            ),
            "disStandaloneRelativeD0ErrorVsAbsD0": ROOT.TH2F(
                "h2_standAloneTrack_relativeD0Error_vs_absD0", "displaced standalone relative d0 uncertainty vs |d0|;|d0^{STA}| [cm];#sigma(d0^{STA})/|d0^{STA}|",
                ABS_D0_BINS, ABS_D0_MIN, ABS_D0_MAX,
                REL_D0_ERROR_BINS, REL_D0_ERROR_MIN, REL_D0_ERROR_MAX,
            ),
            "disBestVsStandaloneRelativePtError": ROOT.TH2F(
                "h2_bestTrack_vs_standAloneTrack_relativePtError",
                "displaced best vs standalone relative p_{T} uncertainty;#sigma(p_{T}^{best})/p_{T}^{best};#sigma(p_{T}^{STA})/p_{T}^{STA}",
                REL_PT_ERROR_BINS, REL_PT_ERROR_MIN, REL_PT_ERROR_MAX,
                REL_PT_ERROR_BINS, REL_PT_ERROR_MIN, REL_PT_ERROR_MAX,
            ),
            "disBestVsStandaloneRelativeD0Error": ROOT.TH2F(
                "h2_bestTrack_vs_standAloneTrack_relativeD0Error",
                "displaced best vs standalone relative d0 uncertainty;#sigma(d0^{best})/|d0^{best}|;#sigma(d0^{STA})/|d0^{STA}|",
                REL_D0_ERROR_BINS, REL_D0_ERROR_MIN, REL_D0_ERROR_MAX,
                REL_D0_ERROR_BINS, REL_D0_ERROR_MIN, REL_D0_ERROR_MAX,
            ),
        }
    )

    for hist in histograms.values():
        hist.SetDirectory(0)
        hist.Sumw2()
    return histograms


def validate_tree(tree):
    if not tree or not tree.InheritsFrom("TTree"):
        raise RuntimeError(f"Could not find TTree: {TREE_PATH}")

    required = [
        "eventWeight",
        "genMuon_pt",
        "genMuon_eta",
        "genMuon_phi",
        "genMuon_charge",
        "muon_pt",
        "muon_ptError",
        "muon_d0",
        "muon_d0Error",
        "muon_eta",
        "muon_phi",
        "muon_charge",
        "muon_hasStandAloneMuon",
        "muon_standAloneMuon_pt",
        "muon_standAloneMuon_ptError",
        "muon_standAloneMuon_d0",
        "muon_standAloneMuon_d0Error",
        "muon_standAloneMuon_eta",
        "muon_standAloneMuon_phi",
        "muon_standAloneMuon_charge",
        "muonVertex_mu1Index",
        "muonVertex_mu2Index",
        "muonVertex_isValid",
        "muonVertex_mass",
        "muonVertex_refit_mu1_pt",
        "muonVertex_refit_mu2_pt",
        "muonStaVertex_mu1Index",
        "muonStaVertex_mu2Index",
        "muonStaVertex_isValid",
        "muonStaVertex_mass",
        "muonStaVertex_refit_mu1_pt",
        "muonStaVertex_refit_mu2_pt",
        "disMuon_pt",
        "disMuon_ptError",
        "disMuon_d0",
        "disMuon_d0Error",
        "disMuon_eta",
        "disMuon_phi",
        "disMuon_charge",
        "disMuon_hasStandAloneMuon",
        "disMuon_standAloneMuon_pt",
        "disMuon_standAloneMuon_ptError",
        "disMuon_standAloneMuon_d0",
        "disMuon_standAloneMuon_d0Error",
        "disMuon_standAloneMuon_eta",
        "disMuon_standAloneMuon_phi",
        "disMuon_standAloneMuon_charge",
        "disMuonVertex_mu1Index",
        "disMuonVertex_mu2Index",
        "disMuonVertex_isValid",
        "disMuonVertex_mass",
        "disMuonVertex_refit_mu1_pt",
        "disMuonVertex_refit_mu2_pt",
        "disMuonStaVertex_mu1Index",
        "disMuonStaVertex_mu2Index",
        "disMuonStaVertex_isValid",
        "disMuonStaVertex_mass",
        "disMuonStaVertex_refit_mu1_pt",
        "disMuonStaVertex_refit_mu2_pt",
    ]
    missing = [branch for branch in required if not tree.GetBranch(branch)]
    if missing:
        message = "Missing required branch(es): " + ", ".join(missing)
        if any(
            branch in missing
            for branch in (
                "muon_ptError",
                "muon_d0",
                "muon_d0Error",
                "muon_standAloneMuon_ptError",
                "muon_standAloneMuon_d0",
                "muon_standAloneMuon_d0Error",
                "disMuon_ptError",
                "disMuon_d0",
                "disMuon_d0Error",
                "disMuon_standAloneMuon_ptError",
                "disMuon_standAloneMuon_d0",
                "disMuon_standAloneMuon_d0Error",
            )
        ):
            message += (
                ". Regenerate the ntuples with the current dimuonAnalyzer.cc; "
                "track-resolution quantities cannot be recovered from older files"
            )
        raise RuntimeError(message)


def fill_if_valid(hist, value, weight):
    if is_valid_number(value):
        hist.Fill(value, weight)


def fill_track_resolution(histograms, prefix, track, gen_muon, weight):
    """Fill the requested observables for one OS-pair-selected matched track."""
    pt = track["pt"]
    pt_error = track["pt_error"]
    d0 = track["d0"]
    d0_error = track["d0_error"]
    gen_pt = gen_muon["pt"]
    abs_gen_eta = abs(gen_muon["eta"])

    histograms[f"{prefix}Pt"].Fill(pt, weight)
    histograms[f"{prefix}GenPt"].Fill(gen_pt, weight)
    if gen_pt > 0.0:
        histograms[f"{prefix}PtOverGenPt"].Fill(pt / gen_pt, weight)

    if is_valid_number(d0):
        abs_d0 = abs(d0)
        histograms[f"{prefix}AbsD0"].Fill(abs_d0, weight)
        if math.isfinite(d0_error) and d0_error > 0.0:
            histograms[f"{prefix}D0Error"].Fill(d0_error, weight)
            if abs_d0 > 0.0:
                relative_d0_error = d0_error / abs_d0
                histograms[f"{prefix}RelativeD0Error"].Fill(
                    relative_d0_error, weight
                )
                histograms[f"{prefix}RelativeD0ErrorVsAbsD0"].Fill(
                    abs_d0, relative_d0_error, weight
                )

    if pt <= 0.0 or not math.isfinite(pt_error) or pt_error <= 0.0:
        return

    pull = (pt - gen_pt) / pt_error
    histograms[f"{prefix}PtError"].Fill(pt_error, weight)
    histograms[f"{prefix}RelativePtError"].Fill(pt_error / pt, weight)
    histograms[f"{prefix}PtPull"].Fill(pull, weight)
    histograms[f"{prefix}PullVsGenPt"].Fill(gen_pt, pull, weight)
    histograms[f"{prefix}PullVsAbsEta"].Fill(abs_gen_eta, pull, weight)


def fill_matched_vertex_refit_pt(
    entry, histograms, histogram_prefix, vertex_prefix, match_by_muon_index, weight
):
    """Fill per-leg refit pT for valid vertices matched to an OS gen pair."""
    mu1_indices = vector_to_ints(getattr(entry, f"{vertex_prefix}_mu1Index"))
    mu2_indices = vector_to_ints(getattr(entry, f"{vertex_prefix}_mu2Index"))
    is_valids = vector_to_ints(getattr(entry, f"{vertex_prefix}_isValid"))
    refit_mu1_pts = vector_to_floats(
        getattr(entry, f"{vertex_prefix}_refit_mu1_pt")
    )
    refit_mu2_pts = vector_to_floats(
        getattr(entry, f"{vertex_prefix}_refit_mu2_pt")
    )
    n_vertices = min(
        len(mu1_indices),
        len(mu2_indices),
        len(is_valids),
        len(refit_mu1_pts),
        len(refit_mu2_pts),
    )

    refit_muon_count = 0
    for index in range(n_vertices):
        if is_valids[index] != 1:
            continue
        match1 = match_by_muon_index.get(mu1_indices[index])
        match2 = match_by_muon_index.get(mu2_indices[index])
        if match1 is None or match2 is None:
            continue
        gen1 = match1["gen"]
        gen2 = match2["gen"]
        if gen1["index"] == gen2["index"] or gen1["charge"] * gen2["charge"] >= 0:
            continue

        for refit_pt, gen_muon in (
            (refit_mu1_pts[index], gen1),
            (refit_mu2_pts[index], gen2),
        ):
            gen_pt = gen_muon["pt"]
            if not is_valid_number(refit_pt) or refit_pt <= 0.0 or gen_pt <= 0.0:
                continue
            histograms[f"{histogram_prefix}RefitGenPt"].Fill(gen_pt, weight)
            histograms[f"{histogram_prefix}RefitPt"].Fill(refit_pt, weight)
            histograms[f"{histogram_prefix}RefitPtOverGenPt"].Fill(
                refit_pt / gen_pt, weight
            )
            refit_muon_count += 1

    return refit_muon_count


def fill_matched_vertices(entry, hist, vertex_prefix, match_by_muon_index, weight):
    """Fill valid vertices whose two tracks match an opposite-sign gen pair."""
    mu1_indices = vector_to_ints(getattr(entry, f"{vertex_prefix}_mu1Index"))
    mu2_indices = vector_to_ints(getattr(entry, f"{vertex_prefix}_mu2Index"))
    is_valids = vector_to_ints(getattr(entry, f"{vertex_prefix}_isValid"))
    fit_masses = vector_to_floats(getattr(entry, f"{vertex_prefix}_mass"))
    n_vertices = min(len(mu1_indices), len(mu2_indices), len(is_valids), len(fit_masses))

    matched_vertex_count = 0
    for index in range(n_vertices):
        if is_valids[index] != 1:
            continue
        match1 = match_by_muon_index.get(mu1_indices[index])
        match2 = match_by_muon_index.get(mu2_indices[index])
        if match1 is None or match2 is None:
            continue
        gen1 = match1["gen"]
        gen2 = match2["gen"]
        if gen1["index"] == gen2["index"] or gen1["charge"] * gen2["charge"] >= 0:
            continue

        matched_vertex_count += 1
        fill_if_valid(hist, fit_masses[index], weight)

    return matched_vertex_count


def valid_matched_vertex_masses(entry, vertex_prefix, match_by_muon_index):
    """Return valid fitted masses keyed by the canonical matched muon-index pair."""
    mu1_indices = vector_to_ints(getattr(entry, f"{vertex_prefix}_mu1Index"))
    mu2_indices = vector_to_ints(getattr(entry, f"{vertex_prefix}_mu2Index"))
    is_valids = vector_to_ints(getattr(entry, f"{vertex_prefix}_isValid"))
    fit_masses = vector_to_floats(getattr(entry, f"{vertex_prefix}_mass"))
    n_vertices = min(len(mu1_indices), len(mu2_indices), len(is_valids), len(fit_masses))

    masses = {}
    for index in range(n_vertices):
        if is_valids[index] != 1 or not is_valid_number(fit_masses[index]):
            continue
        mu1_index = mu1_indices[index]
        mu2_index = mu2_indices[index]
        match1 = match_by_muon_index.get(mu1_index)
        match2 = match_by_muon_index.get(mu2_index)
        if match1 is None or match2 is None:
            continue
        gen1 = match1["gen"]
        gen2 = match2["gen"]
        if gen1["index"] == gen2["index"] or gen1["charge"] * gen2["charge"] >= 0:
            continue
        key = (min(mu1_index, mu2_index), max(mu1_index, mu2_index))
        masses[key] = fit_masses[index]
    return masses


def fill_common_vertex_masses(
    entry,
    best_hist,
    standalone_hist,
    best_vertex_prefix,
    standalone_vertex_prefix,
    common_match_by_index,
    weight,
):
    best_masses = valid_matched_vertex_masses(
        entry, best_vertex_prefix, common_match_by_index
    )
    standalone_masses = valid_matched_vertex_masses(
        entry, standalone_vertex_prefix, common_match_by_index
    )
    common_keys = best_masses.keys() & standalone_masses.keys()
    for key in common_keys:
        best_hist.Fill(best_masses[key], weight)
        standalone_hist.Fill(standalone_masses[key], weight)
    return len(common_keys)


def fill_best_vs_standalone_relative_pt_error(
    hist, best_match_by_index, standalone_match_by_index, weight
):
    """Compare uncertainties when both tracks at one muon index match the same gen muon."""
    for muon_index in best_match_by_index.keys() & standalone_match_by_index.keys():
        best_match = best_match_by_index[muon_index]
        standalone_match = standalone_match_by_index[muon_index]
        if best_match["gen"]["index"] != standalone_match["gen"]["index"]:
            continue
        best = best_match["muon"]
        standalone = standalone_match["muon"]
        if (
            best["pt"] <= 0.0
            or standalone["pt"] <= 0.0
            or not math.isfinite(best["pt_error"])
            or not math.isfinite(standalone["pt_error"])
            or best["pt_error"] <= 0.0
            or standalone["pt_error"] <= 0.0
        ):
            continue
        hist.Fill(
            best["pt_error"] / best["pt"],
            standalone["pt_error"] / standalone["pt"],
            weight,
        )


def fill_best_vs_standalone_relative_d0_error(
    hist, best_match_by_index, standalone_match_by_index, weight
):
    """Compare relative d0 errors for two tracks matched to the same gen muon."""
    for muon_index in best_match_by_index.keys() & standalone_match_by_index.keys():
        best_match = best_match_by_index[muon_index]
        standalone_match = standalone_match_by_index[muon_index]
        if best_match["gen"]["index"] != standalone_match["gen"]["index"]:
            continue
        best = best_match["muon"]
        standalone = standalone_match["muon"]
        if (
            not is_valid_number(best["d0"])
            or not is_valid_number(standalone["d0"])
            or abs(best["d0"]) <= 0.0
            or abs(standalone["d0"]) <= 0.0
            or not math.isfinite(best["d0_error"])
            or not math.isfinite(standalone["d0_error"])
            or best["d0_error"] <= 0.0
            or standalone["d0_error"] <= 0.0
        ):
            continue
        hist.Fill(
            best["d0_error"] / abs(best["d0"]),
            standalone["d0_error"] / abs(standalone["d0"]),
            weight,
        )


def process_file(input_path, output_path, max_events):
    ROOT = get_root()
    root_file = ROOT.TFile.Open(input_path)
    if not root_file or root_file.IsZombie():
        raise RuntimeError(f"Could not open input ROOT file: {input_path}")

    try:
        tree = root_file.Get(TREE_PATH)
        validate_tree(tree)
        histograms = make_histograms(ROOT)
        event_count = 0
        matched_muon_count = 0
        matched_refit_muon_count = 0
        matched_vertex_count = 0
        max_events = None if max_events < 0 else max_events
        total_entries = tree.GetEntries()
        event_limit = total_entries if max_events is None else min(total_entries, max_events)
        print(
            f"[START] pid={os.getpid()} file={os.path.basename(input_path)} "
            f"events={event_limit}/{total_entries}",
            flush=True,
        )

        for entry in tree:
            if max_events is not None and event_count >= max_events:
                break
            event_count += 1
            weight = float(entry.eventWeight)

            gen_muons = make_gen_records(entry)
            best_tracks = make_best_track_records(entry)
            standalone_tracks = make_standalone_track_records(entry)

            best_matches = match_gen_to_muons_by_dr(ROOT, gen_muons, best_tracks)
            standalone_matches = match_gen_to_muons_by_dr(
                ROOT, gen_muons, standalone_tracks
            )
            selected_best_matches, selected_standalone_matches = (
                common_best_and_standalone_matches(best_matches, standalone_matches)
            )

            for match in selected_best_matches:
                fill_track_resolution(
                    histograms, "best", match["muon"], match["gen"], weight
                )
            for match in selected_standalone_matches:
                fill_track_resolution(
                    histograms, "standalone", match["muon"], match["gen"], weight
                )

            best_match_by_index = {
                match["muon"]["index"]: match for match in selected_best_matches
            }
            standalone_match_by_index = {
                match["muon"]["index"]: match
                for match in selected_standalone_matches
            }
            fill_best_vs_standalone_relative_pt_error(
                histograms["bestVsStandaloneRelativePtError"],
                best_match_by_index,
                standalone_match_by_index,
                weight,
            )
            fill_best_vs_standalone_relative_d0_error(
                histograms["bestVsStandaloneRelativeD0Error"],
                best_match_by_index,
                standalone_match_by_index,
                weight,
            )

            matched_refit_muon_count += fill_matched_vertex_refit_pt(
                entry,
                histograms,
                "best",
                BEST_VERTEX_PREFIX,
                best_match_by_index,
                weight,
            )
            matched_refit_muon_count += fill_matched_vertex_refit_pt(
                entry,
                histograms,
                "standalone",
                STA_VERTEX_PREFIX,
                standalone_match_by_index,
                weight,
            )

            matched_vertex_count += fill_common_vertex_masses(
                entry,
                histograms["bestVertexFitMass"],
                histograms["standaloneVertexFitMass"],
                BEST_VERTEX_PREFIX,
                STA_VERTEX_PREFIX,
                best_match_by_index,
                weight,
            )

            displaced_muons = make_displaced_muon_records(entry)
            displaced_standalone_tracks = make_standalone_track_records(
                entry, DISPLACED_MUON_PREFIX
            )
            displaced_best_matches = match_gen_to_muons_by_dr(
                ROOT, gen_muons, displaced_muons
            )
            displaced_standalone_matches = match_gen_to_muons_by_dr(
                ROOT, gen_muons, displaced_standalone_tracks
            )
            selected_displaced_best, selected_displaced_standalone = (
                common_best_and_standalone_matches(
                    displaced_best_matches, displaced_standalone_matches
                )
            )
            for match in selected_displaced_best:
                fill_track_resolution(
                    histograms, "dis", match["muon"], match["gen"], weight
                )
            for match in selected_displaced_standalone:
                fill_track_resolution(
                    histograms,
                    "disStandalone",
                    match["muon"],
                    match["gen"],
                    weight,
                )
            displaced_best_by_index = {
                match["muon"]["index"]: match for match in selected_displaced_best
            }
            displaced_standalone_by_index = {
                match["muon"]["index"]: match
                for match in selected_displaced_standalone
            }
            fill_best_vs_standalone_relative_pt_error(
                histograms["disBestVsStandaloneRelativePtError"],
                displaced_best_by_index,
                displaced_standalone_by_index,
                weight,
            )
            fill_best_vs_standalone_relative_d0_error(
                histograms["disBestVsStandaloneRelativeD0Error"],
                displaced_best_by_index,
                displaced_standalone_by_index,
                weight,
            )
            matched_refit_muon_count += fill_matched_vertex_refit_pt(
                entry,
                histograms,
                "dis",
                DISPLACED_VERTEX_PREFIX,
                displaced_best_by_index,
                weight,
            )
            matched_refit_muon_count += fill_matched_vertex_refit_pt(
                entry,
                histograms,
                "disStandalone",
                DISPLACED_STA_VERTEX_PREFIX,
                displaced_standalone_by_index,
                weight,
            )
            matched_vertex_count += fill_common_vertex_masses(
                entry,
                histograms["disVertexFitMass"],
                histograms["disStandaloneVertexFitMass"],
                DISPLACED_VERTEX_PREFIX,
                DISPLACED_STA_VERTEX_PREFIX,
                displaced_best_by_index,
                weight,
            )
            matched_muon_count += len(selected_best_matches) + len(
                selected_standalone_matches
            ) + len(selected_displaced_best) + len(selected_displaced_standalone)

            if PROGRESS_EVERY > 0 and event_count % PROGRESS_EVERY == 0:
                print(
                    f"[PROGRESS] pid={os.getpid()} file={os.path.basename(input_path)} "
                    f"events={event_count}/{event_limit}",
                    flush=True,
                )

        ensure_dir(os.path.dirname(output_path))
        tmp_output = f"{output_path}.tmp.root"
        output_file = ROOT.TFile.Open(tmp_output, "RECREATE")
        if not output_file or output_file.IsZombie():
            raise RuntimeError(f"Could not create output ROOT file: {tmp_output}")
        try:
            slimmed_directory = output_file.mkdir("slimmedMuon")
            displaced_directory = output_file.mkdir("disMuon")
            for key, hist in histograms.items():
                directory = displaced_directory if key.startswith("dis") else slimmed_directory
                directory.cd()
                hist.Write()
        finally:
            output_file.Close()
        os.replace(tmp_output, output_path)

        print(
            f"[DONE] Wrote {output_path} "
            f"({event_count} events, matched muons={matched_muon_count}, "
            f"matched refit muons={matched_refit_muon_count}, "
            f"matched vertices={matched_vertex_count})",
            flush=True,
        )
        return output_path
    finally:
        root_file.Close()


def main():
    args = parse_cli()
    input_path = os.path.abspath(args.input_root)
    output_path = os.path.abspath(args.output_root)
    if not os.path.isfile(input_path):
        print(f"[ERROR] Input file does not exist: {input_path}", file=sys.stderr)
        return 1
    if input_path == output_path:
        print("[ERROR] Input and output paths must differ", file=sys.stderr)
        return 1

    print(f"[INFO] Input       : {input_path}")
    print(f"[INFO] Output      : {output_path}")
    print(f"[INFO] Tree        : {TREE_PATH}")
    print(
        f"[INFO] Gen match   : common best/standalone parent muons, "
        f"same charge, smallest dR, dR < {MATCH_DR_MAX}"
    )
    print("[INFO] Pair select : opposite-sign matched gen-muon pairs")
    if args.max_events < 0:
        print("[INFO] Events      : all events")
    else:
        print(f"[INFO] Events      : max {args.max_events}")

    process_file(input_path, output_path, args.max_events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
