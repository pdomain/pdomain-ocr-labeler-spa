# Upstream First Pdomain UI Component Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the missing `pdomain-ui` component contracts first, then migrate every labeler SPA local UI wrapper onto shared `pdomain-ui` pieces.

**Architecture:** Phase 1 changes `/workspaces/ocr-container/pdomain-ui` so the shared library can cover the labeler contracts for Button, tri-state chips, Tabs, and Accordion. Phase 2 changes `/workspaces/ocr-container/pdomain-ocr-labeler-spa` so existing local import paths become thin adapters over the upgraded shared components. This keeps the labeler stable while moving real component ownership upstream.

**Tech Stack:** React 19 consumers, React 18/19-compatible `@pdomain/pdomain-ui`, TypeScript, Vite, Vitest, React Testing Library, Radix Slot/Tabs/Accordion, shared `theme/primitives.css`, `pnpm`.

---

## Execution Order

Run Tasks 1-5 in `pdomain-ui` first. Tasks 1-4 can run in parallel because their write sets are separate; Task 5 integrates and builds the package. After Task 5 passes, run Tasks 6-11 in `pdomain-ocr-labeler-spa`.

| Phase | Task                                           | Repo                      | Worker ownership                                        |
| ----- | ---------------------------------------------- | ------------------------- | ------------------------------------------------------- |
| 1A    | Task 1: Expand shared Button                   | `pdomain-ui`              | `src/primitives/Button.*`, package dependency           |
| 1B    | Task 2: Add shared TriStateChip                | `pdomain-ui`              | `src/primitives/TriStateChip.*`, primitive exports, CSS |
| 1C    | Task 3: Add underline Tabs contract            | `pdomain-ui`              | `src/primitives/Tabs.*`, CSS                            |
| 1D    | Task 4: Add rich Accordion contract            | `pdomain-ui`              | `src/primitives/Accordion.*`, CSS                       |
| 1E    | Task 5: Build and package shared UI            | `pdomain-ui`              | package-level verification                              |
| 2A    | Task 6: Import shared primitive CSS in labeler | `pdomain-ocr-labeler-spa` | `frontend/src/styles/*`                                 |
| 2B    | Task 7: Migrate simple labeler wrappers        | `pdomain-ocr-labeler-spa` | `Input`, `KeyCap`, `StatusPip` wrappers                 |
| 2C    | Task 8: Migrate Button and Chip wrappers       | `pdomain-ocr-labeler-spa` | `button`, `Chip` wrappers                               |
| 2D    | Task 9: Migrate Tabs and Accordion wrappers    | `pdomain-ocr-labeler-spa` | `tabs`, `accordion` wrappers                            |
| 2E    | Task 10: Consumer verification                 | `pdomain-ocr-labeler-spa` | representative tests                                    |
| 2F    | Task 11: Document migration matrix             | `pdomain-ocr-labeler-spa` | docs                                                    |

## File Structure

- `/workspaces/ocr-container/pdomain-ui/src/primitives/Button.tsx`: shared Button supports the labeler API surface: `secondary`, `outline`, `destructive`, `default`, and `asChild`.
- `/workspaces/ocr-container/pdomain-ui/src/primitives/TriStateChip.tsx`: shared button-like tri-state chip for off/on/mixed style and component palettes.
- `/workspaces/ocr-container/pdomain-ui/src/primitives/Tabs.tsx`: shared Radix Tabs wrapper gains `appearance="underline"` for labeler detail panels.
- `/workspaces/ocr-container/pdomain-ui/src/primitives/Accordion.tsx`: shared Radix Accordion wrapper gains tone/tag, hint, keycap, and content inner-slot support.
- `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`: canonical shared CSS gains the classes needed by those contracts.
- `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/*`: labeler compatibility wrappers delegate to `@pdomain/pdomain-ui/primitives`.
- `/workspaces/ocr-container/pdomain-ocr-labeler-spa/docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md`: records final ownership decisions.

## Shared Constraints

- Do not bulk-rewrite labeler feature components first. Keep existing imports such as `../ui/accordion` stable until wrapper tests pass.
- Import primitives from `@pdomain/pdomain-ui/primitives`, not the root barrel.
- Preserve existing labeler test IDs and public wrapper names.
- `pdomain-ui` must remain compatible with existing consumers. New props must be optional and default to current behavior.
- `pdomain-ui` package verification must pass before any labeler wrapper migration starts.

---

### Task 1: Expand Shared Button

**Files:**

- Modify: `/workspaces/ocr-container/pdomain-ui/package.json`
- Modify: `/workspaces/ocr-container/pdomain-ui/src/primitives/Button.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ui/src/primitives/Button.test.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`

- [ ] **Step 1: Add a failing Button contract test**

