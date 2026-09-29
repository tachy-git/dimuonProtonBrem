## this is the cfg file for the signal sample EDAnalyzer

import FWCore.ParameterSet.Config as cms
from FWCore.ParameterSet.VarParsing import VarParsing

options = VarParsing("analysis")
options.parseArguments()

if not options.inputFiles:
    raise RuntimeError("Pass inputFiles=file:/path/to/input.root")

process = cms.Process("dimuonAnalyzer")

# Message logger
process.load("FWCore.MessageService.MessageLogger_cfi")
process.MessageLogger.cerr.FwkReport.reportEvery = 1000

# Magnetic field + geometry (needed by transient tracks / vertexing)
process.load("Configuration.Geometry.GeometryRecoDB_cff")
process.load("Configuration.StandardSequences.MagneticField_cff")

# TransientTrackBuilder record
process.load("TrackingTools.TransientTrack.TransientTrackBuilder_cfi")

process.load("Configuration.StandardSequences.FrontierConditions_GlobalTag_cff")
from Configuration.AlCa.GlobalTag import GlobalTag
#process.GlobalTag = GlobalTag(process.GlobalTag, "auto:run3_data", "")
process.GlobalTag = GlobalTag(process.GlobalTag, '150X_mcRun3_2024_realistic_v3', '')

print(">>> Loading input files...")

# Max events
process.maxEvents = cms.untracked.PSet(
    input = cms.untracked.int32(options.maxEvents)
)

# Input
process.source = cms.Source("PoolSource",
    fileNames = cms.untracked.vstring(options.inputFiles)
)

print(">>> Setting TFileService")

process.TFileService = cms.Service("TFileService",
    fileName = cms.string(options.outputFile)
)

# Analyzer
process.dimuonAnalyzer = cms.EDAnalyzer("dimuonAnalyzer",
    muons = cms.InputTag("slimmedMuons"),
    displacedMuons = cms.InputTag("slimmedDisplacedMuons"),
    displacedSATracks = cms.InputTag("displacedStandAloneMuons"),
    vertices = cms.InputTag("offlineSlimmedPrimaryVertices"),
    genParticles = cms.InputTag("prunedGenParticles"),
    genMotherPdgId = cms.int32(999999),
)
process.p = cms.Path(process.dimuonAnalyzer)

print(">>> CMSSW config loaded successfully.")
