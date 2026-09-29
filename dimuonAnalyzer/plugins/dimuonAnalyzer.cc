// dimuonAnalyzer.cc

#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/Frameworkfwd.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/Framework/interface/one/EDAnalyzer.h"
#include "FWCore/ParameterSet/interface/ConfigurationDescriptions.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/ParameterSet/interface/ParameterSetDescription.h"
#include "FWCore/ServiceRegistry/interface/Service.h"
#include "FWCore/Utilities/interface/EDMException.h"
#include "FWCore/Utilities/interface/ESInputTag.h"

#include "CommonTools/UtilAlgos/interface/TFileService.h"
#include "DataFormats/GeometryCommonDetAlgo/interface/GlobalError.h"
#include "DataFormats/GeometryVector/interface/GlobalPoint.h"
#include "DataFormats/HepMCCandidate/interface/GenParticle.h"
#include "DataFormats/PatCandidates/interface/Muon.h"
#include "DataFormats/TrackReco/interface/HitPattern.h"
#include "DataFormats/TrackReco/interface/Track.h"
#include "DataFormats/VertexReco/interface/Vertex.h"
#include "RecoVertex/KalmanVertexFit/interface/KalmanVertexFitter.h"
#include "SimDataFormats/GeneratorProducts/interface/GenEventInfoProduct.h"
#include "TrackingTools/Records/interface/TransientTrackRecord.h"
#include "TrackingTools/TransientTrack/interface/TransientTrackBuilder.h"

#include "TH1F.h"
#include "TLorentzVector.h"
#include "TMath.h"
#include "TTree.h"

#include <cmath>
#include <string>
#include <vector>

namespace {
constexpr float kInvalid = -999.f;
constexpr float kMuonMass = 0.1056583745f;

template <typename Func>
void ignoreMissingProduct(Func&& func) {
  try {
    func();
  } catch (const edm::Exception& ex) {
    if (ex.categoryCode() != edm::errors::ProductNotFound) {
      throw;
    }
  }
}

struct MuonBranches {
  int nMuon = 0;
  std::vector<float> pt;
  std::vector<float> ptError;
  std::vector<float> eta;
  std::vector<float> phi;
  std::vector<int> charge;
  std::vector<int> numberOfStandAloneMuonHits;
  std::vector<int> numberOfValidMuonCSCHits;
  std::vector<int> numberOfValidMuonDTHits;
  std::vector<int> numberOfStandAloneMuonMatchedStations;
  std::vector<float> standAloneMuonNormChi2;
  std::vector<float> d0;
  std::vector<float> d0Error;
  std::vector<float> dz;
  std::vector<int> simExtType;
  std::vector<int> isGlobal;
  std::vector<int> isStandAlone;
  std::vector<int> isTracker;
  std::vector<int> hasStandAloneMuon;
  std::vector<float> standAloneMuonPt;
  std::vector<float> standAloneMuonPtError;
  std::vector<float> standAloneMuonEta;
  std::vector<float> standAloneMuonPhi;
  std::vector<int> standAloneMuonCharge;
  std::vector<float> standAloneMuonD0;
  std::vector<float> standAloneMuonD0Error;
  std::vector<float> standAloneMuonDz;

  void clear() {
    nMuon = 0;
    pt.clear();
    ptError.clear();
    eta.clear();
    phi.clear();
    charge.clear();
    numberOfStandAloneMuonHits.clear();
    numberOfValidMuonCSCHits.clear();
    numberOfValidMuonDTHits.clear();
    numberOfStandAloneMuonMatchedStations.clear();
    standAloneMuonNormChi2.clear();
    d0.clear();
    d0Error.clear();
    dz.clear();
    simExtType.clear();
    isGlobal.clear();
    isStandAlone.clear();
    isTracker.clear();
    hasStandAloneMuon.clear();
    standAloneMuonPt.clear();
    standAloneMuonPtError.clear();
    standAloneMuonEta.clear();
    standAloneMuonPhi.clear();
    standAloneMuonCharge.clear();
    standAloneMuonD0.clear();
    standAloneMuonD0Error.clear();
    standAloneMuonDz.clear();
  }
};

struct DimuonVertexBranches {
  int nVertex = 0;
  std::vector<int> mu1Index;
  std::vector<int> mu2Index;
  std::vector<float> massBeforeFit;
  std::vector<int> isValid;
  std::vector<float> mass;
  std::vector<float> vtxProb;
  std::vector<float> lxy;
  std::vector<float> lxyErr;
  std::vector<float> normChi2;
  std::vector<float> vx;
  std::vector<float> vy;
  std::vector<float> vz;
  std::vector<float> refitMu1Pt;
  std::vector<float> refitMu1PtError;
  std::vector<float> refitMu1Eta;
  std::vector<float> refitMu1Phi;
  std::vector<float> refitMu1D0;
  std::vector<float> refitMu1D0Error;
  std::vector<float> refitMu2Pt;
  std::vector<float> refitMu2PtError;
  std::vector<float> refitMu2Eta;
  std::vector<float> refitMu2Phi;
  std::vector<float> refitMu2D0;
  std::vector<float> refitMu2D0Error;

