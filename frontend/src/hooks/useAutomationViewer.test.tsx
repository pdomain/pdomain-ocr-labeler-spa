import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AutomationApiError, type ViewerAck, type ViewerCommand } from "../api/automation";
import {
  acceptPagePayload,
  isCurrentPageCacheEpoch,
  pageCacheEpoch,
  pageCacheScope,
  resetPageCacheOrder,
} from "../lib/page-cache-order";
import { useAutomationViewer } from "./automation-viewer-context";
import { AutomationViewerProvider } from "./useAutomationViewer";

type Listener = (event: MessageEvent<string>) => void;

class MockEventSource {
  readonly listeners = new Map<string, Listener[]>();
  onerror: (() => void) | null = null;

  constructor(_url: string) {
    sources.push(this);
  }

  addEventListener(kind: string, listener: Listener): void {
    const listeners = this.listeners.get(kind) ?? [];
    listeners.push(listener);
    this.listeners.set(kind, listeners);
  }

  close(): void {}

  emit(kind: string, payload: unknown): void {
    for (const listener of this.listeners.get(kind) ?? []) {
      listener({ data: JSON.stringify(payload) } as MessageEvent<string>);
    }
  }
}

let sources: MockEventSource[] = [];
let snapshotRevision = 5;
let pendingCommand: ViewerCommand | null = null;
let conflictOnAcknowledgement = false;
let activeViewerId = "viewer-1";
let registrationRequests = 0;
let reRegisterOnNextRequest = false;
let delayViewerRead = false;
let resolveDelayedViewerRead: ((response: Response) => void) | null = null;

const sourceCommand: ViewerCommand = {
  viewer_id: "viewer-1",
  command_seq: 8,
  project_id: "Poems00986",
  page_index: 0,
  panel: "source_alignment",
  selection: {
    word_ids: [],
    region_id: null,
    proposal_id: null,
    alignment_group_id: "group-86",
    alignment_id: "result-86",
  },
};

const acknowledgement: ViewerAck = {
  ...sourceCommand,
  generation: 4,
  status: "applied",
  error: null,
};

function viewerState() {
  return {
    viewer_id: activeViewerId,
    connected: true,
    desired: pendingCommand,
    acknowledged: pendingCommand === null ? acknowledgement : null,
    pending: pendingCommand !== null,
    last_observation: null,
  };
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function conflict(): Response {
  return new Response(
    JSON.stringify({ error: "generation_conflict", message: "Page generation changed." }),
    {
      status: 409,
      headers: { "Content-Type": "application/json" },
    },
  );
}

function renderProvider(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AutomationViewerProvider>
          <div>viewer</div>
        </AutomationViewerProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function ViewerProbe() {
  const viewer = useAutomationViewer();
  const [conflictObserved, setConflictObserved] = useState(false);
  const acknowledgementForCommand =
    viewer.command === null
      ? null
      : {
          ...viewer.command,
          generation: 4,
          status: "applied" as const,
          error: null,
        };
  return (
    <>
      <output data-testid="pending-panel">{viewer.command?.panel ?? "none"}</output>
      <output data-testid="pending-sequence">{String(viewer.command?.command_seq ?? 0)}</output>
      <output data-testid="displayed-panel">{viewer.displayedCommand?.panel ?? "none"}</output>
      <output data-testid="conflict-observed">{String(conflictObserved)}</output>
      {acknowledgementForCommand !== null && (
        <button
          type="button"
          onClick={async () => {
            try {
              await viewer.reportObservation(acknowledgementForCommand);
            } catch (error: unknown) {
              if (error instanceof AutomationApiError && error.status === 409)
                setConflictObserved(true);
              else throw error;
            }
          }}
        >
          acknowledge
        </button>
      )}
    </>
  );
}

function renderProbe(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AutomationViewerProvider>
          <ViewerProbe />
        </AutomationViewerProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  resetPageCacheOrder();
  sources = [];
  snapshotRevision = 5;
  pendingCommand = null;
  conflictOnAcknowledgement = false;
  activeViewerId = "viewer-1";
  registrationRequests = 0;
  reRegisterOnNextRequest = false;
  delayViewerRead = false;
  resolveDelayedViewerRead = null;
  sessionStorage.clear();
  vi.stubGlobal("EventSource", MockEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/automation/viewers") {
        registrationRequests += 1;
        if (reRegisterOnNextRequest && registrationRequests === 2) {
          return new Response(
            JSON.stringify({ error: "viewer_not_found", message: "viewer expired" }),
            {
              status: 404,
              headers: { "Content-Type": "application/json" },
            },
          );
        }
        if (reRegisterOnNextRequest && registrationRequests === 3) activeViewerId = "viewer-2";
        return json(viewerState());
      }
      if (path === "/api/automation/state")
        return json({ revision: snapshotRevision, viewers: [viewerState()] });
      if (path === "/api/automation/view/ack") {
        if (conflictOnAcknowledgement) return conflict();
        pendingCommand = null;
        return json(viewerState());
      }
      if (path.startsWith("/api/automation/view?")) {
        if (delayViewerRead) {
          return new Promise<Response>((resolve) => {
            resolveDelayedViewerRead = resolve;
          });
        }
        return json(viewerState());
      }
      throw new Error(`unexpected request ${path}`);
    }),
  );
});

