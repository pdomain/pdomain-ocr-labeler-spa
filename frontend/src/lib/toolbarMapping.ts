export interface ToolbarActionMapping {
  endpoint: string;
  method: 'GET' | 'POST' | 'DELETE' | 'PUT';
  body?: Record<string, unknown>;
}

type ToolbarMappingRecord = Record<string, ToolbarActionMapping | null>;

export const toolbarMapping: ToolbarMappingRecord = {
  // Page scope actions
  'page-merge': null, // disabled
  'page-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'page', mode: 'refine' },
  },
  'page-expand-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'page', mode: 'expand_then_refine' },
  },
  'page-expand': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'page', mode: 'expand_only' },
  },
  'page-split-after': null, // disabled
  'page-split-selected': null, // disabled
  'page-word-to-line': null, // disabled
  'page-word-to-para': null, // disabled
  'page-gt-to-ocr': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'page', direction: 'gt_to_ocr' },
  },
  'page-ocr-to-gt': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'page', direction: 'ocr_to_gt' },
  },
  'page-validate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'page', validated: true },
  },
  'page-unvalidate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'page', validated: false },
  },
  'page-delete': null, // disabled

  // Paragraph scope actions
  'paragraph-merge': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/paragraphs/merge',
    method: 'POST',
    body: { scope: 'paragraph' },
  },
  'paragraph-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'paragraph', mode: 'refine' },
  },
  'paragraph-expand-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'paragraph', mode: 'expand_then_refine' },
  },
  'paragraph-expand': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'paragraph', mode: 'expand_only' },
  },
  'paragraph-split-after': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/paragraphs/{paragraphIndex}/split-after-line',
    method: 'POST',
  },
  'paragraph-split-selected': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/paragraphs/split-selected',
    method: 'POST',
  },
  'paragraph-word-to-line': null, // disabled
  'paragraph-word-to-para': null, // disabled
  'paragraph-gt-to-ocr': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'paragraph', direction: 'gt_to_ocr' },
  },
  'paragraph-ocr-to-gt': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'paragraph', direction: 'ocr_to_gt' },
  },
  'paragraph-validate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'paragraph', validated: true },
  },
  'paragraph-unvalidate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'paragraph', validated: false },
  },
  'paragraph-delete': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/paragraphs/delete-batch',
    method: 'POST',
    body: { scope: 'paragraph' },
  },

  // Line scope actions
  'line-merge': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/merge',
    method: 'POST',
    body: { scope: 'line' },
  },
  'line-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'line', mode: 'refine' },
  },
  'line-expand-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'line', mode: 'expand_then_refine' },
  },
  'line-expand': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'line', mode: 'expand_only' },
  },
  'line-split-after': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/{lineIndex}/split-after-word',
    method: 'POST',
  },
  'line-split-selected': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/{lineIndex}/split-with-selected-words',
    method: 'POST',
  },
  'line-word-to-line': null, // disabled
  'line-word-to-para': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/paragraphs/group-selected-words',
    method: 'POST',
    body: { scope: 'line' },
  },
  'line-gt-to-ocr': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'line', direction: 'gt_to_ocr' },
  },
  'line-ocr-to-gt': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'line', direction: 'ocr_to_gt' },
  },
  'line-validate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'line', validated: true },
  },
  'line-unvalidate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'line', validated: false },
  },
  'line-delete': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/delete-batch',
    method: 'POST',
    body: { scope: 'line' },
  },

  // Word scope actions
  'word-merge': null, // disabled
  'word-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'word', mode: 'refine' },
  },
  'word-expand-refine': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'word', mode: 'expand_then_refine' },
  },
  'word-expand': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/refine',
    method: 'POST',
    body: { scope: 'word', mode: 'expand_only' },
  },
  'word-split-after': null, // disabled
  'word-split-selected': null, // disabled
  'word-word-to-line': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/{lineIndex}/split-with-selected-words',
    method: 'POST',
    body: { mode: 'extract_to_new' },
  },
  'word-word-to-para': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/paragraphs/group-selected-words',
    method: 'POST',
  },
  'word-gt-to-ocr': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'word', direction: 'gt_to_ocr' },
  },
  'word-ocr-to-gt': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/lines/copy-gt-batch',
    method: 'POST',
    body: { scope: 'word', direction: 'ocr_to_gt' },
  },
  'word-validate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'word', validated: true },
  },
  'word-unvalidate': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/validate-batch',
    method: 'POST',
    body: { scope: 'word', validated: false },
  },
  'word-delete': {
    endpoint: '/api/projects/{projectId}/pages/{pageIndex}/words/delete-batch',
    method: 'POST',
    body: { scope: 'word' },
  },
};