Replace `/workspaces/ocr-container/pdomain-ui/src/primitives/Button.test.tsx` with:

```tsx
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Button } from "./Button.js";

describe("Button", () => {
  it("renders primary by default", () => {
    render(<Button>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button.classList.contains("btn")).toBe(true);
    expect(button.classList.contains("primary")).toBe(true);
  });

  it.each(["secondary", "outline", "ghost", "danger", "destructive"] as const)(
    "renders %s variant class",
    (variant) => {
      render(<Button variant={variant}>{variant}</Button>);
      const button = screen.getByRole("button", { name: variant });
      expect(button.classList.contains("btn")).toBe(true);
      expect(button.classList.contains(variant)).toBe(true);
    },
  );

  it.each(["sm", "md", "default", "lg"] as const)("renders %s size", (size) => {
    render(<Button size={size}>{size}</Button>);
    const button = screen.getByRole("button", { name: size });
    expect(button.classList.contains("btn")).toBe(true);
    if (size === "md" || size === "default") {
      expect(button.classList.contains("sm")).toBe(false);
      expect(button.classList.contains("lg")).toBe(false);
    } else {
      expect(button.classList.contains(size)).toBe(true);
    }
  });

  it("supports asChild for link-style buttons", () => {
    render(
      <Button asChild variant="ghost" size="sm">
        <a href="/projects">Projects</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Projects" });
    expect(link.classList.contains("btn")).toBe(true);
    expect(link.classList.contains("ghost")).toBe(true);
    expect(link.classList.contains("sm")).toBe(true);
  });

  it("fires click handlers and respects disabled state", () => {
    const enabled = vi.fn();
    const disabled = vi.fn();
    render(
      <>
        <Button onClick={enabled}>Enabled</Button>
        <Button disabled onClick={disabled}>
          Disabled
        </Button>
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enabled" }));
    fireEvent.click(screen.getByRole("button", { name: "Disabled" }));
    expect(enabled).toHaveBeenCalledOnce();
    expect(disabled).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/Button.test.tsx
```

Expected: FAIL because `secondary`, `outline`, `destructive`, `default`, and `asChild` are not supported yet.

- [ ] **Step 3: Add Radix Slot dependency**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm add @radix-ui/react-slot@^1.2.0
```

Expected: `package.json` and `pnpm-lock.yaml` update with `@radix-ui/react-slot`.

- [ ] **Step 4: Replace the Button implementation**

Replace `/workspaces/ocr-container/pdomain-ui/src/primitives/Button.tsx` with:

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "./cn.js";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "danger"
  | "destructive";
export type ButtonSize = "sm" | "md" | "default" | "lg";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  full?: boolean;
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      variant = "primary",
      size = "md",
      icon,
      iconRight,
      full,
      asChild = false,
      children,
      ...props
    },
    ref,
  ) {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(
          "btn",
          variant,
          size === "md" || size === "default" ? undefined : size,
          full === true ? "full" : undefined,
          className,
        )}
        {...props}
      >
        {icon != null ? (
          <span className="btn-icon btn-icon--left" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        {children}
        {iconRight != null ? (
          <span className="btn-icon btn-icon--right" aria-hidden="true">
            {iconRight}
          </span>
        ) : null}
      </Comp>
    );
  },
);

Button.displayName = "Button";
```

- [ ] **Step 5: Add shared Button CSS variants**

Append these rules near the existing `.btn` variant rules in `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`:

```css
.btn.secondary,
.btn.outline {
  background: var(--bg-raised);
  border-color: var(--border-2);
  color: var(--ink-1);
}

.btn.secondary:hover,
.btn.outline:hover {
  background: var(--bg-sunk);
}

.btn.destructive {
  color: var(--mismatch);
  background: color-mix(in srgb, var(--mismatch) 7%, transparent);
  border-color: color-mix(in srgb, var(--mismatch) 27%, transparent);
}

.btn.destructive:hover {
  background: color-mix(in srgb, var(--mismatch) 14%, transparent);
}
```

- [ ] **Step 6: Verify Button**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/Button.test.tsx
pnpm run typecheck
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ui
git add package.json pnpm-lock.yaml src/primitives/Button.tsx src/primitives/Button.test.tsx theme/primitives.css
git commit -m "feat: expand shared button contract"
```

---

### Task 2: Add Shared TriStateChip

**Files:**

- Create: `/workspaces/ocr-container/pdomain-ui/src/primitives/TriStateChip.tsx`
- Create: `/workspaces/ocr-container/pdomain-ui/src/primitives/TriStateChip.test.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ui/src/primitives/index.ts`
- Modify: `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`

- [ ] **Step 1: Add the failing TriStateChip test**

Create `/workspaces/ocr-container/pdomain-ui/src/primitives/TriStateChip.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TriStateChip } from "./TriStateChip.js";

