type ViewerPanel = "closed" | "selection" | "source_alignment";

interface ViewerSelection {
  readonly word_ids: readonly string[];
  readonly region_id: string | null;
  readonly proposal_id: string | null;
  readonly alignment_group_id: string | null;
  readonly alignment_id: string | null;
}

export interface ViewerCommand {
  readonly viewer_id: string;
  readonly command_seq: number;
  readonly project_id: string;
  readonly page_index: number;
  readonly panel: ViewerPanel;
  readonly selection: ViewerSelection;
}

interface ViewerError {
  readonly error: string;
  readonly message: string;
  readonly details: unknown;
}

export interface ViewerAck extends ViewerCommand {
  readonly generation: number;
  readonly status: "applied" | "failed";
  readonly error: ViewerError | null;
}

export interface ViewerState {
  readonly viewer_id: string;
  readonly connected: boolean;
  readonly desired: ViewerCommand | null;
  readonly acknowledged: ViewerAck | null;
  readonly pending: boolean;
  readonly last_observation: ViewerAck | null;
}

type AutomationEventKind =
  "project_changed" | "page_changed" | "job_changed" | "viewer_command" | "viewer_ack" | "reset";

export interface AutomationEvent {
  readonly revision: number;
  readonly kind: AutomationEventKind;
  readonly project_id: string | null;
  readonly page_index: number | null;
  readonly generation: number | null;
  readonly job_id: string | null;
  readonly viewer_id: string | null;
  readonly command_seq: number | null;
}

export interface AutomationStateSnapshot {
  readonly revision: number;
  readonly viewers: readonly ViewerState[];
}

export class AutomationApiError extends Error {
  readonly status: number;
  readonly error: string;
  readonly details: unknown;

  constructor(status: number, error: string, message: string, details: unknown) {
    super(message);
    this.name = "AutomationApiError";
    this.status = status;
    this.error = error;
    this.details = details;
  }
}

function recordOf(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return Object.fromEntries(Object.entries(value));
}

function stringOf(record: Record<string, unknown>, key: string, label: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new Error(`${label} must be a string`);
  return value;
}

function booleanOf(record: Record<string, unknown>, key: string, label: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
  return value;
}

function nonNegativeIntegerOf(record: Record<string, unknown>, key: string, label: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return value;
}

function positiveIntegerOf(record: Record<string, unknown>, key: string, label: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1) {
    throw new Error(`${label} must be a positive integer`);
  }
  return value;
}

function nullableStringOf(
  record: Record<string, unknown>,
  key: string,
  label: string,
): string | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== "string") throw new Error(`${label} must be a string or null`);
  return value;
}

