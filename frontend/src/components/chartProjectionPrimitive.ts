import type {
  IChartApi,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import type { ChartProjection } from '../types/prediction';

const SIDE_COLORS: Record<string, string> = {
  BULLISH: 'rgba(34, 197, 94, 0.95)',
  BEARISH: 'rgba(239, 68, 68, 0.95)',
  NEUTRAL: 'rgba(148, 163, 184, 0.95)',
};

const ZONE_FILL: Record<string, string> = {
  BULLISH: 'rgba(34, 197, 94, 0.12)',
  BEARISH: 'rgba(239, 68, 68, 0.12)',
  NEUTRAL: 'rgba(148, 163, 184, 0.12)',
};

export class ChartProjectionPrimitive implements ISeriesPrimitive<Time> {
  private _projections: ChartProjection[] = [];
  private _timeOffset = 0;
  private _chart: IChartApi | null = null;
  private _series: ISeriesApi<'Candlestick'> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private readonly _paneViews = [new ProjectionPaneView(this)];

  get projections() {
    return this._projections;
  }

  get timeOffset() {
    return this._timeOffset;
  }

  get chart() {
    return this._chart;
  }

  get series() {
    return this._series;
  }

  attached(param: SeriesAttachedParameter<Time>) {
    this._chart = param.chart as IChartApi;
    this._series = param.series as ISeriesApi<'Candlestick'>;
    this._requestUpdate = param.requestUpdate;
    this._chart.timeScale().applyOptions({ rightOffset: 16 });
  }

  detached() {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  updateAllViews() {
    this._paneViews[0].update();
  }

  paneViews() {
    return this._paneViews;
  }

  setProjections(projections: ChartProjection[], timeOffset: number) {
    this._projections = projections;
    this._timeOffset = timeOffset;
    this._paneViews[0].update();
    this._requestUpdate?.();
  }
}

class ProjectionPaneView {
  private readonly _owner: ChartProjectionPrimitive;

  constructor(owner: ChartProjectionPrimitive) {
    this._owner = owner;
  }

  update() {
    // coordinates are resolved at draw time
  }

  zOrder() {
    return 'top' as const;
  }

  renderer() {
    const owner = this._owner;
    return {
      draw(target: {
        useMediaCoordinateSpace: (cb: (scope: { context: CanvasRenderingContext2D }) => void) => void;
      }) {
        const chart = owner.chart;
        const series = owner.series;
        if (!chart || !series) return;
        target.useMediaCoordinateSpace(({ context: ctx }) => {
          const timeScale = chart.timeScale();
          for (const item of owner.projections) {
            const color = SIDE_COLORS[item.side] ?? SIDE_COLORS.NEUTRAL;
            const x1 = timeScale.timeToCoordinate((item.time_start + owner.timeOffset) as UTCTimestamp);
            const x2 = timeScale.timeToCoordinate((item.time_end + owner.timeOffset) as UTCTimestamp);
            if (x1 == null || x2 == null) continue;

            if (item.kind === 'TARGET_ZONE' && item.price_low != null && item.price_high != null) {
              const y1 = series.priceToCoordinate(item.price_high);
              const y2 = series.priceToCoordinate(item.price_low);
              if (y1 == null || y2 == null) continue;
              ctx.fillStyle = ZONE_FILL[item.side] ?? ZONE_FILL.NEUTRAL;
              ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
              continue;
            }

            if (item.kind === 'PATTERN_LABEL') {
              const y = series.priceToCoordinate(item.price_start);
              if (y == null) continue;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(x1, y, 5, 0, Math.PI * 2);
              ctx.fill();
              ctx.font = '11px sans-serif';
              ctx.fillText(item.label, x1 + 8, y - 8);
              continue;
            }

            const y1 = series.priceToCoordinate(item.price_start);
            const y2 = series.priceToCoordinate(item.price_end);
            if (y1 == null || y2 == null) continue;
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.setLineDash(item.kind.includes('CHANNEL') ? [] : [6, 4]);
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = color;
            ctx.font = '10px sans-serif';
            ctx.fillText(item.label, x2 - 4, y2 - 6);
          }
        });
      },
    };
  }
}
