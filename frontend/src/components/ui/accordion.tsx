// accordion.tsx — Labeler accordion, pdomain-ui 0.11.0 composition.
//
// Strategy:
//   AccordionItem   → pdomain-ui AccordionItem (adds .acc base class, tone prop)
//   AccordionTrigger → pdomain-ui AccordionTrigger (0.11.0 generic slots):
//                      · keycap  → endContent={<KeyCap keys={keycap} />}
//                      · hint    → <span className="acc-hint">{hint}</span> in children
//                      · chevron → pdui default (omitted → built-in .chev span "›")
//                      Pdui owns the Header (.acc-head) + trigger (.acc-trigger) wrappers.
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
  AccordionTrigger as PduiAccordionTrigger,
  AccordionContent as PduiAccordionContent,
  type AccordionTone,
} from "@pdomain/pdomain-ui/primitives";

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

// AccordionTrigger — labeler's richer trigger, composed via pdui's AccordionTrigger
// (pdomain-ui 0.11.0 generic slots).
//
// Slot mapping:
//   keycap → endContent={<KeyCap keys={keycap} />}
//   hint   → <span className="acc-hint">{hint}</span> appended to children
//   chevron → omitted (pdui default: .chev span with "›")
//
// Pdui owns the Header (.acc-head) and trigger button (.acc-trigger) wrappers.
// The labeler adds layout + typography via className prop.
type AccordionTriggerProps = React.ComponentPropsWithoutRef<typeof PduiAccordionTrigger> & {
  /** Short helper text shown between the label and the keycap. */
  hint?: string;
  /** Keyboard shortcut shown as a KeyCap chip at the right. */
  keycap?: string | string[];
};

const AccordionTrigger = React.forwardRef<
  React.ComponentRef<typeof PduiAccordionTrigger>,
  AccordionTriggerProps
>(({ className, children, hint, keycap, ...props }, ref) => (
  <PduiAccordionTrigger
    ref={ref}
    className={cn(
      "flex flex-1 items-center justify-between py-2.5 px-4",
      "text-[10.5px] font-bold tracking-[0.05em] uppercase text-ink-1 transition-all",
      "hover:bg-bg-raised",
      className,
    )}
    endContent={keycap ? <KeyCap keys={keycap} /> : undefined}
    {...props}
  >
    {/* Left: label + optional hint text (pdui .acc-hint = muted secondary text) */}
    <span className="flex items-baseline gap-2 min-w-0">
      <span className="shrink-0">{children}</span>
      {hint && <span className="acc-hint truncate">{hint}</span>}
    </span>
  </PduiAccordionTrigger>
));
AccordionTrigger.displayName = PduiAccordionTrigger.displayName;

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
