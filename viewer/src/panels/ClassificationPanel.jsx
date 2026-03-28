import React from 'react'
import { formatDetailValue, formatLabel } from '../pipelineUi'
import { getClassificationStatusLabel, getClassificationStatusClass } from './helpers'

function formatDeviation(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n.v.t.'
  if (value === 0) return '0.000'
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}`
}

export default function ClassificationPanel({ classificationVisuals }) {
  if (!classificationVisuals) return null

  const routerVisuals = classificationVisuals.router || null
  const classificationFinal = classificationVisuals.final_decision || null
  const step0Review = classificationVisuals.step0_review || null
  const legacyClassification = classificationVisuals.legacy_classification || null

  return (
    <div className="visual-stage-card">
      <div className="timeline-title">Classificatie Flow</div>
      <div className="timeline-text">
        Categorie: {classificationVisuals.part_category || '-'} | Type: {classificationVisuals.part_type || '-'}
      </div>
      <div className="timeline-text">Dikte: {classificationVisuals.thickness ?? '-'} mm</div>
      <div className="timeline-text">
        Visualisatie: donkerrood = section contouren, oranje = buitenmaat, roze = tweede maat, geel = dikte-as.
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
              Confidence: {Math.round((routerVisuals.confidence || 0) * 100)}% | Methode: {routerVisuals.method || '-'}
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
              <span className={`hole-status-pill ${classificationFinal.step0_only ? 'is-accepted' : 'is-warning'}`}>
                {classificationFinal.step0_only ? 'Step 0 only' : 'Step 0 -> legacy'}
              </span>
            </div>
            <div className="timeline-text">
              Klasse: {formatLabel(classificationFinal.classification)} | Gestopt in: {classificationFinal.stopped_in || '-'}
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
              Bron: {step0Review.doc || classificationVisuals.step0_doc || 'docs/classification_step_review.md'}
            </div>
            {step0Review.stopped_in && <div className="timeline-text">Stopte in: {step0Review.stopped_in}</div>}
            {step0Review.error && <div className="timeline-text">Trace-fout: {step0Review.error}</div>}
          </div>
          {(step0Review.steps || []).map((step) => (
            <div className="reasoning-card" key={`step0-${step.step}`}>
              <div className="timeline-item-head">
                <div className="timeline-stage">{step.step} | {step.name}</div>
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
                        <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                          {criterion.passed ? 'Pass' : 'Fail'}
                        </span>
                      )}
                      {criterion.passed == null && <span className="hole-status-pill is-neutral">Info</span>}
                    </div>
                    <div className="timeline-text">
                      Actual: {formatDetailValue(criterion.actual)} | Threshold: {formatDetailValue(criterion.threshold)}
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
              Bron: {legacyClassification.doc || classificationVisuals.matrix_doc || 'docs/CLASSIFICATION_THRESHOLDS_MATRIX.md'}
            </div>
            {legacyClassification.winner_gate && (
              <div className="timeline-text">Winnende gate: STEP {legacyClassification.winner_gate}</div>
            )}
            {(legacyClassification.rules || []).length > 0 && (
              <div className="timeline-text">Beslispad: {(legacyClassification.rules || []).join(' -> ')}</div>
            )}
          </div>
          {(legacyClassification.gates || []).map((gate) => (
            <div className="reasoning-card" key={`legacy-${gate.step}`}>
              <div className="timeline-item-head">
                <div className="timeline-stage">STEP {gate.step} | {gate.name}</div>
                <span className={`hole-status-pill ${getClassificationStatusClass(gate.status)}`}>
                  {getClassificationStatusLabel(gate.status)}
                </span>
              </div>
              <div className="timeline-text">{gate.description}</div>
              {gate.rule && <div className="timeline-text">Winnende rule: {gate.rule}</div>}
              <div className="timeline-payload-grid">
                {(gate.criteria || []).map((criterion, index) => (
                  <div className="timeline-payload-row" key={`legacy-${gate.step}-${criterion.name}-${index}`}>
                    <div className="timeline-item-head">
                      <div className="timeline-payload-key">{formatLabel(criterion.name)}</div>
                      {typeof criterion.passed === 'boolean' && (
                        <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                          {criterion.passed ? 'Pass' : 'Fail'}
                        </span>
                      )}
                    </div>
                    <div className="timeline-text">
                      Actual: {formatDetailValue(criterion.actual)} | Threshold: {formatDetailValue(criterion.threshold)} | Delta: {formatDeviation(criterion.deviation)}
                    </div>
                    {criterion.note && <div className="timeline-text">{criterion.note}</div>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {!step0Review && (classificationVisuals.matrix_doc || (classificationVisuals.rules || []).length > 0) && (
        <div className="timeline-text">Bron: {classificationVisuals.matrix_doc || '-'}</div>
      )}

      {!step0Review && (classificationVisuals.criteria || []).length > 0 && (
        <div className="reasoning-list">
          {(classificationVisuals.criteria || []).map((criterion, index) => (
            <div className="reasoning-card" key={`${criterion.step}-${criterion.name}-${index}`}>
              <div className="timeline-item-head">
                <div className="timeline-stage">{criterion.step} | {criterion.name}</div>
                {typeof criterion.passed === 'boolean' && (
                  <span className={`hole-status-pill ${criterion.passed ? 'is-accepted' : 'is-rejected'}`}>
                    {criterion.passed ? 'Pass' : 'Fail'}
                  </span>
                )}
              </div>
              <div className="timeline-text">
                Actual: {formatDetailValue(criterion.actual)} | Threshold: {formatDetailValue(criterion.threshold)} | Delta: {formatDeviation(criterion.deviation)}
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
  )
}
