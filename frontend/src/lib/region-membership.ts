import type { BBox } from "./coords";

/** Same 5-tuple `Word.bbox_signature` stores: minX, minY, maxX, maxY, is_normalized. */
export type WordSignature = readonly [number, number, number, number, boolean | null];

export interface MembershipWord {
  lineIndex: number;
  wordIndex: number;
  bbox: BBox;
}

export function wordMemberKey(word: Pick<MembershipWord, "lineIndex" | "wordIndex">): string {
  return `${String(word.lineIndex)}:${String(word.wordIndex)}`;
}

/** Python 3 `round`: halves go to the even integer, not away from zero. */
function roundHalfEven(value: number): number {
  if (!Number.isFinite(value)) return 0;
  const floor = Math.floor(value);
  const fraction = value - floor;
  if (fraction < 0.5) return floor;
  if (fraction > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1;
}

/**
 * Convert a stored signature into the source-pixel box the page payload
 * already uses for `WordMatch.bbox`.
 *
 * Rounding matches `_bbox_to_model`: scale a normalized signature by the
 * source page size first, then round the origin and the span separately
 * with Python's half-even `round`. A normalized signature with no source
 * size cannot be matched.
 */
function signatureToSourceBox(
  signature: WordSignature,
  srcWidth: number | null,
  srcHeight: number | null,
): BBox | null {
  let minX = signature[0];
  let minY = signature[1];
  let maxX = signature[2];
  let maxY = signature[3];
  if (signature[4] === true) {
    if (srcWidth === null || srcHeight === null) return null;
    minX *= srcWidth;
    maxX *= srcWidth;
    minY *= srcHeight;
    maxY *= srcHeight;
  }
  return {
    x: roundHalfEven(minX),
    y: roundHalfEven(minY),
    width: Math.max(0, roundHalfEven(maxX - minX)),
    height: Math.max(0, roundHalfEven(maxY - minY)),
  };
}

function sameBox(left: BBox, right: BBox): boolean {
  return (
    left.x === right.x &&
    left.y === right.y &&
    left.width === right.width &&
    left.height === right.height
  );
}

/**
 * Words whose boxes match `signatures`.
 * Identical boxes are consumed once each, in word order, so two words with
 * the same box are not both claimed by one signature.
 */
export function matchingMemberKeys(
  words: readonly MembershipWord[],
  signatures: readonly WordSignature[],
  srcWidth: number | null,
  srcHeight: number | null,
): string[] {
  const used = new Set<number>();
  const keys: string[] = [];
  for (const signature of signatures) {
    const box = signatureToSourceBox(signature, srcWidth, srcHeight);
    if (box === null) continue;
    const index = words.findIndex(
      (word, wordIndex) => !used.has(wordIndex) && sameBox(word.bbox, box),
    );
    if (index < 0) continue;
    const word = words[index];
    if (word === undefined) continue;
    used.add(index);
    keys.push(wordMemberKey(word));
  }
  return keys;
}
