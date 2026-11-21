import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api.js';

const READ_TIMEOUT = 15000;

// Mentor-approved answers for lookup and reuse. Read once on mount, on Refresh and after
// each approval. Not polled: the list only grows when a mentor approves something.
export default function useKnowledge() {
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const mounted = useRef(false);
  const request = useRef(null);

  // force: replace a read already in flight. After an approval the older read may have
  // started before the new answer was saved, so it must not be the one that wins.
  const refresh = useCallback(async ({ force = false } = {}) => {
    if (!mounted.current) return;
    if (request.current) {
      if (!force) return;
      request.current.abort();
    }
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, READ_TIMEOUT);
    try {
      const next = await api.knowledge({ signal: controller.signal });
      if (controller.signal.aborted || !mounted.current || request.current !== controller) return;
      if (!Array.isArray(next)) throw new Error('Invalid knowledge list');
      // Only entries with an actual review record can be offered as mentor-approved.
      setItems(next.filter(item => item?.status === 'approved' && item.reviewed_answer));
      setLoaded(true);
      setError(false);
    } catch {
      if (mounted.current && request.current === controller && (!controller.signal.aborted || timedOut)) {
        setError(true);
      }
    } finally {
      clearTimeout(timeout);
      if (request.current === controller) {
        request.current = null;
        if (mounted.current) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    refresh();
    return () => {
      mounted.current = false;
      request.current?.abort();
      request.current = null;
    };
  }, [refresh]);

  return { items, loaded, loading, error, refresh };
}
