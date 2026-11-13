import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  acknowledgeViewer,
  AutomationApiError,
  fetchAutomationState,
  fetchViewerState,
  parseAutomationEvent,
  registerViewer,
  type AutomationEvent,
  type ViewerAck,
  type ViewerCommand,
  type ViewerState,
} from "../api/automation";
import { pageNoUrl } from "../lib/routes";
import { resetProjectPageCacheBoundary } from "../lib/page-cache-boundary";
import { resetPageCacheOrder } from "../lib/page-cache-order";
import { displayedViewerCommand } from "../lib/viewer-display";
import {
  AutomationViewerContext,
  type AutomationViewerContextValue,
} from "./automation-viewer-context";

const VIEWER_ID_STORAGE_KEY = "pdomain-ocr-labeler.viewer-id";

function readStoredViewerId(): string | null {
  try {
    const viewerId = sessionStorage.getItem(VIEWER_ID_STORAGE_KEY);
    return viewerId === null || viewerId === "" ? null : viewerId;
  } catch {
    return null;
  }
}

function storeViewerId(viewerId: string): void {
  try {
    sessionStorage.setItem(VIEWER_ID_STORAGE_KEY, viewerId);
  } catch {
    // Browser privacy settings can disable session storage; the registration remains valid in memory.
  }
}

function clearStoredViewerId(): void {
  try {
    sessionStorage.removeItem(VIEWER_ID_STORAGE_KEY);
  } catch {
    // Browser privacy settings can disable session storage.
  }
}

function observe(promise: Promise<void>): void {
  promise.catch((error: unknown) => {
    console.error("automation viewer synchronization failed", error);
  });
}

function stateCommand(state: ViewerState | undefined): ViewerCommand | null {
  if (!state?.pending) return null;
  return state.desired;
}

