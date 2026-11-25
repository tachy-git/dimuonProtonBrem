"""Add a parallel standard displaced-muon chain, sharing the original seeds."""
import FWCore.ParameterSet.Config as cms
from PhysicsTools.PatAlgos.tools.helpers import (
    cloneProcessingSnippetTask,
    massSearchReplaceAnyInputTag,
)

POSTFIX = "VertexConstrained"


def customise_reco(process):
    # Do not clone seeds, tracker reconstruction, hits, or PF candidates.
    process.dsaComparisonTemplateTask = cms.Task(
        process.displacedStandAloneMuons,
        process.displacedGlobalMuons,
        process.displacedMuons1stStep,
        process.muIsolationDisplacedTask,
        process.displacedMuonPFIsolationTask,
        process.displacedMuons,
        process.displacedMuonReducedTrackExtras,
    )
    task = cloneProcessingSnippetTask(process, process.dsaComparisonTemplateTask, POSTFIX)
    process.displacedStandAloneMuonsVertexConstrained.TrackLoaderParameters.VertexConstraint = True
    # The clone's empty instance remains unconstrained. Downstream reconstruction
    # must explicitly consume UpdatedAtVtx, while TrackExtras use the empty instance.
    process.displacedGlobalMuonsVertexConstrained.MuonCollectionLabel = cms.InputTag(
        "displacedStandAloneMuonsVertexConstrained", "UpdatedAtVtx"
    )
    process.displacedMuons1stStepVertexConstrained.inputCollectionLabels = [
        "displacedTracks",
        "displacedGlobalMuonsVertexConstrained",
        "displacedStandAloneMuonsVertexConstrained:UpdatedAtVtx",
    ]
    process.dsaComparisonStep = cms.Path(
        process.displacedMuonsVertexConstrained
        + process.displacedMuonReducedTrackExtrasVertexConstrained,
        task,
    )
    # Associate original reconstruction tasks as well: shared seeds and tracker
    # inputs remain available even if early deletion is enabled by the base cfg.
    process.dsaComparisonStep.associate(process.reconstructionTask)
    process.schedule.insert(3, process.dsaComparisonStep)
    process.AODSIMoutput.outputCommands.extend([
        "keep *_*VertexConstrained_*_*",
        "keep *_displacedMuonSeeds_*_*",
    ])
    return process


def customise_miniaod(process):
    # Clone only after miniAOD_customizeAllMC has applied the standard settings.
    process.dsaComparisonPatTemplateTask = cms.Task(
        process.filteredDisplacedMuons,
        process.patDisplacedMuons,
        process.selectedPatDisplacedMuons,
        process.slimmedDisplacedMuonTrackExtras,
        process.slimmedDisplacedMuons,
    )
    task = cloneProcessingSnippetTask(process, process.dsaComparisonPatTemplateTask, POSTFIX)
    for original in ("displacedMuons", "displacedMuonReducedTrackExtras", "displacedStandAloneMuons"):
        massSearchReplaceAnyInputTag(task, original, original + POSTFIX, moduleLabelOnly=True)
    process.dsaComparisonPatStep = cms.Path(process.slimmedDisplacedMuonsVertexConstrained, task)
    process.dsaComparisonPatStep.associate(process.patTask)
    process.schedule.insert(0, process.dsaComparisonPatStep)
    process.MINIAODSIM1output.outputCommands.extend([
        "keep *_*VertexConstrained_*_*",
        "keep *_displacedStandAloneMuons_*_*",
        "keep *_displacedMuonSeeds_*_*",
        "keep *_displacedMuonReducedTrackExtras_*_*",
        "keep *_displacedTracks_*_*",
        "keep *_displacedGlobalMuons_*_*",
    ])
    return process
