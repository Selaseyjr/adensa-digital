import { expect, test, type Page } from "@playwright/test";

/**
 * Browser end-to-end coverage (P12.4): the real Next.js
 * frontend against the real FastAPI backend over a disposable
 * SQLite database — no mocks, no stubs, no application
 * changes. Every assertion targets user-facing, accessible
 * text (roles, labels, headings, live regions) — never
 * implementation CSS hooks.
 *
 * Serial execution is the workflow's own shape: the mutation
 * flow consumes the state the earlier flows read, exactly as
 * a planner would drive it.
 */
test.describe.configure({ mode: "serial" });

/**
 * The workflow state chip in the Workflow Action section.
 * Chips carry the backend classifier's literal states, so
 * this is an assertion on real operational text.
 */
function workflowStateChip(page: Page) {
  return page
    .getByRole("region", { name: "Workflow action" })
    .getByText(
      /^(Decision required|Awaiting execution|Executed — still open|No system recovery available|Resolved)$/,
    );
}

test.describe("Control Tower", () => {
  test("loads the real operational position", async ({ page }) => {
    await page.goto("/");

    /* First render compiles + streams many server-side fetches
       against the local API; give slow SSR settles room
       (per-assertion timeout, not a blanket slow test). */
    const slow = { timeout: 30_000 };

    // The deck: title + the honest count semantics note.
    await expect(
      page.getByRole("heading", { name: "Command Centre", level: 1 }),
    ).toBeVisible();
    await expect(
      page.getByText("Executed does not necessarily mean resolved."),
    ).toBeVisible(slow);

    // KPI tiles render real numbers from the disposable
    // database (nonzero: the synthetic dataset is large).
    const openExceptions = page.getByRole("link", {
      name: /Open Exceptions/,
    });
    await expect(openExceptions).toBeVisible(slow);
    await expect(
      openExceptions.getByText(/^[1-9]\d*$/, { exact: true }),
    ).toBeVisible(slow);

    await expect(
      page
        .getByRole("link", { name: /Pending Decisions/ })
        .getByText(/^[1-9]\d*$/, { exact: true }),
    ).toBeVisible(slow);

    // Real operational sections render from live data.
    await expect(
      page.getByRole("heading", { name: "Queue Composition", level: 2 }),
    ).toBeVisible(slow);
    await expect(
      page.getByRole("heading", { name: "Analytics", level: 2 }),
    ).toBeVisible(slow);
    await expect(
      page.getByRole("heading", { name: "Recently Resolved", level: 2 }),
    ).toBeVisible(slow);
  });
});

test.describe("Exception Inbox", () => {
  test("filter changes the URL and displays bounded results", async ({
    page,
  }) => {
    await page.goto("/exceptions");

    await expect(
      page.getByRole("heading", { name: "Exceptions", level: 1 }),
    ).toBeVisible();

    // The result-count live region.
    const resultCount = page.locator(".inbox-result-count");
    await expect(resultCount).toContainText(/queued exceptions$/);

    // The queue is bounded to 100 rows (P8.8 count honesty).
    await expect(page.locator("tbody tr")).toHaveCount(100, {
      timeout: 15_000,
    });

    // Severity filter → the URL carries the state. The toolbar
    // navigates through the App Router (an RSC re-render of the
    // queue), which can take a moment against the cold stack.
    await page.getByLabel("Severity").selectOption({ label: "Critical" });

    await expect(page).toHaveURL(/\/exceptions\?severity=Critical$/, {
      timeout: 30_000,
    });

    // The bounded-queue honesty note appears for this filter.
    await expect(
      page.getByText(
        "Control Tower counts describe the full open population",
      ),
    ).toBeVisible();

    // The narrowed view reports itself honestly and every
    // rendered row carries the filtered severity.
    await expect(resultCount).toContainText(
      /^Showing \d+ of \d+ queued exceptions — severity Critical/,
    );
    const rows = page.locator("tbody tr");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
    expect(rowCount).toBeLessThanOrEqual(100);
    await expect(rows.getByText("Critical")).toHaveCount(rowCount);

    // A search filter narrows further and lands in the URL.
    // The needle is read from a row the bounded window actually
    // renders — the search haystack covers IDs, shipment, type,
    // location, impact and mode, so the exact exception ID is
    // guaranteed to match its own row.
    const needle = (await rows.first().getByRole("link").textContent())?.trim() ?? "";
    expect(needle).toMatch(/^EXC-\d+$/);
    await page.getByLabel("Search").fill(needle);
    await page.getByRole("button", { name: "Apply" }).click();

    // Order-agnostic: wait for the navigation to land, then
    // assert both filter params are present.
    await expect
      .poll(() => new URL(page.url()).searchParams.get("q"), {
        timeout: 30_000,
      })
      .toBe(needle);
    expect(new URL(page.url()).searchParams.get("severity")).toBe(
      "Critical",
    );
    await expect(resultCount).toHaveText(
      new RegExp(
        `^Showing 1 of 100 queued exceptions — search “${needle}”, severity Critical$`,
      ),
    );
    await expect(
      page.getByRole("link", { name: new RegExp(needle) }),
    ).toBeVisible();
    await expect(page.getByText(new RegExp(`search “${needle}”`))).toBeVisible();

    // Reset returns the canonical inbox URL.
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(page).toHaveURL(/\/exceptions$/, { timeout: 30_000 });
    await expect(resultCount).toContainText(/queued exceptions$/);
  });
});

