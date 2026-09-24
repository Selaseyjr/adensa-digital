"use client";

/**
 * Primary navigation.
 *
 * Client component for one reason only: the active/current-page
 * treatment comes from usePathname(). The list stays semantic
 * (<ul>/<li>) and keyboard-navigable; styling lives in
 * globals.css (.app-nav), which styles the list element itself
 * — the layout applies both classes there.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Control Tower" },
  { href: "/exceptions", label: "Exceptions" },
  { href: "/operations", label: "Operations" },
  { href: "/administration", label: "Administration" },
] as const;

export function AppNav() {
  const pathname = usePathname();

  return (
    <ul className="app-nav app-nav-list">
      {NAV_ITEMS.map((item) => {
        const isCurrent =
          item.href === "/"
            ? pathname === "/"
            : pathname === item.href || pathname.startsWith(`${item.href}/`);

        return (
          <li key={item.href}>
            <Link
              href={item.href}
              aria-current={isCurrent ? "page" : undefined}
            >
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
