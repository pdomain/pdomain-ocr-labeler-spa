# Component Migration To Pdomain UI Implementation Plan

> Superseded by `docs/superpowers/plans/2026-06-14-upstream-first-pdomain-ui-component-migration.md`. Do not execute this older plan unless the newer upstream-first plan is explicitly rejected.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the labeler SPA's local reusable UI wrappers to delegate to `@pdomain/pdomain-ui` primitives where the contracts fit, while keeping labeler-specific Tabs, Accordion, and tri-state behavior intact.

**Architecture:** Keep existing labeler import paths stable by converting local wrappers into compatibility adapters over `@pdomain/pdomain-ui/primitives`. Add the shared primitive CSS import first, then let independent workers migrate `Input`, `KeyCap`, `StatusPip`, `Button`, and `Chip` in parallel. Keep Tabs and Accordion local behind an explicit decision record until `pdomain-ui` supports their active-state and rich-trigger contracts.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, React Testing Library, `@pdomain/pdomain-ui@0.7.3`, Radix primitives, Tailwind utility classes, shared `pdomain-ui` CSS tokens and primitive classes.

---

## Parallel Execution Map

Run Task 1 first. After Task 1 passes, Tasks 2, 3, 4, 5, 6, and 7 can run in parallel because their write sets are disjoint. Task 8 runs after all migration lanes have landed.

| Lane | Task                                        | Worker ownership                                                | Depends on |
| ---- | ------------------------------------------- | --------------------------------------------------------------- | ---------- |
| 0    | Task 1: Import shared primitive CSS         | `frontend/src/styles/*` only                                    | None       |
| A    | Task 2: Migrate `Input` wrapper             | `frontend/src/components/ui/Input.*` only                       | Task 1     |
| B    | Task 3: Migrate `KeyCap` wrapper            | `frontend/src/components/ui/KeyCap.*` only                      | Task 1     |
| C    | Task 4: Migrate `StatusPip` wrapper         | `frontend/src/components/ui/StatusPip.*` only                   | Task 1     |
| D    | Task 5: Migrate `Button` wrapper            | `frontend/src/components/ui/button.tsx`, `Button.test.tsx` only | Task 1     |
| E    | Task 6: Migrate `Chip` static path          | `frontend/src/components/ui/Chip.*` only                        | Task 1     |
| F    | Task 7: Record Tabs/Accordion non-migration | docs only                                                       | None       |
| Z    | Task 8: Integration verification and matrix | docs plus final checks                                          | Tasks 1-7  |

## File Structure

- `frontend/src/styles/primitives.css`: imports the canonical `@pdomain/pdomain-ui/theme/primitives.css` before local labeler overrides, so delegated primitives have required classes like `input-wrapper`, `key-cap-wrapper`, `.pip`, `.chip3`, and `.btn`.
- `frontend/src/styles/primitives-import.test.ts`: guards the CSS import order.
- `frontend/src/components/ui/Input.tsx`: compatibility adapter around `@pdomain/pdomain-ui/primitives` `Input`.
- `frontend/src/components/ui/Input.test.tsx`: tests the adapter's public labeler API and shared class output.
- `frontend/src/components/ui/KeyCap.tsx`: compatibility re-export of `pdomain-ui` `KeyCap`.
- `frontend/src/components/ui/KeyCap.test.tsx`: tests shared keycap DOM classes and separator behavior.
- `frontend/src/components/ui/StatusPip.tsx`: compatibility re-export of `pdomain-ui` `StatusPip`.
- `frontend/src/components/ui/StatusPip.test.tsx`: tests shared token semantics for `exact`, `fuzzy`, `mismatch`, `ocr`, and `gt`.
- `frontend/src/components/ui/button.tsx`: compatibility adapter over `pdomain-ui` `Button`, preserving local `secondary`, `outline`, `destructive`, `default`, and `asChild` API names.
- `frontend/src/components/ui/Button.test.tsx`: tests the compatibility API and shared `.btn` classes.
- `frontend/src/components/ui/Chip.tsx`: delegates static chips to `pdomain-ui` `Chip`; preserves labeler tri-state behavior locally with shared `.chip3` classes.
- `frontend/src/components/ui/Chip.test.tsx`: tests static delegation, `data-testid`, tri-state keyboard/click cycling, and ARIA state.
- `docs/decisions/2026-06-14-tabs-accordion-remain-local.md`: records why Tabs and Accordion are not migrated in this implementation slice.
- `docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md`: final migration matrix for future workers and reviewers.

## Shared Constraints

