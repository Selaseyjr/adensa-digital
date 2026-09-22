/**
 * Application-shell contract: brand, the four product
 * sections in the navigation, and the human-in-the-loop
 * statement. The shell renders without any API.
 *
 * RootLayout renders <html>/<body>, which React Testing
 * Library tolerates in jsdom; each test cleans up before the
 * next mounts a fresh shell.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen, within } from "@testing-library/react";
import { render } from "@testing-library/react";
import RootLayout from "@/app/layout";

afterEach(() => cleanup());

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
