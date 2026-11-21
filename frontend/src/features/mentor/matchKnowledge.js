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

export function keywords(text) {
  const normalized = String(text ?? '').normalize('NFKC').toLowerCase();
  const found = new Set();
  for (const word of normalized.match(/[a-z0-9]+/g) ?? []) {
    if (!STOP_WORDS.has(word)) found.add(word);
  }
  for (const run of normalized.match(/\p{Script=Han}+/gu) ?? []) {
    for (let index = 0; index + 1 < run.length; index += 1) {
      const pair = run.slice(index, index + 2);
      if (!STOP_WORDS.has(pair)) found.add(pair);
    }
  }
  return found;
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
export function findSimilar(question, knowledge, { limit = 3, min = 0.25 } = {}) {
  const query = keywords(question);
  if (!query.size) return [];
  return knowledge
    .map(item => {
      const candidate = keywords(item.question);
      const score = candidate.size ? (2 * overlap(query, candidate)) / (query.size + candidate.size) : 0;
      return { item, score };
    })
    .filter(result => result.score >= min)
    .sort(newestFirst)
    .slice(0, limit)
    .map(result => result.item);
}

// Free-text search over approved questions and answers: share of the typed keywords
// that appear in an entry.
export function searchKnowledge(text, knowledge, { limit = 10, min = 0.5 } = {}) {
  const query = keywords(text);
  if (!query.size) return [];
  return knowledge
    .map(item => {
      const candidate = keywords(`${item.question}\n${item.reviewed_answer ?? ''}`);
      return { item, score: overlap(query, candidate) / query.size };
    })
    .filter(result => result.score >= min)
    .sort(newestFirst)
    .slice(0, limit)
    .map(result => result.item);
}
