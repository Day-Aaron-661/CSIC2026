// Keyword matching over mentor-approved answers. This is plain string overlap, not AI
// retrieval: it can miss a question that is worded differently, and the UI says so.

// Common words that carry no topic on their own. Chinese entries are character pairs,
// because Chinese text is split into overlapping two-character pairs below.
const STOP_WORDS = new Set([
  'a', 'about', 'an', 'and', 'any', 'are', 'as', 'at', 'be', 'by', 'can', 'could', 'do', 'does',
  'for', 'from', 'get', 'have', 'how', 'i', 'if', 'in', 'into', 'is', 'it', 'me', 'my', 'need',
  'of', 'on', 'or', 'our', 'please', 'should', 'so', 'that', 'the', 'there', 'this', 'to', 'use',
  'was', 'we', 'what', 'when', 'where', 'which', 'who', 'why', 'will', 'with', 'would', 'you', 'your',
  '請問', '怎麼', '如何', '什麼', '為什', '可以', '我們', '我要', '一下', '是否', '哪裡', '應該', '需要', '要怎',
]);

// Scripts written without spaces between words (Chinese, Japanese kana) are split into
// overlapping two-character pairs; every other script is split into words.
const PAIRED = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}ー]+/u;
const PAIRED_OR_WORD = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}ー]+|[^\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}ー]+/gu;

// Lower-case, unify full/half width, and drop Latin accents so "café" matches "cafe".
// Only U+0300–U+036F is removed, so Japanese voicing marks (e.g. ガ) are kept.
export function normalize(text) {
  return String(text ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').normalize('NFKC').toLowerCase();
}

export function keywords(text) {
  const found = new Set();
  for (const run of normalize(text).match(/[\p{L}\p{N}]+/gu) ?? []) {
    for (const part of run.match(PAIRED_OR_WORD)) {
      if (!PAIRED.test(part)) {
        if (!STOP_WORDS.has(part)) found.add(part);
        continue;
      }
      for (let index = 0; index + 1 < part.length; index += 1) {
        const pair = part.slice(index, index + 2);
        if (!STOP_WORDS.has(pair)) found.add(pair);
      }
    }
  }
  return found;
}

// Keywords of every approved entry, computed once per knowledge list rather than on
// every queue poll.
export function prepareKnowledge(items) {
  return items.map(item => {
    const text = `${item.question}\n${item.reviewed_answer ?? ''}`;
    return { item, question: keywords(item.question), all: keywords(text), text: normalize(text) };
  });
}

function overlap(a, b) {
  let shared = 0;
  for (const word of a) if (b.has(word)) shared += 1;
  return shared;
}

function newestFirst(a, b) {
  return b.score - a.score || b.item.id - a.item.id;
}

// Approved questions similar to a pending one. Dice coefficient on the two question
// texts, so a short and a long question with one shared word do not count as similar.
export function findSimilar(question, prepared, { limit = 3, min = 0.25 } = {}) {
  const query = keywords(question);
  if (!query.size) return [];
  return prepared
    .map(entry => {
      const score = entry.question.size
        ? (2 * overlap(query, entry.question)) / (query.size + entry.question.size)
        : 0;
      return { item: entry.item, score };
    })
    .filter(result => result.score >= min)
    .sort(newestFirst)
    .slice(0, limit)
    .map(result => result.item);
}

// Free-text search over approved questions and answers. Normally ranks by the share of
// typed keywords found in an entry. When the text yields no keywords (one Chinese
// character, or only common words such as "how"), it falls back to a plain
// case-insensitive substring match instead of wrongly reporting no matches.
export function searchKnowledge(text, prepared, { limit = 10, min = 0.5 } = {}) {
  const query = keywords(text);
  if (!query.size) {
    const needle = normalize(text).trim();
    if (!needle) return { mode: 'keywords', items: [] };
    const items = prepared
      .filter(entry => entry.text.includes(needle))
      .sort((a, b) => b.item.id - a.item.id)
      .slice(0, limit)
      .map(entry => entry.item);
    return { mode: 'text', items };
  }
  const items = prepared
    .map(entry => ({ item: entry.item, score: overlap(query, entry.all) / query.size }))
    .filter(result => result.score >= min)
    .sort(newestFirst)
    .slice(0, limit)
    .map(result => result.item);
  return { mode: 'keywords', items };
}
