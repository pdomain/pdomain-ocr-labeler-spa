import { describe, expect, it } from "vitest";
import { ROUTES, typographyPageNoUrl } from "./routes";

describe("typography route", () => {
  it("defines and builds the dedicated geometry-free page route", () => {
    expect(ROUTES.PROJECT_TYPOGRAPHY_PAGE_NO).toBe(
      "/projects/:projectId/pages/pageno/:pageNo/typography",
    );
    expect(typographyPageNoUrl("project/one", 4)).toBe(
      "/projects/project%2Fone/pages/pageno/4/typography",
    );
  });
});
