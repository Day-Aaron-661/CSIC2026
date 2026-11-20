import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api.js';

// Same timings as the newcomer view, so both sides of a two-browser demo stay in step.
const REFRESH_INTERVAL = 5000;
const REFRESH_TIMEOUT = 15000;
const MAX_NOTICES = 5;
const MAX_ANSWER = 10000;
const MAX_REVIEWER = 100;

function without(record, key) {
  const { [key]: _removed, ...rest } = record;
  return rest;
}

export default function useMentorQueue() {
  const [items, setItems] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [approving, setApproving] = useState({});
  const [approveErrors, setApproveErrors] = useState({});
  const [notices, setNotices] = useState([]);
  const mounted = useRef(false);
  const readRequest = useRef(null);
  // Question ids with a review POST in flight; a ref blocks double clicks before React re-renders.
  const approvals = useRef(new Set());
  // Ids whose last approval attempt failed; if they leave the queue we explain why.
  const failedApprovals = useRef(new Set());
  // Mirrors of state, so a refresh can compare the old queue with the new one.
  const itemsRef = useRef([]);
  const draftsRef = useRef({});

  const updateDrafts = useCallback((update) => {
    setDrafts(previous => {
      const next = update(previous);
      draftsRef.current = next;
      return next;
    });
  }, []);

  const addNotice = useCallback((notice) => {
    setNotices(previous => [notice, ...previous.filter(existing => existing.key !== notice.key)].slice(0, MAX_NOTICES));
  }, []);

  const dismissNotice = useCallback((key) => {
    setNotices(previous => previous.filter(notice => notice.key !== key));
  }, []);

  const refresh = useCallback(async () => {
    // One read at a time, and none while an approval is in flight:
    // an older list must not bring back a question that was just approved.
    if (!mounted.current || readRequest.current || approvals.current.size) return;
    const controller = new AbortController();
    readRequest.current = controller;
    setRefreshing(true);
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REFRESH_TIMEOUT);
    try {
      const next = await api.questions('pending', { signal: controller.signal });
      if (controller.signal.aborted || !mounted.current || readRequest.current !== controller) return;
      if (!Array.isArray(next)) throw new Error('Invalid question list');
      const nextIds = new Set(next.map(item => item.id));
      for (const item of itemsRef.current) {
        if (nextIds.has(item.id)) continue;
        // Someone else approved it. Only interrupt the mentor if they had work in progress on it.
        const draft = draftsRef.current[item.id];
        const edited = draft !== undefined && draft !== (item.ai_answer ?? '');
        if (edited || failedApprovals.current.has(item.id)) {
          addNotice({ key: `elsewhere-${item.id}`, kind: 'elsewhere', id: item.id });
        }
        failedApprovals.current.delete(item.id);
      }
      itemsRef.current = next;
      setItems(next);
      // Pre-fill only questions seen for the first time; never overwrite a draft being edited.
      updateDrafts(previous => {
        const kept = {};
        for (const item of next) kept[item.id] = previous[item.id] ?? (item.ai_answer ?? '');
        return kept;
      });
      setApproveErrors(previous => Object.fromEntries(
        Object.entries(previous).filter(([id]) => nextIds.has(Number(id)))
      ));
      setLoaded(true);
      setLoadError(false);
    } catch {
      if (mounted.current && readRequest.current === controller && (!controller.signal.aborted || timedOut)) {
        setLoadError(true);
      }
    } finally {
      clearTimeout(timeout);
      if (readRequest.current === controller) {
        readRequest.current = null;
        if (mounted.current) setRefreshing(false);
      }
    }
  }, [addNotice, updateDrafts]);

  const setDraft = useCallback((id, text) => {
    updateDrafts(previous => ({ ...previous, [id]: text }));
  }, [updateDrafts]);

  const resetDraft = useCallback((id) => {
    const item = itemsRef.current.find(existing => existing.id === id);
    if (item) updateDrafts(previous => ({ ...previous, [id]: item.ai_answer ?? '' }));
  }, [updateDrafts]);

  const approve = useCallback(async (id, answer, reviewer) => {
    const text = answer.trim();
    const name = reviewer.trim();
    if (!mounted.current || approvals.current.has(id) || !text || !name
      || text.length > MAX_ANSWER || name.length > MAX_REVIEWER) return false;
    approvals.current.add(id);
    readRequest.current?.abort();
    readRequest.current = null;
    setRefreshing(false);
    setApproving(previous => ({ ...previous, [id]: true }));
    setApproveErrors(previous => without(previous, id));
    let failed = false;
    try {
      // api.review has no cancellation signal yet (planned for PR2); a reply after unmount is ignored.
      await api.review(id, text, name);
      if (!mounted.current) return false;
      failedApprovals.current.delete(id);
      itemsRef.current = itemsRef.current.filter(item => item.id !== id);
      setItems(itemsRef.current);
      updateDrafts(previous => without(previous, id));
      addNotice({ key: `approved-${id}`, kind: 'approved', id });
      return true;
    } catch (error) {
      if (!mounted.current) return false;
      failed = true;
      failedApprovals.current.add(id);
      setApproveErrors(previous => ({ ...previous, [id]: error.message || 'Unknown error' }));
      return false;
    } finally {
      approvals.current.delete(id);
      if (mounted.current) {
        setApproving(previous => without(previous, id));
        // A lost response may still have saved. Re-read so a 409 or another mentor's
        // approval shows up as "already reviewed" rather than as a retry loop.
        if (failed) refresh();
      }
    }
  }, [addNotice, refresh, updateDrafts]);

  useEffect(() => {
    mounted.current = true;
    const onVisibility = () => {
      if (!document.hidden) {
        refresh();
      } else {
        readRequest.current?.abort();
        readRequest.current = null;
        setRefreshing(false);
      }
    };
    if (!document.hidden) refresh();
    const interval = setInterval(() => {
      if (!document.hidden) refresh();
    }, REFRESH_INTERVAL);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      mounted.current = false;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibility);
      readRequest.current?.abort();
      readRequest.current = null;
    };
  }, [refresh]);

  return {
    items, drafts, loaded, refreshing, loadError, approving, approveErrors, notices,
    refresh, setDraft, resetDraft, approve, dismissNotice,
  };
}
