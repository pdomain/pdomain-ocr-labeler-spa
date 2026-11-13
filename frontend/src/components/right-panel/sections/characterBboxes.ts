import type { BBox } from "../../../lib/coords";
import type { CharacterBBox } from "./CharFixerCanvas";

export function initialCharBboxes(
  wordBbox: BBox,
  ranges: readonly { start: number; end: number }[],
  totalChars: number,
): CharacterBBox[] {
  if (totalChars <= 0 || ranges.length === 0) return [];
  const charW = wordBbox.width / totalChars;
  return ranges.map((r) => {
    const startIdx = Math.max(0, Math.min(totalChars - 1, r.start));
    const endIdx = Math.max(startIdx, Math.min(totalChars - 1, r.end));
    const x = wordBbox.x + charW * startIdx;
    const width = Math.max(1, charW * (endIdx - startIdx + 1));
    return {
      start: r.start,
      end: r.end,
      bbox: { x, y: wordBbox.y, width, height: wordBbox.height },
    };
  });
}