afterEach(() => {
  resetPageCacheOrder();
  vi.unstubAllGlobals();
});

describe("AutomationViewerProvider event reconciliation", () => {
  it("starts a fresh page-cache epoch from an authoritative state snapshot", async () => {
    const scope = pageCacheScope("Poems00986", 0, "all");
    const epochBeforeRestart = pageCacheEpoch("Poems00986");
    acceptPagePayload(scope, { generation: 7, imageUrl: "before-restart" });
    snapshotRevision = 0;

    renderProvider(new QueryClient());

    await waitFor(() => expect(sources).toHaveLength(1));
    expect(isCurrentPageCacheEpoch("Poems00986", epochBeforeRestart)).toBe(false);
    expect(acceptPagePayload(scope, { generation: 0, imageUrl: "after-restart" }).imageUrl).toBe(
      "after-restart",
    );
  });

  it("starts a fresh epoch only for the project named by a project reload event", async () => {
    const client = new QueryClient();
    const cancel = vi.spyOn(client, "cancelQueries");
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const reloaded = pageCacheScope("Poems00986", 0, "all");
    const unrelated = pageCacheScope("Poems02000", 0, "all");
    renderProvider(client);

    await waitFor(() => expect(sources).toHaveLength(1));
    acceptPagePayload(reloaded, { generation: 7, imageUrl: "before-reload" });
    acceptPagePayload(unrelated, { generation: 3, imageUrl: "other-project" });
    const source = sources[0];
    if (source === undefined) throw new Error("automation EventSource was not opened");
    source.emit("project_changed", {
      revision: 6,
      kind: "project_changed",
      project_id: "Poems00986",
      page_index: null,
      generation: null,
      job_id: null,
      viewer_id: null,
      command_seq: null,
    });

    await waitFor(() => expect(cancel).toHaveBeenCalledWith({ queryKey: ["page", "Poems00986"] }));
    expect(cancel).toHaveBeenCalledWith({ queryKey: ["source-text", "Poems00986"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["source-text", "Poems00986"] });
    expect(acceptPagePayload(reloaded, { generation: 0, imageUrl: "after-reload" }).imageUrl).toBe(
      "after-reload",
    );
    expect(acceptPagePayload(unrelated, { generation: 1, imageUrl: "late-other" }).imageUrl).toBe(
      "other-project",
    );
  });

  it("ignores a delayed old-viewer refresh after a re-registration replacement", async () => {
    pendingCommand = sourceCommand;
    renderProbe(new QueryClient());

    await waitFor(() => expect(screen.getByTestId("pending-sequence")).toHaveTextContent("8"));
    delayViewerRead = true;
    const initialSource = sources[sources.length - 1];
    expect(initialSource).toBeDefined();
    if (initialSource === undefined) throw new Error("automation EventSource was not opened");
    initialSource.emit("viewer_command", {
      revision: 6,
      kind: "viewer_command",
      project_id: "Poems00986",
      page_index: 0,
      generation: 4,
      job_id: null,
      viewer_id: "viewer-1",
      command_seq: 8,
    });
    await waitFor(() => expect(resolveDelayedViewerRead).not.toBeNull());

    pendingCommand = {
      ...sourceCommand,
      viewer_id: "viewer-2",
      command_seq: 1,
      panel: "selection",
    };
    activeViewerId = "viewer-2";
    const registrationsBeforeReplacement = registrationRequests;
    window.dispatchEvent(new Event("online"));
    await waitFor(() => expect(screen.getByTestId("pending-sequence")).toHaveTextContent("1"), {
      timeout: 3_000,
    });
    expect(registrationRequests).toBeGreaterThan(registrationsBeforeReplacement);

    const resolve = resolveDelayedViewerRead;
    if (resolve === null) throw new Error("delayed viewer refresh was not registered");
    resolve(
      json({
        viewer_id: "viewer-1",
        connected: true,
        desired: sourceCommand,
        acknowledged: null,
        pending: true,
        last_observation: null,
      }),
    );

    await waitFor(() => expect(screen.getByTestId("pending-sequence")).toHaveTextContent("1"));
    expect(screen.getByTestId("pending-panel")).toHaveTextContent("selection");
  });

  it("reconciles a pending viewer command when the browser comes online without an SSE error", async () => {
    pendingCommand = sourceCommand;
    renderProbe(new QueryClient());

    await waitFor(() => expect(sources).toHaveLength(1));
    const registrationsBeforeOnline = registrationRequests;
    window.dispatchEvent(new Event("online"));

    await waitFor(() => expect(registrationRequests).toBeGreaterThan(registrationsBeforeOnline));
    expect(sources.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId("pending-sequence")).toHaveTextContent("8");
  });

  it("accepts a new viewer's sequence one after re-registration behind an old pending command", async () => {
    pendingCommand = sourceCommand;
    renderProbe(new QueryClient());

    await waitFor(() => expect(screen.getByTestId("pending-sequence")).toHaveTextContent("8"));
    pendingCommand = {
      ...sourceCommand,
      viewer_id: "viewer-2",
      command_seq: 1,
      panel: "selection",
    };
    reRegisterOnNextRequest = true;
    const source = sources[sources.length - 1];
    expect(source).toBeDefined();
    if (source === undefined || source.onerror === null)
      throw new Error("automation EventSource did not expose an error handler");
    source.onerror();

    await waitFor(
      () => {
        expect(screen.getByTestId("pending-panel")).toHaveTextContent("selection");
        expect(screen.getByTestId("pending-sequence")).toHaveTextContent("1");
      },
      { timeout: 3_000 },
    );
  });

  it("refreshes the viewer state and surfaces a generation conflict to the acknowledgement owner", async () => {
    pendingCommand = sourceCommand;
    conflictOnAcknowledgement = true;
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    renderProbe(new QueryClient());

    await waitFor(() =>
      expect(screen.getByTestId("pending-panel")).toHaveTextContent("source_alignment"),
    );
    await user.click(screen.getByRole("button", { name: "acknowledge" }));

    await waitFor(() => expect(screen.getByTestId("conflict-observed")).toHaveTextContent("true"));
    expect(screen.getByTestId("pending-panel")).toHaveTextContent("source_alignment");
    expect(
      fetchMock.mock.calls.some(([path]) => String(path).startsWith("/api/automation/view?")),
    ).toBe(true);
  });

  it("retains the observed source-alignment panel after its acknowledgement clears pending work", async () => {
    pendingCommand = sourceCommand;
    const user = userEvent.setup();
    renderProbe(new QueryClient());

    await waitFor(() =>
      expect(screen.getByTestId("pending-panel")).toHaveTextContent("source_alignment"),
    );
    await user.click(screen.getByRole("button", { name: "acknowledge" }));
    await waitFor(() => expect(screen.getByTestId("pending-panel")).toHaveTextContent("none"));
    expect(screen.getByTestId("displayed-panel")).toHaveTextContent("source_alignment");
  });

  it("ignores replayed revisions and invalidates current source alignment for a new page event", async () => {
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderProvider(client);

    await waitFor(() => expect(sources).toHaveLength(1));
    invalidate.mockClear();
    const scope = pageCacheScope("Poems00986", 0, "all");
    const epochBeforeOrdinaryChange = pageCacheEpoch("Poems00986");
    acceptPagePayload(scope, { generation: 7, imageUrl: "before-ordinary-change" });
    const source = sources[0];
    expect(source).toBeDefined();
    if (source === undefined) throw new Error("automation EventSource was not opened");

    source.emit("page_changed", {
      revision: 5,
      kind: "page_changed",
      project_id: "Poems00986",
      page_index: 0,
      generation: 4,
      job_id: null,
      viewer_id: null,
      command_seq: null,
    });
    expect(invalidate).not.toHaveBeenCalled();

    source.emit("page_changed", {
      revision: 6,
      kind: "page_changed",
      project_id: "Poems00986",
      page_index: 0,
      generation: 5,
      job_id: null,
      viewer_id: null,
      command_seq: null,
    });
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["page", "Poems00986", 0] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["source-alignment", "Poems00986", 0] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["source-text", "Poems00986", 0] });
    });
    expect(isCurrentPageCacheEpoch("Poems00986", epochBeforeOrdinaryChange)).toBe(true);
    expect(acceptPagePayload(scope, { generation: 5, imageUrl: "older-page-event" }).imageUrl).toBe(
      "before-ordinary-change",
    );
  });

  it("starts a new epoch when a completed external page reload marks its event", async () => {
    const client = new QueryClient();
    const cancel = vi.spyOn(client, "cancelQueries");
    renderProvider(client);

    await waitFor(() => expect(sources).toHaveLength(1));
    cancel.mockClear();
    const scope = pageCacheScope("Poems00986", 0, "all");
    const epochBeforeReload = pageCacheEpoch("Poems00986");
    acceptPagePayload(scope, { generation: 7, imageUrl: "before-external-reload" });
    const source = sources[0];
    if (source === undefined) throw new Error("automation EventSource was not opened");
    source.emit("page_changed", {
      revision: 6,
      kind: "page_changed",
      project_id: "Poems00986",
      page_index: 0,
      generation: 0,
      generation_reset: true,
      job_id: null,
      viewer_id: null,
      command_seq: null,
    });

    await waitFor(() => expect(cancel).toHaveBeenCalledWith({ queryKey: ["page", "Poems00986"] }));
    expect(isCurrentPageCacheEpoch("Poems00986", epochBeforeReload)).toBe(false);
    expect(
      acceptPagePayload(scope, { generation: 0, imageUrl: "after-external-reload" }).imageUrl,
    ).toBe("after-external-reload");
  });

  it("reconciles all domain caches from a newer reset snapshot", async () => {
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderProvider(client);

    await waitFor(() => expect(sources).toHaveLength(1));
    invalidate.mockClear();
    snapshotRevision = 6;
    const source = sources[0];
    expect(source).toBeDefined();
    if (source === undefined) throw new Error("automation EventSource was not opened");
    source.emit("reset", {
      revision: 6,
      kind: "reset",
      project_id: null,
      page_index: null,
      generation: null,
      job_id: null,
      viewer_id: null,
      command_seq: null,
    });

    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["jobs"] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["project"] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["page"] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["source-alignment"] });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["source-text"] });
    });
  });
});
