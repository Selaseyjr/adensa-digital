/**
 * Application-shell contract: brand, the four product
 * sections in the navigation, and the human-in-the-loop
 * statement. The shell renders without any API.
 *
 * RootLayout renders <html>/<body>, which React Testing
 * Library tolerates in jsdom; each test cleans up before the
 * next mounts a fresh shell.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, within } from "@testing-library/react";
import { render } from "@testing-library/react";
import RootLayout from "@/app/layout";

// The active-page treatment is a real client behavior
// (usePathname), which jsdom renders outside the App Router —
// the test provides the pathname directly.
const usePathnameMock = vi.hoisted(() => ({ current: "/" }));

vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock.current,
}));

vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "--font-inter-test" }),
}));

afterEach(() => {
  cleanup();
  usePathnameMock.current = "/";
});

function renderShell(children: React.ReactNode = <p>surface content</p>) {
  return render(<RootLayout>{children}</RootLayout>);
}

describe("application shell", () => {
  it("renders the Adensa Digital brand", () => {
    renderShell();

    expect(screen.getByText("Adensa Digital")).toBeInTheDocument();
    expect(screen.getByText("Supply-chain operations")).toBeInTheDocument();
  });

  it("navigates the four product sections", () => {
    renderShell();

    const nav = screen.getByRole("navigation", { name: "Primary" });

    const expected = [
      ["Control Tower", "/"],
      ["Exceptions", "/exceptions"],
      ["Operations", "/operations"],
      ["Administration", "/administration"],
    ] as const;

    for (const [label, href] of expected) {
      expect(within(nav).getByRole("link", { name: label })).toHaveAttribute(
        "href",
        href,
      );
    }
  });

  it("marks the current page in the navigation", () => {
    usePathnameMock.current = "/exceptions";
    renderShell();

    const nav = screen.getByRole("navigation", { name: "Primary" });

    expect(within(nav).getByRole("link", { name: "Exceptions" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      within(nav).getByRole("link", { name: "Control Tower" }),
    ).not.toHaveAttribute("aria-current");
  });

  it("offers a skip link to the main content landmark", () => {
    renderShell();

    const skipLink = screen.getByRole("link", { name: "Skip to main content" });

    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("renders surface content and the human-in-the-loop footer", () => {
    renderShell();

    expect(screen.getByText("surface content")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Adensa Digital — operational decision support. Recommendations are decision support; planners approve every recovery.",
      ),
    ).toBeInTheDocument();
  });
});