- Use `@pdomain/pdomain-ui/primitives` for primitive imports. Do not import primitive subparts from the package root because the root barrel does not expose every part.
- Do not rewrite application call sites in the first pass unless a wrapper API cannot preserve behavior. Existing imports such as `../ui/StatusPip` and `../../ui/button` remain valid.
- Do not migrate `frontend/src/components/ui/tabs.tsx` or `frontend/src/components/ui/accordion.tsx` in this plan. Their current comments identify real incompatibilities with `pdomain-ui` active-state styling and trigger layout.
- Preserve test IDs that existing unit and driver-contract tests use.
- Run commands from `/workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend` unless the step states another working directory.

---

### Task 1: Import Shared Primitive CSS

**Files:**

- Modify: `frontend/src/styles/primitives.css`
- Create: `frontend/src/styles/primitives-import.test.ts`

- [ ] **Step 1: Write the failing CSS import-order test**

Create `frontend/src/styles/primitives-import.test.ts`:

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

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/styles/primitives-import.test.ts --passWithNoTests
```

Expected: FAIL with an assertion showing `@import "@pdomain/pdomain-ui/theme/primitives.css";` is missing.

- [ ] **Step 3: Import shared primitive CSS before local rules**

Modify the top of `frontend/src/styles/primitives.css` so it begins:

```css
/* ─── ocr-project-prep · primitives ────────────────────────────────
 * Requires tokens.css. Every rule references CSS vars — never literals.
 * Load Inter + JetBrains Mono separately (see README).
 * Reset rules (*, html, body, a) are omitted here because the SPA uses
 * Tailwind preflight and has its own body rule in index.css.
 * ────────────────────────────────────────────────────────────────── */

@import "@pdomain/pdomain-ui/theme/primitives.css";

.mono {
  font-family: var(--mono-font);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/styles/primitives-import.test.ts --passWithNoTests
```

Expected: PASS for `labeler primitive CSS bridge`.

- [ ] **Step 5: Verify Vite resolves the package CSS export**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm run build
```

Expected: PASS with `tsc -b` and `vite build` completing without an unresolved CSS import error.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/primitives.css frontend/src/styles/primitives-import.test.ts
git commit -m "chore: import shared pdomain-ui primitive css"
```

---

### Task 2: Migrate The Local Input Wrapper

**Files:**

- Modify: `frontend/src/components/ui/Input.tsx`
- Modify: `frontend/src/components/ui/Input.test.tsx`

- [ ] **Step 1: Replace the Input tests with shared-primitive expectations**

Replace `frontend/src/components/ui/Input.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Input } from "./Input";

