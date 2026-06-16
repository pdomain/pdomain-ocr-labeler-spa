import * as React from "react";
import * as AccordionPrimitive from "@radix-ui/react-accordion";
import { ChevronDown } from "@pdomain/pdomain-ui/icons";

import { cn } from "@/lib/utils";
import { KeyCap } from "@pdomain/pdomain-ui/primitives";

// Static class lookup for tag variants — no string interpolation for Tailwind
type AccordionTagVariant = "accent" | "mismatch";

const tagClasses: Record<AccordionTagVariant, string> = {
  accent: "border-l-2 border-accent bg-accent/5",
  mismatch: "border-l-2 border-status-mismatch bg-status-mismatch/5",
};

const defaultItemClasses = "border border-border-1 rounded-md";

// LabelerAccordionItem adds the labeler's `tag` variant. The root/item/trigger
// all use this package's Radix primitives so their Accordion context matches
// even when pdomain-ui is linked locally.
type AccordionItemProps = React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Item> & {
  tag?: AccordionTagVariant;
};

const AccordionItem = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Item>,
  AccordionItemProps
>(({ className, tag, ...props }, ref) => (
  <AccordionPrimitive.Item
    ref={ref}
    className={cn("acc", tag ? tagClasses[tag] : defaultItemClasses, className)}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

// AccordionTrigger: the labeler's trigger has a richer layout than pdomain-ui's
// AccordionTrigger (hint text, keycap chip, custom chevron, uppercase label).
// pdomain-ui's AccordionTrigger internally wraps with AccordionPrimitive.Header AND
// appends its own chevron span, making it incompatible with the labeler layout.
// We build on the Radix primitives directly here; @radix-ui/react-accordion
// remains an explicit dep for this reason.
//
// Extended trigger props: optional helper text + keycap hint.
// P2.g (Gap 32, 54): spec'd row is: UPPERCASE LABEL · hint text · keycap
type AccordionTriggerProps = React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Trigger> & {
  /** Short helper text shown between the label and the chevron (e.g. "crop, nudge"). */
  hint?: string;
  /** Keyboard shortcut shown as a KeyCap chip at the right (e.g. "B" or ["⌘","B"]). */
  keycap?: string | string[];
};

const AccordionTrigger = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Trigger>,
  AccordionTriggerProps
>(({ className, children, hint, keycap, ...props }, ref) => (
  <AccordionPrimitive.Header className="flex">
    <AccordionPrimitive.Trigger
      ref={ref}
      className={cn(
        "flex flex-1 items-center justify-between py-2.5 px-4",
        "text-[10.5px] font-bold tracking-[0.05em] uppercase text-ink-1 transition-all",
        "hover:bg-bg-raised",
        "[&[data-state=open]>svg]:rotate-180",
        className,
      )}
      {...props}
    >
      {/* Left: label (always uppercase via CSS) + optional hint text */}
      <span className="flex items-baseline gap-2 min-w-0">
        <span className="shrink-0">{children}</span>
        {hint && (
          <span className="text-[9px] font-normal normal-case tracking-normal text-ink-3 truncate">
            {hint}
          </span>
        )}
      </span>

      {/* Right: optional keycap + chevron */}
      <span className="flex items-center gap-2 shrink-0 ml-2">
        {keycap && <KeyCap keys={keycap} />}
        <ChevronDown className="h-4 w-4 shrink-0 transition-transform duration-200" />
      </span>
    </AccordionPrimitive.Trigger>
  </AccordionPrimitive.Header>
));
AccordionTrigger.displayName = AccordionPrimitive.Trigger.displayName;

// AccordionContent: built directly on Radix Content rather than pdomain-ui's wrapper
// because the labeler's bg-bg-sunk + animation classes are applied at this layer
// and pdomain-ui's AccordionContent adds its own 'acc-body' class that would conflict.
const AccordionContent = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Content
    ref={ref}
    className={cn(
      "overflow-hidden bg-bg-sunk text-body text-ink-1 transition-all",
      "data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down",
      className,
    )}
    {...props}
  >
    <div className="pb-4 pt-0 px-4">{children}</div>
  </AccordionPrimitive.Content>
));
AccordionContent.displayName = AccordionPrimitive.Content.displayName;

const Accordion = Object.assign(AccordionPrimitive.Root, {
  Item: AccordionItem,
  Trigger: AccordionTrigger,
  Content: AccordionContent,
});

export { Accordion };
