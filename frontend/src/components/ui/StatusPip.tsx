export interface StatusPipProps {
  status: "exact" | "fuzzy" | "mismatch";
  label?: string;
}

const statusClasses: Record<StatusPipProps["status"], string> = {
  exact: "bg-status-exact/10 border-status-exact/33 text-status-exact",
  fuzzy: "bg-status-fuzzy/10 border-status-fuzzy/33 text-status-fuzzy",
  mismatch: "bg-status-mismatch/10 border-status-mismatch/33 text-status-mismatch",
};

export function StatusPip({ status, label }: StatusPipProps) {
  return (
    <div
      className={`inline-flex items-center gap-1 h-[18px] px-2 rounded-[9px] border ${statusClasses[status]}`}
    >
      <div className={`w-[5px] h-[5px] rounded-full flex-shrink-0 bg-status-${status}`} />
      {label && <span className="text-[10px] font-semibold">{label}</span>}
    </div>
  );
}