export function AutomationViewerProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [command, setCommand] = useState<ViewerCommand | null>(null);
  const [displayedCommand, setDisplayedCommand] = useState<ViewerCommand | null>(null);
  const viewerIdRef = useRef<string | null>(null);
  const commandRef = useRef<ViewerCommand | null>(null);

  const applyCommand = useCallback(
    (nextCommand: ViewerCommand | null): void => {
      if (nextCommand === null) return;
      const current = commandRef.current;
      if (
        current !== null &&
        current.viewer_id === nextCommand.viewer_id &&
        current.command_seq > nextCommand.command_seq
      )
        return;
      commandRef.current = nextCommand;
      setCommand(nextCommand);
      setDisplayedCommand((currentDisplayed) =>
        displayedViewerCommand(nextCommand, currentDisplayed),
      );
      observe(
        Promise.resolve(navigate(pageNoUrl(nextCommand.project_id, nextCommand.page_index + 1))),
      );
    },
    [navigate],
  );

  const applyViewerState = useCallback(
    (state: ViewerState): void => {
      const desired = stateCommand(state);
      if (desired !== null) {
        applyCommand(desired);
        return;
      }
      const current = commandRef.current;
      if (
        current !== null &&
        current.viewer_id === state.viewer_id &&
        state.acknowledged?.viewer_id === current.viewer_id &&
        state.acknowledged.command_seq === current.command_seq
      ) {
        commandRef.current = null;
        setCommand(null);
      }
    },
    [applyCommand],
  );

  const reportObservation = useCallback(
    async (acknowledgement: ViewerAck): Promise<void> => {
      try {
        const state = await acknowledgeViewer(acknowledgement);
        applyViewerState(state);
      } catch (error: unknown) {
        if (!(error instanceof AutomationApiError) || error.status !== 409) throw error;
        const viewerId = viewerIdRef.current;
        if (viewerId === null) throw error;
        applyViewerState(await fetchViewerState(viewerId));
        throw error;
      }
    },
    [applyViewerState],
  );

  useEffect(() => {
    const cancellation = new AbortController();
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let revision = 0;
    let reconnecting = false;

    const invalidatePage = (event: AutomationEvent): void => {
      if (event.project_id === null || event.page_index === null) return;
      const projectId = event.project_id;
      const pageIndex = event.page_index;
      if (event.generation_reset) {
        observe(
          (async () => {
            await resetProjectPageCacheBoundary(queryClient, projectId);
            await Promise.all([
              queryClient.invalidateQueries({
                queryKey: ["page", projectId, pageIndex],
              }),
              queryClient.invalidateQueries({
                queryKey: ["source-alignment", projectId, pageIndex],
              }),
              queryClient.invalidateQueries({
                queryKey: ["source-text", projectId, pageIndex],
              }),
            ]);
          })(),
        );
        return;
      }
      observe(
        queryClient.invalidateQueries({ queryKey: ["page", event.project_id, event.page_index] }),
      );
      observe(
        queryClient.invalidateQueries({
          queryKey: ["source-alignment", event.project_id, event.page_index],
        }),
      );
      observe(
        queryClient.invalidateQueries({
          queryKey: ["source-text", event.project_id, event.page_index],
        }),
      );
    };

    const invalidateDomainCaches = async (): Promise<void> => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: ["page"] }),
        queryClient.cancelQueries({ queryKey: ["source-text"] }),
      ]);
      resetPageCacheOrder();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["project"] }),
        queryClient.invalidateQueries({ queryKey: ["page"] }),
        queryClient.invalidateQueries({ queryKey: ["source-alignment"] }),
        queryClient.invalidateQueries({ queryKey: ["source-text"] }),
      ]);
    };

    const closeSource = (): void => {
      source?.close();
      source = null;
    };

    function scheduleReconnect(): void {
      if (cancellation.signal.aborted || reconnectTimer !== null) return;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        observe(synchronize());
      }, 1_000);
    }

    const connect = (): void => {
      if (cancellation.signal.aborted || viewerIdRef.current === null) return;
      closeSource();
      const viewerId = viewerIdRef.current;
      source = new EventSource(
        `/api/automation/events?after=${encodeURIComponent(String(revision))}&viewer_id=${encodeURIComponent(viewerId)}`,
      );
      const onEvent = (message: MessageEvent<string>): void => {
        let event: AutomationEvent;
        try {
          event = parseAutomationEvent(JSON.parse(message.data) as unknown);
        } catch (error: unknown) {
          console.error("ignoring malformed automation event", error);
          return;
        }
        if (event.revision <= revision) return;
        revision = Math.max(revision, event.revision);
        if (event.kind === "reset") {
          observe(synchronize());
          return;
        }
        if (event.kind === "job_changed") {
          observe(queryClient.invalidateQueries({ queryKey: ["jobs"] }));
        }
        if (event.kind === "page_changed") invalidatePage(event);
        if (event.kind === "project_changed") {
          observe(
            (async () => {
              if (event.project_id !== null) {
                await resetProjectPageCacheBoundary(queryClient, event.project_id);
                await queryClient.cancelQueries({ queryKey: ["source-text", event.project_id] });
                await Promise.all([
                  queryClient.invalidateQueries({ queryKey: ["page", event.project_id] }),
                  queryClient.invalidateQueries({ queryKey: ["source-text", event.project_id] }),
                ]);
              }
              await queryClient.invalidateQueries({ queryKey: ["project"] });
            })(),
          );
        }
        if (event.kind === "viewer_command" && event.viewer_id === viewerId) {
          observe(refreshViewerCommand(viewerId));
        }
      };
      for (const kind of [
        "project_changed",
        "page_changed",
        "job_changed",
        "viewer_command",
        "viewer_ack",
        "reset",
      ] as const) {
        source.addEventListener(kind, onEvent);
      }
      source.onerror = () => {
        closeSource();
        scheduleReconnect();
      };
    };

    const isCancelled = () => cancellation.signal.aborted;

    const refreshViewerCommand = async (viewerId: string): Promise<void> => {
      if (isCancelled()) return;
      const state = await fetchViewerState(viewerId);
      if (isCancelled() || viewerIdRef.current !== viewerId || state.viewer_id !== viewerId) {
        return;
      }
      applyViewerState(state);
    };

    const synchronize = async (): Promise<void> => {
      if (isCancelled() || reconnecting) return;
      reconnecting = true;
      try {
        let state: ViewerState;
        try {
          state = await registerViewer(viewerIdRef.current ?? readStoredViewerId());
        } catch (error: unknown) {
          if (!(error instanceof AutomationApiError) || error.status !== 404) throw error;
          clearStoredViewerId();
          state = await registerViewer(null);
        }
        if (isCancelled()) return;
        if (viewerIdRef.current !== null && viewerIdRef.current !== state.viewer_id) {
          commandRef.current = null;
          setCommand(null);
          setDisplayedCommand(null);
        }
        viewerIdRef.current = state.viewer_id;
        storeViewerId(state.viewer_id);
        applyViewerState(state);

        const snapshot = await fetchAutomationState();
        if (isCancelled()) return;
        revision = snapshot.revision;
        await invalidateDomainCaches();
        if (isCancelled()) return;
        applyViewerState(
          snapshot.viewers.find((viewer) => viewer.viewer_id === state.viewer_id) ?? state,
        );
        connect();
      } catch (error: unknown) {
        if (!isCancelled()) {
          console.error("automation viewer synchronization failed", error);
          scheduleReconnect();
        }
      } finally {
        reconnecting = false;
      }
    };

    const onBrowserOnline = (): void => {
      observe(synchronize());
    };

    window.addEventListener("online", onBrowserOnline);
    observe(synchronize());
    return () => {
      cancellation.abort();
      window.removeEventListener("online", onBrowserOnline);
      closeSource();
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
    };
  }, [applyViewerState, queryClient]);

  const value = useMemo<AutomationViewerContextValue>(
    () => ({ command, displayedCommand, reportObservation }),
    [command, displayedCommand, reportObservation],
  );

  return (
    <AutomationViewerContext.Provider value={value}>{children}</AutomationViewerContext.Provider>
  );
}