  void clear() {
    nVertex = 0;
    mu1Index.clear();
    mu2Index.clear();
    massBeforeFit.clear();
    isValid.clear();
    mass.clear();
    vtxProb.clear();
    lxy.clear();
    lxyErr.clear();
    normChi2.clear();
    vx.clear();
    vy.clear();
    vz.clear();
    refitMu1Pt.clear();
    refitMu1PtError.clear();
    refitMu1Eta.clear();
    refitMu1Phi.clear();
    refitMu1D0.clear();
    refitMu1D0Error.clear();
    refitMu2Pt.clear();
    refitMu2PtError.clear();
    refitMu2Eta.clear();
    refitMu2Phi.clear();
    refitMu2D0.clear();
    refitMu2D0Error.clear();
  }
};


void bookMuonBranches(TTree* tree,
                      const std::string& prefix,
                      const std::string& countName,
                      MuonBranches& branches,
                      bool bookSimExtType = false,
                      bool bookMuonTypeFlags = false,
                      bool bookStandAloneTrack = false,
                      bool bookPtError = true,
                      bool bookSubsystemHitCounts = false) {
  tree->Branch(countName.c_str(), &branches.nMuon, (countName + "/I").c_str());
  tree->Branch((prefix + "_pt").c_str(), &branches.pt);
  if (bookPtError) {
    tree->Branch((prefix + "_ptError").c_str(), &branches.ptError);
  }
  tree->Branch((prefix + "_eta").c_str(), &branches.eta);
  tree->Branch((prefix + "_phi").c_str(), &branches.phi);
  tree->Branch((prefix + "_charge").c_str(), &branches.charge);
  tree->Branch((prefix + "_numberOfStandAloneMuonHits").c_str(), &branches.numberOfStandAloneMuonHits);
  if (bookSubsystemHitCounts) {
    tree->Branch((prefix + "_numberOfValidMuonCSCHits").c_str(), &branches.numberOfValidMuonCSCHits);
    tree->Branch((prefix + "_numberOfValidMuonDTHits").c_str(), &branches.numberOfValidMuonDTHits);
  }
  tree->Branch((prefix + "_numberOfStandAloneMuonMatchedStations").c_str(),
               &branches.numberOfStandAloneMuonMatchedStations);
  tree->Branch((prefix + "_standAloneMuonNormChi2").c_str(), &branches.standAloneMuonNormChi2);
  tree->Branch((prefix + "_d0").c_str(), &branches.d0);
  tree->Branch((prefix + "_d0Error").c_str(), &branches.d0Error);
  tree->Branch((prefix + "_dz").c_str(), &branches.dz);
  if (bookSimExtType) {
    tree->Branch((prefix + "_simExtType").c_str(), &branches.simExtType);
  }
  if (bookMuonTypeFlags) {
    tree->Branch((prefix + "_isGlobal").c_str(), &branches.isGlobal);
    tree->Branch((prefix + "_isStandAlone").c_str(), &branches.isStandAlone);
    tree->Branch((prefix + "_isTracker").c_str(), &branches.isTracker);
  }
  if (bookStandAloneTrack) {
    tree->Branch((prefix + "_hasStandAloneMuon").c_str(), &branches.hasStandAloneMuon);
    tree->Branch((prefix + "_standAloneMuon_pt").c_str(), &branches.standAloneMuonPt);
    tree->Branch((prefix + "_standAloneMuon_ptError").c_str(), &branches.standAloneMuonPtError);
    tree->Branch((prefix + "_standAloneMuon_eta").c_str(), &branches.standAloneMuonEta);
    tree->Branch((prefix + "_standAloneMuon_phi").c_str(), &branches.standAloneMuonPhi);
    tree->Branch((prefix + "_standAloneMuon_charge").c_str(), &branches.standAloneMuonCharge);
    tree->Branch((prefix + "_standAloneMuon_d0").c_str(), &branches.standAloneMuonD0);
    tree->Branch((prefix + "_standAloneMuon_d0Error").c_str(), &branches.standAloneMuonD0Error);
    tree->Branch((prefix + "_standAloneMuon_dz").c_str(), &branches.standAloneMuonDz);
  }
}

void bookDimuonVertexBranches(TTree* tree,
                              const std::string& prefix,
                              const std::string& countName,
                              DimuonVertexBranches& branches) {
  tree->Branch(countName.c_str(), &branches.nVertex, (countName + "/I").c_str());
  tree->Branch((prefix + "_mu1Index").c_str(), &branches.mu1Index);
  tree->Branch((prefix + "_mu2Index").c_str(), &branches.mu2Index);
  tree->Branch((prefix + "_mass_beforeFit").c_str(), &branches.massBeforeFit);
  tree->Branch((prefix + "_isValid").c_str(), &branches.isValid);
  tree->Branch((prefix + "_mass").c_str(), &branches.mass);
  tree->Branch((prefix + "_vtxProb").c_str(), &branches.vtxProb);
  tree->Branch((prefix + "_lxy").c_str(), &branches.lxy);
  tree->Branch((prefix + "_lxyErr").c_str(), &branches.lxyErr);
  tree->Branch((prefix + "_normChi2").c_str(), &branches.normChi2);
  tree->Branch((prefix + "_vx").c_str(), &branches.vx);
  tree->Branch((prefix + "_vy").c_str(), &branches.vy);
  tree->Branch((prefix + "_vz").c_str(), &branches.vz);
  tree->Branch((prefix + "_refit_mu1_pt").c_str(), &branches.refitMu1Pt);
  tree->Branch((prefix + "_refit_mu1_ptError").c_str(), &branches.refitMu1PtError);
  tree->Branch((prefix + "_refit_mu1_eta").c_str(), &branches.refitMu1Eta);
  tree->Branch((prefix + "_refit_mu1_phi").c_str(), &branches.refitMu1Phi);
  tree->Branch((prefix + "_refit_mu1_d0").c_str(), &branches.refitMu1D0);
  tree->Branch((prefix + "_refit_mu1_d0Error").c_str(), &branches.refitMu1D0Error);
  tree->Branch((prefix + "_refit_mu2_pt").c_str(), &branches.refitMu2Pt);
  tree->Branch((prefix + "_refit_mu2_ptError").c_str(), &branches.refitMu2PtError);
  tree->Branch((prefix + "_refit_mu2_eta").c_str(), &branches.refitMu2Eta);
  tree->Branch((prefix + "_refit_mu2_phi").c_str(), &branches.refitMu2Phi);
  tree->Branch((prefix + "_refit_mu2_d0").c_str(), &branches.refitMu2D0);
  tree->Branch((prefix + "_refit_mu2_d0Error").c_str(), &branches.refitMu2D0Error);
}


void fillGenMuonBranches(const edm::Handle<reco::GenParticleCollection>& genParticles,
                         MuonBranches& branches) {
  if (!genParticles.isValid()) return;

  for (const auto& genParticle : *genParticles) {
    if (std::abs(genParticle.pdgId()) != 13) continue;
    if (genParticle.status() != 1) continue;
    if (!genParticle.isLastCopy()) continue;

    branches.pt.push_back(genParticle.pt());
    branches.ptError.push_back(kInvalid);
    branches.eta.push_back(genParticle.eta());
    branches.phi.push_back(genParticle.phi());
    branches.charge.push_back(genParticle.charge());
    branches.numberOfStandAloneMuonHits.push_back(-1);
    branches.numberOfStandAloneMuonMatchedStations.push_back(-1);
    branches.standAloneMuonNormChi2.push_back(kInvalid);
    branches.d0.push_back(kInvalid);
    branches.d0Error.push_back(kInvalid);
    branches.dz.push_back(kInvalid);
  }

  branches.nMuon = static_cast<int>(branches.pt.size());
}

void fillMuonBranches(const std::vector<const pat::Muon*>& muons,
                      MuonBranches& branches,
                      bool fillSimExtType = false,
                      bool fillStandAloneTrack = false) {
  for (const pat::Muon* muon : muons) {
    if (!muon) continue;

    branches.pt.push_back(muon->pt());
    branches.eta.push_back(muon->eta());
    branches.phi.push_back(muon->phi());
    branches.charge.push_back(muon->charge());
    if (fillSimExtType) {
      branches.simExtType.push_back(static_cast<int>(muon->simExtType()));
    }
    branches.isGlobal.push_back(muon->isGlobalMuon() ? 1 : 0);
    branches.isStandAlone.push_back(muon->isStandAloneMuon() ? 1 : 0);
    branches.isTracker.push_back(muon->isTrackerMuon() ? 1 : 0);

    const auto standAloneTrack = muon->standAloneMuon();
    if (fillStandAloneTrack) {
      int hasStandAloneMuon = 0;
      float standAloneMuonPt = kInvalid;
      float standAloneMuonPtError = kInvalid;
      float standAloneMuonEta = kInvalid;
      float standAloneMuonPhi = kInvalid;
      int standAloneMuonCharge = -1;
      float standAloneMuonD0 = kInvalid;
      float standAloneMuonD0Error = kInvalid;
      float standAloneMuonDz = kInvalid;
      if (standAloneTrack.isNonnull()) {
        ignoreMissingProduct([&]() {
          hasStandAloneMuon = 1;
          standAloneMuonPt = standAloneTrack->pt();
          standAloneMuonPtError = standAloneTrack->ptError();
          standAloneMuonEta = standAloneTrack->eta();
          standAloneMuonPhi = standAloneTrack->phi();
          standAloneMuonCharge = standAloneTrack->charge();
          standAloneMuonD0 = standAloneTrack->d0();
          standAloneMuonD0Error = standAloneTrack->d0Error();
          standAloneMuonDz = standAloneTrack->dz();
        });
      }
      branches.hasStandAloneMuon.push_back(hasStandAloneMuon);
      branches.standAloneMuonPt.push_back(standAloneMuonPt);
      branches.standAloneMuonPtError.push_back(standAloneMuonPtError);
      branches.standAloneMuonEta.push_back(standAloneMuonEta);
      branches.standAloneMuonPhi.push_back(standAloneMuonPhi);
      branches.standAloneMuonCharge.push_back(standAloneMuonCharge);
      branches.standAloneMuonD0.push_back(standAloneMuonD0);
      branches.standAloneMuonD0Error.push_back(standAloneMuonD0Error);
      branches.standAloneMuonDz.push_back(standAloneMuonDz);
    }

    float ptError = kInvalid;
    float d0 = kInvalid;
    float d0Error = kInvalid;
    float dz = kInvalid;
    const auto bestTrack = muon->muonBestTrack();
    if (bestTrack.isNonnull()) {
      ptError = bestTrack->ptError();
      d0 = bestTrack->d0();
      d0Error = bestTrack->d0Error();
      dz = bestTrack->dz();
    }
    branches.ptError.push_back(ptError);
    branches.d0.push_back(d0);
    branches.d0Error.push_back(d0Error);
    branches.dz.push_back(dz);

    int numberOfStandAloneMuonHits = -1;
    int numberOfValidMuonCSCHits = -1;
    int numberOfValidMuonDTHits = -1;
    int numberOfStandAloneMuonMatchedStations = -1;
    float standAloneMuonNormChi2 = kInvalid;
    if (standAloneTrack.isNonnull()) {
      ignoreMissingProduct([&]() {
        standAloneMuonNormChi2 = standAloneTrack->normalizedChi2();
        const reco::HitPattern& hitPattern = standAloneTrack->hitPattern();
        numberOfStandAloneMuonHits = hitPattern.numberOfValidMuonHits();
        numberOfValidMuonCSCHits = hitPattern.numberOfValidMuonCSCHits();
        numberOfValidMuonDTHits = hitPattern.numberOfValidMuonDTHits();
        numberOfStandAloneMuonMatchedStations = hitPattern.muonStationsWithValidHits();
      });
    }
    branches.numberOfStandAloneMuonHits.push_back(numberOfStandAloneMuonHits);
    branches.numberOfValidMuonCSCHits.push_back(numberOfValidMuonCSCHits);
    branches.numberOfValidMuonDTHits.push_back(numberOfValidMuonDTHits);
    branches.numberOfStandAloneMuonMatchedStations.push_back(numberOfStandAloneMuonMatchedStations);
    branches.standAloneMuonNormChi2.push_back(standAloneMuonNormChi2);
  }

  branches.nMuon = static_cast<int>(branches.pt.size());
}

void pushInvalidVertex(const pat::Muon& mu1,
                       int mu1Index,
                       const pat::Muon& mu2,
                       int mu2Index,
                       DimuonVertexBranches& branches,
                       bool useStandAloneTrack = false) {
  float massBeforeFit = kInvalid;
  if (useStandAloneTrack) {
    const auto mu1Track = mu1.standAloneMuon();
    const auto mu2Track = mu2.standAloneMuon();
    if (mu1Track.isNonnull() && mu2Track.isNonnull()) {
      TLorentzVector p1Before;
      TLorentzVector p2Before;
      p1Before.SetPtEtaPhiM(mu1Track->pt(), mu1Track->eta(), mu1Track->phi(), kMuonMass);
      p2Before.SetPtEtaPhiM(mu2Track->pt(), mu2Track->eta(), mu2Track->phi(), kMuonMass);
      massBeforeFit = (p1Before + p2Before).M();
    }
  } else {
    TLorentzVector p1Before;
    TLorentzVector p2Before;
    p1Before.SetPtEtaPhiM(mu1.pt(), mu1.eta(), mu1.phi(), kMuonMass);
    p2Before.SetPtEtaPhiM(mu2.pt(), mu2.eta(), mu2.phi(), kMuonMass);
    massBeforeFit = (p1Before + p2Before).M();
  }

  branches.mu1Index.push_back(mu1Index);
  branches.mu2Index.push_back(mu2Index);
  branches.massBeforeFit.push_back(massBeforeFit);
  branches.isValid.push_back(0);
  branches.mass.push_back(kInvalid);
  branches.vtxProb.push_back(kInvalid);
  branches.lxy.push_back(kInvalid);
  branches.lxyErr.push_back(kInvalid);
  branches.normChi2.push_back(kInvalid);
  branches.vx.push_back(kInvalid);
  branches.vy.push_back(kInvalid);
  branches.vz.push_back(kInvalid);
  branches.refitMu1Pt.push_back(kInvalid);
  branches.refitMu1PtError.push_back(kInvalid);
  branches.refitMu1Eta.push_back(kInvalid);
  branches.refitMu1Phi.push_back(kInvalid);
  branches.refitMu1D0.push_back(kInvalid);
  branches.refitMu1D0Error.push_back(kInvalid);
  branches.refitMu2Pt.push_back(kInvalid);
  branches.refitMu2PtError.push_back(kInvalid);
  branches.refitMu2Eta.push_back(kInvalid);
  branches.refitMu2Phi.push_back(kInvalid);
  branches.refitMu2D0.push_back(kInvalid);
  branches.refitMu2D0Error.push_back(kInvalid);
  branches.nVertex = static_cast<int>(branches.mu1Index.size());
}

void pushInvalidTrackVertex(const reco::Track& mu1Track,
                            int mu1Index,
                            const reco::Track& mu2Track,
                            int mu2Index,
                            DimuonVertexBranches& branches) {
  TLorentzVector p1Before;
  TLorentzVector p2Before;
  p1Before.SetPtEtaPhiM(mu1Track.pt(), mu1Track.eta(), mu1Track.phi(), kMuonMass);
  p2Before.SetPtEtaPhiM(mu2Track.pt(), mu2Track.eta(), mu2Track.phi(), kMuonMass);

  branches.mu1Index.push_back(mu1Index);
  branches.mu2Index.push_back(mu2Index);
  branches.massBeforeFit.push_back((p1Before + p2Before).M());
  branches.isValid.push_back(0);
  branches.mass.push_back(kInvalid);
  branches.vtxProb.push_back(kInvalid);
  branches.lxy.push_back(kInvalid);
  branches.lxyErr.push_back(kInvalid);
  branches.normChi2.push_back(kInvalid);
  branches.vx.push_back(kInvalid);
  branches.vy.push_back(kInvalid);
  branches.vz.push_back(kInvalid);
  branches.refitMu1Pt.push_back(kInvalid);
  branches.refitMu1PtError.push_back(kInvalid);
  branches.refitMu1Eta.push_back(kInvalid);
  branches.refitMu1Phi.push_back(kInvalid);
  branches.refitMu1D0.push_back(kInvalid);
  branches.refitMu1D0Error.push_back(kInvalid);
  branches.refitMu2Pt.push_back(kInvalid);
  branches.refitMu2PtError.push_back(kInvalid);
  branches.refitMu2Eta.push_back(kInvalid);
  branches.refitMu2Phi.push_back(kInvalid);
  branches.refitMu2D0.push_back(kInvalid);
  branches.refitMu2D0Error.push_back(kInvalid);
  branches.nVertex = static_cast<int>(branches.mu1Index.size());
}

void fillDimuonVertexBranches(const std::vector<const pat::Muon*>& selectedMuons,
                              const edm::Handle<std::vector<reco::Vertex>>& vertices,
                              const TransientTrackBuilder& ttBuilder,
                              DimuonVertexBranches& branches,
                              bool useStandAloneTrack = false) {
  const bool hasPV = vertices.isValid() && !vertices->empty();
  GlobalPoint pvPos(0.f, 0.f, 0.f);
  GlobalError pvErr;
  if (hasPV) {
    const reco::Vertex& pv = vertices->at(0);
    const reco::Vertex::Error& ve = pv.error();
    pvPos = GlobalPoint(pv.x(), pv.y(), pv.z());
    pvErr = GlobalError(ve.At(0, 0), ve.At(1, 0), ve.At(1, 1),
                        ve.At(2, 0), ve.At(2, 1), ve.At(2, 2));
  }

  for (size_t i = 0; i < selectedMuons.size(); ++i) {
    const pat::Muon* mu1Ptr = selectedMuons[i];
    if (!mu1Ptr) continue;

    for (size_t j = i + 1; j < selectedMuons.size(); ++j) {
      const pat::Muon* mu2Ptr = selectedMuons[j];
      if (!mu2Ptr) continue;

      const pat::Muon& mu1 = *mu1Ptr;
      const pat::Muon& mu2 = *mu2Ptr;
      if (mu1.charge() * mu2.charge() >= 0) continue;

      const int mu1Index = static_cast<int>(i);
      const int mu2Index = static_cast<int>(j);
      pushInvalidVertex(mu1, mu1Index, mu2, mu2Index, branches, useStandAloneTrack);
      const size_t vertexIndex = branches.mu1Index.size() - 1;

      const auto mu1Track = useStandAloneTrack ? mu1.standAloneMuon() : mu1.muonBestTrack();
      const auto mu2Track = useStandAloneTrack ? mu2.standAloneMuon() : mu2.muonBestTrack();
      if (mu1Track.isNull() || mu2Track.isNull()) continue;

      reco::TransientTrack tt1 = ttBuilder.build(mu1Track);
      reco::TransientTrack tt2 = ttBuilder.build(mu2Track);

      KalmanVertexFitter kvf(true, true);
      std::vector<reco::TransientTrack> tracks = {tt1, tt2};
      TransientVertex tv = kvf.vertex(tracks);

      if (!tv.isValid() || tv.refittedTracks().size() != 2) continue;

      const auto& refitTracks = tv.refittedTracks();
      const auto gm1 = refitTracks[0].impactPointState().globalMomentum();
      const auto gm2 = refitTracks[1].impactPointState().globalMomentum();

      TLorentzVector p1After;
      TLorentzVector p2After;
      p1After.SetXYZM(gm1.x(), gm1.y(), gm1.z(), kMuonMass);
      p2After.SetXYZM(gm2.x(), gm2.y(), gm2.z(), kMuonMass);

      const GlobalPoint svPos = tv.position();
      const GlobalError svErr = tv.positionError();
      const GlobalPoint disp(svPos.x() - pvPos.x(), svPos.y() - pvPos.y(), 0.f);
      const GlobalError totErr = svErr + pvErr;

      branches.isValid[vertexIndex] = 1;
      branches.mass[vertexIndex] = (p1After + p2After).M();
      const float chi2 = tv.totalChiSquared();
      const float ndof = tv.degreesOfFreedom();
      branches.normChi2[vertexIndex] =
          ndof > 0.f ? chi2 / ndof : kInvalid;
      if (ndof > 0.f) {
        branches.vtxProb[vertexIndex] = static_cast<float>(TMath::Prob(chi2, static_cast<int>(ndof)));
      }
      if (hasPV) {
        branches.lxy[vertexIndex] = disp.perp();
        branches.lxyErr[vertexIndex] = std::sqrt(totErr.rerr(disp));
      }
      branches.vx[vertexIndex] = svPos.x();
      branches.vy[vertexIndex] = svPos.y();
      branches.vz[vertexIndex] = svPos.z();
      branches.refitMu1Pt[vertexIndex] = gm1.perp();
      branches.refitMu1PtError[vertexIndex] = refitTracks[0].track().ptError();
      branches.refitMu1Eta[vertexIndex] = gm1.eta();
      branches.refitMu1Phi[vertexIndex] = gm1.phi();
      branches.refitMu1D0[vertexIndex] = refitTracks[0].track().d0();
      branches.refitMu1D0Error[vertexIndex] = refitTracks[0].track().d0Error();
      branches.refitMu2Pt[vertexIndex] = gm2.perp();
      branches.refitMu2PtError[vertexIndex] = refitTracks[1].track().ptError();
      branches.refitMu2Eta[vertexIndex] = gm2.eta();
      branches.refitMu2Phi[vertexIndex] = gm2.phi();
      branches.refitMu2D0[vertexIndex] = refitTracks[1].track().d0();
      branches.refitMu2D0Error[vertexIndex] = refitTracks[1].track().d0Error();
    }
  }
}

void fillDimuonTrackVertexBranches(const edm::Handle<std::vector<reco::Track>>& tracks,
                                   const edm::Handle<std::vector<reco::Vertex>>& vertices,
                                   const TransientTrackBuilder& ttBuilder,
                                   DimuonVertexBranches& branches) {
  if (!tracks.isValid()) return;

  const bool hasPV = vertices.isValid() && !vertices->empty();
  GlobalPoint pvPos(0.f, 0.f, 0.f);
  GlobalError pvErr;
  if (hasPV) {
    const reco::Vertex& pv = vertices->at(0);
    const reco::Vertex::Error& ve = pv.error();
    pvPos = GlobalPoint(pv.x(), pv.y(), pv.z());
    pvErr = GlobalError(ve.At(0, 0), ve.At(1, 0), ve.At(1, 1),
                        ve.At(2, 0), ve.At(2, 1), ve.At(2, 2));
  }

  for (size_t i = 0; i < tracks->size(); ++i) {
    const reco::Track& mu1Track = tracks->at(i);

    for (size_t j = i + 1; j < tracks->size(); ++j) {
      const reco::Track& mu2Track = tracks->at(j);
      if (mu1Track.charge() * mu2Track.charge() >= 0) continue;

      const int mu1Index = static_cast<int>(i);
      const int mu2Index = static_cast<int>(j);
      pushInvalidTrackVertex(mu1Track, mu1Index, mu2Track, mu2Index, branches);
      const size_t vertexIndex = branches.mu1Index.size() - 1;

      reco::TransientTrack tt1 = ttBuilder.build(mu1Track);
      reco::TransientTrack tt2 = ttBuilder.build(mu2Track);

      KalmanVertexFitter kvf(true, true);
      std::vector<reco::TransientTrack> transientTracks = {tt1, tt2};
      TransientVertex tv = kvf.vertex(transientTracks);

      if (!tv.isValid() || tv.refittedTracks().size() != 2) continue;

      const auto& refitTracks = tv.refittedTracks();
      const auto gm1 = refitTracks[0].impactPointState().globalMomentum();
      const auto gm2 = refitTracks[1].impactPointState().globalMomentum();

      TLorentzVector p1After;
      TLorentzVector p2After;
      p1After.SetXYZM(gm1.x(), gm1.y(), gm1.z(), kMuonMass);
      p2After.SetXYZM(gm2.x(), gm2.y(), gm2.z(), kMuonMass);

      const GlobalPoint svPos = tv.position();
      const GlobalError svErr = tv.positionError();
      const GlobalPoint disp(svPos.x() - pvPos.x(), svPos.y() - pvPos.y(), 0.f);
      const GlobalError totErr = svErr + pvErr;

      branches.isValid[vertexIndex] = 1;
      branches.mass[vertexIndex] = (p1After + p2After).M();
      const float chi2 = tv.totalChiSquared();
      const float ndof = tv.degreesOfFreedom();
      branches.normChi2[vertexIndex] =
          ndof > 0.f ? chi2 / ndof : kInvalid;
      if (ndof > 0.f) {
        branches.vtxProb[vertexIndex] = static_cast<float>(TMath::Prob(chi2, static_cast<int>(ndof)));
      }
      if (hasPV) {
        branches.lxy[vertexIndex] = disp.perp();
        branches.lxyErr[vertexIndex] = std::sqrt(totErr.rerr(disp));
      }
      branches.vx[vertexIndex] = svPos.x();
      branches.vy[vertexIndex] = svPos.y();
      branches.vz[vertexIndex] = svPos.z();
      branches.refitMu1Pt[vertexIndex] = gm1.perp();
      branches.refitMu1PtError[vertexIndex] = refitTracks[0].track().ptError();
      branches.refitMu1Eta[vertexIndex] = gm1.eta();
      branches.refitMu1Phi[vertexIndex] = gm1.phi();
      branches.refitMu1D0[vertexIndex] = refitTracks[0].track().d0();
      branches.refitMu1D0Error[vertexIndex] = refitTracks[0].track().d0Error();
      branches.refitMu2Pt[vertexIndex] = gm2.perp();
      branches.refitMu2PtError[vertexIndex] = refitTracks[1].track().ptError();
      branches.refitMu2Eta[vertexIndex] = gm2.eta();
      branches.refitMu2Phi[vertexIndex] = gm2.phi();
      branches.refitMu2D0[vertexIndex] = refitTracks[1].track().d0();
      branches.refitMu2D0Error[vertexIndex] = refitTracks[1].track().d0Error();
    }
  }
}
}  // namespace

