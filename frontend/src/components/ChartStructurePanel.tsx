import type { ChartAnnotationCategory, ChartStructureFeatures } from '../types/prediction';
import { CHART_CATEGORIES, chartStructureSummary } from '../utils/chartStructureView';

const labelStyle = { fontSize: '0.68rem', color: 'var(--text-muted)' } as const;

interface ChartStructurePanelProps {
  chart: ChartStructureFeatures | null;
  enabledCategories: Set<ChartAnnotationCategory>;
  onToggleCategory: (category: ChartAnnotationCategory) => void;
}

export default function ChartStructurePanel({
  chart,
  enabledCategories,
  onToggleCategory,
}: ChartStructurePanelProps) {
  if (!chart) {
    return (
      <div style={{ ...labelStyle, marginTop: 10 }}>
        Loading chart structure from completed candles (works off-session too)…
      </div>
    );
  }

  const report = chart.report;

  return (
    <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {CHART_CATEGORIES.map(category => {
          const on = enabledCategories.has(category);
          return (
            <button
              key={category}
              type="button"
              onClick={() => onToggleCategory(category)}
              className={`btn ${on ? 'btn-primary' : 'btn-ghost'}`}
              style={{ padding: '3px 8px', fontSize: '0.65rem' }}
            >
              {category}
            </button>
          );
        })}
      </div>

      <div style={{ ...labelStyle, marginBottom: 6 }}>
        Chart analysis · shadow only · not scored · forward paths are scenarios (toggle SCENARIOS)
      </div>
      {(chart.projections?.length ?? 0) > 0 && (
        <div style={{ ...labelStyle, marginBottom: 8, color: 'var(--text-primary)' }}>
          {chart.projections!.length} projection segment(s) drawn on chart (channel / measured move / breakout)
        </div>
      )}
      <div style={{ fontSize: '0.75rem', fontWeight: 600, marginBottom: 8 }}>{chartStructureSummary(chart)}</div>

      {chart.data_quality && (
        <div style={{ ...labelStyle, marginBottom: 8 }}>
          Data: {chart.data_quality.ok ? 'OK' : 'Issues'} · gaps {chart.data_quality.gap_count} · dupes{' '}
          {chart.data_quality.duplicate_bars}
        </div>
      )}

      {report?.narrative && (
        <div style={{ fontSize: '0.75rem', marginBottom: 10, lineHeight: 1.4 }}>{report.narrative}</div>
      )}

      {chart.data_ok && (
        <>
          {chart.evidence.length > 0 && (
            <div style={{ ...labelStyle, marginBottom: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--text-primary)' }}>Evidence</div>
              {chart.evidence.map((line, index) => (
                <div key={`${index}-${line}`}>{line}</div>
              ))}
            </div>
          )}

          {report && (
            <div style={{ display: 'grid', gap: 8, marginBottom: 8 }}>
              <ScenarioBlock title="Bullish" scenario={report.bullish} />
              <ScenarioBlock title="Bearish" scenario={report.bearish} />
              <ScenarioBlock title="Wait" scenario={report.wait} />
            </div>
          )}

          {chart.trigger && <div style={labelStyle}>Trigger: {chart.trigger}</div>}
          {chart.invalidation_price != null && (
            <div style={labelStyle}>
              Invalidation: {chart.invalidation_price.toFixed(2)}
              {chart.invalidation_rule ? ` · ${chart.invalidation_rule}` : ''}
            </div>
          )}

          {(chart.patterns?.length ?? 0) > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ ...labelStyle, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                Patterns
              </div>
              {chart.patterns?.map(pattern => (
                <div key={`${pattern.pattern}-${pattern.time ?? pattern.evidence}`} style={labelStyle}>
                  {pattern.pattern.replace(/_/g, ' ')} · {pattern.status} · {pattern.evidence}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ScenarioBlock({
  title,
  scenario,
}: {
  title: string;
  scenario: { summary: string; confirmation?: string | null; invalidation?: string | null; invalidation_price?: number | null };
}) {
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 8 }}>
      <div style={{ fontSize: '0.72rem', fontWeight: 700, marginBottom: 4 }}>{title}</div>
      <div style={labelStyle}>{scenario.summary}</div>
      {scenario.confirmation && <div style={labelStyle}>Confirm: {scenario.confirmation}</div>}
      {scenario.invalidation && (
        <div style={labelStyle}>
          Invalidate: {scenario.invalidation}
          {scenario.invalidation_price != null ? ` @ ${scenario.invalidation_price.toFixed(1)}` : ''}
        </div>
      )}
    </div>
  );
}
