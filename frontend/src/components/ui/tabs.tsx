import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { Tabs as PdTabs } from "@concavetrillion/pd-ui/primitives";

import { cn } from "@/lib/utils";

// Tabs root: pd-ui re-exports TabsPrimitive.Root unchanged.
// Using pd-ui's wrapper to track the shared primitive layer.
const Tabs = PdTabs;

// TabsList: kept as a labeler-specific wrapper on raw Radix.
// pd-ui's TabsList adds the semantic CSS class 'tabs' (from pd-ui's
// primitives.css), which styles active state via a CSS `.tab.active`
// selector — not compatible with Radix's `data-[state=active]` attribute
// that our Tailwind utilities rely on. The labeler's border-b / Tailwind
// approach is structurally different, so we own this wrapper.
const TabsList = React.forwardRef<
  React.ComponentRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn("flex gap-0 border-b border-border-1 bg-transparent p-0", className)}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

// TabsTrigger: kept as a labeler-specific wrapper on raw Radix.
// pd-ui's TabsTrigger adds CSS class 'tab' whose active styling uses
// `.tab.active` (a CSS class selector, not a data-attribute). Radix sets
// `data-[state=active]` on the trigger, so pd-ui's `.tab.active` rule
// would never fire. The labeler's `-mb-px` border-b-2 overlap approach
// is also visually distinct from pd-ui's `::after` pseudo-element underline.
// Keeping on Radix preserves the labeler's accent-underline appearance.
const TabsTrigger = React.forwardRef<
  React.ComponentRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "relative px-3 py-1.5 text-body text-ink-3 border-b-2 border-transparent -mb-px transition-colors duration-100 hover:text-ink-2 data-[state=active]:text-ink-1 data-[state=active]:border-b-2 data-[state=active]:border-accent disabled:pointer-events-none disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

// TabsContent: kept as a labeler-specific wrapper on raw Radix.
// pd-ui's TabsContent adds CSS class 'tabs-content' with no Tailwind;
// the labeler needs mt-2 + focus-visible scoping via Tailwind utilities.
const TabsContent = React.forwardRef<
  React.ComponentRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn("mt-2 focus-visible:outline-none", className)}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
