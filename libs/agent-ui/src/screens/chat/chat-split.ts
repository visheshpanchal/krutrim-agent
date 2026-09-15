import type { TurnSplitter } from '../types';

/**
 * Plain chat is told (see `backend/harness/prompts/shared/output-decision.md`,
 * included by `chat-system-prompt.md`) to answer quick questions inline and,
 * for a deliverable (a report, an explicit file/PDF request), write a short
 * narration line, then a single marker, then the deliverable:
 *
 *     I've put together the analysis and saved it below.
 *     ===OUTPUT===
 *     # The Analysis
 *     …
 *
 * Everything before the marker is what stays in the chat bubble; everything
 * after is routed to the output panel by `ChatRenderer`. Deliberately its own
 * marker (not research's `===FINAL_REPORT===`) so the two screens' splitters
 * never collide.
 *
 * **Different fallback than research's `researchSplitTurn`**: when no marker
 * is found, the *entire* text stays as narration and `output` is `null`,
 * regardless of `finished` — most chat turns are plain short answers and must
 * never be shoved into the output panel just because the turn ended.
 */
export const OUTPUT_MARKER = '===OUTPUT===';

/** Tolerant: 2+ `=`, optional spaces, `OUTPUT`. */
const MARKER_RE = /^[ \t]*={2,}[ \t]*OUTPUT[ \t]*={2,}[ \t]*$/im;

/** Strips a stray marker line a weaker model leaks into text that isn't
 * actually being split on it (e.g. still-streaming narration). */
function stripStrayMarker(text: string): string {
  return text.replace(MARKER_RE, '').replace(/\n{3,}/g, '\n\n').trim();
}

export const chatSplitTurn: TurnSplitter = (text, { title }) => {
  const match = MARKER_RE.exec(text);
  if (!match) {
    return { narration: text, output: null };
  }

  const narration = text.slice(0, match.index).trimEnd();
  const reportSource = text.slice(match.index + match[0].length).replace(/^\s+/, '');
  const reportClean = stripStrayMarker(reportSource);

  return {
    narration,
    output: reportClean ? { kind: 'markdown', title, content: reportClean } : null,
  };
};