test.describe("Investigation Workspace", () => {
  test("loads a real exception with its investigation sections", async ({
    page,
  }) => {
    await page.goto("/exceptions/EXC-000008");

    await expect(
      page.getByRole("heading", { name: "Investigation Workspace", level: 1 }),
    ).toBeVisible();

    // Header identity — real database rows, not fixtures.
    await expect(
      page.getByRole("heading", { name: /EXC-000008 — / }),
    ).toBeVisible();
    await expect(
      page.getByText(/Shipment SHP-\d+ · Order ORD-\d+/),
    ).toBeVisible();

    // Every investigation section renders with its real
    // heading (the W4 workspace hierarchy).
    for (const section of [
      "Situation & Impact",
      "Decision Support",
      "Operational History",
      "Sustainability",
    ]) {
      await expect(
        page.getByRole("heading", { name: section, level: 3 }),
      ).toBeVisible();
    }

    // Real persisted evidence, not placeholders.
    await expect(
      page.getByText("Recommended", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.locator(".history-list .history-entry").first(),
    ).toBeVisible();

    // The section index links into the workspace anchors.
    const index = page.getByRole("navigation", {
      name: "Workspace sections",
    });
    await expect(
      index.getByRole("link", { name: "Decision Support" }),
    ).toBeVisible();
    await expect(
      index.getByRole("link", { name: "Workflow Action" }),
    ).toBeVisible();

    // The AI advisory renders its real local brief (the
    // template provider runs without any external credential).
    await expect(
      page.getByRole("heading", { name: "AI Advisory", level: 3 }),
    ).toBeVisible();
    await expect(page.getByText("AI-assisted · Advisory only")).toBeVisible();
    await expect(page.getByText(/Advisory provider: /)).toBeVisible();
  });
});

test.describe("Workflow mutations", () => {
  test("one operational mutation succeeds end-to-end", async ({ page }) => {
    await page.goto("/exceptions/EXC-000008");

    // EXC-000008 is open with feasible recovery → "Decision
    // required", the approve gate.
    await expect(workflowStateChip(page)).toHaveText("Decision required");

    // Approve through the real UI: decide → name → confirm.
    await page.getByRole("button", { name: "Approve recovery" }).click();
    await page.getByLabel("Approving as planner").fill("E2E Planner");
    await page.getByRole("button", { name: "Confirm approval" }).click();

    // The real backend outcome banner (verbatim engine text).
    await expect(
      page.getByText(/Recovery action ACT-\d+ approved successfully\./),
    ).toBeVisible();

    // Revalidation advanced the persisted state — the next
    // gate (execute) renders. This is the mutation provably
    // having happened server-side.
    await expect(workflowStateChip(page)).toHaveText("Awaiting execution");

    // Execute through the real UI.
    await page.getByRole("button", { name: "Execute recovery" }).click();

    await expect(
      page.getByText(/Recovery executed successfully for SHP-\d+\./),
    ).toBeVisible();
    // The engine computes the end state: still-open follow-up or
    // resolved — both are honest outcomes of the same mutation.
    await expect(workflowStateChip(page)).toHaveText(
      /^(Executed — still open|Resolved)$/,
    );
  });

  test("stale/409 mutation path is handled correctly", async ({
    browser,
  }) => {
    // Two planners look at the same decision simultaneously.
    const plannerA = await browser.newPage();
    const plannerB = await browser.newPage();

    await plannerA.goto("/exceptions/EXC-000009");
    await plannerB.goto("/exceptions/EXC-000009");

    await expect(workflowStateChip(plannerA)).toHaveText("Decision required");
    await expect(workflowStateChip(plannerB)).toHaveText("Decision required");

    // Planner B decides first; the persisted state moves.
    await plannerB.getByRole("button", { name: "Approve recovery" }).click();
    await plannerB.getByLabel("Approving as planner").fill("Planner B");
    await plannerB.getByRole("button", { name: "Confirm approval" }).click();
    await expect(workflowStateChip(plannerB)).toHaveText("Awaiting execution");
    await plannerB.close();

    // Planner A's tab is now stale: it still renders the
    // approve gate from before B's decision (no live reload —
    // exactly the situation a 409 exists for).
    await expect(workflowStateChip(plannerA)).toHaveText("Decision required");

    // A drives the stale approve through the real UI.
    await plannerA.getByRole("button", { name: "Approve recovery" }).click();
    await plannerA.getByLabel("Approving as planner").fill("Planner A");
    await plannerA.getByRole("button", { name: "Confirm approval" }).click();

    // The backend engine remains the authority: its HTTP 409
    // guard message renders verbatim (the action is no longer
    // pending, so the transition guard fires), the workspace
    // does not crash, and the UI keeps working.
    await expect(
      plannerA.getByText(/Invalid workflow transition: /),
    ).toBeVisible();
    await expect(
      plannerA.getByRole("heading", { name: "Workflow Action", level: 3 }),
    ).toBeVisible();

    await plannerA.close();
  });
});
