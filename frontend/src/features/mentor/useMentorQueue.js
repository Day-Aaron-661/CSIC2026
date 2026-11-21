import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api.js';

// Same timings as the newcomer view, so both sides of a two-browser demo stay in step.
const REFRESH_INTERVAL = 5000;
const REFRESH_TIMEOUT = 15000;
// An approval may have been saved even if its reply never arrives, so a timeout
// re-reads the queue instead of resending (see docs/API_CONTRACT.md).
const APPROVE_TIMEOUT = 15000;
const MAX_NOTICES = 5;
const MAX_ANSWER = 10000;
const MAX_REVIEWER = 100;

function without(record, key) {
  const { [key]: _removed, ...rest } = record;
  return rest;
}

// onApproved(id) runs after the server confirms an approval (used to re-read approved answers).
export default function useMentorQueue({ onApproved } = {}) {
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
  // A refresh was asked for while a read was already running; read again when it ends,
  // so a re-read after a failed approval is never silently dropped.
  const refreshAgain = useRef(false);
  // Question id -> AbortController of its review POST in flight. A ref blocks double clicks
  // before React re-renders, and lets unmount cancel the request.
  const approvals = useRef(new Map());
  // Ids whose last approval attempt failed; if they leave the queue we explain why.
  const failedApprovals = useRef(new Set());
  // Ids this mentor approved successfully. Approval is final (a second review is 409),
  // so an older list that still shows one of them is ignored for that id.
  const approvedIds = useRef(new Set());
  // Mirrors of state, so a refresh can compare the old queue with the new one.
  const itemsRef = useRef([]);
  const draftsRef = useRef({});
  // Latest callback in a ref, so a new function each render does not restart polling.
  const onApprovedRef = useRef(onApproved);
  onApprovedRef.current = onApproved;

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
    // One read at a time. Reads continue while approvals are in flight, so a stalled
    // approval cannot freeze the queue.
    if (!mounted.current) return;
    if (readRequest.current) {
      refreshAgain.current = true;
      return;
    }
    refreshAgain.current = false;
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
      // Cards with an approval in flight stay exactly as shown until that approval settles;
      // questions already approved here are dropped even if an older list still has them.
      const inFlight = itemsRef.current.filter(item => approvals.current.has(item.id));
      const inFlightIds = new Set(inFlight.map(item => item.id));
      const merged = next
        .filter(item => !approvedIds.current.has(item.id) && !inFlightIds.has(item.id))
        .concat(inFlight)
        .sort((a, b) => b.id - a.id);
      const nextIds = new Set(merged.map(item => item.id));
      for (const item of itemsRef.current) {
        if (nextIds.has(item.id)) continue;
        if (failedApprovals.current.has(item.id)) {
          // Our own approval may have been saved with its reply lost, so do not blame another mentor.
          addNotice({ key: `gone-${item.id}`, kind: 'unconfirmed', id: item.id });
        } else {
          // Someone else approved it. Only interrupt the mentor if they had work in progress on it.
          const draft = draftsRef.current[item.id];
          const edited = draft !== undefined && draft !== (item.ai_answer ?? '');
          if (edited) addNotice({ key: `gone-${item.id}`, kind: 'elsewhere', id: item.id });
        }
        failedApprovals.current.delete(item.id);
      }
      itemsRef.current = merged;
      setItems(merged);
      // Pre-fill only questions seen for the first time; never overwrite a draft being edited.
      updateDrafts(previous => {
        const kept = {};
        for (const item of merged) kept[item.id] = previous[item.id] ?? (item.ai_answer ?? '');
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
        if (mounted.current) {
          setRefreshing(false);
          if (refreshAgain.current) refresh();
        }
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
    const controller = new AbortController();
    approvals.current.set(id, controller);
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, APPROVE_TIMEOUT);
    setApproving(previous => ({ ...previous, [id]: true }));
    setApproveErrors(previous => without(previous, id));
    let failed = false;
    try {
      await api.review(id, text, name, { signal: controller.signal });
      if (!mounted.current) return false;
      failedApprovals.current.delete(id);
      approvedIds.current.add(id);
      itemsRef.current = itemsRef.current.filter(item => item.id !== id);
      setItems(itemsRef.current);
      updateDrafts(previous => without(previous, id));
      addNotice({ key: `approved-${id}`, kind: 'approved', id });
      onApprovedRef.current?.(id);
      return true;
    } catch (error) {
      if (!mounted.current) return false;
      failed = true;
      failedApprovals.current.add(id);
      const message = timedOut
        ? `no reply after ${APPROVE_TIMEOUT / 1000} seconds; it may still have been saved`
        : error.message || 'Unknown error';
      setApproveErrors(previous => ({ ...previous, [id]: message }));
      return false;
    } finally {
      clearTimeout(timeout);
      approvals.current.delete(id);
      if (mounted.current) {
        setApproving(previous => without(previous, id));
        // A lost response may still have saved. Re-read (queued if a read is running) so a
        // 409 or another mentor's approval shows up as "no longer pending" rather than as a retry loop.
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
      // Unmount: cancel approvals in flight. No error is shown; the next visit re-reads the queue.
      for (const controller of approvals.current.values()) controller.abort();
      approvals.current.clear();
    };
  }, [refresh]);

  return {
    items, drafts, loaded, refreshing, loadError, approving, approveErrors, notices,
    refresh, setDraft, resetDraft, approve, dismissNotice,
  };
}