class dimuonAnalyzer : public edm::one::EDAnalyzer<edm::one::SharedResources> {
public:
  explicit dimuonAnalyzer(const edm::ParameterSet&);
  ~dimuonAnalyzer() override = default;

  static void fillDescriptions(edm::ConfigurationDescriptions& descriptions);

private:
  void beginJob() override;
  void analyze(const edm::Event&, const edm::EventSetup&) override;
  void clearBranches();

  edm::EDGetTokenT<std::vector<pat::Muon>> muonToken_;
  edm::EDGetTokenT<std::vector<pat::Muon>> displacedMuonToken_;
  edm::EDGetTokenT<std::vector<reco::Track>> displacedSATrackToken_;
  edm::EDGetTokenT<std::vector<reco::Vertex>> vertexToken_;
  edm::EDGetTokenT<reco::GenParticleCollection> genParticleToken_;
  edm::EDGetTokenT<GenEventInfoProduct> genEventInfoToken_;
  edm::ESGetToken<TransientTrackBuilder, TransientTrackRecord> ttBuilderToken_;
  int genMotherPdgId_;

  TH1F* eventWeightHist_;
  TTree* tree_;
  float eventWeight_;
  float genMotherPt_;
  float genMotherEta_;
  float genMotherPhi_;
  float genMotherMass_;