describe("TriStateChip", () => {
  it.each([
    ["off", "false"],
    ["on", "true"],
    ["mixed", "mixed"],
  ] as const)("renders %s with aria-pressed=%s", (value, ariaPressed) => {
    render(
      <TriStateChip value={value} onChange={() => {}}>
        Style
      </TriStateChip>,
    );
    expect(screen.getByRole("button")).toHaveAttribute(
      "aria-pressed",
      ariaPressed,
    );
  });

  it.each([
    ["off", "on"],
    ["on", "mixed"],
    ["mixed", "off"],
  ] as const)("cycles from %s to %s", (value, next) => {
    const onChange = vi.fn();
    render(
      <TriStateChip value={value} onChange={onChange}>
        Style
      </TriStateChip>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith(next);
  });

  it("cycles on Enter and Space", () => {
    const onChange = vi.fn();
    render(
      <TriStateChip value="off" onChange={onChange}>
        Style
      </TriStateChip>,
    );
    fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });
    fireEvent.keyDown(screen.getByRole("button"), { key: " " });
    expect(onChange).toHaveBeenNthCalledWith(1, "on");
    expect(onChange).toHaveBeenNthCalledWith(2, "on");
  });

  it("forwards data-testid and className", () => {
    render(
      <TriStateChip
        value="mixed"
        onChange={() => {}}
        data-testid="chip"
        className="extra"
      >
        Style
      </TriStateChip>,
    );
    const chip = screen.getByTestId("chip");
    expect(chip.classList.contains("chip3")).toBe(true);
    expect(chip.classList.contains("some")).toBe(true);
    expect(chip.classList.contains("extra")).toBe(true);
  });
});
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/TriStateChip.test.tsx
```

Expected: FAIL because `TriStateChip.tsx` does not exist.

- [ ] **Step 3: Add TriStateChip**

Create `/workspaces/ocr-container/pdomain-ui/src/primitives/TriStateChip.tsx`:

```tsx
import * as React from "react";
import { cn } from "./cn.js";

export type TriStateValue = "off" | "on" | "mixed";

export interface TriStateChipProps extends Omit<
  React.HTMLAttributes<HTMLDivElement>,
  "onChange"
> {
  value?: TriStateValue;
  onChange?: (next: TriStateValue) => void;
}

const cycle: Record<TriStateValue, TriStateValue> = {
  off: "on",
  on: "mixed",
  mixed: "off",
};

const stateClass: Record<TriStateValue, string | undefined> = {
  off: undefined,
  on: "all",
  mixed: "some",
};

export const TriStateChip = React.forwardRef<HTMLDivElement, TriStateChipProps>(
  function TriStateChip(
    { value = "off", onChange, className, children, ...props },
    ref,
  ) {
    const handleClick = () => {
      onChange?.(cycle[value]);
    };
    const ariaPressed: true | false | "mixed" =
      value === "on" ? true : value === "mixed" ? "mixed" : false;

    return (
      <div
        ref={ref}
        role="button"
        tabIndex={0}
        aria-pressed={ariaPressed}
        data-tristate
        data-tristate-value={value}
        className={cn("chip3", stateClass[value], className)}
        onClick={handleClick}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            handleClick();
          }
        }}
        {...props}
      >
        <span aria-hidden="true" className="tri-dot" />
        {children}
      </div>
    );
  },
);

TriStateChip.displayName = "TriStateChip";
```

- [ ] **Step 4: Export TriStateChip**

Add to `/workspaces/ocr-container/pdomain-ui/src/primitives/index.ts` near `Chip`:

```ts
export { TriStateChip } from "./TriStateChip.js";
export type { TriStateChipProps, TriStateValue } from "./TriStateChip.js";
```

- [ ] **Step 5: Verify CSS exists**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
rg -n "\.chip3|\.tri-dot|\.chip3\.some|\.chip3\.all" theme/primitives.css
```

Expected: output shows `.chip3`, `.chip3 .tri-dot`, `.chip3.some .tri-dot`, and `.chip3.all`. If any rule is missing, copy the existing labeler `.chip3` rules from `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/styles/primitives.css` into `theme/primitives.css`.

