// StatusPip.test.tsx — Vitest unit tests for the pdomain-ui StatusPip primitive.
// After Tier A migration, StatusPip comes from @pdomain/pdomain-ui/primitives.
// The upstream component bakes data-testid={`status-pip-${status}`} automatically.
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusPip } from "@pdomain/pdomain-ui/primitives";

describe("StatusPip — existing variants", () => {
  it("renders without label (dot only)", () => {
    render(<StatusPip status="exact" />);
    expect(screen.getByTestId("status-pip-exact")).toBeInTheDocument();
  });

  it("renders with label", () => {
    render(<StatusPip status="fuzzy" label="Fuzzy" />);
    expect(screen.getByText("Fuzzy")).toBeInTheDocument();
  });

  it("mismatch renders with correct testid", () => {
    render(<StatusPip status="mismatch" />);
    expect(screen.getByTestId("status-pip-mismatch")).toBeInTheDocument();
  });

  it("exact status renders with correct testid", () => {
    render(<StatusPip status="exact" />);
    expect(screen.getByTestId("status-pip-exact")).toBeInTheDocument();
  });

  it("fuzzy status with label renders both testid and label", () => {
    render(<StatusPip status="fuzzy" label="Match" />);
    expect(screen.getByTestId("status-pip-fuzzy")).toBeInTheDocument();
    expect(screen.getByText("Match")).toBeInTheDocument();
  });
});

describe("StatusPip — Gap 57: ocr/gt variants", () => {
  it("renders ocr variant with testid status-pip-ocr", () => {
    render(<StatusPip status="ocr" label="OCR" />);
    expect(screen.getByTestId("status-pip-ocr")).toBeInTheDocument();
  });

  it("renders gt variant with testid status-pip-gt", () => {
    render(<StatusPip status="gt" label="GT" />);
    expect(screen.getByTestId("status-pip-gt")).toBeInTheDocument();
  });

  it("ocr variant renders label text", () => {
    render(<StatusPip status="ocr" label="0.92" />);
    expect(screen.getByText("0.92")).toBeInTheDocument();
  });

  it("gt renders label text", () => {
    render(<StatusPip status="gt" label="Confirmed" />);
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
  });

  it("exact status uses testid status-pip-exact", () => {
    render(<StatusPip status="exact" />);
    expect(screen.getByTestId("status-pip-exact")).toBeInTheDocument();
  });
});