  MuonBranches genMuonBranches_;
  MuonBranches muonBranches_;
  MuonBranches disMuonBranches_;
  DimuonVertexBranches muonVertexBranches_;
  DimuonVertexBranches muonStaVertexBranches_;
  DimuonVertexBranches disMuonVertexBranches_;
  DimuonVertexBranches disMuonStaVertexBranches_;
  DimuonVertexBranches disStaTrackVertexBranches_;
};

dimuonAnalyzer::dimuonAnalyzer(const edm::ParameterSet& iConfig)
    : muonToken_(consumes<std::vector<pat::Muon>>(iConfig.getParameter<edm::InputTag>("muons"))),
      displacedMuonToken_(
          consumes<std::vector<pat::Muon>>(iConfig.getParameter<edm::InputTag>("displacedMuons"))),
      displacedSATrackToken_(
          consumes<std::vector<reco::Track>>(iConfig.getParameter<edm::InputTag>("displacedSATracks"))),
      vertexToken_(consumes<std::vector<reco::Vertex>>(iConfig.getParameter<edm::InputTag>("vertices"))),
      genParticleToken_(mayConsume<reco::GenParticleCollection>(
          iConfig.getParameter<edm::InputTag>("genParticles"))),
      genEventInfoToken_(mayConsume<GenEventInfoProduct>(edm::InputTag("generator"))),
      ttBuilderToken_(esConsumes<TransientTrackBuilder, TransientTrackRecord>(
          edm::ESInputTag("", "TransientTrackBuilder"))),
      genMotherPdgId_(iConfig.getParameter<int>("genMotherPdgId")),
      eventWeightHist_(nullptr),
      tree_(nullptr),
      eventWeight_(1.f),
      genMotherPt_(kInvalid),
      genMotherEta_(kInvalid),
      genMotherPhi_(kInvalid),
      genMotherMass_(kInvalid) {
  usesResource("TFileService");
}