- [ ] **Step 6: Verify TriStateChip**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/TriStateChip.test.tsx src/primitives/Chip.test.tsx
pnpm run typecheck
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ui
git add src/primitives/TriStateChip.tsx src/primitives/TriStateChip.test.tsx src/primitives/index.ts theme/primitives.css
git commit -m "feat: add shared tri-state chip"
```

---

### Task 3: Add Underline Tabs Contract

**Files:**

- Modify: `/workspaces/ocr-container/pdomain-ui/src/primitives/Tabs.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ui/src/primitives/Tabs.test.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`

- [ ] **Step 1: Add failing underline Tabs tests**

Append to `/workspaces/ocr-container/pdomain-ui/src/primitives/Tabs.test.tsx`:

```tsx
it("supports underline appearance for labeler detail panels", () => {
  render(
    <Tabs defaultValue="line">
      <TabsList appearance="underline">
        <TabsTrigger appearance="underline" value="line">
          Line
        </TabsTrigger>
        <TabsTrigger appearance="underline" value="words">
          Words
        </TabsTrigger>
      </TabsList>
      <TabsContent value="line">Line content</TabsContent>
      <TabsContent value="words">Words content</TabsContent>
    </Tabs>,
  );
  expect(
    screen.getByRole("tablist").classList.contains("tabs--underline"),
  ).toBe(true);
  expect(
    screen
      .getByRole("tab", { name: "Line" })
      .classList.contains("tab--underline"),
  ).toBe(true);
});
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/Tabs.test.tsx
```

Expected: FAIL because `appearance` is not a supported prop.

- [ ] **Step 3: Replace Tabs with appearance-aware wrappers**

Replace `/workspaces/ocr-container/pdomain-ui/src/primitives/Tabs.tsx` with:

```tsx
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "./cn.js";

export type TabsAppearance = "default" | "underline";

const Tabs = TabsPrimitive.Root;

type TabsListProps = React.ComponentPropsWithoutRef<
  typeof TabsPrimitive.List
> & {
  appearance?: TabsAppearance;
};

const TabsList = React.forwardRef<
  React.ComponentRef<typeof TabsPrimitive.List>,
  TabsListProps
