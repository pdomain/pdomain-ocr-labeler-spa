export interface KeyCapProps {
  keys: string | string[];
}

export function KeyCap({ keys }: KeyCapProps) {
  const keyArray = Array.isArray(keys) ? keys : [keys];

  return (
    <div className="inline-flex items-center gap-1">
      {keyArray.map((key, index) => (
        <div key={`${key}-${index}`}>
          <div className="inline-flex items-center justify-center min-w-[18px] h-[17px] px-1.5 rounded-[3px] bg-sunk border border-border-3 shadow-[0_1px_0_0_var(--border-3)] text-ink-2 font-mono text-[9.5px] font-medium select-none">
            {key}
          </div>
          {index < keyArray.length - 1 && (
            <span className="inline-block mx-1 text-ink-3 text-[10px] font-medium">+</span>
          )}
        </div>
      ))}
    </div>
  );
}
