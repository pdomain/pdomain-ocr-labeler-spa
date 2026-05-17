// StatusPip.tsx — small status pill used in Worklist rows and WordDetail.
// P5.i Gap 57: added "ocr" and "gt" as distinct visual variants for
// OCR-confidence and GT-confidence display.
//
// Variants:
//   exact / fuzzy / mismatch — match quality (existing)
//   ocr                      — OCR confidence indicator (amber/warning tone)
//   gt                       — GT present indicator (accent/confirmed tone)
//
// "ocr" and "gt" share the same pill shape but use theme tokens --accent and
// --status-fuzzy (amber) to signal data-source rather than match quality.

export type StatusPipStatus = "exact" | "fuzzy" | "mismatch" | "ocr" | "gt";

export interface StatusPipProps {
  status: StatusPipStatus;
  label?: string | undefined;
}

const statusClasses: Record<StatusPipStatus, string> = {
  exact: "bg-status-exact/10 border-status-exact/33 text-status-exact",
  fuzzy: "bg-status-fuzzy/10 border-status-fuzzy/33 text-status-fuzzy",
  mismatch: "bg-status-mismatch/10 border-status-mismatch/33 text-status-mismatch",
  // Gap 57: ocr = amber/warning to signal "from OCR engine, unconfirmed"
  ocr: "bg-status-fuzzy/10 border-status-fuzzy/33 text-status-fuzzy",
  // Gap 57: gt = accent-toned to signal "ground-truth confirmed"
  gt: "bg-accent/10 border-accent/33 text-accent",
};

const dotClasses: Record<StatusPipStatus, string> = {
  exact: "bg-status-exact",
  fuzzy: "bg-status-fuzzy",
  mismatch: "bg-status-mismatch",
  ocr: "bg-status-fuzzy",
  gt: "bg-accent",
};

export function StatusPip({ status, label }: StatusPipProps) {
  return (
    <div
      data-testid={`status-pip-${status}`}
      className={`inline-flex items-center gap-1 h-[18px] px-2 rounded-[9px] border ${statusClasses[status]}`}
    >
      <div className={`w-[5px] h-[5px] rounded-full flex-shrink-0 ${dotClasses[status]}`} />
      {label && <span className="text-[10px] font-semibold">{label}</span>}
    </div>
  );
}
