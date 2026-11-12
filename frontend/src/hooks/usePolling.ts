import { useEffect, useRef, useState } from 'react';
import type { DependencyList } from 'react';
import { useRouteActive } from './routeActivity';

function useTabVisible() {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  useEffect(() => {
    const onVisibility = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);
  return visible;
}

export function usePolling(callback: () => Promise<void>, intervalMs: number, deps: DependencyList, enabled = true) {
  const inFlight = useRef(false);
  const callbackRef = useRef(callback);
  callbackRef.current = callback;
  const tabVisible = useTabVisible();
  const routeActive = useRouteActive();
  const active = enabled && tabVisible && routeActive;

  useEffect(() => {
    if (!active) return;
    const run = async () => {
      if (inFlight.current || document.visibilityState !== 'visible') return;
      inFlight.current = true;
      try {
        await callbackRef.current();
      } finally {
        inFlight.current = false;
      }
    };
    run();
    const timer = setInterval(run, intervalMs);
    return () => clearInterval(timer);
  }, [...deps, active, intervalMs]);
}
