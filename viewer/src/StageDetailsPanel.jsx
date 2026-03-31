import React, { useEffect, useMemo, useState } from 'react'
import {
  formatDetailValue,
  formatDeviation,
  formatDuration,
  formatLabel,
  getStageMeta,
  isPreUnfoldStageName,
  MERGED_HOLES_STAGE,
  PRE_UNFOLD_HOLES_STAGE,
  summarizePayload,
} from './pipelineUi'
import { normalizeFoldId, isIrregularHole, isHiddenHoleCandidate } from './lib/holes'

function getHoleStatusLabel(status) {
  if (status === 'accepted') return 'Geaccepteerd'
  if (status === 'rejected') return 'Afgewezen'
  if (status === 'probe') return 'Handmatige probe'
  return status || 'Onbekend'
}

function getHoleMethodLabel(method) {
  if (method === 'face_boundary_missing_round') return 'Face Boundary (missend rond)'
  if (method === 'face_boundary_missing_contour') return 'Face Boundary (missende contour)'
  if (method === 'face_boundary_primary') return 'Face Boundary (primair)'
  if (method === 'face_boundary_primary_for_irregular') return 'Face Boundary (irregulair)'
  if (method === 'pre_unfold_face_boundary_bridge_for_missing_irregular') return 'Face Boundary bridge'
  if (method === 'face_boundary_rejected_promoted') return 'Face Boundary promoted'
  if (method === 'face_boundary_round_contour_fallback') return 'Face Boundary round fallback'
  if (method === 'recovery_bucket_fallback') return 'Recovery Bucket (fallback)'
  if (method === 'recovery_bucket_fallback_for_unclassified') return 'Recovery Bucket'
  if (method === 'detect_holes_cylindrical') return 'Cylindrical detector'
  if (method === 'cylindrical_detector') return 'Cylindrical detector'
  return method || 'Onbekend'
}

function getHoleMethodDescription(method) {
  if (method === 'detect_holes_cylindrical' || method === 'cylindrical_detector') {
    return 'Zoekt cilindrische gaten via faces.'
  }
  if (method === 'face_boundary_missing_round' || method === 'face_boundary_missing_contour') {
    return 'Aanvulling alleen op plekken zonder bestaande hole-match.'
  }
  if (
    method === 'face_boundary_primary' ||
    method === 'face_boundary_primary_for_irregular' ||
    method === 'pre_unfold_face_boundary_bridge_for_missing_irregular' ||
    method === 'face_boundary_rejected_promoted' ||
    method === 'face_boundary_round_contour_fallback'
  ) {
    return 'Werkt op face boundaries en inner contours.'
  }
  if (method === 'recovery_bucket_fallback' || method === 'recovery_bucket_fallback_for_unclassified') {
    return 'Fallback voor resterende of onduidelijke kandidaten.'
  }
  return 'Detectiemethode voor deze kandidaatgroep.'
}

function isOverlapRejectedHole(hole) {
  const reason = String(hole?.reason || '').toLowerCase()
  const criteria = Array.isArray(hole?.criteria) ? hole.criteria : []
  return (
    reason.includes('onderdeel van een shaped hole') ||
    criteria.some((criterion) => String(criterion?.name || '').toLowerCase() === 'duplicate_of_shaped_hole')
  )
}

function buildOverlapSummary(items, providedSummary) {
  if (Array.isArray(providedSummary) && providedSummary.length > 0) return providedSummary
  const summary = new Map()
  items.forEach((item) => {
    const overlapWith = item?.overlap_with
    if (!overlapWith) return
    const fromMethod = String(item.method || 'unknown')
    const toMethod = String(overlapWith.method || 'unknown')
    const key = `${fromMethod}__${toMethod}`
    if (!summary.has(key)) {
      summary.set(key, { from_method: fromMethod, to_method: toMethod, count: 0 })
    }
    summary.get(key).count += 1
  })
  return Array.from(summary.values()).sort((a, b) => b.count - a.count)
}

function getClassificationStatusLabel(status) {
  if (status === 'WINNER') return 'Winner'
  if (status === 'MATCH') return 'Match'
  if (status === 'PASS') return 'Pass'
  if (status === 'FAIL') return 'Fail'
  if (status === 'SKIP') return 'Skip'
  if (status === 'FALLTHROUGH') return 'Fallthrough'
  return status || 'Onbekend'
}

function getClassificationStatusClass(status) {
  if (status === 'WINNER' || status === 'MATCH') return 'is-winner'
  if (status === 'PASS') return 'is-accepted'
  if (status === 'FAIL') return 'is-rejected'
  if (status === 'FALLTHROUGH') return 'is-warning'
  return 'is-neutral'
}