describe("Input", () => {
  it("renders md size by default using the pdomain-ui input class", () => {
    const { container } = render(<Input placeholder="test" />);
    const input = container.firstChild as HTMLInputElement;

    expect(input).toHaveClass("input");
    expect(input).not.toHaveClass("sm");
    expect(input).not.toHaveClass("lg");
  });

  it("renders sm size", () => {
    const { container } = render(<Input size="sm" placeholder="test" />);
    expect(container.firstChild).toHaveClass("input");
    expect(container.firstChild).toHaveClass("sm");
  });

  it("forwards ref", () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<Input ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });

  it("combines custom className with shared input classes", () => {
    const { container } = render(
      <Input size="md" className="custom-class" placeholder="test" />,
    );
    const input = container.firstChild as HTMLInputElement;

    expect(input).toHaveClass("input");
    expect(input).toHaveClass("custom-class");
  });

  it("passes through standard HTML attributes", () => {
    render(
      <Input placeholder="enter text" disabled data-testid="test-input" />,
    );
    const input = screen.getByTestId("test-input");

    expect(input).toHaveAttribute("placeholder", "enter text");
    expect(input).toHaveAttribute("disabled");
  });

  it("passes through pdomain-ui suffix support", () => {
    render(<Input data-testid="input-with-suffix" suffix="px" />);
    const input = screen.getByTestId("input-with-suffix");

    expect(input).toHaveClass("input");
    expect(input).toHaveClass("input-inner");
    expect(input.closest(".input-wrapper")).toBeInTheDocument();
    expect(screen.getByText("px")).toHaveClass("input-suffix");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Input.test.tsx --passWithNoTests
```

Expected: FAIL because the current local wrapper renders Tailwind classes like `h-[30px]` and does not expose the `suffix` prop.

- [ ] **Step 3: Replace the local Input implementation with a pdomain-ui adapter**

Replace `frontend/src/components/ui/Input.tsx` with:

```tsx
import * as React from "react";
import {
  Input as PdomainInput,
  type InputProps as PdomainInputProps,
} from "@pdomain/pdomain-ui/primitives";

export interface InputProps extends Omit<PdomainInputProps, "size"> {
  size?: "sm" | "md";
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input({ size = "md", ...props }, ref) {
    return <PdomainInput ref={ref} size={size} {...props} />;
  },
);

Input.displayName = "Input";
```

- [ ] **Step 4: Run focused usage tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Input.test.tsx src/components/right-panel/OcrGtCompareRow.test.tsx src/components/right-panel/sections/BBoxSection.test.tsx src/components/right-panel/sections/CharFixerSection.test.tsx --passWithNoTests
```

Expected: PASS for the wrapper test and the three known Input consumers.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/Input.tsx frontend/src/components/ui/Input.test.tsx
git commit -m "refactor: adapt labeler input to pdomain-ui primitive"
```

---

### Task 3: Migrate The Local KeyCap Wrapper

**Files:**

- Modify: `frontend/src/components/ui/KeyCap.tsx`
- Modify: `frontend/src/components/ui/KeyCap.test.tsx`

- [ ] **Step 1: Replace the KeyCap tests with shared DOM expectations**

Replace `frontend/src/components/ui/KeyCap.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KeyCap } from "./KeyCap";

describe("KeyCap", () => {
  it("renders a single key", () => {
    render(<KeyCap keys="Ctrl" />);
    expect(screen.getByText("Ctrl")).toBeInTheDocument();
  });

  it("renders multiple keys joined by separator spans", () => {
    const { container } = render(<KeyCap keys={["Ctrl", "K"]} />);

    expect(screen.getByText("Ctrl")).toBeInTheDocument();
    expect(screen.getByText("K")).toBeInTheDocument();
    expect(container.querySelectorAll(".key__sep")).toHaveLength(1);
  });

  it("renders single key in array format", () => {
    render(<KeyCap keys={["Enter"]} />);
    expect(screen.getByText("Enter")).toBeInTheDocument();
  });

  it("uses pdomain-ui keycap classes", () => {
    const { container } = render(<KeyCap keys={["Shift", "Alt", "Delete"]} />);

    expect(container.firstChild).toHaveClass("key-cap-wrapper");
    expect(container.querySelectorAll(".key")).toHaveLength(3);
    expect(container.querySelectorAll(".key__sep")).toHaveLength(2);
  });

  it("passes through root element attributes", () => {
    render(
      <KeyCap
        keys="Cmd"
        data-testid="shortcut-keycap"
        className="custom-class"
      />,
    );

    expect(screen.getByTestId("shortcut-keycap")).toHaveClass(
      "key-cap-wrapper",
    );
    expect(screen.getByTestId("shortcut-keycap")).toHaveClass("custom-class");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/KeyCap.test.tsx --passWithNoTests
```

Expected: FAIL because the current local wrapper uses nested Tailwind-only elements and does not accept `data-testid` or `className` root attributes.

- [ ] **Step 3: Re-export the pdomain-ui KeyCap primitive through the local path**

Replace `frontend/src/components/ui/KeyCap.tsx` with:

```tsx
export { KeyCap } from "@pdomain/pdomain-ui/primitives";
export type { KeyCapProps } from "@pdomain/pdomain-ui/primitives";
```

- [ ] **Step 4: Run focused usage tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/KeyCap.test.tsx src/components/HotkeyHelpModal.test.tsx src/components/right-panel/WordFooter.test.tsx src/components/ui/Accordion.test.tsx --passWithNoTests
```

Expected: PASS for the wrapper test and the known KeyCap consumers.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/KeyCap.tsx frontend/src/components/ui/KeyCap.test.tsx
git commit -m "refactor: adapt keycaps to pdomain-ui primitive"
```

---

### Task 4: Migrate The Local StatusPip Wrapper

**Files:**

- Modify: `frontend/src/components/ui/StatusPip.tsx`
- Modify: `frontend/src/components/ui/StatusPip.test.tsx`

- [ ] **Step 1: Replace the StatusPip tests with shared token expectations**

Replace `frontend/src/components/ui/StatusPip.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPip } from "./StatusPip";

describe("StatusPip", () => {
  it.each([
    ["exact", "var(--exact)"],
    ["fuzzy", "var(--fuzzy)"],
    ["mismatch", "var(--mismatch)"],
    ["ocr", "var(--ocr)"],
    ["gt", "var(--gt)"],
  ] as const)("renders %s with the shared status token", (status, token) => {
    render(<StatusPip status={status} label={status.toUpperCase()} />);
    const pip = screen.getByTestId(`status-pip-${status}`);

    expect(pip).toHaveClass("pip");
    expect(pip).toHaveStyle({ color: token });
    expect(pip).toHaveTextContent(status.toUpperCase());
    expect(pip.querySelector(".dot")).toBeInTheDocument();
  });

  it("renders without a label", () => {
    render(<StatusPip status="exact" />);
    const pip = screen.getByTestId("status-pip-exact");

    expect(pip).toHaveClass("pip");
    expect(pip).toHaveTextContent("");
  });

  it("passes through root element attributes", () => {
    render(
      <StatusPip
        status="gt"
        aria-label="ground truth status"
        className="custom-pip"
      />,
    );
    const pip = screen.getByLabelText("ground truth status");

    expect(pip).toHaveClass("pip");
    expect(pip).toHaveClass("custom-pip");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/StatusPip.test.tsx --passWithNoTests
```

Expected: FAIL because the current local wrapper uses Tailwind status classes and maps `ocr` to fuzzy/amber and `gt` to accent rather than shared `--ocr` and `--gt`.

- [ ] **Step 3: Re-export the pdomain-ui StatusPip primitive through the local path**

Replace `frontend/src/components/ui/StatusPip.tsx` with:

```tsx
export { StatusPip } from "@pdomain/pdomain-ui/primitives";
export type {
  StatusPipProps,
  StatusPipStatus,
} from "@pdomain/pdomain-ui/primitives";
```

- [ ] **Step 4: Run focused usage tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/StatusPip.test.tsx src/components/drawer/Worklist.test.tsx src/components/right-panel/WordHeader.test.tsx src/components/right-panel/LineDetail.test.tsx src/components/right-panel/MultiLineDetail.test.tsx src/components/right-panel/BlockDetail.test.tsx src/components/right-panel/LineWordsCard.test.tsx --passWithNoTests
```

Expected: PASS for the wrapper test and known status-pip consumers.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/StatusPip.tsx frontend/src/components/ui/StatusPip.test.tsx
git commit -m "refactor: adapt status pips to pdomain-ui primitive"
```

---

### Task 5: Migrate The Local Button Wrapper

**Files:**

- Modify: `frontend/src/components/ui/button.tsx`
- Modify: `frontend/src/components/ui/Button.test.tsx`

- [ ] **Step 1: Replace the Button tests with compatibility-adapter expectations**

Replace `frontend/src/components/ui/Button.test.tsx` with:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./button";

describe("Button", () => {
  it("renders with pdomain-ui base classes by default", () => {
    render(<Button>Click me</Button>);

    const button = screen.getByRole("button", { name: "Click me" });
    expect(button).toHaveClass("btn");
    expect(button).toHaveClass("primary");
  });

  it("maps local secondary variant to the shared neutral button", () => {
    render(<Button variant="secondary">Secondary</Button>);
    const button = screen.getByRole("button", { name: "Secondary" });

    expect(button).toHaveClass("btn");
    expect(button).not.toHaveClass("primary");
    expect(button).not.toHaveClass("ghost");
    expect(button).not.toHaveClass("danger");
  });

  it("maps local outline variant to the shared neutral button", () => {
    render(<Button variant="outline">Outline</Button>);
    const button = screen.getByRole("button", { name: "Outline" });

    expect(button).toHaveClass("btn");
    expect(button).not.toHaveClass("primary");
    expect(button).not.toHaveClass("ghost");
    expect(button).not.toHaveClass("danger");
  });

  it("maps ghost variant to the shared ghost button", () => {
    render(<Button variant="ghost">Ghost</Button>);
    expect(screen.getByRole("button", { name: "Ghost" })).toHaveClass("ghost");
  });

  it.each(["danger", "destructive"] as const)(
    "maps %s variant to shared danger styling",
    (variant) => {
      render(<Button variant={variant}>{variant}</Button>);
      expect(screen.getByRole("button", { name: variant })).toHaveClass(
        "danger",
      );
    },
  );

  it("maps local sm size to shared sm size", () => {
    render(<Button size="sm">Small</Button>);
    expect(screen.getByRole("button", { name: "Small" })).toHaveClass("sm");
  });

  it("maps local default size to shared md size with no size class", () => {
    render(<Button size="default">Default</Button>);
    const button = screen.getByRole("button", { name: "Default" });

    expect(button).toHaveClass("btn");
    expect(button).not.toHaveClass("sm");
    expect(button).not.toHaveClass("lg");
  });

  it("maps lg size to shared lg size", () => {
    render(<Button size="lg">Large</Button>);
    expect(screen.getByRole("button", { name: "Large" })).toHaveClass("lg");
  });

  it("click fires callback", () => {
    const handler = vi.fn();
    render(<Button onClick={handler}>Click</Button>);

    fireEvent.click(screen.getByRole("button", { name: "Click" }));
    expect(handler).toHaveBeenCalledOnce();
  });

  it("disabled button does not fire click", () => {
    const handler = vi.fn();
    render(
      <Button disabled onClick={handler}>
        Click
      </Button>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Click" }));
    expect(handler).not.toHaveBeenCalled();
  });

  it("preserves asChild support for link-style buttons", () => {
    render(
      <Button asChild variant="ghost" size="sm">
        <a href="/projects">Projects</a>
      </Button>,
    );

    const link = screen.getByRole("link", { name: "Projects" });
    expect(link).toHaveClass("btn");
    expect(link).toHaveClass("ghost");
    expect(link).toHaveClass("sm");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Button.test.tsx --passWithNoTests
```

Expected: FAIL because the current local wrapper uses Tailwind classes like `bg-accent`, `bg-raised`, and `h-[30px]` instead of shared `.btn` classes.

- [ ] **Step 3: Replace the Button implementation with a pdomain-ui compatibility adapter**

Replace `frontend/src/components/ui/button.tsx` with:

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import {
  Button as PdomainButton,
  type ButtonSize as PdomainButtonSize,
  type ButtonVariant as PdomainButtonVariant,
} from "@pdomain/pdomain-ui/primitives";

import { cn } from "@/lib/utils";

type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "danger"
  | "destructive";
type ButtonSize = "sm" | "default" | "lg";

interface ButtonProps extends Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  "className"
> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  asChild?: boolean;
  className?: string;
}

const VARIANT_MAP: Record<ButtonVariant, PdomainButtonVariant | undefined> = {
  primary: "primary",
  secondary: undefined,
  outline: undefined,
  ghost: "ghost",
  danger: "danger",
  destructive: "danger",
};

const SIZE_MAP: Record<ButtonSize, PdomainButtonSize> = {
  sm: "sm",
  default: "md",
  lg: "lg",
};

function classForMappedButton(
  variant: ButtonVariant,
  size: ButtonSize,
  className?: string,
) {
  const mappedVariant = VARIANT_MAP[variant];
  const mappedSize = SIZE_MAP[size];

  return cn(
    "btn",
    mappedVariant,
    mappedSize === "md" ? undefined : mappedSize,
    className,
  );
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size = "default",
      asChild = false,
      ...props
    },
    ref,
  ) => {
    if (asChild) {
      return (
        <Slot
          ref={ref}
          className={classForMappedButton(variant, size, className)}
          {...props}
        />
      );
    }

    const mappedVariant = VARIANT_MAP[variant];

    return (
      <PdomainButton
        ref={ref}
        {...props}
        {...(mappedVariant === undefined ? {} : { variant: mappedVariant })}
        size={SIZE_MAP[size]}
        className={className}
      />
    );
  },
);

Button.displayName = "Button";

export { Button };
export type { ButtonProps, ButtonSize, ButtonVariant };
```

- [ ] **Step 4: Run focused usage tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Button.test.tsx src/pages/RootPage.test.tsx src/components/right-panel/sections/BBoxSection.test.tsx src/components/right-panel/sections/CharRangesSection.test.tsx src/components/right-panel/sections/CharFixerSection.test.tsx src/components/right-panel/sections/ErasePixelsSection.test.tsx src/components/right-panel/sections/ReboxSection.test.tsx src/components/right-panel/sections/StructureSection.test.tsx --passWithNoTests
```

Expected: PASS for the wrapper test and known local Button consumers.

- [ ] **Step 5: Run typecheck for adapter prop compatibility**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm run typecheck
```

Expected: PASS with no `ButtonProps` assignment errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/button.tsx frontend/src/components/ui/Button.test.tsx
git commit -m "refactor: adapt labeler buttons to pdomain-ui primitive"
```

---

### Task 6: Migrate Static Chip Rendering And Preserve Tri-State Behavior

**Files:**

- Modify: `frontend/src/components/ui/Chip.tsx`
- Modify: `frontend/src/components/ui/Chip.test.tsx`

- [ ] **Step 1: Replace Chip tests with static-delegation and tri-state expectations**

Replace `frontend/src/components/ui/Chip.test.tsx` with:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Chip } from "./Chip";

describe("Chip static variant", () => {
  it("renders children through the shared chip class", () => {
    render(<Chip variant="static">Exact</Chip>);
    expect(screen.getByText("Exact")).toHaveClass("chip");
  });

  it("forwards data-testid on static variant", () => {
    render(
      <Chip variant="static" data-testid="static-chip">
        Badge
      </Chip>,
    );

    expect(screen.getByTestId("static-chip")).toHaveClass("chip");
  });

  it("combines custom className on static variant", () => {
    render(
      <Chip variant="static" className="custom-chip">
        Badge
      </Chip>,
    );

    expect(screen.getByText("Badge")).toHaveClass("chip");
    expect(screen.getByText("Badge")).toHaveClass("custom-chip");
  });
});

describe("Chip tristate variant", () => {
  it.each([
    ["off", "false"],
    ["on", "true"],
    ["mixed", "mixed"],
  ] as const)("exposes aria-pressed=%s for %s state", (value, ariaPressed) => {
    render(
      <Chip variant="tristate" value={value} onChange={() => {}}>
        Status
      </Chip>,
    );

    expect(screen.getByRole("button")).toHaveAttribute(
      "aria-pressed",
      ariaPressed,
    );
  });

  it("forwards data-testid on tristate variant", () => {
    render(
      <Chip
        variant="tristate"
        value="off"
        data-testid="my-chip"
        onChange={() => {}}
      >
        Label
      </Chip>,
    );

    expect(screen.getByTestId("my-chip")).toHaveAttribute(
      "data-tristate-value",
      "off",
    );
    expect(screen.getByTestId("my-chip")).toHaveClass("chip3");
  });

  it.each([
    ["off", "on"],
    ["on", "mixed"],
    ["mixed", "off"],
  ] as const)("cycles from %s to %s on click", (value, next) => {
    const onChange = vi.fn();
    render(
      <Chip variant="tristate" value={value} onChange={onChange}>
        Status
      </Chip>,
    );

    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith(next);
  });

  it("cycles on Enter and Space key", () => {
    const onChange = vi.fn();
    render(
      <Chip variant="tristate" value="off" onChange={onChange}>
        Status
      </Chip>,
    );

    fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });
    fireEvent.keyDown(screen.getByRole("button"), { key: " " });

    expect(onChange).toHaveBeenNthCalledWith(1, "on");
    expect(onChange).toHaveBeenNthCalledWith(2, "on");
  });

  it("uses shared chip3 visual classes for on and mixed states", () => {
    const { rerender } = render(
      <Chip variant="tristate" value="on" onChange={() => {}}>
        Status
      </Chip>,
    );

    expect(screen.getByRole("button")).toHaveClass("chip3");
    expect(screen.getByRole("button")).toHaveClass("all");
    expect(
      screen.getByRole("button").querySelector(".tri-dot"),
    ).toBeInTheDocument();

    rerender(
      <Chip variant="tristate" value="mixed" onChange={() => {}}>
        Status
      </Chip>,
    );

    expect(screen.getByRole("button")).toHaveClass("some");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Chip.test.tsx --passWithNoTests
```

Expected: FAIL because the current local chip renders Tailwind-only classes and not shared `.chip` / `.chip3` classes.

- [ ] **Step 3: Delegate static chips to pdomain-ui and keep tri-state local**

Replace `frontend/src/components/ui/Chip.tsx` with:

```tsx
import * as React from "react";
import { Chip as PdomainChip } from "@pdomain/pdomain-ui/primitives";

import { cn } from "@/lib/utils";

type ChipVariant = "static" | "tristate";
export type TristateValue = "off" | "on" | "mixed";

export interface ChipProps {
  variant?: ChipVariant;
  value?: TristateValue;
  onChange?: (next: TristateValue) => void;
  children: React.ReactNode;
  className?: string;
  /** Forwarded to the root element so Chip is addressable in tests/E2E. */
  "data-testid"?: string;
}

const cycle: Record<TristateValue, TristateValue> = {
  off: "on",
  on: "mixed",
  mixed: "off",
};

const stateClass: Record<TristateValue, string | undefined> = {
  off: undefined,
  on: "all",
  mixed: "some",
};

export function Chip({
  variant = "static",
  value = "off",
  onChange,
  children,
  className,
  "data-testid": dataTestId,
}: ChipProps) {
  if (variant === "tristate") {
    const handleClick = () => {
      onChange?.(cycle[value]);
    };

    const ariaPressed: true | false | "mixed" =
      value === "on" ? true : value === "mixed" ? "mixed" : false;

    return (
      <div
        role="button"
        aria-pressed={ariaPressed}
        tabIndex={0}
        data-tristate
        data-tristate-value={value}
        data-testid={dataTestId}
        onClick={handleClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleClick();
          }
        }}
        className={cn("chip3", stateClass[value], className)}
      >
        <span aria-hidden className="tri-dot" />
        {children}
      </div>
    );
  }

  return (
    <PdomainChip data-testid={dataTestId} className={className}>
      {children}
    </PdomainChip>
  );
}
```

- [ ] **Step 4: Run focused usage tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Chip.test.tsx src/components/right-panel/StylePalette.test.tsx src/components/right-panel/sections/CharRangesSection.test.tsx --passWithNoTests
```

Expected: PASS for the wrapper test and known Chip consumers.

- [ ] **Step 5: Run typecheck for exported `TristateValue` users**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm run typecheck
```

Expected: PASS with no errors in `ComponentPalette.tsx`, `StylePalette.tsx`, or `CharRangesSection.tsx`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/Chip.tsx frontend/src/components/ui/Chip.test.tsx
git commit -m "refactor: adapt chips to pdomain-ui static primitive"
```

---

### Task 7: Record Tabs And Accordion As Intentional Local Wrappers

**Files:**

- Create: `docs/decisions/2026-06-14-tabs-accordion-remain-local.md`

- [ ] **Step 1: Write the decision record**

Create `docs/decisions/2026-06-14-tabs-accordion-remain-local.md`:

```markdown
# Tabs And Accordion Remain Local During Pdomain UI Component Migration

Date: 2026-06-14

## Status

Accepted for the component-migration slice.

## Context

`pdomain-ocr-labeler-spa` is migrating local reusable UI wrappers toward `@pdomain/pdomain-ui/primitives`.
The labeler has local wrappers for `Button`, `Input`, `Chip`, `StatusPip`, `KeyCap`, `tabs`, and `accordion`.

`frontend/src/components/ui/tabs.tsx` currently wraps Radix Tabs directly because the labeler relies on Tailwind `data-[state=active]` styling and a border-overlap active underline. `pdomain-ui` Tabs expose `.tabs`, `.tab`, and `.tabs-content` classes and require importing subcomponents from `@pdomain/pdomain-ui/primitives`.

`frontend/src/components/ui/accordion.tsx` currently wraps Radix Accordion directly because the labeler needs:

- `Accordion.Item` `tag="accent" | "mismatch"`
- `Accordion.Trigger` `hint`
- `Accordion.Trigger` `keycap`
- a custom chevron from `@pdomain/pdomain-ui/icons`
- content padding and animation classes that match the right-panel editor

The current `pdomain-ui` Accordion trigger owns its chevron and does not expose these labeler trigger slots.

## Decision

Migrate `Input`, `KeyCap`, `StatusPip`, `Button`, and the static `Chip` path through compatibility adapters.

Keep labeler `tabs` and `accordion` local in this implementation slice. Do not bulk-replace their imports with `@pdomain/pdomain-ui/primitives`.

## Future Pdomain UI Enhancements Needed Before Migration

- Tabs: support the labeler active underline contract through Radix `data-state` styling or a slot/class API that does not require `.tab.active`.
- Accordion: expose trigger slots for label, hint, keycap, and chevron, plus item tone/tag variants that match `accent` and `mismatch`.
- Accordion: allow content body padding and animation classes to be controlled by the consuming app.

## Verification

The local wrappers remain covered by:

- `frontend/src/components/ui/Tabs.test.tsx`
- `frontend/src/components/ui/Accordion.test.tsx`
- `frontend/src/components/right-panel/LineDetail.test.tsx`
- `frontend/src/components/right-panel/BlockDetail.test.tsx`
- `frontend/src/components/right-panel/WordDetail.test.tsx`
```

- [ ] **Step 2: Verify the decision record contains the intended boundary phrase**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
rg -n "bulk-replace" docs/decisions/2026-06-14-tabs-accordion-remain-local.md
```

Expected: the command prints only the intentional phrase `Do not bulk-replace their imports`.

- [ ] **Step 3: Run local wrapper tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/components/ui/Tabs.test.tsx src/components/ui/Accordion.test.tsx src/components/right-panel/LineDetail.test.tsx src/components/right-panel/BlockDetail.test.tsx src/components/right-panel/WordDetail.test.tsx --passWithNoTests
```

Expected: PASS, confirming the intentionally local wrappers still satisfy their current consumers.

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/2026-06-14-tabs-accordion-remain-local.md
git commit -m "docs: record tabs and accordion migration boundary"
```

---

### Task 8: Integration Verification And Migration Matrix

**Files:**

- Create: `docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md`

- [ ] **Step 1: Create the migration matrix**

Create `docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md`:

```markdown
# Pdomain UI Component Migration Matrix

Date: 2026-06-14

## Scope

This matrix covers the local reusable UI wrappers in `pdomain-ocr-labeler-spa/frontend/src/components/ui` and their relationship to `@pdomain/pdomain-ui/primitives`.

The migration uses compatibility adapters first so existing labeler imports and driver-contract test IDs remain stable.

## Results

- `components/ui/Input.tsx`
  - Decision: Adapter over shared primitive.
  - Shared primitive: `@pdomain/pdomain-ui/primitives` `Input`.
  - Reason: Current app uses bare input semantics; shared suffix and FieldContext behavior are compatible additions.
- `components/ui/KeyCap.tsx`
  - Decision: Re-export shared primitive.
  - Shared primitive: `@pdomain/pdomain-ui/primitives` `KeyCap`.
  - Reason: API matches `keys: string | string[]`; shared CSS supplies wrapper, key, and separator classes.
- `components/ui/StatusPip.tsx`
  - Decision: Re-export shared primitive.
  - Shared primitive: `@pdomain/pdomain-ui/primitives` `StatusPip`.
  - Reason: API matches `exact`, `fuzzy`, `mismatch`, `ocr`, and `gt`; shared token mapping becomes canonical.
- `components/ui/button.tsx`
  - Decision: Compatibility adapter over shared primitive.
  - Shared primitive: `@pdomain/pdomain-ui/primitives` `Button`.
  - Reason: Local callers still use `secondary`, `outline`, `destructive`, `default`, and `asChild`; adapter maps them onto shared `.btn` classes.
- `components/ui/Chip.tsx`
  - Decision: Partial adapter.
  - Shared primitive: `@pdomain/pdomain-ui/primitives` `Chip`.
  - Reason: Static chips delegate to shared `Chip`; tri-state chips remain labeler behavior with shared `.chip3` classes.
- `components/ui/tabs.tsx`
  - Decision: Keep local.
  - Shared primitive: No migration in this slice.
  - Reason: Local active-state styling uses Radix `data-state`; current shared tabs need a richer styling contract before migration.
- `components/ui/accordion.tsx`
  - Decision: Keep local.
  - Shared primitive: No migration in this slice.
  - Reason: Local trigger needs hint, keycap, tag variants, custom chevron, and right-panel-specific body layout.

## Verification Commands

Run from `frontend`:

- `pnpm exec vitest run src/styles/primitives-import.test.ts src/components/ui/Input.test.tsx src/components/ui/KeyCap.test.tsx src/components/ui/StatusPip.test.tsx src/components/ui/Button.test.tsx src/components/ui/Chip.test.tsx src/components/ui/Tabs.test.tsx src/components/ui/Accordion.test.tsx --passWithNoTests`
- `pnpm run typecheck`
- `pnpm run lint`
- `pnpm run build`

## Remaining Follow-Up

The next shared-library work belongs in `pdomain-ui`, not the labeler SPA:

- Add a Tabs styling contract that supports Radix `data-state` active styling without app-local Tailwind wrappers.
- Add Accordion trigger slots for hint, keycap, and custom chevron.
- Add Accordion item tone variants for `accent` and `mismatch`.
- Decide whether tri-state chip behavior belongs in `pdomain-ui` as a first-class primitive.
```

- [ ] **Step 2: Run the full wrapper suite**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/styles/primitives-import.test.ts src/components/ui/Input.test.tsx src/components/ui/KeyCap.test.tsx src/components/ui/StatusPip.test.tsx src/components/ui/Button.test.tsx src/components/ui/Chip.test.tsx src/components/ui/Tabs.test.tsx src/components/ui/Accordion.test.tsx --passWithNoTests
```

Expected: PASS for all listed wrapper and CSS bridge tests.

- [ ] **Step 3: Run representative consumer tests**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm exec vitest run src/pages/RootPage.test.tsx src/components/HotkeyHelpModal.test.tsx src/components/drawer/Worklist.test.tsx src/components/right-panel/WordHeader.test.tsx src/components/right-panel/WordFooter.test.tsx src/components/right-panel/LineDetail.test.tsx src/components/right-panel/BlockDetail.test.tsx src/components/right-panel/WordDetail.test.tsx src/components/right-panel/StylePalette.test.tsx src/components/right-panel/sections/BBoxSection.test.tsx src/components/right-panel/sections/CharRangesSection.test.tsx src/components/right-panel/sections/CharFixerSection.test.tsx src/components/right-panel/sections/ErasePixelsSection.test.tsx src/components/right-panel/sections/ReboxSection.test.tsx src/components/right-panel/sections/StructureSection.test.tsx --passWithNoTests
```

Expected: PASS for the known component consumers touched by the wrapper adapters.

- [ ] **Step 4: Run project gates**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa/frontend
pnpm run typecheck
pnpm run lint
pnpm run build
```

Expected: all three commands PASS.

- [ ] **Step 5: Verify migration boundaries by search**

Run:

```bash
cd /workspaces/ocr-container/pdomain-ocr-labeler-spa
rg -n "@pdomain/pdomain-ui/primitives|components/ui/(tabs|accordion)|Tabs And Accordion Remain Local|Partial adapter" frontend/src/components/ui docs/decisions/2026-06-14-tabs-accordion-remain-local.md docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md
```

Expected: output shows `@pdomain/pdomain-ui/primitives` imports in the migrated wrappers, local Tabs/Accordion files still present, and the decision/matrix docs present.

- [ ] **Step 6: Commit**

```bash
git add docs/research/2026-06-14-pdomain-ui-component-migration-matrix.md
git commit -m "docs: summarize pdomain-ui component migration"
```

---

## Self-Review

Spec coverage:

- Local primitive audit from the PGDP alignment backlog is covered by the migration matrix in Task 8.
- Safe primitive migrations are covered by Tasks 2, 3, 4, 5, and 6.
- Shared CSS dependency is covered by Task 1.
- Tabs and Accordion migration boundary is covered by Task 7.
- Parallel agentic execution is covered by the Parallel Execution Map and disjoint task file ownership.

Placeholder scan:

- The plan contains no empty placeholder markers or unspecified code-change steps.
- Every code-changing task includes the exact replacement code for the files it owns.

Type consistency:

- `InputProps`, `KeyCapProps`, `StatusPipProps`, `ButtonProps`, and `TristateValue` are exported from the same local paths existing consumers already import.
- All primitive imports use `@pdomain/pdomain-ui/primitives`, the subpath that exposes the full primitive surface.
