import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  isMergedHolesStageName,
  isPreUnfoldStageName,
  MERGED_HOLES_STAGE,
} from '../pipelineUi'
import { getFoldSegmentId, normalizeFoldId, isHiddenHoleCandidate } from '../lib/holes'

export function useSelection({ pipelineVisuals, flatMesh, backendMesh, groupedStages, pipelineEnabled, pipelineState }) {
  // Selection state
  const [focusedStage, setFocusedStage] = useState(null)
  const [selectedHoleId, setSelectedHoleId] = useState(null)
  const [selectedFoldId, setSelectedFoldId] = useState(null)
  const [selectedProbe, setSelectedProbe] = useState(null)
  const [probeMode, setProbeMode] = useState(false)
  const [selectedStageIndex, setSelectedStageIndex] = useState(0)
  const [selectedEventIndex, setSelectedEventIndex] = useState(0)
  const [showHiddenHoles, setShowHiddenHoles] = useState(false)
  const [highlightHiddenHoleLocations, setHighlightHiddenHoleLocations] = useState(false)

  // Derived values
  const selectedStage = groupedStages[selectedStageIndex] || null
  const activeHoleVisuals = isPreUnfoldStageName(focusedStage)
    ? pipelineVisuals?.holes_pre_unfold || pipelineVisuals?.holes || null
    : pipelineVisuals?.holes || null
  const holeSource = activeHoleVisuals?.source || null
  const unfoldSuccess = Boolean(pipelineVisuals?.unfold?.success)
  const selectedHole = (activeHoleVisuals?.items || []).find((item) => item.id === selectedHoleId) || null
  const selectedFeature = selectedHole || selectedProbe
  const selectedHoleSource = selectedFeature?.source || null
  const useFlatView =
    focusedStage === MERGED_HOLES_STAGE &&
    (unfoldSuccess || selectedHoleSource === 'flat' || (!selectedHoleSource && holeSource === 'flat')) &&
    Boolean(flatMesh)
  const activeMesh = useFlatView ? flatMesh : backendMesh
  const shouldWaitForBackendMesh =
    pipelineEnabled &&
    !backendMesh &&
    !null &&
    ['checking', 'queued', 'processing'].includes(pipelineState.status)
  const parseMode = shouldWaitForBackendMesh ? 'backend-only' : 'auto'
  const canUseProbeMode = focusedStage === MERGED_HOLES_STAGE

  // Effects to clamp indices
  useEffect(() => {
    setSelectedStageIndex((value) => {
      if (groupedStages.length === 0) return 0
      return Math.min(value, groupedStages.length - 1)
    })
  }, [groupedStages.length])

  useEffect(() => {
    setSelectedEventIndex((value) => {
      const eventCount = selectedStage?.events?.length || 0
      if (eventCount === 0) return 0
      return Math.min(value, eventCount - 1)
    })
  }, [selectedStage])

  useEffect(() => {
    setFocusedStage(selectedStage?.stage || null)
  }, [selectedStage])

  // Clear invalid hole selection
  useEffect(() => {
    if (!selectedHoleId) return
    const holeItems = activeHoleVisuals?.items || []
    if (!holeItems.some((item) => item.id === selectedHoleId)) {
      setSelectedHoleId(null)
      return
    }
    if (!showHiddenHoles && holeItems.some((item) => item.id === selectedHoleId && isHiddenHoleCandidate(item))) {
      setSelectedHoleId(null)
    }
  }, [activeHoleVisuals, selectedHoleId, showHiddenHoles])

  // Clear invalid fold selection
  useEffect(() => {
    const foldIds = new Set(
      [
        ...(pipelineVisuals?.unfold?.fold_details || []).map((fold, idx) => normalizeFoldId(fold?.id ?? idx + 1)),
        ...(pipelineVisuals?.unfold?.bends_logical || []).map((bend, idx) => normalizeFoldId(bend?.id ?? idx + 1)),
        ...(pipelineVisuals?.unfold?.bend_line_segments || []).map((segment, idx) => getFoldSegmentId(segment, idx)),
      ].filter((id) => id != null),
    )
    if (selectedFoldId != null && !foldIds.has(normalizeFoldId(selectedFoldId))) {
      setSelectedFoldId(null)
    }
  }, [pipelineVisuals, selectedFoldId])

  // Callbacks
  const handleSelectStageIndex = useCallback((index) => {
    setSelectedStageIndex(index)
    setSelectedEventIndex(0)
  }, [])

  const selectDetectHolesStage = useCallback(() => {
    const preferPreUnfold = isPreUnfoldStageName(focusedStage)
    let detectStageIndex = preferPreUnfold
      ? groupedStages.findIndex((group) => isPreUnfoldStageName(group.stage))
      : groupedStages.findIndex((group) => isMergedHolesStageName(group.stage))
    if (detectStageIndex < 0 && !preferPreUnfold) {
      detectStageIndex = groupedStages.findIndex((group) => group.stage === MERGED_HOLES_STAGE)
    }
    if (detectStageIndex >= 0) {
      handleSelectStageIndex(detectStageIndex)
      setFocusedStage(groupedStages[detectStageIndex]?.stage || MERGED_HOLES_STAGE)
      return
    }
    setFocusedStage(MERGED_HOLES_STAGE)
  }, [focusedStage, groupedStages, handleSelectStageIndex])

  const selectHole = useCallback(
    (holeId) => {
      selectDetectHolesStage()
      setSelectedFoldId(null)
      setSelectedHoleId(holeId)
      setSelectedProbe(null)
    },
    [selectDetectHolesStage],
  )

  const selectFold = useCallback(
    (foldId) => {
      const normalizedId = normalizeFoldId(foldId)
      if (normalizedId == null) return
      selectDetectHolesStage()
      setSelectedFoldId(normalizedId)
      setSelectedHoleId(null)
      setSelectedProbe(null)
      setProbeMode(false)
    },
    [selectDetectHolesStage],
  )

  const handleSurfaceProbe = useCallback(
    (sample) => {
      if (!sample?.point) return
      const inferredContour = sample.inferredContour || null
      selectDetectHolesStage()
      setSelectedFoldId(null)
      setSelectedHoleId(null)
      setSelectedProbe({
        id: `probe-${Date.now()}`,
        status: 'probe',
        source: useFlatView ? 'flat' : '3d',
        label: 'Handmatige probe',
        reason: inferredContour
          ? 'Waarschijnlijke hole-edge gevonden op deze kliklocatie, maar hij bestaat niet als backend hole-candidate.'
          : 'Geen gedetecteerde hole-candidate op deze kliklocatie binnen de detectieradius.',
        position:
          inferredContour?.position ||
          [sample.point.x, sample.point.y, sample.point.z],
        normal:
          inferredContour?.normal || (sample.normal ? [sample.normal.x, sample.normal.y, sample.normal.z] : [0, 0, 1]),
        nearestHole: sample.nearestHole || null,
        nearestHoleDistance: sample.nearestHoleDistance || null,
        inferredContour,
        criteria: [
          {
            name: 'detected_candidate',
            value: false,
            threshold: true,
            passed: false,
            note: 'Op deze plek is geen geaccepteerde of afgewezen hole-candidate gevonden.',
          },
          ...(inferredContour
            ? [
                {
                  name: 'inferred_edge_contour',
                  value: inferredContour.label || inferredContour.type || 'unknown',
                  threshold: 'known candidate expected',
                  passed: false,
                  note: 'De viewer ziet wel een lokale gesloten edge-loop, maar de pipeline heeft er geen hole-candidate van gemaakt.',
                },
                {
                  name: 'inferred_edge_segments',
                  value: inferredContour.debug?.edge_segment_count ?? null,
                  threshold: '>= 5 nearby segments',
                  passed: false,
                  note: 'Aantal edge-segmenten dat rond de probe als lokale contour is meegenomen.',
                },
                {
                  name: 'probe_confidence',
                  value: inferredContour.debug?.confidence ?? null,
                  threshold: 'higher = stronger contour',
                  passed: false,
                  note: 'Heuristische confidence van de viewer op basis van local edge-shape.',
                },
              ]
            : []),
          ...(sample.nearestHole
            ? [
                {
                  name: 'nearest_known_candidate_distance_mm',
                  value: Number(sample.nearestHoleDistance?.toFixed?.(2) || sample.nearestHoleDistance || 0),
                  threshold: 'inspect only',
                  passed: false,
                  note: `${sample.nearestHole.label || sample.nearestHole.type || 'Onbekend'} is de dichtstbijzijnde bekende kandidaat.`,
                },
              ]
            : []),
        ],
      })
    },
    [selectDetectHolesStage, useFlatView],
  )

  return {
    focusedStage,
    setFocusedStage,
    selectedHoleId,
    setSelectedHoleId,
    selectedFoldId,
    setSelectedFoldId,
    selectedProbe,
    setSelectedProbe,
    probeMode,
    setProbeMode,
    selectedStageIndex,
    setSelectedStageIndex,
    selectedEventIndex,
    setSelectedEventIndex,
    selectedStage,
    activeHoleVisuals,
    selectedHole,
    selectedFeature,
    useFlatView,
    activeMesh,
    parseMode,
    canUseProbeMode,
    showHiddenHoles,
    setShowHiddenHoles,
    highlightHiddenHoleLocations,
    setHighlightHiddenHoleLocations,
    handleSelectStageIndex,
    selectDetectHolesStage,
    selectHole,
    selectFold,
    handleSurfaceProbe,
  }
}
