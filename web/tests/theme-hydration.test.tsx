/**
 * Visual Identity v1 — dark-mode hydration contract.
 *
 * The theme init script sets [data-theme="dark"] on <html>
 * before first paint. React 19 hydration "recovers" <html> to
 * its VDOM attributes, which would silently delete that
 * attribute (theme data is not a React prop). These tests pin
 * the contract that keeps the dark environment stable:
 *
 * 1. suppressHydrationWarning on <html> tells React the
 *    attribute is owned outside the VDOM.
 * 2. The ThemeToggle re-asserts the attribute from its state.
 * The jsdom assertion of (1) is heuristic (jsdom does not run
 * React's DOM-recovery path); (2) is the behavioural guarantee.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RootLayout from "@/app/layout";
import { ThemeToggle } from "@/components/ThemeToggle";

vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "--font-inter-test" }),
}));

const usePathnameMock = vi.hoisted(() => ({ current: "/" }));
vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock.current,
}));

afterEach(() => {
  cleanup();
  usePathnameMock.current = "/";
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("dark-mode hydration contract", () => {
  it("keeps data-theme across hydration when init set dark", async () => {
    document.documentElement.dataset.theme = "dark";
    const user = userEvent.setup();
    render(<RootLayout>{<p>surface</p>}</RootLayout>);

    // Toggle once in each direction to complete a full React
    // commit cycle over the <html> owner.
    const button = screen.getByRole("button");
    await user.click(button);
    expect(document.documentElement.dataset.theme).toBe("light");
    await user.click(button);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(button).toHaveAttribute("aria-pressed", "true");
  });

  it("re-asserts data-theme from toggle state on mount", () => {
    document.documentElement.dataset.theme = "dark";
    render(<ThemeToggle />);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
