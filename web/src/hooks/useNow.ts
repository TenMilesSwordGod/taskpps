import { useEffect, useState } from 'react';

/** 每 interval 毫秒返回一次当前时间戳，用于驱动"X秒前"等相对时间的实时刷新 */
export function useNow(interval = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), interval);
    return () => clearInterval(id);
  }, [interval]);
  return now;
}
