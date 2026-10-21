import { useEffect, useRef, useState } from 'react';
import { CandlestickSeries, ColorType, LineStyle, createChart } from 'lightweight-charts';
import type { CandlestickData, IChartApi, IPriceLine, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import { tradingAPI } from '../api/client';
import type { ChartProjection } from '../types/prediction';
import type { CandleInterval, Tick } from '../types/trading';
import type { ChartPriceLine } from '../utils/chartStructureView';
import { isMarketOpen } from '../utils/market-hours';
import { apiErrorMessage } from '../utils/api-error';
import { ChartProjectionPrimitive } from './chartProjectionPrimitive';

const INTERVAL_SECONDS: Record<CandleInterval, number> = { '1m': 60, '5m': 300, '15m': 900 };
const CANDLE_REFRESH_MS = 60000;
// lightweight-charts renders timestamps as UTC, so shift them to the browser's local time.
const LOCAL_OFFSET_SECONDS = -new Date().getTimezoneOffset() * 60;

interface LiveChartProps {
  symbol: string;
  interval: CandleInterval;
  tick: Tick | null;
  levels?: ChartPriceLine[];
  projections?: ChartProjection[];
}

export default function LiveChart({
  symbol,
  interval,
  tick,
  levels = [],
  projections = [],
}: LiveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const lastBarRef = useRef<CandlestickData<UTCTimestamp> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const projectionPrimitiveRef = useRef<ChartProjectionPrimitive | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const chart = createChart(containerRef.current as HTMLDivElement, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 16 },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e', downColor: '#ef4444', borderVisible: false, wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    });
    const primitive = new ChartProjectionPrimitive();
    series.attachPrimitive(primitive);
    seriesRef.current = series;
    chartRef.current = chart;
    projectionPrimitiveRef.current = primitive;
    return () => {
      series.detachPrimitive(primitive);
      chart.remove();
      projectionPrimitiveRef.current = null;
    };
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await tradingAPI.getCandles(symbol, interval);
        const bars = res.data.candles.map(c => ({
          time: (c.time + LOCAL_OFFSET_SECONDS) as UTCTimestamp,
          open: c.open, high: c.high, low: c.low, close: c.close,
        }));
        seriesRef.current?.setData(bars);
        lastBarRef.current = bars.length ? bars[bars.length - 1] : null;
        setError('');
      } catch (err) {
        setError(apiErrorMessage(err));
      }
    };
    lastBarRef.current = null;
    load().then(() => chartRef.current?.timeScale().fitContent());
    const timer = setInterval(load, CANDLE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [symbol, interval]);

  useEffect(() => {
    const last = lastBarRef.current;
    if (!tick || tick.symbol !== symbol || !last) return;
    const step = INTERVAL_SECONDS[interval];
    const tickTime = Math.floor(new Date(tick.timestamp).getTime() / 1000) + LOCAL_OFFSET_SECONDS;
    const bucket = (Math.floor(tickTime / step) * step) as UTCTimestamp;
    const bar = isMarketOpen() && bucket > last.time
      ? { time: bucket, open: last.close, high: Math.max(last.close, tick.ltp), low: Math.min(last.close, tick.ltp), close: tick.ltp }
      : { ...last, high: Math.max(last.high, tick.ltp), low: Math.min(last.low, tick.ltp), close: tick.ltp };
    seriesRef.current?.update(bar);
    lastBarRef.current = bar;
  }, [tick, symbol, interval]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const line of priceLinesRef.current) {
      series.removePriceLine(line);
    }
    priceLinesRef.current = levels.map(level =>
      series.createPriceLine({
        price: level.price,
        color: level.color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: level.title,
      }),
    );
  }, [levels, symbol, interval]);

  useEffect(() => {
    projectionPrimitiveRef.current?.setProjections(projections, LOCAL_OFFSET_SECONDS);
  }, [projections, symbol, interval]);

  return (
    <div>
      <div ref={containerRef} style={{ height: 420, width: '100%' }} />
      {error && <div style={{ color: 'var(--sell)', fontSize: '0.75rem', marginTop: 6 }}>{error}</div>}
    </div>
  );
}
