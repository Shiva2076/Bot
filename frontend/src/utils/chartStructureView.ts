import type {
  ChartAnnotation,
  ChartAnnotationCategory,
  ChartLevel,
  ChartLevelKind,
  ChartStructureFeatures,
} from '../types/prediction';

export interface ChartPriceLine {
  price: number;
  title: string;
  color: string;
  category: ChartAnnotationCategory;
}

const LEVEL_COLORS: Partial<Record<ChartLevelKind, string>> = {
  PDH: '#f87171',
  PDL: '#4ade80',
  PDC: '#a3a3a3',
  OPENING_GAP: '#fbbf24',
  SESSION_HIGH: '#fb7185',
  SESSION_LOW: '#34d399',
  SWING_HIGH: '#f472b6',
  SWING_LOW: '#2dd4bf',
  FVG_TOP: '#c084fc',
  FVG_BOTTOM: '#818cf8',
  BOS: '#38bdf8',
  CHOCH: '#f97316',
  NECKLINE: '#eab308',
  TRENDLINE: '#94a3b8',
  CHANNEL: '#64748b',
  INVALIDATION: '#ef4444',
};

const CATEGORY_COLORS: Record<ChartAnnotationCategory, string> = {
  LEVELS: '#93c5fd',
  ZONES: '#64748b',
  FVG: '#c084fc',
  TRENDLINES: '#94a3b8',
  PATTERNS: '#f97316',
  SCENARIOS: '#ef4444',
};

export const CHART_CATEGORIES: ChartAnnotationCategory[] = [
  'LEVELS',
  'ZONES',
  'FVG',
  'TRENDLINES',
  'PATTERNS',
  'SCENARIOS',
];

export function chartLevelsToPriceLines(levels: ChartLevel[]): ChartPriceLine[] {
  const seen = new Set<string>();
  const lines: ChartPriceLine[] = [];
  for (const level of levels) {
    const key = `${level.kind}:${level.price}`;
    if (seen.has(key)) continue;
    seen.add(key);
    lines.push({
      price: level.price,
      title: level.kind.replace(/_/g, ' '),
      color: LEVEL_COLORS[level.kind] ?? '#93c5fd',
      category: level.kind.includes('FVG') ? 'FVG' : 'LEVELS',
    });
  }
  return lines;
}

export function annotationsToPriceLines(
  annotations: ChartAnnotation[],
  enabled: Set<ChartAnnotationCategory>,
): ChartPriceLine[] {
  const lines: ChartPriceLine[] = [];
  const seen = new Set<string>();
  for (const annotation of annotations) {
    if (!enabled.has(annotation.category)) continue;
    const color = CATEGORY_COLORS[annotation.category];
    if (annotation.price != null) {
      const key = `${annotation.kind}:${annotation.price}`;
      if (!seen.has(key)) {
        seen.add(key);
        lines.push({
          price: annotation.price,
          title: annotation.label,
          color,
          category: annotation.category,
        });
      }
    }
    if (annotation.price_low != null) {
      const key = `${annotation.kind}:low:${annotation.price_low}`;
      if (!seen.has(key)) {
        seen.add(key);
        lines.push({
          price: annotation.price_low,
          title: `${annotation.label} lo`,
          color,
          category: annotation.category,
        });
      }
    }
    if (annotation.price_high != null) {
      const key = `${annotation.kind}:high:${annotation.price_high}`;
      if (!seen.has(key)) {
        seen.add(key);
        lines.push({
          price: annotation.price_high,
          title: `${annotation.label} hi`,
          color,
          category: annotation.category,
        });
      }
    }
  }
  return lines;
}

export function chartOverlayLines(
  chart: ChartStructureFeatures | null,
  enabled: Set<ChartAnnotationCategory>,
): ChartPriceLine[] {
  if (!chart?.data_ok) return [];
  if (chart.annotations && chart.annotations.length > 0) {
    return annotationsToPriceLines(chart.annotations, enabled);
  }
  return chartLevelsToPriceLines(chart.key_levels).filter(line => enabled.has(line.category));
}

export function chartStructureSummary(chart: ChartStructureFeatures): string {
  if (!chart.data_ok) {
    return chart.detail || 'Chart structure unavailable';
  }
  const gap =
    chart.opening_gap_points == null
      ? ''
      : ` · gap ${chart.opening_gap_points >= 0 ? '+' : ''}${chart.opening_gap_points.toFixed(1)}`;
  const pattern = chart.report?.primary_pattern ? ` · ${chart.report.primary_pattern}` : '';
  return (
    `5m ${chart.structure_5m} · 15m ${chart.structure_15m} · ${chart.setup.replace(/_/g, ' ')}` +
    ` · hint ${chart.action_hint}${pattern}${gap} · shadow only`
  );
}
