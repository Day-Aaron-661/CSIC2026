import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api.js';

const REFRESH_INTERVAL = 5000;
const REFRESH_TIMEOUT = 15000;
const SUBMIT_TIMEOUT = 60000;

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
  // Keep the same key after an uncertain POST outcome. A's new backend returns
  // the original item when that key is retried; changing the text gets a new key.
  const pendingSubmit = useRef(null);

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
    const attempt = pendingSubmit.current?.question === question
      ? pendingSubmit.current
      : { question, key: crypto.randomUUID() };
    pendingSubmit.current = attempt;
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
      const item = await api.ask(question, { signal: controller.signal, clientRequestId: attempt.key });
      if (controller.signal.aborted || !mounted.current || writeRequest.current !== controller) return false;
      // POST is authoritative. A separate failed GET must not look like a failed save.
      pendingSubmit.current = null;
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