function nullableIntegerOf(
  record: Record<string, unknown>,
  key: string,
  label: string,
): number | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer or null`);
  }
  return value;
}

function nullableObjectOf(
  record: Record<string, unknown>,
  key: string,
  label: string,
): Record<string, unknown> | null {
  const value = record[key];
  if (value === null) return null;
  return recordOf(value, label);
}

function panelOf(record: Record<string, unknown>, key: string, label: string): ViewerPanel {
  const value = stringOf(record, key, label);
  if (value === "closed" || value === "selection" || value === "source_alignment") return value;
  throw new Error(`${label} is not a supported panel`);
}

function parseSelection(value: unknown): ViewerSelection {
  const record = recordOf(value, "viewer selection");
  const rawWordIds = record["word_ids"];
  if (!Array.isArray(rawWordIds) || !rawWordIds.every((wordId) => typeof wordId === "string")) {
    throw new Error("viewer selection word_ids must be strings");
  }
  return {
    word_ids: rawWordIds,
    region_id: nullableStringOf(record, "region_id", "viewer selection region_id"),
    proposal_id: nullableStringOf(record, "proposal_id", "viewer selection proposal_id"),
    alignment_group_id: nullableStringOf(
      record,
      "alignment_group_id",
      "viewer selection alignment_group_id",
    ),
    alignment_id: nullableStringOf(record, "alignment_id", "viewer selection alignment_id"),
  };
}

function parseCommandRecord(record: Record<string, unknown>): ViewerCommand {
  return {
    viewer_id: stringOf(record, "viewer_id", "viewer command viewer_id"),
    command_seq: positiveIntegerOf(record, "command_seq", "viewer command command_seq"),
    project_id: stringOf(record, "project_id", "viewer command project_id"),
    page_index: nonNegativeIntegerOf(record, "page_index", "viewer command page_index"),
    panel: panelOf(record, "panel", "viewer command panel"),
    selection: parseSelection(record["selection"]),
  };
}

function parseViewerError(value: unknown): ViewerError {
  const record = recordOf(value, "viewer error");
  return {
    error: stringOf(record, "error", "viewer error error"),
    message: stringOf(record, "message", "viewer error message"),
    details: record["details"] ?? null,
  };
}

function parseViewerAck(value: unknown): ViewerAck {
  const record = recordOf(value, "viewer acknowledgement");
  const command = parseCommandRecord(record);
  const status = stringOf(record, "status", "viewer acknowledgement status");
  if (status !== "applied" && status !== "failed") {
    throw new Error("viewer acknowledgement status is not supported");
  }
  const rawError = record["error"];
  return {
    ...command,
    generation: nonNegativeIntegerOf(record, "generation", "viewer acknowledgement generation"),
    status,
    error: rawError === null ? null : parseViewerError(rawError),
  };
}

function parseNullableCommand(record: Record<string, unknown>, key: string): ViewerCommand | null {
  const value = nullableObjectOf(record, key, `viewer state ${key}`);
  return value === null ? null : parseCommandRecord(value);
}

function parseNullableAck(record: Record<string, unknown>, key: string): ViewerAck | null {
  const value = nullableObjectOf(record, key, `viewer state ${key}`);
  return value === null ? null : parseViewerAck(value);
}

export function parseViewerState(value: unknown): ViewerState {
  const record = recordOf(value, "viewer state");
  return {
    viewer_id: stringOf(record, "viewer_id", "viewer state viewer_id"),
    connected: booleanOf(record, "connected", "viewer state connected"),
    desired: parseNullableCommand(record, "desired"),
    acknowledged: parseNullableAck(record, "acknowledged"),
    pending: booleanOf(record, "pending", "viewer state pending"),
    last_observation: parseNullableAck(record, "last_observation"),
  };
}

export function parseAutomationEvent(value: unknown): AutomationEvent {
  const record = recordOf(value, "automation event");
  const kind = stringOf(record, "kind", "automation event kind");
  if (
    kind !== "project_changed" &&
    kind !== "page_changed" &&
    kind !== "job_changed" &&
    kind !== "viewer_command" &&
    kind !== "viewer_ack" &&
    kind !== "reset"
  ) {
    throw new Error("automation event kind is not supported");
  }
  return {
    revision: nonNegativeIntegerOf(record, "revision", "automation event revision"),
    kind,
    project_id: nullableStringOf(record, "project_id", "automation event project_id"),
    page_index: nullableIntegerOf(record, "page_index", "automation event page_index"),
    generation: nullableIntegerOf(record, "generation", "automation event generation"),
    job_id: nullableStringOf(record, "job_id", "automation event job_id"),
    viewer_id: nullableStringOf(record, "viewer_id", "automation event viewer_id"),
    command_seq: nullableIntegerOf(record, "command_seq", "automation event command_seq"),
  };
}

function parseAutomationStateSnapshot(value: unknown): AutomationStateSnapshot {
  const record = recordOf(value, "automation state");
  const viewers = record["viewers"];
  if (!Array.isArray(viewers)) throw new Error("automation state viewers must be an array");
  return {
    revision: nonNegativeIntegerOf(record, "revision", "automation state revision"),
    viewers: viewers.map(parseViewerState),
  };
}

async function responseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text === "") return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, init);
  const body = await responseJson(response);
  if (response.ok) return body;
  const record =
    body === null || typeof body !== "object" || Array.isArray(body)
      ? null
      : recordOf(body, "HTTP error response");
  const errorValue: unknown = record === null ? undefined : record["error"];
  const messageValue: unknown = record === null ? undefined : record["message"];
  const details: unknown = record === null ? null : (record["details"] ?? null);
  const error = typeof errorValue === "string" ? errorValue : `http_${String(response.status)}`;
  const message = typeof messageValue === "string" ? messageValue : response.statusText;
  throw new AutomationApiError(response.status, error, message, details);
}

export async function registerViewer(viewerId: string | null): Promise<ViewerState> {
  return parseViewerState(
    await request("/api/automation/viewers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ viewer_id: viewerId }),
    }),
  );
}

export async function fetchAutomationState(): Promise<AutomationStateSnapshot> {
  return parseAutomationStateSnapshot(await request("/api/automation/state"));
}

export async function fetchViewerState(viewerId: string): Promise<ViewerState> {
  return parseViewerState(
    await request(`/api/automation/view?viewer_id=${encodeURIComponent(viewerId)}`),
  );
}

export async function acknowledgeViewer(acknowledgement: ViewerAck): Promise<ViewerState> {
  return parseViewerState(
    await request("/api/automation/view/ack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(acknowledgement),
    }),
  );
}