void dimuonAnalyzer::beginJob() {
  edm::Service<TFileService> fs;
  eventWeightHist_ = fs->make<TH1F>("eventWeight", "Event weights", 1, 0., 1.);
  tree_ = fs->make<TTree>("tree", "Selected muons");

  tree_->Branch("eventWeight", &eventWeight_, "eventWeight/F");
  tree_->Branch("genMother_pt", &genMotherPt_, "genMother_pt/F");
  tree_->Branch("genMother_eta", &genMotherEta_, "genMother_eta/F");
  tree_->Branch("genMother_phi", &genMotherPhi_, "genMother_phi/F");
  tree_->Branch("genMother_mass", &genMotherMass_, "genMother_mass/F");
  bookMuonBranches(tree_, "genMuon", "nGenMuon", genMuonBranches_, false, false, false, false);
  bookMuonBranches(tree_, "muon", "nMuon", muonBranches_, true, true, true, true, true);
  bookMuonBranches(tree_, "disMuon", "nDisMuon", disMuonBranches_, false, true, true, true, true);
  bookDimuonVertexBranches(tree_, "muonVertex", "nMuonVertex", muonVertexBranches_);
  bookDimuonVertexBranches(tree_, "muonStaVertex", "nMuonStaVertex", muonStaVertexBranches_);
  bookDimuonVertexBranches(tree_, "disMuonVertex", "nDisMuonVertex", disMuonVertexBranches_);
  bookDimuonVertexBranches(tree_, "disMuonStaVertex", "nDisMuonStaVertex", disMuonStaVertexBranches_);
  bookDimuonVertexBranches(tree_, "disStaTrackVertex", "nDisStaTrackVertex", disStaTrackVertexBranches_);
}

