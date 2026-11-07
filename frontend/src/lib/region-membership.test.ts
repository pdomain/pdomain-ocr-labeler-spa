import { describe, it, expect } from "vitest";
import { matchingMemberKeys, type MembershipWord, type WordSignature } from "./region-membership";

const pixelWord: MembershipWord = {
  lineIndex: 0,
  wordIndex: 1,
  bbox: { x: 10, y: 20, width: 30, height: 8 },
};

const pixelSignature: WordSignature = [10, 20, 40, 28, false];

describe("matchingMemberKeys", () => {
  it("matches a pixel signature to the word with the same rounded box", () => {
    expect(matchingMemberKeys([pixelWord], [pixelSignature], null, null)).toEqual(["0:1"]);
  });

  it("scales a normalized signature by the source page size", () => {
    const word: MembershipWord = {
      lineIndex: 2,
      wordIndex: 0,
      bbox: { x: 100, y: 100, width: 200, height: 100 },
    };
    const signature: WordSignature = [0.1, 0.2, 0.3, 0.4, true];
    expect(matchingMemberKeys([word], [signature], 1000, 500)).toEqual(["2:0"]);
  });

  it("rounds a scaled half to the even integer, matching Python round", () => {
    const word: MembershipWord = {
      lineIndex: 0,
      wordIndex: 0,
      bbox: { x: 0, y: 0, width: 1, height: 0 },
    };
    // 0.25 * 2 = 0.5 and 0.75 * 2 = 1.5. Python round(0.5) is 0; Math.round(0.5) is 1.
    const signature: WordSignature = [0.25, 0, 0.75, 0.05, true];
    expect(matchingMemberKeys([word], [signature], 2, 2)).toEqual(["0:0"]);
  });

  it("does not match a normalized signature when the source size is missing", () => {
    const word: MembershipWord = {
      lineIndex: 0,
      wordIndex: 0,
      bbox: { x: 100, y: 100, width: 200, height: 100 },
    };
    const signature: WordSignature = [0.1, 0.2, 0.3, 0.4, true];
    expect(matchingMemberKeys([word], [signature], null, null)).toEqual([]);
  });

  it("assigns identical boxes to one unused word each", () => {
    const twin: MembershipWord = {
      lineIndex: 1,
      wordIndex: 0,
      bbox: { x: 4, y: 4, width: 6, height: 6 },
    };
    const twinAgain: MembershipWord = {
      lineIndex: 1,
      wordIndex: 1,
      bbox: { x: 4, y: 4, width: 6, height: 6 },
    };
    const signature: WordSignature = [4, 4, 10, 10, false];
    expect(matchingMemberKeys([twin, twinAgain], [signature], null, null)).toEqual(["1:0"]);
    expect(matchingMemberKeys([twin, twinAgain], [signature, signature], null, null)).toEqual([
      "1:0",
      "1:1",
    ]);
  });
});
