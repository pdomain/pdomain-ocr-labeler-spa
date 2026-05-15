import * as React from "react";

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  size?: "sm" | "md";
}

const sizeClasses: Record<NonNullable<InputProps["size"]>, string> = {
  sm: "h-[26px] px-2 text-[11px]",
  md: "h-[30px] px-2.5 text-body",
};

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { size = "md", className, ...props },
  ref,
) {
  const baseClasses =
    "block w-full bg-sunk border border-border-2 rounded-[5px] text-ink-1 placeholder:text-ink-3 font-mono transition-colors focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 disabled:opacity-40 disabled:cursor-not-allowed";

  const finalClassName = [baseClasses, sizeClasses[size], className].filter(Boolean).join(" ");

  return <input ref={ref} className={finalClassName} {...props} />;
});

Input.displayName = "Input";
