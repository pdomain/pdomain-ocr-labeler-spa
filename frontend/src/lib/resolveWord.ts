import type { components } from "../api/types";
import { findWordByIndex } from "./word-order";
type PagePayload = components["schemas"]["PagePayload"];
type WordMatch = components["schemas"]["WordMatch"];

export function resolveWord(
  page: PagePayload,
  lineId: number,
  wordId: [number, number],
): WordMatch | null {
  const [, wi] = wordId;
  return findWordByIndex(page, lineId, wi);
}