void dimuonAnalyzer::clearBranches() {
  eventWeight_ = 1.f;
  genMotherPt_ = kInvalid;
  genMotherEta_ = kInvalid;
  genMotherPhi_ = kInvalid;
  genMotherMass_ = kInvalid;
  genMuonBranches_.clear();
  muonBranches_.clear();
  disMuonBranches_.clear();
  muonVertexBranches_.clear();
  muonStaVertexBranches_.clear();
  disMuonVertexBranches_.clear();
  disMuonStaVertexBranches_.clear();
  disStaTrackVertexBranches_.clear();
}

void dimuonAnalyzer::analyze(const edm::Event& iEvent, const edm::EventSetup& iSetup) {
  clearBranches();

  edm::Handle<std::vector<pat::Muon>> muons;
  edm::Handle<std::vector<pat::Muon>> displacedMuons;
  edm::Handle<std::vector<reco::Track>> displacedSATracks;
  edm::Handle<std::vector<reco::Vertex>> vertices;
  edm::Handle<reco::GenParticleCollection> genParticles;
  edm::Handle<GenEventInfoProduct> genEventInfo;
  iEvent.getByToken(muonToken_, muons);
  iEvent.getByToken(displacedMuonToken_, displacedMuons);
  iEvent.getByToken(displacedSATrackToken_, displacedSATracks);
  iEvent.getByToken(vertexToken_, vertices);
  iEvent.getByToken(genParticleToken_, genParticles);
  iEvent.getByToken(genEventInfoToken_, genEventInfo);
  eventWeight_ = genEventInfo.isValid() ? static_cast<float>(genEventInfo->weight()) : 1.f;
  eventWeightHist_->Fill(0., eventWeight_);
  if (genParticles.isValid()) {
    for (const auto& genParticle : *genParticles) {
      if (std::abs(genParticle.pdgId()) != std::abs(genMotherPdgId_)) continue;
      genMotherPt_ = genParticle.pt();
      genMotherEta_ = genParticle.eta();
      genMotherPhi_ = genParticle.phi();
      genMotherMass_ = genParticle.mass();
      break;
    }
  }
  fillGenMuonBranches(genParticles, genMuonBranches_);

  std::vector<const pat::Muon*> selectedMuons;
  if (muons.isValid()) {
    selectedMuons.reserve(muons->size());
    for (const auto& muon : *muons) {
      selectedMuons.push_back(&muon);
    }
    fillMuonBranches(selectedMuons, muonBranches_, true, true);
  }

  std::vector<const pat::Muon*> selectedDisplacedMuons;
  if (displacedMuons.isValid()) {
    selectedDisplacedMuons.reserve(displacedMuons->size());
    for (const auto& muon : *displacedMuons) {
      selectedDisplacedMuons.push_back(&muon);
    }
    fillMuonBranches(selectedDisplacedMuons, disMuonBranches_, false, true);
  }

  const auto& ttBuilder = iSetup.getData(ttBuilderToken_);
  fillDimuonVertexBranches(selectedMuons, vertices, ttBuilder, muonVertexBranches_);
  fillDimuonVertexBranches(selectedMuons, vertices, ttBuilder, muonStaVertexBranches_, true);
  fillDimuonVertexBranches(selectedDisplacedMuons, vertices, ttBuilder, disMuonVertexBranches_);
  fillDimuonVertexBranches(selectedDisplacedMuons, vertices, ttBuilder, disMuonStaVertexBranches_, true);
  fillDimuonTrackVertexBranches(displacedSATracks, vertices, ttBuilder, disStaTrackVertexBranches_);

  tree_->Fill();
}

void dimuonAnalyzer::fillDescriptions(edm::ConfigurationDescriptions& descriptions) {
  edm::ParameterSetDescription desc;
  desc.add<edm::InputTag>("muons", edm::InputTag("slimmedMuons"));
  desc.add<edm::InputTag>("displacedMuons", edm::InputTag("slimmedDisplacedMuons"));
  desc.add<edm::InputTag>("displacedSATracks", edm::InputTag("displacedStandAloneMuons"));
  desc.add<edm::InputTag>("vertices", edm::InputTag("offlineSlimmedPrimaryVertices"));
  desc.add<edm::InputTag>("genParticles", edm::InputTag("prunedGenParticles"));
  desc.add<int>("genMotherPdgId", 999999);
  descriptions.addWithDefaultLabel(desc);
}

DEFINE_FWK_MODULE(dimuonAnalyzer);
