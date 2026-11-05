import { createContext, useContext, type ReactNode } from 'react';

const RouteActivityContext = createContext(true);

export function RouteActivityProvider({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  return (
    <RouteActivityContext.Provider value={active}>
      {children}
    </RouteActivityContext.Provider>
  );
}

/** False when a keep-alive route is mounted but hidden (e.g. user left Trade/Personal). */
export function useRouteActive(): boolean {
  return useContext(RouteActivityContext);
}