export default function StageDetailsPanel({
  pipelineVisuals,
  groupedStages,
  summary,
  liveActiveElapsed,
  selectedStageIndex,
  selectedEventIndex,
  onSelectStageIndex,
  onSelectEventIndex,
  selectedHoleId,
  selectedFoldId,
  onFoldSelect,
  onHoleSelect,
  selectedProbe,
  pipelineStatus,
  showHiddenHoles,
  onShowHiddenHolesChange,
  highlightHiddenHoleLocations,
  onHighlightHiddenHoleLocationsChange,
}) {
  const [holeFilter, setHoleFilter] = useState('all')
  const [activeHoleMethod, setActiveHoleMethod] = useState('all')
  const [exportFeedback, setExportFeedback] = useState('')
  const [showAdvancedHoleDebug, setShowAdvancedHoleDebug] = useState(false)
  const [showHoleInspector, setShowHoleInspector] = useState(false)
  const [showStageExtraOptions, setShowStageExtraOptions] = useState(false)
  const [showHoleExtraOptions, setShowHoleExtraOptions] = useState(false)
  const [showUnfoldExtraOptions, setShowUnfoldExtraOptions] = useState(false)
  const selectedStage = groupedStages[selectedStageIndex] || null
  const selectedEvent = selectedStage?.events?.[selectedEventIndex] || null
  const selectedPayloadEntries = Object.entries(selectedEvent?.payload || {}).filter(([, value]) => value !== undefined)

  const routerVisuals = pipelineVisuals?.router || null
  const classificationVisuals = pipelineVisuals?.classification || null
  const classificationFinal = classificationVisuals?.final_decision || null
  const step0Review = classificationVisuals?.step0_review || null
  const legacyClassification = classificationVisuals?.legacy_classification || null
  const isPreUnfoldHoleStage = isPreUnfoldStageName(selectedStage?.stage)
  const isMergedHoleStage = selectedStage?.stage === MERGED_HOLES_STAGE
  const holeVisuals = isPreUnfoldHoleStage
    ? pipelineVisuals?.holes_pre_unfold || pipelineVisuals?.holes || null
    : pipelineVisuals?.holes || null
  const unfoldVisuals = pipelineVisuals?.unfold || null
  const holeItems = holeVisuals?.items || []
  const boundarySuppressedItems = holeVisuals?.boundary_suppressed || []
  const foldRows = useMemo(() => {
    const bends = unfoldVisuals?.bends_logical || []
    const foldDetails = unfoldVisuals?.fold_details || []
    const rowCount = Math.max(bends.length, foldDetails.length)
    return Array.from({ length: rowCount }, (_, i) => {
      const bend = bends[i] || {}
      const detail = foldDetails[i] || {}
      const id = normalizeFoldId(detail.id || bend.id || i + 1)
      return {
        id,
        direction: bend.type || '–',
        angle: bend.angle ?? null,
        radius: bend.radius ?? null,
        length: detail.length ?? null,
        center: detail.center ?? null,
        axis: detail.axis ?? null,
        start: detail.start ?? null,
        end: detail.end ?? null,
        segmentIndices: detail.segment_indices || [],
      }
    })
  }, [unfoldVisuals])
  const selectedHole = holeItems.find((hole) => hole.id === selectedHoleId) || null
  const normalizedSelectedFoldId = normalizeFoldId(selectedFoldId)
  const selectedFold = foldRows.find((row) => row.id === normalizedSelectedFoldId) || null
  const selectedInspection = selectedHole || selectedProbe
  const preUnfoldGroup = useMemo(
    () => groupedStages.find((group) => isPreUnfoldStageName(group?.stage)) || null,
    [groupedStages],
  )
  const preUnfoldEvents = preUnfoldGroup?.events || []
  const preUnfoldDebugPayload = useMemo(() => {
    const hasPreUnfold = Boolean(preUnfoldGroup)
    const effectiveEvents = hasPreUnfold ? preUnfoldEvents : selectedStage?.events || []
    const effectiveVisuals = hasPreUnfold
      ? pipelineVisuals?.holes_pre_unfold || holeVisuals || null
      : holeVisuals || null
    if (!effectiveVisuals && effectiveEvents.length === 0) return null

    return {
      generated_at: new Date().toISOString(),
      source_stage: hasPreUnfold ? preUnfoldGroup.stage : selectedStage?.stage || 'Unknown',
      event_count: effectiveEvents.length,
      timeline_summary: summary || null,
      pre_unfold_hole_visuals: effectiveVisuals,
      selected_stage: selectedStage?.stage || null,
      selected_event: selectedEvent
        ? {
            type: selectedEvent.type,
            status: selectedEvent.status,
            timestamp_ms: selectedEvent.timestamp_ms,
            payload: selectedEvent.payload || null,
          }
        : null,
      pre_unfold_events: effectiveEvents.map((event) => ({
        type: event.type,
        status: event.status,
        timestamp_ms: event.timestamp_ms,
        original_stage: event.originalStage || event.stage,
        payload: event.payload || null,
      })),
    }
  }, [
    holeVisuals,
    pipelineVisuals?.holes_pre_unfold,
    preUnfoldEvents,
    preUnfoldGroup,
    selectedEvent,
    selectedStage?.events,
    selectedStage?.stage,
    summary,
  ])
  const hiddenHoleItems = useMemo(() => holeItems.filter((hole) => isHiddenHoleCandidate(hole)), [holeItems])
  const normalHoleItems = useMemo(
    () => holeItems.filter((hole) => hole.status === 'accepted' && !isIrregularHole(hole)),
    [holeItems],
  )
  const irregularHoleItems = useMemo(
    () => holeItems.filter((hole) => isIrregularHole(hole) || hole.status === 'rejected'),
    [holeItems],
  )
  const overlapRejectedHoleItems = useMemo(
    () => holeItems.filter((hole) => hole.status === 'rejected' && isOverlapRejectedHole(hole)),
    [holeItems],
  )
  const baseVisibleHoleItems = useMemo(() => {
    if (showHiddenHoles) return holeItems
    return holeItems.filter((hole) => !isHiddenHoleCandidate(hole))
  }, [holeItems, showHiddenHoles])
  const visibleHoleItems = useMemo(() => {
    if (holeFilter === 'accepted') return baseVisibleHoleItems.filter((hole) => hole.status === 'accepted')
    if (holeFilter === 'rejected') return baseVisibleHoleItems.filter((hole) => hole.status === 'rejected')
    return baseVisibleHoleItems
  }, [baseVisibleHoleItems, holeFilter])
  const holeMethods = useMemo(() => {
    const methodMap = new Map()
    holeItems.forEach((hole) => {
      const method = hole.method || 'unknown'
      if (!methodMap.has(method)) {
        methodMap.set(method, {
          key: method,
          label: getHoleMethodLabel(method),
          description: getHoleMethodDescription(method),
          items: [],
        })
      }
      methodMap.get(method).items.push(hole)
    })

    const orderedKeys = [
      ...(Array.isArray(holeVisuals?.method_order) ? holeVisuals.method_order : []),
      ...Array.from(methodMap.keys()),
    ].filter((value, index, array) => value && array.indexOf(value) === index)

    return orderedKeys
      .filter((key) => methodMap.has(key))
      .map((key) => {
        const group = methodMap.get(key)
        const items = group.items
        return {
          ...group,
          total: items.length,
          accepted: items.filter((hole) => hole.status === 'accepted').length,
          rejected: items.filter((hole) => hole.status === 'rejected').length,
          overlapRejected: items.filter((hole) => hole.status === 'rejected' && isOverlapRejectedHole(hole)).length,
          netUnique: items.filter((hole) => hole.status === 'accepted').length,
          visible: items.filter((hole) => showHiddenHoles || !isHiddenHoleCandidate(hole)).length,
        }
      })
  }, [holeItems, holeVisuals?.method_order, showHiddenHoles])
  const overlapReductionSummary = useMemo(
    () => ({
      rawCandidates: holeItems.length,
      overlapRejected: overlapRejectedHoleItems.length,
      otherRejected: holeItems.filter((hole) => hole.status === 'rejected' && !isOverlapRejectedHole(hole)).length,
      netUnique: holeItems.filter((hole) => hole.status === 'accepted').length,
    }),
    [holeItems, overlapRejectedHoleItems],
  )
  const overlapSummary = useMemo(
    () => buildOverlapSummary(holeItems, holeVisuals?.overlap_summary),
    [holeItems, holeVisuals?.overlap_summary],
  )
  const activeHoleItems = useMemo(() => {
    const methodFiltered =
      activeHoleMethod === 'all'
        ? visibleHoleItems
        : visibleHoleItems.filter((hole) => (hole.method || 'unknown') === activeHoleMethod)
    return methodFiltered
  }, [activeHoleMethod, visibleHoleItems])
  const overlapSummaryForActiveMethod = useMemo(() => {
    if (activeHoleMethod === 'all') return overlapSummary
    return overlapSummary.filter(
      (entry) => entry.from_method === activeHoleMethod || entry.to_method === activeHoleMethod,
    )
  }, [activeHoleMethod, overlapSummary])
  const visibleHoleCriteriaNote = useMemo(() => {
    const note = String(holeVisuals?.criteria_note || '').trim()
    if (!note) return ''
    if (note.includes('tijdelijk uitgeschakeld')) return ''
    return note
  }, [holeVisuals?.criteria_note])
  const activeHoleMethodSummary = useMemo(() => {
    if (activeHoleMethod === 'all') {
      return {
        label: 'Alle tools',
        description: 'Gecombineerde lijst van alle zichtbare kandidaten.',
      }
    }
    const selectedMethod = holeMethods.find((method) => method.key === activeHoleMethod)
    return (
      selectedMethod || {
        label: getHoleMethodLabel(activeHoleMethod),
        description: getHoleMethodDescription(activeHoleMethod),
      }
    )
  }, [activeHoleMethod, holeMethods])

  useEffect(() => {
    setShowAdvancedHoleDebug(false)
    setExportFeedback('')
    setActiveHoleMethod('all')
    setShowHoleInspector(false)
    setShowStageExtraOptions(false)
    setShowHoleExtraOptions(false)
    setShowUnfoldExtraOptions(false)
  }, [selectedStage?.stage])

  const downloadPreUnfoldDebug = () => {
    if (!preUnfoldDebugPayload) return
    const fileName = `pre-unfold-hole-debug-${Date.now()}.json`
    const content = JSON.stringify(preUnfoldDebugPayload, null, 2)
    try {
      const blob = new Blob([content], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      setExportFeedback(`Debug JSON gedownload: ${fileName}`)
    } catch {
      try {
        const dataUrl = `data:application/json;charset=utf-8,${encodeURIComponent(content)}`
        window.open(dataUrl, '_blank', 'noopener,noreferrer')
        setExportFeedback('Download fallback geopend in nieuwe tab')
      } catch {
        setExportFeedback('Download mislukt in deze browser')
      }
    }
  }

  const copyPreUnfoldDebug = async () => {
    if (!preUnfoldDebugPayload) return
    const content = JSON.stringify(preUnfoldDebugPayload, null, 2)
    try {
      await navigator.clipboard.writeText(content)
      setExportFeedback('Debug JSON gekopieerd naar klembord')
    } catch {
      try {
        const textArea = document.createElement('textarea')
        textArea.value = content
        textArea.style.position = 'fixed'
        textArea.style.left = '-9999px'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        const ok = document.execCommand('copy')
        document.body.removeChild(textArea)
        setExportFeedback(ok ? 'Debug JSON gekopieerd (fallback)' : 'Kopieren mislukt (clipboard niet beschikbaar)')
      } catch {
        setExportFeedback('Kopieren mislukt (clipboard niet beschikbaar)')
      }
    }
  }

  if (!selectedStage) {
    return (
      <div className="details-panel">
        <div className="details-placeholder">Kies links een afgeronde pipeline-stap om hier de details te zien.</div>
      </div>
    )
  }

  const stageMeta = getStageMeta(selectedStage, summary, liveActiveElapsed, pipelineStatus)
  const previousSelectableIndex = groupedStages
    .slice(0, selectedStageIndex)
    .map((group, index) => ({
      index,
      selectable: getStageMeta(group, summary, liveActiveElapsed, pipelineStatus).isSelectable,
    }))
    .filter((item) => item.selectable)
    .map((item) => item.index)
    .pop()
  const nextSelectableIndex = groupedStages
    .slice(selectedStageIndex + 1)
    .map((group, offset) => ({
      index: selectedStageIndex + offset + 1,
      selectable: getStageMeta(group, summary, liveActiveElapsed, pipelineStatus).isSelectable,
    }))
    .find((item) => item.selectable)?.index

  return (
    <div className="details-panel">
      <div className="timeline-detail-card">
        <div className="timeline-detail-head">
          <div>
            <div className="timeline-title">{selectedStage.stage}</div>
            <div className="timeline-text">
              Stap {selectedStageIndex + 1} van {groupedStages.length}
            </div>
            <div className="timeline-text">{`${stageMeta.stateLabel} · ${formatDuration(stageMeta.elapsed)}`}</div>
          </div>
          <div className="timeline-nav">
            <button
              className="timeline-nav-btn"
              onClick={() => {
                if (previousSelectableIndex == null) return
                onSelectStageIndex(previousSelectableIndex)
              }}
              disabled={previousSelectableIndex == null}
            >
              Vorige
            </button>
            <button
              className="timeline-nav-btn"
              onClick={() => {
                if (nextSelectableIndex == null) return
                onSelectStageIndex(nextSelectableIndex)
              }}
              disabled={nextSelectableIndex == null}
            >
              Volgende
            </button>
          </div>
        </div>

        {selectedEvent && (
          <div className="timeline-payload">
            {(isMergedHoleStage || isPreUnfoldHoleStage) && holeVisuals && (
              <div className="visual-stage-card" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none' }}>
                <div className="timeline-title">Hole Overlay</div>
                <div className="hole-summary-grid">
                  <div className="hole-summary-card">
                    <div className="hole-summary-label">Kandidaten</div>
                    <div className="hole-summary-value">{holeVisuals.total_candidates || 0}</div>
                  </div>
                  <div className="hole-summary-card">
                    <div className="hole-summary-label">Gevonden</div>
                    <div className="hole-summary-value">{holeVisuals.accepted_total || 0}</div>
                  </div>
                  <div className="hole-summary-card">
                    <div className="hole-summary-label">Afgewezen</div>
                    <div className="hole-summary-value">{holeVisuals.rejected_total || 0}</div>
                  </div>
                  <div className="hole-summary-card">
                    <div className="hole-summary-label">Zichtbaar</div>
                    <div className="hole-summary-value">{baseVisibleHoleItems.length}</div>
                  </div>
                  <div className="hole-summary-card">
                    <div className="hole-summary-label">Overlap eruit</div>
                    <div className="hole-summary-value">{overlapReductionSummary.overlapRejected}</div>
                  </div>
                  <div className="hole-summary-card">
                    <div className="hole-summary-label">Netto uniek</div>
                    <div className="hole-summary-value">{overlapReductionSummary.netUnique}</div>
                  </div>
                  <div className="hole-summary-card">
                    <div className="hole-summary-label">Boundary onderdrukt</div>
                    <div className="hole-summary-value">{boundarySuppressedItems.length}</div>
                  </div>
                </div>
                <div className="timeline-text">
                  Bron: {holeVisuals.source || '-'} | Viewer totaal {holeItems.length}
                  {hiddenHoleItems.length > 0 ? ` | Verborgen ${hiddenHoleItems.length}` : ''}
                </div>
                <div className="timeline-text">
                  Reductie: raw {overlapReductionSummary.rawCandidates}, overlap eruit {overlapReductionSummary.overlapRejected}, netto{' '}
                  {overlapReductionSummary.netUnique}
                  {overlapReductionSummary.otherRejected > 0
                    ? ` | overige afwijzingen ${overlapReductionSummary.otherRejected}`
                    : ''}
                </div>
                <div className="hole-filter-row" style={{ marginTop: 8 }}>
                  <button
                    className={`hole-filter-btn ${showHoleInspector ? 'is-active' : ''}`}
                    onClick={() => setShowHoleInspector((value) => !value)}
                  >
                    {showHoleInspector ? 'Sluit detailweergave' : 'Open detailweergave'}
                  </button>
                  <button
                    className={`hole-filter-btn ${showHoleExtraOptions ? 'is-active' : ''}`}
                    onClick={() => setShowHoleExtraOptions((value) => !value)}
                  >
                    {showHoleExtraOptions ? 'Verberg hole extra opties' : 'Toon hole extra opties'}
                  </button>
                  <button
                    className={`hole-filter-btn ${showAdvancedHoleDebug ? 'is-active' : ''}`}
                    onClick={() => setShowAdvancedHoleDebug((value) => !value)}
                  >
                    {showAdvancedHoleDebug ? 'Verberg uitgebreide debug' : 'Toon uitgebreide debug'}
                  </button>
                </div>

                {showHoleExtraOptions && overlapSummary.length > 0 && (
                  <div className="reasoning-list" style={{ marginTop: 8 }}>
                    <div className="reasoning-card">
                      <div className="timeline-title">Overlap Tussen Tools</div>
                      <div className="timeline-payload-grid">
                        {overlapSummary.map((entry) => (
                          <div className="timeline-payload-row" key={`overlap-${entry.from_method}-${entry.to_method}`}>
                            <div className="timeline-item-head">
                              <div className="timeline-payload-key">
                                {getHoleMethodLabel(entry.from_method)} -&gt; {getHoleMethodLabel(entry.to_method)}
                              </div>
                              <span className="hole-status-pill is-warning">{entry.count}</span>
                            </div>
                            <div className="timeline-text">
                              {entry.count} kandidaat{entry.count === 1 ? '' : 'en'} van {getHoleMethodLabel(entry.from_method)} zijn
                              weggefilterd door {getHoleMethodLabel(entry.to_method)}.
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {showHoleExtraOptions && visibleHoleCriteriaNote && <div className="timeline-text">{visibleHoleCriteriaNote}</div>}
                {showHoleExtraOptions && boundarySuppressedItems.length > 0 && (
                  <div className="reasoning-list" style={{ marginTop: 8 }}>
                    <div className="reasoning-card">
                      <div className="timeline-title">Boundary Onderdrukt Door Cilindrisch</div>
                      <div className="timeline-payload-grid">
                        {boundarySuppressedItems.slice(0, 8).map((item) => (
                          <div className="timeline-payload-row" key={item.id}>
                            <div className="timeline-item-head">
                              <div className="timeline-payload-key">{item.label || item.size || 'Boundary contour'}</div>
                              <span className="hole-status-pill is-neutral">Onderdrukt</span>
                            </div>
                            <div className="timeline-text">{item.reason}</div>
                            <div className="timeline-text">
                              Match: {getHoleMethodLabel(item.suppressed_by?.method)} | {item.suppressed_by?.label || '-'}
                            </div>
                            <div className="timeline-text">Positie {formatDetailValue(item.position)}</div>
                          </div>
                        ))}
                      </div>
                      {boundarySuppressedItems.length > 8 && (
                        <div className="timeline-text">
                          Nog {boundarySuppressedItems.length - 8} onderdrukte boundary-kandidaten buiten dit compacte overzicht.
                        </div>
                      )}
                    </div>
                  </div>
                )}
                <div className="timeline-text" style={{ marginTop: 8 }}>
                  Snel overzicht: normale gaten {normalHoleItems.length} | irregulair/afgewezen {irregularHoleItems.length}
                </div>

                <div className="timeline-text" style={{ marginTop: 4 }}>
                  Kleur: <span style={{ color: '#ff4d3b' }}>rood</span> = cilindrisch,{' '}
                  <span style={{ color: '#d97706' }}>oranje</span> = Face Boundary aanvulling,{' '}
                  <span style={{ color: '#2dd4bf' }}>blauw-groen</span> = gevormd/irregulair,{' '}
                  <span style={{ color: '#f5c542' }}>goud</span> = geselecteerd
                </div>
                <div className="hole-toggle-row" style={{ marginTop: 6 }}>
                  <button
                    className={`hole-filter-btn ${showHiddenHoles ? 'is-active' : ''}`}
                    onClick={() => onShowHiddenHolesChange?.(!showHiddenHoles)}
                    title="Toon of verberg afgewezen gaten in het 3D model"
                  >
                    {showHiddenHoles ? 'Verberg afgewezen' : 'Toon afgewezen'}
                  </button>
                  <button
                    className={`hole-filter-btn ${highlightHiddenHoleLocations ? 'is-active' : ''}`}
                    onClick={() => onHighlightHiddenHoleLocationsChange?.(!highlightHiddenHoleLocations)}
                    title="Toon of verberg extra locatie-markers op het 3D model"
                  >
                    {highlightHiddenHoleLocations ? 'Locatie-markers aan' : 'Locatie-markers uit'}
                  </button>
                </div>

                {holeMethods.length > 0 && (
                  <div className="hole-method-grid">
                    {holeMethods.map((method) => (
                      <button
                        key={method.key}
                        className={`hole-method-card ${activeHoleMethod === method.key ? 'is-active' : ''}`}
                        onClick={() => {
                          setActiveHoleMethod(method.key)
                          setShowHoleInspector(true)
                        }}
                        type="button"
                      >
                        <div className="timeline-item-head">
                          <span className="timeline-stage">{method.label}</span>
                          <span className="hole-status-pill is-neutral">{method.total}</span>
                        </div>
                        <div className="timeline-text">{method.description}</div>
                        <div className="hole-method-stats">
                          <span>Raw {method.total}</span>
                          <span>Gevonden {method.accepted}</span>
                          <span>Afgewezen {method.rejected}</span>
                          <span>Overlap eruit {method.overlapRejected}</span>
                          <span>Netto {method.netUnique}</span>
                          <span>Zichtbaar {method.visible}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {!showAdvancedHoleDebug && !showHoleInspector && (
                  <>
                    <div className="timeline-text" style={{ marginTop: 8 }}>
                      Kies een toolkaart om de kandidaten van alleen die methode te zien. Zo blijft de rechterkant compact.
                    </div>
                    {selectedInspection && (
                      <div className="reasoning-list">
                        <div className="reasoning-card">
                          <div className="timeline-stage">
                            {selectedInspection.label || formatLabel(selectedInspection.type)} |{' '}
                            {getHoleStatusLabel(selectedInspection.status)}
                          </div>
                          <div className="timeline-text">{selectedInspection.reason || 'Geen toelichting'}</div>
                          <div className="timeline-text">
                            Tool: {getHoleMethodLabel(selectedInspection.method)} | Positie{' '}
                            {formatDetailValue(selectedInspection.position)}
                          </div>
                        </div>
                      </div>
                    )}
                    {normalHoleItems.length === 0 && irregularHoleItems.length === 0 && (
                      <div className="timeline-text" style={{ marginTop: 8 }}>
                        Geen pre-unfold gaten gevonden in deze stap.
                      </div>
                    )}
                  </>
                )}

                {showHoleInspector && (
                  <div className="hole-inspector-panel">
                    <div className="timeline-item-head">
                      <div>
                        <div className="timeline-title" style={{ marginTop: 0 }}>
                          Details: {activeHoleMethodSummary.label}
                        </div>
                        <div className="timeline-text">{activeHoleMethodSummary.description}</div>
                      </div>
                      <button className="hole-filter-btn" onClick={() => setShowHoleInspector(false)}>
                        Sluiten
                      </button>
                    </div>
                    <div className="hole-filter-row">
                      <button
                        className={`hole-filter-btn ${activeHoleMethod === 'all' ? 'is-active' : ''}`}
                        onClick={() => setActiveHoleMethod('all')}
                      >
                        Alle tools
                      </button>
                      {holeMethods.map((method) => (
                        <button
                          key={`filter-${method.key}`}
                          className={`hole-filter-btn ${activeHoleMethod === method.key ? 'is-active' : ''}`}
                          onClick={() => setActiveHoleMethod(method.key)}
                        >
                          {method.label}
                        </button>
                      ))}
                    </div>
                    <div className="hole-filter-row">
                      <button
                        className={`hole-filter-btn ${holeFilter === 'all' ? 'is-active' : ''}`}
                        onClick={() => setHoleFilter('all')}
                      >
                        Alle
                      </button>
                      <button
                        className={`hole-filter-btn ${holeFilter === 'accepted' ? 'is-active' : ''}`}
                        onClick={() => setHoleFilter('accepted')}
                      >
                        Gevonden
                      </button>
                      <button
                        className={`hole-filter-btn ${holeFilter === 'rejected' ? 'is-active' : ''}`}
                        onClick={() => setHoleFilter('rejected')}
                      >
                        Afgewezen
                      </button>
                    </div>
                    {overlapSummaryForActiveMethod.length > 0 && (
                      <div className="reasoning-list">
                        <div className="reasoning-card">
                          <div className="timeline-title">Overlap In Deze Selectie</div>
                          <div className="timeline-payload-grid">
                            {overlapSummaryForActiveMethod.map((entry) => (
                              <div
                                className="timeline-payload-row"
                                key={`active-overlap-${entry.from_method}-${entry.to_method}`}
                              >
                                <div className="timeline-item-head">
                                  <div className="timeline-payload-key">
                                    {getHoleMethodLabel(entry.from_method)} -&gt; {getHoleMethodLabel(entry.to_method)}
                                  </div>
                                  <span className="hole-status-pill is-warning">{entry.count}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                    <div className="hole-list">
                      {activeHoleItems.map((hole) => (
                        <button
                          key={hole.id}
                          className={`hole-list-item ${selectedHoleId === hole.id ? 'is-active' : ''} is-${hole.status}`}
                          onClick={() => onHoleSelect?.(hole.id)}
                        >
                          <div className="timeline-item-head">
                            <span className="timeline-stage">{hole.label || formatLabel(hole.type)}</span>
                            <span className={`hole-status-pill is-${hole.status}`}>
                              {getHoleStatusLabel(hole.status)}
                            </span>
                          </div>
                          <div className="timeline-text">{hole.reason || 'Geen toelichting'}</div>
                          <div className="timeline-text">
                            {getHoleMethodLabel(hole.method)} | {formatLabel(hole.type)} | {hole.source || '-'}
                          </div>
                          {hole.overlap_with && (
                            <div className="timeline-text">
                              Overlap: {getHoleMethodLabel(hole.method)} -&gt; {getHoleMethodLabel(hole.overlap_with.method)} | wint:{' '}
                              {hole.overlap_with.label || formatLabel(hole.overlap_with.type)}
                            </div>
                          )}
                          {hole.recovered_from && (
                            <div className="timeline-text">
                              Recovery: boundary toegevoegd nadat {hole.recovered_from.label || 'cilindrische kandidaat'} afviel
                            </div>
                          )}
                          {isOverlapRejectedHole(hole) && (
                            <div className="timeline-text">Overlap/dubbel met andere methode</div>
                          )}
                        </button>
                      ))}
                    </div>
                    {activeHoleItems.length === 0 && (
                      <div className="timeline-text" style={{ marginTop: 8 }}>
                        Geen gaten in deze filter.
                      </div>
                    )}
                  </div>
                )}

                {showAdvancedHoleDebug && (
                  <>
                    {Array.isArray(holeVisuals.method_order) && holeVisuals.method_order.length > 0 && (
                      <div className="timeline-text">Methodiekvolgorde: {holeVisuals.method_order.join(' -> ')}</div>
                    )}
                    <div className="hole-filter-row" style={{ marginTop: 8 }}>
                      <button
                        className="hole-filter-btn"
                        onClick={downloadPreUnfoldDebug}
                        disabled={!preUnfoldDebugPayload}
                      >
                        Download pre-unfold debug JSON
                      </button>
                      <button
                        className="hole-filter-btn"
                        onClick={copyPreUnfoldDebug}
                        disabled={!preUnfoldDebugPayload}
                      >
                        Kopieer pre-unfold debug
                      </button>
                    </div>
                    {exportFeedback && <div className="timeline-text">{exportFeedback}</div>}
                    {holeVisuals.thresholds && (
                      <div className="reasoning-list" style={{ marginTop: 8 }}>
                        <div className="reasoning-card">
                          <div className="timeline-title">Thresholds</div>
                          <div className="timeline-payload-grid">
                            {Object.entries(holeVisuals.thresholds).map(([key, value]) => (
                              <div className="timeline-payload-row" key={`hole-threshold-${key}`}>
                                <div className="timeline-payload-key">{formatLabel(key)}</div>
                                <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                    <div className="timeline-text">
                      Klik op een gat om exact de gedetecteerde hole-rand te highlighten en de camera erop te focussen.
                      In `Probe mode` wordt elke klik op het model altijd een probe op exact die plek, zonder snap naar
                      een bekende hole.
                    </div>
                    {hiddenHoleItems.length > 0 && (
                      <div className="timeline-text">
                        Extra locatie-markers staan op de afgewezen/irregulaire gaten zodat direct zichtbaar is waar de
                        ontbrekende gaten op het model zitten.
                      </div>
                    )}
                  </>
                )}
                {selectedInspection && showAdvancedHoleDebug && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-stage">
                        {selectedInspection.label || formatLabel(selectedInspection.type)} |{' '}
                        {getHoleStatusLabel(selectedInspection.status)}
                      </div>
                      <div className="timeline-text">{selectedInspection.reason || 'Geen toelichting'}</div>
                      <div className="timeline-text">Methodiek: {getHoleMethodLabel(selectedInspection.method)}</div>
                      {isOverlapRejectedHole(selectedInspection) && (
                        <div className="timeline-text">Deze kandidaat is afgewezen als overlap/dubbel met een shaped detectie.</div>
                      )}
                      {selectedInspection.overlap_with && (
                        <div className="timeline-text">
                          Koppeling: {getHoleMethodLabel(selectedInspection.method)} -&gt;{' '}
                          {getHoleMethodLabel(selectedInspection.overlap_with.method)} | wint:{' '}
                          {selectedInspection.overlap_with.label || formatLabel(selectedInspection.overlap_with.type)}
                          {selectedInspection.overlap_with.distance != null
                            ? ` op ${formatDetailValue(selectedInspection.overlap_with.distance)} mm`
                            : ''}
                        </div>
                      )}
                      {selectedInspection.recovered_from && (
                        <div className="timeline-text">
                          Recovery vanaf reject: {selectedInspection.recovered_from.label || 'cilindrische kandidaat'} |{' '}
                          {selectedInspection.recovered_from.reason || 'cilindrische detectie afgewezen'}
                        </div>
                      )}
                      <pre className="timeline-payload-value">{formatDetailValue(selectedInspection.position)}</pre>
                      {selectedInspection.inferredContour && (
                        <div className="timeline-text">
                          Inferred contour:{' '}
                          {selectedInspection.inferredContour.label ||
                            formatLabel(selectedInspection.inferredContour.type)}
                        </div>
                      )}
                      {selectedInspection.nearestHole && (
                        <div className="timeline-text">
                          Dichtstbijzijnde bekende kandidaat:{' '}
                          {selectedInspection.nearestHole.label || formatLabel(selectedInspection.nearestHole.type)} op{' '}
                          {formatDetailValue(selectedInspection.nearestHoleDistance)} mm.
                        </div>
                      )}
                    </div>
                    <div className="reasoning-card">
                      <div className="timeline-title">Criteria</div>
                      <div className="timeline-payload-grid">
                        {(selectedInspection.criteria || []).map((criterion, index) => (
                          <div className="timeline-payload-row" key={`${selectedInspection.id}-criterion-${index}`}>
                            <div className="timeline-item-head">
                              <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
                              <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                                {criterion.passed ? 'Pass' : 'Fail'}
                              </span>
                            </div>
                            <pre className="timeline-payload-value">
                              {formatDetailValue({
                                value: criterion.value,
                                threshold: criterion.threshold,
                                note: criterion.note,
                              })}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </div>
                    {selectedInspection.inferredContour?.debug && (
                      <div className="reasoning-card">
                        <div className="timeline-title">Probe Debug</div>
                        <div className="timeline-text">
                          Viewer heuristic: {selectedInspection.inferredContour.debug.inferred_family} | confidence{' '}
                          {formatDetailValue(selectedInspection.inferredContour.debug.confidence)}
                        </div>
                        <div className="timeline-payload-grid">
                          {Object.entries(selectedInspection.inferredContour.debug).map(([key, value]) => (
                            <div className="timeline-payload-row" key={`${selectedInspection.id}-debug-${key}`}>
                              <div className="timeline-payload-key">{formatLabel(key)}</div>
                              <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {selectedInspection == null && showAdvancedHoleDebug && (
                  <div className="timeline-text" style={{ marginTop: 8 }}>
                    Kies een gat links of klik in het 3D-model om criteria en viewer-focus te zien.
                  </div>
                )}
              </div>
            )}

            {selectedStage.stage === 'Classify geometry' && classificationVisuals && (
              <div className="visual-stage-card">
                <div className="timeline-title">Classificatie Flow</div>
                <div className="timeline-text">
                  Categorie: {classificationVisuals.part_category || '-'} | Type:{' '}
                  {classificationVisuals.part_type || '-'}
                </div>
                <div className="timeline-text">Dikte: {classificationVisuals.thickness ?? '-'} mm</div>
                <div className="timeline-text">
                  Visualisatie: donkerrood = section contouren, oranje = buitenmaat, roze = tweede maat, geel =
                  dikte-as.
                </div>

                {routerVisuals && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Voorclassificatie uit sections</div>
                        <span className="hole-status-pill is-warning">Router ingebed</span>
                      </div>
                      <div className="timeline-text">
                        Router category: {routerVisuals.category || '-'} | Label: {routerVisuals.profile_label || '-'}
                      </div>
                      <div className="timeline-text">
                        Confidence: {Math.round((routerVisuals.confidence || 0) * 100)}% | Methode:{' '}
                        {routerVisuals.method || '-'}
                      </div>
                      <div className="timeline-text">
                        {routerVisuals.reason || routerVisuals.reasoning || 'Geen extra router-uitleg'}
                      </div>
                      {routerVisuals.features && (
                        <div className="timeline-payload-grid">
                          {Object.entries(routerVisuals.features).map(([key, value]) => (
                            <div className="timeline-payload-row" key={`router-${key}`}>
                              <div className="timeline-payload-key">{formatLabel(key)}</div>
                              <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {classificationFinal && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Eindbesluit</div>
                        <span
                          className={`hole-status-pill ${classificationFinal.step0_only ? 'is-accepted' : 'is-warning'}`}
                        >
                          {classificationFinal.step0_only ? 'Step 0 only' : 'Step 0 -> legacy'}
                        </span>
                      </div>
                      <div className="timeline-text">
                        Klasse: {formatLabel(classificationFinal.classification)} | Gestopt in:{' '}
                        {classificationFinal.stopped_in || '-'}
                      </div>
                      <div className="timeline-text">Bron: {classificationFinal.source || '-'}</div>
                    </div>
                  </div>
                )}

                {step0Review && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Step 0 Review</div>
                        <span className={`hole-status-pill ${step0Review.fallthrough ? 'is-warning' : 'is-accepted'}`}>
                          {step0Review.fallthrough ? 'Fallthrough' : 'Besliste'}
                        </span>
                      </div>
                      <div className="timeline-text">
                        Bron:{' '}
                        {step0Review.doc || classificationVisuals.step0_doc || 'docs/classification_step_review.md'}
                      </div>
                      {step0Review.stopped_in && (
                        <div className="timeline-text">Stopte in: {step0Review.stopped_in}</div>
                      )}
                      {step0Review.error && <div className="timeline-text">Trace-fout: {step0Review.error}</div>}
                    </div>
                    {(step0Review.steps || []).map((step) => (
                      <div className="reasoning-card" key={`step0-${step.step}`}>
                        <div className="timeline-item-head">
                          <div className="timeline-stage">
                            {step.step} | {step.name}
                          </div>
                          <span className={`hole-status-pill ${getClassificationStatusClass(step.status)}`}>
                            {getClassificationStatusLabel(step.status)}
                          </span>
                        </div>
                        {step.result && <div className="timeline-text">Resultaat: {formatLabel(step.result)}</div>}
                        {step.next && <div className="timeline-text">Volgende stap: {step.next}</div>}
                        {step.note && <div className="timeline-text">{step.note}</div>}
                        <div className="timeline-payload-grid">
                          {(step.criteria || []).map((criterion, index) => (
                            <div className="timeline-payload-row" key={`step0-${step.step}-${criterion.name}-${index}`}>
                              <div className="timeline-item-head">
                                <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
                                {typeof criterion.passed === 'boolean' && (
                                  <span
                                    className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}
                                  >
                                    {criterion.passed ? 'Pass' : 'Fail'}
                                  </span>
                                )}
                                {criterion.passed == null && <span className="hole-status-pill is-neutral">Info</span>}
                              </div>
                              <div className="timeline-text">
                                Actual: {formatDetailValue(criterion.actual)} | Threshold:{' '}
                                {formatDetailValue(criterion.threshold)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {legacyClassification && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-item-head">
                        <div className="timeline-stage">Legacy Classify Fallback</div>
                        <span className="hole-status-pill is-warning">Actief</span>
                      </div>
                      <div className="timeline-text">
                        Bron:{' '}
                        {legacyClassification.doc ||
                          classificationVisuals.matrix_doc ||
                          'docs/CLASSIFICATION_THRESHOLDS_MATRIX.md'}
                      </div>
                      {legacyClassification.winner_gate && (
                        <div className="timeline-text">Winnende gate: STEP {legacyClassification.winner_gate}</div>
                      )}
                      {(legacyClassification.rules || []).length > 0 && (
                        <div className="timeline-text">
                          Beslispad: {(legacyClassification.rules || []).join(' -> ')}
                        </div>
                      )}
                    </div>
                    {(legacyClassification.gates || []).map((gate) => (
                      <div className="reasoning-card" key={`legacy-${gate.step}`}>
                        <div className="timeline-item-head">
                          <div className="timeline-stage">
                            STEP {gate.step} | {gate.name}
                          </div>
                          <span className={`hole-status-pill ${getClassificationStatusClass(gate.status)}`}>
                            {getClassificationStatusLabel(gate.status)}
                          </span>
                        </div>
                        <div className="timeline-text">{gate.description}</div>
                        {gate.rule && <div className="timeline-text">Winnende rule: {gate.rule}</div>}
                        <div className="timeline-payload-grid">
                          {(gate.criteria || []).map((criterion, index) => (
                            <div
                              className="timeline-payload-row"
                              key={`legacy-${gate.step}-${criterion.name}-${index}`}
                            >
                              <div className="timeline-item-head">
                                <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
                                {typeof criterion.passed === 'boolean' && (
                                  <span
                                    className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}
                                  >
                                    {criterion.passed ? 'Pass' : 'Fail'}
                                  </span>
                                )}
                              </div>
                              <div className="timeline-text">
                                Actual: {formatDetailValue(criterion.actual)} | Threshold:{' '}
                                {formatDetailValue(criterion.threshold)} | Delta: {formatDeviation(criterion.deviation)}
                              </div>
                              {criterion.note && <div className="timeline-text">{criterion.note}</div>}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {!step0Review &&
                  (classificationVisuals.matrix_doc || (classificationVisuals.rules || []).length > 0) && (
                    <div className="timeline-text">Bron: {classificationVisuals.matrix_doc || '-'}</div>
                  )}

                {!step0Review && (classificationVisuals.criteria || []).length > 0 && (
                  <div className="reasoning-list">
                    {(classificationVisuals.criteria || []).map((criterion, index) => (
                      <div className="reasoning-card" key={`${criterion.step}-${criterion.name}-${index}`}>
                        <div className="timeline-item-head">
                          <div className="timeline-stage">
                            {criterion.step} | {criterion.name}
                          </div>
                          {typeof criterion.passed === 'boolean' && (
                            <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                              {criterion.passed ? 'Pass' : 'Fail'}
                            </span>
                          )}
                        </div>
                        <div className="timeline-text">
                          Actual: {formatDetailValue(criterion.actual)} | Threshold:{' '}
                          {formatDetailValue(criterion.threshold)} | Delta: {formatDeviation(criterion.deviation)}
                        </div>
                        {criterion.note && <div className="timeline-text">{criterion.note}</div>}
                      </div>
                    ))}
                  </div>
                )}

                {(classificationVisuals.reasoning || []).length > 0 && (
                  <div className="reasoning-list">
                    <div className="reasoning-card">
                      <div className="timeline-stage">Aanvullende reasoning</div>
                      <div className="timeline-text">
                        Deze uitleg komt uit de geometrie-analyse en ondersteunt de classify-flow hierboven.
                      </div>
                    </div>
                    {(classificationVisuals.reasoning || []).map((reason, index) => (
                      <div className="reasoning-card" key={`${reason.step}-${index}`}>
                        <div className="timeline-stage">{reason.step}</div>
                        <div className="timeline-text">{reason.observation}</div>
                        <div className="timeline-text">{reason.conclusion}</div>
                        {reason.details && Object.keys(reason.details).length > 0 && (
                          <pre className="timeline-payload-value">{formatDetailValue(reason.details)}</pre>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {selectedStage.stage === MERGED_HOLES_STAGE && (
              <div className="visual-stage-card">
                <div className="timeline-title">Unfold data</div>
                <div className="hole-filter-row" style={{ marginTop: 8 }}>
                  <button
                    className={`hole-filter-btn ${showUnfoldExtraOptions ? 'is-active' : ''}`}
                    onClick={() => setShowUnfoldExtraOptions((value) => !value)}
                  >
                    {showUnfoldExtraOptions ? 'Verberg unfold extra opties' : 'Toon unfold extra opties'}
                  </button>
                </div>

                {/* ── Status ── */}
                {unfoldVisuals ? (
                  unfoldVisuals.success ? (
                    <div className="timeline-text" style={{ color: '#4caf50', fontWeight: 600 }}>
                      ✓ Unfold geslaagd
                    </div>
                  ) : (
                    <div className="timeline-text" style={{ color: '#f44336', fontWeight: 600 }}>
                      ✗ Unfold niet geslaagd{unfoldVisuals.error ? `: ${unfoldVisuals.error}` : ''}
                      {unfoldVisuals.skipped && (
                        <span style={{ color: '#aaa', fontWeight: 400 }}> (overgeslagen – {unfoldVisuals.reason})</span>
                      )}
                    </div>
                  )
                ) : (
                  <div className="timeline-text" style={{ color: '#aaa' }}>
                    Geen unfold data beschikbaar
                  </div>
                )}

                {/* ── Afmetingen uitslag ── */}
                {unfoldVisuals?.success && (
                  <div style={{ marginTop: 10 }}>
                    <div className="timeline-stage" style={{ marginBottom: 4 }}>
                      Uitslag afmetingen
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <tbody>
                        <tr>
                          <td style={{ padding: '2px 8px 2px 0', color: '#aaa' }}>Lengte</td>
                          <td style={{ fontWeight: 600 }}>
                            {unfoldVisuals.flat_length ? `${Math.round(unfoldVisuals.flat_length)} mm` : '–'}
                          </td>
                          <td style={{ padding: '2px 0 2px 16px', color: '#aaa' }}>Breedte</td>
                          <td style={{ fontWeight: 600 }}>
                            {unfoldVisuals.flat_width ? `${Math.round(unfoldVisuals.flat_width)} mm` : '–'}
                          </td>
                        </tr>
                        <tr>
                          <td style={{ color: '#aaa' }}>Zetlijnen</td>
                          <td style={{ fontWeight: 600 }}>{unfoldVisuals.fold_lines ?? '–'}</td>
                        </tr>
                      </tbody>
                    </table>
                    <div className="timeline-text" style={{ marginTop: 8 }}>
                      Klik op een zetlijn in de tabel of in de viewer om die lijn te markeren.
                    </div>
                  </div>
                )}

                {/* ── Criteria / thresholds ── */}
                {showUnfoldExtraOptions && (
                  <div style={{ marginTop: 12 }}>
                    <div className="timeline-stage" style={{ marginBottom: 4 }}>
                      Criteria &amp; thresholds (freecad_unfold)
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, color: '#ccc' }}>
                      <tbody>
                        {[
                          ['K-factor', '0.44 (vast voor alle plaatdiktes)'],
                          ['Max pogingen (base face)', '5'],
                          ['Subprocess timeout', '300 s'],
                          ['Bend filter: min hoek', '> 0.3 rad (≈ 17°)'],
                          ['Bend filter: min lengte', '> 5 mm'],
                          ['Deduplicatie key', '(round(hoek,1), round(lengte,1))'],
                          ['Bij duplicaat', 'Kleinste radius wint (inner radius)'],
                          ['Merge gesplitste bends', 'Exact gelijke hoek + radius'],
                        ].map(([label, val]) => (
                          <tr key={label}>
                            <td style={{ padding: '2px 8px 2px 0', color: '#888', whiteSpace: 'nowrap' }}>{label}</td>
                            <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{val}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* ── Zetlijnen tabel ── */}
                {unfoldVisuals?.success &&
                  (() => {
                    if (foldRows.length === 0) return null
                    return (
                      <div style={{ marginTop: 12 }}>
                        <div className="timeline-stage" style={{ marginBottom: 6 }}>
                          Zetlijnen ({foldRows.length} gevonden)
                        </div>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                          <thead>
                            <tr style={{ color: '#888', borderBottom: '1px solid #333' }}>
                              <th style={{ textAlign: 'left', padding: '2px 6px 4px 0', fontWeight: 400 }}>#</th>
                              <th style={{ textAlign: 'left', padding: '2px 6px 4px 0', fontWeight: 400 }}>Richting</th>
                              <th style={{ textAlign: 'right', padding: '2px 6px 4px 0', fontWeight: 400 }}>
                                Hoek (°)
                              </th>
                              <th style={{ textAlign: 'right', padding: '2px 6px 4px 0', fontWeight: 400 }}>
                                Radius (mm)
                              </th>
                              <th style={{ textAlign: 'right', padding: '2px 0 4px 0', fontWeight: 400 }}>
                                Lengte (mm)
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {foldRows.map((row, i) => {
                              const dir = row.direction || '–'
                              const angle = row.angle != null ? Math.round(row.angle * 10) / 10 : '–'
                              const radius = row.radius != null ? Math.round(row.radius * 10) / 10 : '–'
                              const length = row.length != null ? Math.round(row.length * 10) / 10 : '–'
                              const dirColor = dir === 'up' ? '#81c784' : dir === 'down' ? '#e57373' : '#aaa'
                              return (
                                <tr
                                  key={row.id ?? i}
                                  style={{
                                    borderBottom: '1px solid #222',
                                    cursor: 'pointer',
                                    background:
                                      normalizedSelectedFoldId === row.id ? 'rgba(255, 59, 48, 0.15)' : 'transparent',
                                  }}
                                  onClick={() => onFoldSelect?.(row.id)}
                                >
                                  <td style={{ padding: '3px 6px 3px 0', color: '#888' }}>{row.id}</td>
                                  <td style={{ padding: '3px 6px 3px 0', fontWeight: 600, color: dirColor }}>
                                    {dir === 'up' ? '▲ Op' : dir === 'down' ? '▼ Neer' : dir}
                                  </td>
                                  <td style={{ textAlign: 'right', padding: '3px 6px 3px 0', fontFamily: 'monospace' }}>
                                    {angle}
                                  </td>
                                  <td style={{ textAlign: 'right', padding: '3px 6px 3px 0', fontFamily: 'monospace' }}>
                                    {radius}
                                  </td>
                                  <td style={{ textAlign: 'right', padding: '3px 0 3px 0', fontFamily: 'monospace' }}>
                                    {length}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )
                  })()}

                {selectedFold && (
                  <div className="reasoning-list" style={{ marginTop: 12 }}>
                    <div className="reasoning-card">
                      <div className="timeline-stage">Geselecteerde zetlijn #{selectedFold.id}</div>
                      <div className="timeline-text">
                        Richting: {selectedFold.direction || 'onbekend'} | Hoek:{' '}
                        {selectedFold.angle != null ? `${Math.round(selectedFold.angle * 10) / 10}°` : '–'} | Radius:{' '}
                        {selectedFold.radius != null ? `${Math.round(selectedFold.radius * 10) / 10} mm` : '–'}
                      </div>
                      <div className="timeline-text">
                        Lengte: {selectedFold.length != null ? `${Math.round(selectedFold.length * 10) / 10} mm` : '–'}
                      </div>
                      <pre className="timeline-payload-value">
                        {formatDetailValue({
                          center: selectedFold.center,
                          axis: selectedFold.axis,
                          start: selectedFold.start,
                          end: selectedFold.end,
                          segment_indices: selectedFold.segmentIndices,
                        })}
                      </pre>
                    </div>
                  </div>
                )}

                {/* ── Error handling codes ── */}
                {showUnfoldExtraOptions && (
                  <div style={{ marginTop: 12 }}>
                    <div className="timeline-stage" style={{ marginBottom: 4 }}>
                      SheetMetalUnfolder foutcodes
                    </div>
                    <div style={{ fontSize: 11, color: '#777', lineHeight: 1.6 }}>
                      {[
                        [1, 'Volume onbruikbaar'],
                        [3, 'Dikte inconsistent of te complex'],
                        [5, 'Onnodige edges (Refine Shape nodig)'],
                        [11, 'Dubbele buigingen niet ondersteund'],
                        [12, 'Meer dan één bend-child'],
                        [17, 'Oppervlaktype niet ondersteund'],
                        [21, 'Section wire niet gesloten'],
                        [26, 'Niet-ondersteund curve type in unbendFace'],
                      ].map(([code, msg]) => (
                        <div key={code}>
                          <span style={{ color: '#555', fontFamily: 'monospace', marginRight: 8 }}>{code}</span>
                          {msg}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="visual-stage-card">
              <div className="timeline-title">Extra opties</div>
              <div className="hole-filter-row" style={{ marginTop: 8 }}>
                <button
                  className={`hole-filter-btn ${showStageExtraOptions ? 'is-active' : ''}`}
                  onClick={() => setShowStageExtraOptions((value) => !value)}
                >
                  {showStageExtraOptions ? 'Verberg stage extra opties' : 'Toon stage extra opties'}
                </button>
              </div>
              {showStageExtraOptions && (
                <>
                  <div className="timeline-event-list">
                    {selectedStage.events.map((event, index) => (
                      <button
                        key={`${event.type}-${event.stage}-${event.originalIndex}`}
                        className={`timeline-item ${selectedEventIndex === index ? 'is-active' : ''}`}
                        onClick={() => onSelectEventIndex(index)}
                      >
                        <div className="timeline-item-head">
                          <span className="timeline-stage">{formatLabel(event.type)}</span>
                          <span className="timeline-type">
                            {event.status || '-'} · {formatDuration((event.timestamp_ms || 0) / 1000)}
                          </span>
                        </div>
                        <div className="timeline-text">{summarizePayload(event.payload)}</div>
                      </button>
                    ))}
                  </div>
                  <div className="timeline-title">Geselecteerde keuze</div>
                  <div className="timeline-text">
                    {formatLabel(selectedEvent.type)} {selectedEvent.status ? `| ${selectedEvent.status}` : ''}
                  </div>
                  {selectedPayloadEntries.length === 0 ? (
                    <div className="timeline-text">Geen extra details voor dit event.</div>
                  ) : (
                    <div className="timeline-payload-grid">
                      {selectedPayloadEntries.map(([key, value]) => (
                        <div className="timeline-payload-row" key={key}>
                          <div className="timeline-payload-key">{formatLabel(key)}</div>
                          <pre className="timeline-payload-value">{formatDetailValue(value)}</pre>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
