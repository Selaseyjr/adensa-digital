/**
 * Visual Identity v1 brand contracts: the replaceable mark,
 * the header lockup, and the theme control.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrandMark, AdensaMarkIcon } from "@/components/brand/BrandMark";
import { ThemeToggle } from "@/components/ThemeToggle";
import RootLayout from "@/app/layout";

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

describe("BrandMark", () => {
  it("renders the mark as decorative SVG by default", () => {
    render(<BrandMark />);

    const svg = document.querySelector("svg.app-brand-mark");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("viewBox", "0 0 32 32");
  });

  it("can render as a named image when not decorative", () => {
    render(<BrandMark decorative={false} />);

    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("renders the standalone icon form with its own name", () => {
    render(<AdensaMarkIcon />);

    expect(screen.getByRole("img", { name: "Adensa Digital" })).toBeInTheDocument();
  });
});

describe("shell brand lockup", () => {
  it("renders the mark, the brand name and the theme control", () => {
    render(<RootLayout>{<p>surface content</p>}</RootLayout>);

    expect(document.querySelector(".app-brand-mark")).not.toBeNull();
    expect(screen.getByText("Adensa Digital")).toBeInTheDocument();
    expect(screen.getByText("Supply-chain operations")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Command Centre|Daylight/ }),
    ).toBeInTheDocument();
  });
});

describe("ThemeToggle", () => {
  it("flips data-theme, persists the choice, and announces the action", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-pressed", "false");
    expect(button).toHaveTextContent("Command Centre");

    await user.click(button);

    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(button).toHaveTextContent("Daylight");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("adensa-theme")).toBe("dark");

    await user.click(button);

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("adensa-theme")).toBe("light");
  });
});