>(({ className, appearance = "default", ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "tabs",
      appearance === "underline" ? "tabs--underline" : undefined,
      className,
    )}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

type TabsTriggerProps = React.ComponentPropsWithoutRef<
  typeof TabsPrimitive.Trigger
> & {
  appearance?: TabsAppearance;
};

const TabsTrigger = React.forwardRef<
  React.ComponentRef<typeof TabsPrimitive.Trigger>,
  TabsTriggerProps
>(({ className, appearance = "default", ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "tab",
      appearance === "underline" ? "tab--underline" : undefined,
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ComponentRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn("tabs-content", className)}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
```

- [ ] **Step 4: Add underline CSS**

Append near the Tabs rules in `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`:

```css
.tabs.tabs--underline {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border-1);
  background: transparent;
  padding: 0;
}

.tab.tab--underline {
  position: relative;
  padding: 6px 12px;
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
  color: var(--ink-3);
}

.tab.tab--underline:hover {
  color: var(--ink-2);
}

.tab.tab--underline[data-state="active"] {
  color: var(--ink-1);
  border-bottom-color: var(--accent);
}
```

- [ ] **Step 5: Verify Tabs**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/Tabs.test.tsx
pnpm run typecheck
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ui
git add src/primitives/Tabs.tsx src/primitives/Tabs.test.tsx theme/primitives.css
git commit -m "feat: add underline tabs appearance"
```

---

### Task 4: Add Rich Accordion Contract

**Files:**

- Modify: `/workspaces/ocr-container/pdomain-ui/src/primitives/Accordion.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ui/src/primitives/Accordion.test.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`

- [ ] **Step 1: Add failing rich Accordion tests**

Append to `/workspaces/ocr-container/pdomain-ui/src/primitives/Accordion.test.tsx`:

```tsx
it("supports labeler item tones, hint text, and keycap trigger slots", async () => {
  const user = userEvent.setup();
  render(
    <Accordion type="single" collapsible>
      <AccordionItem value="bbox" tag="accent">
        <AccordionTrigger hint="coords · nudge" keycap="B">
          Bbox
        </AccordionTrigger>
        <AccordionContent innerClassName="content-inner">
          Content
        </AccordionContent>
      </AccordionItem>
    </Accordion>,
  );

  const item = document.querySelector(".acc");
  expect(item?.classList.contains("accent")).toBe(true);
  expect(screen.getByText("coords · nudge")).toBeTruthy();
  expect(screen.getByText("B")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: /bbox/i }));
  expect(screen.getByText("Content")).toBeTruthy();
  expect(document.querySelector(".content-inner")).toBeTruthy();
});
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/Accordion.test.tsx
```

Expected: FAIL because `tag`, `hint`, `keycap`, and `innerClassName` are not supported yet.

- [ ] **Step 3: Replace Accordion with rich slot support**

Replace `/workspaces/ocr-container/pdomain-ui/src/primitives/Accordion.tsx` with:

```tsx
import * as React from "react";
import * as AccordionPrimitive from "@radix-ui/react-accordion";
import { KeyCap, type KeyCapProps } from "./KeyCap.js";
import { cn } from "./cn.js";

const Accordion = AccordionPrimitive.Root;

export type AccordionTone = "default" | "accent" | "mismatch" | "danger";

type AccordionItemProps = React.ComponentPropsWithoutRef<
  typeof AccordionPrimitive.Item
> & {
  tone?: AccordionTone;
  tag?: Exclude<AccordionTone, "default">;
};

const AccordionItem = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Item>,
  AccordionItemProps
>(({ className, tone = "default", tag, ...props }, ref) => {
  const resolvedTone = tag ?? tone;
  return (
    <AccordionPrimitive.Item
      ref={ref}
      className={cn(
        "acc",
        resolvedTone === "default" ? undefined : resolvedTone,
        className,
      )}
      {...props}
    />
  );
});
AccordionItem.displayName = AccordionPrimitive.Item.displayName;

type AccordionTriggerProps = React.ComponentPropsWithoutRef<
  typeof AccordionPrimitive.Trigger
> & {
  hint?: string;
  keycap?: KeyCapProps["keys"];
  chevron?: React.ReactNode;
};

const AccordionTrigger = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Trigger>,
  AccordionTriggerProps
>(({ className, children, hint, keycap, chevron, ...props }, ref) => (
  <AccordionPrimitive.Header className="acc-head">
    <AccordionPrimitive.Trigger
      ref={ref}
      className={cn("acc-trigger", className)}
      {...props}
    >
      <span className="acc-trigger__main">
        <span className="acc-trigger__label">{children}</span>
        {hint !== undefined ? (
          <span className="acc-trigger__hint">{hint}</span>
        ) : null}
      </span>
      <span className="acc-trigger__meta">
        {keycap !== undefined ? <KeyCap keys={keycap} /> : null}
        <span className="chev" aria-hidden="true">
          {chevron ?? "›"}
        </span>
      </span>
    </AccordionPrimitive.Trigger>
  </AccordionPrimitive.Header>
));
AccordionTrigger.displayName = AccordionPrimitive.Trigger.displayName;

type AccordionContentProps = React.ComponentPropsWithoutRef<
  typeof AccordionPrimitive.Content
> & {
  innerClassName?: string;
};

const AccordionContent = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Content>,
  AccordionContentProps
>(({ className, innerClassName, children, ...props }, ref) => (
  <AccordionPrimitive.Content
    ref={ref}
    className={cn("acc-body", className)}
    {...props}
  >
    <div className={cn("acc-body__inner", innerClassName)}>{children}</div>
  </AccordionPrimitive.Content>
));
AccordionContent.displayName = AccordionPrimitive.Content.displayName;

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };
```

- [ ] **Step 4: Add rich Accordion CSS**

Append near the Accordion rules in `/workspaces/ocr-container/pdomain-ui/theme/primitives.css`:

```css
.acc.mismatch {
  border-left: 2px solid var(--mismatch);
  background: color-mix(in srgb, var(--mismatch) 5%, transparent);
}

.acc-trigger {
  width: 100%;
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.acc-trigger__main {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 8px;
}

.acc-trigger__label {
  flex: none;
}

.acc-trigger__hint {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink-3);
  font-size: 9px;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
}

.acc-trigger__meta {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 8px;
  margin-left: 8px;
}

.acc-body__inner {
  padding: 0 16px 16px;
}
```

- [ ] **Step 5: Verify Accordion**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm exec vitest run src/primitives/Accordion.test.tsx src/primitives/KeyCap.test.tsx
pnpm run typecheck
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ui
git add src/primitives/Accordion.tsx src/primitives/Accordion.test.tsx theme/primitives.css
git commit -m "feat: add rich accordion slots"
```

---

### Task 5: Build And Package Shared UI

**Files:**

- Modify as generated: `/workspaces/ocr-container/pdomain-ui/dist/*`

- [ ] **Step 1: Run the shared package gates**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
pnpm run format:check
pnpm run lint
pnpm run typecheck
pnpm run test:unit
pnpm run build
```

Expected: all commands PASS.

- [ ] **Step 2: Verify public exports**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
rg -n "TriStateChip|TabsAppearance|AccordionTone|ButtonVariant" src/primitives src/index.ts dist
```

Expected: output shows the new component/types in `src/primitives`, `dist/primitives.d.ts`, and any root barrel entries generated by the build.

- [ ] **Step 3: Commit generated package output if this repo tracks it**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ui
git status --short
```

Expected: if `dist/` files are modified and tracked, add them to the commit; if `dist/` is ignored, do not add it.

Commit tracked build outputs only when present:

```bash
cd /workspaces/ocr-container/pdomain-ui
git add dist
git commit -m "build: update pdomain-ui package artifacts"
```

If `git add dist` reports no pathspec because `dist` is ignored or absent, record that in the worker final response and do not force-add it.

---

### Task 6: Import Shared Primitive CSS In Labeler

**Files:**

- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/styles/primitives.css`
- Create: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/styles/primitives-import.test.ts`

- [ ] **Step 1: Add the CSS bridge test**

Create `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/styles/primitives-import.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

describe("labeler primitive CSS bridge", () => {
  it("imports pdomain-ui primitive classes before local overrides", () => {
    const cssPath = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "primitives.css",
    );
    const css = readFileSync(cssPath, "utf8");
    const importLine = '@import "@pdomain/pdomain-ui/theme/primitives.css";';

    expect(css).toContain(importLine);
    expect(css.indexOf(importLine)).toBeLessThan(css.indexOf(".mono"));
  });
});
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/styles/primitives-import.test.ts --passWithNoTests
```

Expected: FAIL until the CSS import exists.

- [ ] **Step 3: Add the import**

Insert near the top of `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/styles/primitives.css`, after the header comment:

```css
@import "@pdomain/pdomain-ui/theme/primitives.css";
```

- [ ] **Step 4: Verify CSS bridge and build resolution**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/styles/primitives-import.test.ts --passWithNoTests
pnpm run build
```

Expected: both commands PASS.

- [ ] **Step 5: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
git add frontend/src/styles/primitives.css frontend/src/styles/primitives-import.test.ts
git commit -m "chore: import shared pdomain-ui primitive css"
```

---

### Task 7: Migrate Simple Labeler Wrappers

**Files:**

- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/Input.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/KeyCap.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/StatusPip.tsx`
- Modify tests beside those files

- [ ] **Step 1: Replace simple wrappers with shared exports**

Use these file contents:

`frontend/src/components/ui/Input.tsx`

```tsx
export { Input } from "@pdomain/pdomain-ui/primitives";
export type { InputProps, InputSize } from "@pdomain/pdomain-ui/primitives";
```

`frontend/src/components/ui/KeyCap.tsx`

```tsx
export { KeyCap } from "@pdomain/pdomain-ui/primitives";
export type { KeyCapProps } from "@pdomain/pdomain-ui/primitives";
```

`frontend/src/components/ui/StatusPip.tsx`

```tsx
export { StatusPip } from "@pdomain/pdomain-ui/primitives";
export type {
  StatusPipProps,
  StatusPipStatus,
} from "@pdomain/pdomain-ui/primitives";
```

- [ ] **Step 2: Update tests to assert shared class contracts**

Run the focused tests after updating assertions from Tailwind-only classes to `.input`, `.key-cap-wrapper`, `.key`, `.key__sep`, and `.pip`:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Input.test.tsx src/components/ui/KeyCap.test.tsx src/components/ui/StatusPip.test.tsx --passWithNoTests
```

Expected: PASS with shared class assertions.

- [ ] **Step 3: Run known consumers**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/HotkeyHelpModal.test.tsx src/components/drawer/Worklist.test.tsx src/components/right-panel/WordHeader.test.tsx src/components/right-panel/WordFooter.test.tsx src/components/right-panel/OcrGtCompareRow.test.tsx src/components/right-panel/sections/BBoxSection.test.tsx src/components/right-panel/sections/CharFixerSection.test.tsx --passWithNoTests
pnpm run typecheck
```

Expected: both commands PASS.

- [ ] **Step 4: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
git add frontend/src/components/ui/Input.tsx frontend/src/components/ui/Input.test.tsx frontend/src/components/ui/KeyCap.tsx frontend/src/components/ui/KeyCap.test.tsx frontend/src/components/ui/StatusPip.tsx frontend/src/components/ui/StatusPip.test.tsx
git commit -m "refactor: use pdomain-ui simple primitives"
```

---

### Task 8: Migrate Button And Chip Wrappers

**Files:**

- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/button.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/Chip.tsx`
- Modify tests beside those files

- [ ] **Step 1: Replace Button wrapper with a shared re-export**

Replace `frontend/src/components/ui/button.tsx` with:

```tsx
export { Button } from "@pdomain/pdomain-ui/primitives";
export type {
  ButtonProps,
  ButtonSize,
  ButtonVariant,
} from "@pdomain/pdomain-ui/primitives";
```

- [ ] **Step 2: Replace Chip wrapper with static Chip plus shared TriStateChip**

Replace `frontend/src/components/ui/Chip.tsx` with:

```tsx
import type { ReactNode } from "react";
import {
  Chip as PdomainChip,
  TriStateChip,
} from "@pdomain/pdomain-ui/primitives";
import type { TriStateValue } from "@pdomain/pdomain-ui/primitives";

type ChipVariant = "static" | "tristate";
export type { TriStateValue };

export interface ChipProps {
  variant?: ChipVariant;
  value?: TriStateValue;
  onChange?: (next: TriStateValue) => void;
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}

export function Chip({
  variant = "static",
  value = "off",
  onChange,
  children,
  className,
  "data-testid": dataTestId,
}: ChipProps) {
  if (variant === "tristate") {
    return (
      <TriStateChip
        value={value}
        onChange={onChange}
        className={className}
        data-testid={dataTestId}
      >
        {children}
      </TriStateChip>
    );
  }

  return (
    <PdomainChip className={className} data-testid={dataTestId}>
      {children}
    </PdomainChip>
  );
}
```

- [ ] **Step 3: Update and run wrapper tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Button.test.tsx src/components/ui/Chip.test.tsx --passWithNoTests
```

Expected: PASS with assertions for `.btn`, shared variants, `.chip`, `.chip3`, and tri-state cycling.

- [ ] **Step 4: Run known consumers**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/pages/RootPage.test.tsx src/components/right-panel/StylePalette.test.tsx src/components/right-panel/sections/BBoxSection.test.tsx src/components/right-panel/sections/CharRangesSection.test.tsx src/components/right-panel/sections/CharFixerSection.test.tsx src/components/right-panel/sections/ErasePixelsSection.test.tsx src/components/right-panel/sections/ReboxSection.test.tsx src/components/right-panel/sections/StructureSection.test.tsx --passWithNoTests
pnpm run typecheck
```

Expected: both commands PASS.

- [ ] **Step 5: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
git add frontend/src/components/ui/button.tsx frontend/src/components/ui/Button.test.tsx frontend/src/components/ui/Chip.tsx frontend/src/components/ui/Chip.test.tsx
git commit -m "refactor: use pdomain-ui button and chip primitives"
```

---

### Task 9: Migrate Tabs And Accordion Wrappers

**Files:**

- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/tabs.tsx`
- Modify: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend/src/components/ui/accordion.tsx`
- Modify tests beside those files

- [ ] **Step 1: Replace Tabs wrapper with underline shared adapters**

Replace `frontend/src/components/ui/tabs.tsx` with:

```tsx
import * as React from "react";
import {
  Tabs,
  TabsContent as PdomainTabsContent,
  TabsList as PdomainTabsList,
  TabsTrigger as PdomainTabsTrigger,
} from "@pdomain/pdomain-ui/primitives";

type TabsListProps = React.ComponentPropsWithoutRef<typeof PdomainTabsList>;
type TabsTriggerProps = React.ComponentPropsWithoutRef<
  typeof PdomainTabsTrigger
>;
type TabsContentProps = React.ComponentPropsWithoutRef<
  typeof PdomainTabsContent
>;

const TabsList = React.forwardRef<
  React.ElementRef<typeof PdomainTabsList>,
  TabsListProps
>((props, ref) => (
  <PdomainTabsList ref={ref} appearance="underline" {...props} />
));
TabsList.displayName = "TabsList";

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof PdomainTabsTrigger>,
  TabsTriggerProps
>((props, ref) => (
  <PdomainTabsTrigger ref={ref} appearance="underline" {...props} />
));
TabsTrigger.displayName = "TabsTrigger";

const TabsContent = React.forwardRef<
  React.ElementRef<typeof PdomainTabsContent>,
  TabsContentProps
>((props, ref) => <PdomainTabsContent ref={ref} {...props} />);
TabsContent.displayName = "TabsContent";

export { Tabs, TabsList, TabsTrigger, TabsContent };
```

- [ ] **Step 2: Replace Accordion wrapper with shared rich parts**

Replace `frontend/src/components/ui/accordion.tsx` with:

```tsx
import {
  Accordion as PdomainAccordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@pdomain/pdomain-ui/primitives";

const Accordion = Object.assign(PdomainAccordion, {
  Item: AccordionItem,
  Trigger: AccordionTrigger,
  Content: AccordionContent,
});

export { Accordion };
```

- [ ] **Step 3: Update wrapper tests**

Update `Tabs.test.tsx` assertions to expect `.tabs--underline` on the list and `.tab--underline` on triggers. Update `Accordion.test.tsx` assertions to expect shared `.acc`, `.acc-trigger`, `.acc-trigger__hint`, `.key-cap-wrapper`, and `.acc-body__inner`.

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Tabs.test.tsx src/components/ui/Accordion.test.tsx --passWithNoTests
```

Expected: PASS.

- [ ] **Step 4: Run known consumers**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/right-panel/LineDetail.test.tsx src/components/right-panel/BlockDetail.test.tsx src/components/right-panel/WordDetail.test.tsx --passWithNoTests
pnpm run typecheck
```

Expected: both commands PASS.

- [ ] **Step 5: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
git add frontend/src/components/ui/tabs.tsx frontend/src/components/ui/Tabs.test.tsx frontend/src/components/ui/accordion.tsx frontend/src/components/ui/Accordion.test.tsx
git commit -m "refactor: use pdomain-ui tabs and accordion"
```

---

### Task 10: Consumer Verification

**Files:**

- No source edits unless tests reveal a real integration defect.

- [ ] **Step 1: Run the full wrapper and consumer suite**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/styles/primitives-import.test.ts src/components/ui/Input.test.tsx src/components/ui/KeyCap.test.tsx src/components/ui/StatusPip.test.tsx src/components/ui/Button.test.tsx src/components/ui/Chip.test.tsx src/components/ui/Tabs.test.tsx src/components/ui/Accordion.test.tsx src/pages/RootPage.test.tsx src/components/HotkeyHelpModal.test.tsx src/components/drawer/Worklist.test.tsx src/components/right-panel/WordHeader.test.tsx src/components/right-panel/WordFooter.test.tsx src/components/right-panel/LineDetail.test.tsx src/components/right-panel/BlockDetail.test.tsx src/components/right-panel/WordDetail.test.tsx src/components/right-panel/StylePalette.test.tsx src/components/right-panel/sections/BBoxSection.test.tsx src/components/right-panel/sections/CharRangesSection.test.tsx src/components/right-panel/sections/CharFixerSection.test.tsx src/components/right-panel/sections/ErasePixelsSection.test.tsx src/components/right-panel/sections/ReboxSection.test.tsx src/components/right-panel/sections/StructureSection.test.tsx --passWithNoTests
```

Expected: PASS.

- [ ] **Step 2: Run project gates**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm run typecheck
pnpm run lint
pnpm run build
```

Expected: all commands PASS.

- [ ] **Step 3: Verify local wrappers are thin**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
rg -n "@pdomain/pdomain-ui/primitives|TriStateChip|appearance=\"underline\"|Object.assign\\(PdomainAccordion" frontend/src/components/ui
```

Expected: output shows every local wrapper delegates to `@pdomain/pdomain-ui/primitives`.

---

### Task 11: Document Migration Matrix

**Files:**

- Create: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md`

- [ ] **Step 1: Create the matrix**

Create `/workspaces/ocr-container/pdomain-ocr-labeler-spa/docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md`:

```markdown
# Pdomain UI Component Migration Matrix

Date: 2026-06-14

## Scope

This matrix records the local labeler UI wrappers migrated after upstream `pdomain-ui` support landed.

## Results

- `components/ui/Input.tsx`: shared `Input` re-export.
- `components/ui/KeyCap.tsx`: shared `KeyCap` re-export.
- `components/ui/StatusPip.tsx`: shared `StatusPip` re-export.
- `components/ui/button.tsx`: shared `Button` re-export after upstream variant, size, and `asChild` support.
- `components/ui/Chip.tsx`: static chips use shared `Chip`; tri-state behavior uses shared `TriStateChip`.
- `components/ui/tabs.tsx`: shared Tabs with `appearance="underline"` defaults for labeler detail panels.
- `components/ui/accordion.tsx`: shared Accordion rich slots with labeler namespace compatibility.

## Upstream Pieces Added First

- Button variant aliases: `secondary`, `outline`, `destructive`.
- Button `size="default"` alias for `md`.
- Button `asChild` support through Radix Slot.
- `TriStateChip` primitive for off/on/mixed controls.
- Tabs underline appearance.
- Accordion item `tag`/tone support, trigger `hint`, trigger `keycap`, and content `innerClassName`.

## Verification

Final verification was:

- `pdomain-ui`: `pnpm run format:check`, `pnpm run lint`, `pnpm run typecheck`, `pnpm run test:unit`, `pnpm run build`.
- `pdomain-ocr-labeler-spa/frontend`: wrapper/consumer Vitest command from Task 10, `pnpm run typecheck`, `pnpm run lint`, `pnpm run build`.
```

- [ ] **Step 2: Run doc formatting**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
./node_modules/.bin/prettier --check ../docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
git add docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md
git commit -m "docs: record upstream-first component migration"
```

---

## Self-Review

Spec coverage:

- The shared `pdomain-ui` pieces are built before labeler migration starts.
- Every local wrapper named in the original component-migration plan is covered.
- Tabs and Accordion are no longer excluded; their missing shared contracts are explicit upstream tasks.
- Tri-state Chip behavior moves into `pdomain-ui` through `TriStateChip`.

Placeholder scan:

- The plan contains no empty placeholder markers.
- Each code-changing task names exact files and includes concrete test/code snippets.

Type consistency:

- `TriStateValue` is defined upstream and re-exported by the labeler wrapper.
- `AccordionItem` keeps a `tag` alias so existing labeler usage can migrate without call-site churn.
- `TabsList` and `TabsTrigger` share the same `appearance` prop.
