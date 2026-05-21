import * as React from "react";
import { Slot } from "@radix-ui/react-slot";

import { cn } from "@/lib/utils";

// Base classes applied to every button regardless of variant/size.
const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-40";

// Variant → CSS classes (design-system tokens only; no Tailwind palette colors).
const VARIANT_CLASSES: Record<string, string> = {
  primary: "bg-accent text-accent-ink hover:opacity-90",
  secondary: "bg-raised border border-border-2 text-ink-1 hover:bg-sunk",
  outline: "bg-raised border border-border-2 text-ink-1 hover:bg-sunk",
  ghost: "bg-transparent text-ink-2 hover:bg-raised",
  danger:
    "bg-status-mismatch/10 border border-status-mismatch text-status-mismatch hover:bg-status-mismatch/20",
  destructive:
    "bg-status-mismatch/10 border border-status-mismatch text-status-mismatch hover:bg-status-mismatch/20",
};

// Size → CSS classes (layout utilities only).
const SIZE_CLASSES: Record<string, string> = {
  sm: "h-6 px-3 text-btn-sm",
  default: "h-[30px] px-3 text-body",
  lg: "h-[34px] px-4 text-body",
};

type ButtonVariant = keyof typeof VARIANT_CLASSES;
type ButtonSize = keyof typeof SIZE_CLASSES;

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "default", asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(BASE, VARIANT_CLASSES[variant], SIZE_CLASSES[size], className)}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button };
export type { ButtonVariant, ButtonSize };
