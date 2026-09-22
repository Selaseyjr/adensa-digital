/**
 * Render a page component inside the real shell markup so
 * tests exercise the navigation contract together with the
 * surface under test.
 */

import { render } from "@testing-library/react";
import RootLayout from "@/app/layout";

export function renderInShell(ui: React.ReactElement) {
  return render(<RootLayout>{ui}</RootLayout>);
}
