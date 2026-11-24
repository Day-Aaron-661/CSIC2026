import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api.js';

const REFRESH_INTERVAL = 5000;
const REFRESH_TIMEOUT = 15000;
const SUBMIT_TIMEOUT = 60000;

// Keep unconfirmed request IDs in this tab for safe manual retries, including
// after a reload. Never persist a confirmed submission or an API response.
const PENDING_KEY = 'cp2-newcomer-unconfirmed-requests-v1';
const MAX_PENDING = 20;
const VALID_ID = /^[A-Za-z0-9_-]{1,100}$/;

function readPending() {
  try {
    const entries = JSON.parse(sessionStorage.getItem(PENDING_KEY) || '[]');
    if (!Array.isArray(entries)) return new Map();
    return new Map(entries.filter(entry => Array.isArray(entry)
      && typeof entry[0] === 'string' && entry[0].trim() === entry[0]
      && entry[0].length > 0 && entry[0].length <= 2000
      && typeof entry[1] === 'string' && VALID_ID.test(entry[1])).slice(-MAX_PENDING));
  } catch {
    // Storage can be unavailable (blocked/private browser); in-memory keys still work.
    return new Map();
  }
}

function writePending(pending) {
  try {
    if (pending.size) sessionStorage.setItem(PENDING_KEY, JSON.stringify([...pending]));
    else sessionStorage.removeItem(PENDING_KEY);
  } catch {
    // Submission must still work if storage is disabled.
  }
}

function newRequestKey() {
  try {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    // getRandomValues works on non-HTTPS LAN origins even when randomUUID does not.
    if (globalThis.crypto?.getRandomValues) {
      const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
      return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    }
  } catch {
    // A's endpoint accepts a request without an idempotency key.
  }
  return null;
}

export default function useNewcomerQuestions() {
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(false);
  const [submittedId, setSubmittedId] = useState(null);
  const mounted = useRef(false);
  const readRequest = useRef(null);
  const writeRequest = useRef(null);
  // Question text -> key, for any request whose outcome is not confirmed.
  // A question edited away and then restored keeps the original key.
  const pendingSubmits = useRef(null);
  if (pendingSubmits.current === null) pendingSubmits.current = readPending();

  const refresh = useCallback(async () => {
    // A single read at a time; a pre-submission read must not erase a new item.
    if (!mounted.current || readRequest.current || writeRequest.current) return;
    const controller = new AbortController();
    readRequest.current = controller;
    setRefreshing(true);
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REFRESH_TIMEOUT);
    try {
      const next = await api.questions(undefined, { signal: controller.signal });
      if (controller.signal.aborted || !mounted.current || readRequest.current !== controller) return;
      if (!Array.isArray(next)) throw new Error('Invalid question list');
      setItems(next);
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
  }, []);

  const submit = useCallback(async (text) => {
    const question = text.trim();
    // The ref closes the double-click window before React renders disabled UI.
    if (!mounted.current || writeRequest.current || !question || question.length > 2000) return false;
    const controller = new AbortController();
    const pending = pendingSubmits.current;
    // Key creation may be unavailable on older/insecure browsers; don't block the
    // question in that case. Keep one key per unconfirmed question, not per attempt.
    const key = pending.get(question) || newRequestKey();
    if (key) {
      pending.delete(question);
      pending.set(question, key);
      while (pending.size > MAX_PENDING) pending.delete(pending.keys().next().value);
      writePending(pending);
    }
    writeRequest.current = controller;
    readRequest.current?.abort();
    readRequest.current = null;
    setRefreshing(false);
    setSubmitting(true);
    setSubmitError(false);
    setSubmittedId(null);
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, SUBMIT_TIMEOUT);
    try {
      const item = await api.ask(question, { signal: controller.signal, clientRequestId: key });
      if (controller.signal.aborted || !mounted.current || writeRequest.current !== controller) return false;
      // POST is authoritative. A separate failed GET must not look like a failed save.
      pending.delete(question);
      writePending(pending);
      setItems(previous => [item, ...previous.filter(existing => existing.id !== item.id)]);
      setLoaded(true);
      setSubmittedId(item.id);
      return true;
    } catch {
      if (mounted.current && writeRequest.current === controller && (!controller.signal.aborted || timedOut)) {
        setSubmitError(true);
      }
      return false;
    } finally {
      clearTimeout(timeout);
      if (writeRequest.current === controller) {
        writeRequest.current = null;
        if (mounted.current) setSubmitting(false);
      }
    }
  }, []);

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
      writeRequest.current?.abort();
      readRequest.current = null;
      writeRequest.current = null;
    };
  }, [refresh]);

  return { items, loaded, refreshing, loadError, refresh, submitting, submitError, submittedId, submit };
}
