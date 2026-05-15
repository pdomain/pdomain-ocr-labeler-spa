import * as React from "react";
import * as AccordionPrimitive from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

// Static class lookup for tag variants — no string interpolation for Tailwind
type AccordionTagVariant = "accent" | "mismatch";

const tagClasses: Record<AccordionTagVariant, string> = {
  accent: "border-l-2 border-accent bg-accent/5",
  mismatch: "border-l-2 border-status-mismatch bg-status-mismatch/5",
};

const defaultItemClasses = "border border-border-1 rounded-md";

type AccordionItemProps = React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Item> & {
  tag?: AccordionTagVariant;
};

const AccordionItem = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Item>,
  AccordionItemProps
>(({ className, tag, ...props }, ref) => (
  <AccordionPrimitive.Item
    ref={ref}
    className={cn(tag ? tagClasses[tag] : defaultItemClasses, className)}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

const AccordionTrigger = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Header className="flex">
    <AccordionPrimitive.Trigger
      ref={ref}
      className={cn(
        "flex flex-1 items-center justify-between py-4 px-4 font-medium",
        "text-body text-ink-1 transition-all",
        "hover:bg-raised",
        "[&[data-state=open]>svg]:rotate-180",
        className,
      )}
      {...props}
    >
      {children}
      <ChevronDown className="h-4 w-4 shrink-0 transition-transform duration-200" />
    </AccordionPrimitive.Trigger>
  </AccordionPrimitive.Header>
));
AccordionTrigger.displayName = AccordionPrimitive.Trigger.displayName;

const AccordionContent = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Content
    ref={ref}
    className={cn(
      "overflow-hidden bg-sunk text-body text-ink-1 transition-all",
      "data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down",
      className,
    )}
    {...props}
  >
    <div className="pb-4 pt-0 px-4">{children}</div>
  </AccordionPrimitive.Content>
));
AccordionContent.displayName = AccordionPrimitive.Content.displayName;

// Rename root to avoid conflict with compound namespace export below
const AccordionRoot = AccordionPrimitive.Root;

// Compound namespace export for convenient API
const Accordion = Object.assign(AccordionRoot, {
  Item: AccordionItem,
  Trigger: AccordionTrigger,
  Content: AccordionContent,
});

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };
export type { AccordionItemProps, AccordionTagVariant };
