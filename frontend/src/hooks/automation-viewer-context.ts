import { createContext, useContext } from "react";

import type { ViewerAck, ViewerCommand } from "../api/automation";

export interface AutomationViewerContextValue {
  readonly command: ViewerCommand | null;
  readonly displayedCommand: ViewerCommand | null;
  reportObservation(acknowledgement: ViewerAck): Promise<void>;
}

const emptyContext: AutomationViewerContextValue = {
  command: null,
  displayedCommand: null,
  reportObservation: () => Promise.resolve(),
};

export const AutomationViewerContext = createContext<AutomationViewerContextValue>(emptyContext);

export function useAutomationViewer(): AutomationViewerContextValue {
  return useContext(AutomationViewerContext);
}
