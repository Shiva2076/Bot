export const isMarketOpen = (): boolean => {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 555 && mins <= 930; // 9:15 – 15:30 IST
};
