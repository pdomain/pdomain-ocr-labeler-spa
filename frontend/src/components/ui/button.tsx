import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-ink hover:opacity-90",
        secondary: "bg-raised border border-border-2 text-ink-1 hover:bg-sunk",
        outline: "bg-raised border border-border-2 text-ink-1 hover:bg-sunk",
        ghost: "bg-transparent text-ink-2 hover:bg-raised",
        danger:
          "bg-status-mismatch/10 border border-status-mismatch text-status-mismatch hover:bg-status-mismatch/20",
        destructive:
          "bg-status-mismatch/10 border border-status-mismatch text-status-mismatch hover:bg-status-mismatch/20",
      },
      size: {
        sm: "h-6 px-3 text-btn-sm",
        default: "h-[30px] px-3 text-body",
        lg: "h-[34px] px-4 text-body",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { Button };
