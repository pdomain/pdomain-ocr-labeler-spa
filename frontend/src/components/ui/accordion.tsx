// accordion.tsx — Labeler accordion, pdomain-ui composition (Slice 6).
//
// Strategy:
//   AccordionItem   → pdomain-ui AccordionItem (adds .acc base class, tone prop)
//   AccordionTrigger → local thin wrapper on raw Radix (NOT pdui AccordionTrigger).
//                      Reason: pdui AccordionTrigger hard-codes its own chevron
//                      (<span className="chev">›</span>) inside the trigger AND
//                      wraps with AccordionPrimitive.Header. Using it would produce
//                      a double chevron and conflict with the labeler's richer
//                      layout (hint text + KeyCap chip + custom ChevronDown icon).
//                      The trigger manually adds .acc-head / .acc-trigger CSS classes
//                      so primitives.css focus/hover rules still apply.
//   AccordionContent → pdomain-ui AccordionContent (adds .acc-body, primitives.css
//                      open/close animation). Labeler adds bg-bg-sunk + inner px-4 pb-4.
//
// tag → tone mapping (labeler API → pdui API):
//   tag="accent"   → tone="accent"  (.acc.accent  in primitives.css)
//   tag="mismatch" → tone="danger"  (.acc.danger  uses --mismatch color in primitives.css)
//
// Re-export Accordion root from pdui for context compatibility.

import * as React from "react";
import * as AccordionPrimitive from "@radix-ui/react-accordion";
import {
  AccordionItem as PduiAccordionItem,
  AccordionContent as PduiAccordionContent,
  type AccordionTone,
} from "@pdomain/pdomain-ui/primitives";
import { ChevronDown } from "@pdomain/pdomain-ui/icons";

import { cn } from "@/lib/utils";
import { KeyCap } from "@pdomain/pdomain-ui/primitives";

// Labeler-facing tag prop; "mismatch" maps to pdui's "danger" tone.
type AccordionTagVariant = "accent" | "mismatch";

const tagToTone: Record<AccordionTagVariant, AccordionTone> = {
  accent: "accent",
  mismatch: "danger",
};

// LabelerAccordionItem wraps pdui's AccordionItem, translating the labeler's
// `tag` prop to pdui's `tone` prop.  All other props (value, className, etc.)
// pass through.
type AccordionItemProps = React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Item> & {
  tag?: AccordionTagVariant;
};

const AccordionItem = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Item>,
  AccordionItemProps
>(({ className, tag, ...props }, ref) => (
  <PduiAccordionItem
    ref={ref}
    tone={tag ? tagToTone[tag] : "default"}
    className={className}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

// AccordionTrigger — labeler's richer trigger, built on raw Radix.
// Adds primitives.css .acc-head / .acc-trigger classes for base styling.
// Extended props: hint text + keycap chip.
type AccordionTriggerProps = React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Trigger> & {
  /** Short helper text shown between the label and the chevron. */
  hint?: string;
  /** Keyboard shortcut shown as a KeyCap chip at the right. */
  keycap?: string | string[];
};

const AccordionTrigger = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Trigger>,
  AccordionTriggerProps
>(({ className, children, hint, keycap, ...props }, ref) => (
  <AccordionPrimitive.Header className="acc-head flex">
    <AccordionPrimitive.Trigger
      ref={ref}
      className={cn(
        "acc-trigger",
        "flex flex-1 items-center justify-between py-2.5 px-4",
        "text-[10.5px] font-bold tracking-[0.05em] uppercase text-ink-1 transition-all",
        "hover:bg-bg-raised",
        "[&[data-state=open]>svg]:rotate-180",
        className,
      )}
      {...props}
    >
      {/* Left: label + optional hint text */}
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

// AccordionContent — pdomain-ui's content adds .acc-body (primitives.css animation).
// Labeler adds bg-bg-sunk for the sunken background and inner padding.
const AccordionContent = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <PduiAccordionContent
    ref={ref}
    className={cn("bg-bg-sunk text-body text-ink-1", className)}
    {...props}
  >
    <div className="pb-4 pt-0 px-4">{children}</div>
  </PduiAccordionContent>
));
AccordionContent.displayName = AccordionPrimitive.Content.displayName;

const Accordion = Object.assign(AccordionPrimitive.Root, {
  Item: AccordionItem,
  Trigger: AccordionTrigger,
  Content: AccordionContent,
});

export { Accordion };
