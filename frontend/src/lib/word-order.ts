import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

export interface WordOrder {
  line: LineMatch | null;
  words: WordMatch[];
  position: number;
  word: WordMatch | null;
  prev: WordMatch | null;
  next: WordMatch | null;
}

function findLineByIndex(page: PagePayload, lineIndex: number): LineMatch | null {
  return page.line_matches?.find((line) => line.line_index === lineIndex) ?? null;
}

function sortedWordsByIndex(line: LineMatch | null): WordMatch[] {
  return (line?.word_matches ?? [])
    .filter((word) => typeof word.word_index === "number")
    .slice()
    .sort((a, b) => (a.word_index ?? 0) - (b.word_index ?? 0));
}

export function findWordByIndex(
  page: PagePayload,
  lineIndex: number,
  wordIndex: number,
): WordMatch | null {
  const line = findLineByIndex(page, lineIndex);
  return line?.word_matches.find((word) => word.word_index === wordIndex) ?? null;
}

export function getWordOrder(page: PagePayload, lineIndex: number, wordIndex: number): WordOrder {
  const line = findLineByIndex(page, lineIndex);
  const words = sortedWordsByIndex(line);
  const position = words.findIndex((word) => word.word_index === wordIndex);
  const word = position >= 0 ? words[position]! : null;
  const prev = position > 0 ? words[position - 1]! : null;
  const next = position >= 0 && position < words.length - 1 ? words[position + 1]! : null;

  return { line, words, position, word, prev, next };
}
