// Spec: docs/specs/2026-05-12-toolbar-actions-design.md §Decision
// Grid layout: docs/architecture/06-toolbar-actions.md §1

export interface Selection {
  selection_mode: "paragraph" | "line" | "word";
  selected_paragraphs: number[];
  selected_lines: number[];
  selected_words: [number, number][]; // [line_idx, word_idx]
}

interface WordValidationInfo {
  line_index: number;
  word_index: number;
  is_validated: boolean;
}

interface LineValidationInfo {
  line_index: number;
  paragraph_index: number | null;
  validated_word_count: number;
  total_word_count: number;
  words: WordValidationInfo[];
}

export interface PageData {
  lines: LineValidationInfo[];
}

// ButtonStates covers only the 40 present cells (✔ in the grid).
// Stub cells (absent from grid) are always false and handled by the component.
export interface ButtonStates {
  // Page row (7 buttons — no Merge, SplitAfter, SplitSelected, W→L, →Para, Delete)
  page_refine: boolean;
  page_expand_refine: boolean;
  page_expand: boolean;
  page_gt_to_ocr: boolean;
  page_ocr_to_gt: boolean;
  page_validate: boolean;
  page_unvalidate: boolean;
  // Para row (11 buttons — no W→L, →Para)
  para_merge: boolean;
  para_refine: boolean;
  para_expand_refine: boolean;
  para_expand: boolean;
  para_split_after: boolean;
  para_split_selected: boolean;
  para_gt_to_ocr: boolean;
  para_ocr_to_gt: boolean;
  para_validate: boolean;
  para_unvalidate: boolean;
  para_delete: boolean;
  // Line row (12 buttons — no W→L)
  line_merge: boolean;
  line_refine: boolean;
  line_expand_refine: boolean;
  line_expand: boolean;
  line_split_after: boolean;
  line_split_selected: boolean;
  line_to_para: boolean;
  line_gt_to_ocr: boolean;
  line_ocr_to_gt: boolean;
  line_validate: boolean;
  line_unvalidate: boolean;
  line_delete: boolean;
  // Word row (10 buttons — no Merge, SplitAfter, SplitSelected)
  word_refine: boolean;
  word_expand_refine: boolean;
  word_expand: boolean;
  word_w_to_l: boolean;
  word_to_para: boolean;
  word_gt_to_ocr: boolean;
  word_ocr_to_gt: boolean;
  word_validate: boolean;
  word_unvalidate: boolean;
  word_delete: boolean;
}

export function useToolbarButtonStates(selection: Selection, page: PageData): ButtonStates {
  const nParas = selection.selected_paragraphs.length;
  const nLines = selection.selected_lines.length;
  const nWords = selection.selected_words.length;

  const wordLineIndices = selection.selected_words.map(([li]) => li);
  const uniqueWordLines = new Set(wordLineIndices);
  const allWordsInSameLine = nWords > 0 && uniqueWordLines.size === 1;

  const wordValidated = new Map<string, boolean>();
  for (const line of page.lines) {
    for (const word of line.words) {
      wordValidated.set(`${word.line_index}-${word.word_index}`, word.is_validated);
    }
  }

  const lineMap = new Map<number, LineValidationInfo>();
  for (const line of page.lines) {
    lineMap.set(line.line_index, line);
  }

  const paraLines = new Map<number, LineValidationInfo[]>();
  for (const line of page.lines) {
    if (line.paragraph_index !== null) {
      const bucket = paraLines.get(line.paragraph_index) ?? [];
      bucket.push(line);
      paraLines.set(line.paragraph_index, bucket);
    }
  }

  const pageHasUnvalidated = page.lines.some((l) => l.validated_word_count < l.total_word_count);
  const pageHasValidated = page.lines.some((l) => l.validated_word_count > 0);

  const selectedParasHaveUnvalidated = selection.selected_paragraphs.some((pi) =>
    (paraLines.get(pi) ?? []).some((l) => l.validated_word_count < l.total_word_count),
  );
  const selectedParasHaveValidated = selection.selected_paragraphs.some((pi) =>
    (paraLines.get(pi) ?? []).some((l) => l.validated_word_count > 0),
  );

  const selectedLinesHaveUnvalidated = selection.selected_lines.some((li) => {
    const line = lineMap.get(li);
    return line ? line.validated_word_count < line.total_word_count : false;
  });
  const selectedLinesHaveValidated = selection.selected_lines.some((li) => {
    const line = lineMap.get(li);
    return line ? line.validated_word_count > 0 : false;
  });

  // Unknown words (not in pageData) are treated as unvalidated
  const selectedWordsHaveUnvalidated = selection.selected_words.some(
    ([li, wi]) => wordValidated.get(`${li}-${wi}`) !== true,
  );
  const selectedWordsHaveValidated = selection.selected_words.some(
    ([li, wi]) => wordValidated.get(`${li}-${wi}`) === true,
  );

  return {
    page_refine: true,
    page_expand_refine: true,
    page_expand: true,
    page_gt_to_ocr: true,
    page_ocr_to_gt: true,
    page_validate: pageHasUnvalidated,
    page_unvalidate: pageHasValidated,

    para_merge: nParas >= 2,
    para_refine: nParas >= 1,
    para_expand_refine: nParas >= 1,
    para_expand: nParas >= 1,
    para_split_after: nParas >= 1,
    para_split_selected: nParas >= 1,
    para_gt_to_ocr: nParas >= 1,
    para_ocr_to_gt: nParas >= 1,
    para_validate: nParas >= 1 && selectedParasHaveUnvalidated,
    para_unvalidate: nParas >= 1 && selectedParasHaveValidated,
    para_delete: nParas >= 1,

    line_merge: nLines >= 2,
    line_refine: nLines >= 1,
    line_expand_refine: nLines >= 1,
    line_expand: nLines >= 1,
    line_split_after: allWordsInSameLine,
    line_split_selected: allWordsInSameLine,
    line_to_para: nLines >= 1 || nWords >= 1,
    line_gt_to_ocr: nLines >= 1,
    line_ocr_to_gt: nLines >= 1,
    line_validate: nLines >= 1 && selectedLinesHaveUnvalidated,
    line_unvalidate: nLines >= 1 && selectedLinesHaveValidated,
    line_delete: nLines >= 1,

    word_refine: nWords >= 1,
    word_expand_refine: nWords >= 1,
    word_expand: nWords >= 1,
    word_w_to_l: allWordsInSameLine,
    word_to_para: nWords >= 1 || nLines >= 1,
    word_gt_to_ocr: nWords >= 1,
    word_ocr_to_gt: nWords >= 1,
    word_validate: nWords >= 1 && selectedWordsHaveUnvalidated,
    word_unvalidate: nWords >= 1 && selectedWordsHaveValidated,
    word_delete: nWords >= 1,
  };
}
