"use client";

/**
 * Primary navigation (Command Centre v2).
 *
 * The header carries the Adensa identity and one environment
 * control; product navigation lives behind a single menu
 * button on every width — compact header, no crowded middle.
 * The list stays semantic (<ul>/<li>) and the panel closes on
 * Escape and outside pointer activation.
 *
 * Information architecture (Command Centre v2): the four
 * shipped operational surfaces under "Command Centre"; the
 * major product areas of the target IA (Analyst, Recovery
 * Assistant, Advisor, Sustainability) are listed as the
 * clearly-marked *Planned* areas they are — no placeholder
 * routes, no invented features.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const COMMAND_CENTRE_LINKS = [
  { href: "/", label: "Command Centre" },
  { href: "/exceptions", label: "Exceptions" },
  { href: "/operations", label: "Operations" },
  { href: "/administration", label: "Administration" },
] as const;

const PLANNED_AREAS = [
  "Analyst",
  "Recovery Assistant",
  "Advisor",
  "Sustainability",
] as const;

export function AppNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement>(null);

  // Close the panel when the route changes (keyboard and
  // pointer navigation both land here).
  useEffect(() => {
    setOpen(false);
    detailsRef.current?.removeAttribute("open");
  }, [pathname]);

  // Escape closes and returns focus to the menu button.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && detailsRef.current?.open) {
        setOpen(false);
        detailsRef.current.removeAttribute("open");
        detailsRef.current
          .querySelector("summary")
          ?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Pointer-down outside the panel closes it (event-delegation
  // keeps one listener for the component's lifetime).
  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      if (
        detailsRef.current?.open &&
        event.target instanceof Node &&
        !detailsRef.current.contains(event.target)
      ) {
        setOpen(false);
        detailsRef.current.removeAttribute("open");
      }
      if (open) {
        const stillOpen = detailsRef.current?.open;
        if (!stillOpen) setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  const isCurrent = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <details className="app-nav" ref={detailsRef}>
      <summary
        aria-label={open ? "Close navigation" : "Open navigation"}
        aria-expanded={open}
        onClick={() => {
          // The click dispatches before the browser's default
          // toggle action, so the ref still holds the pre-click
          // state — the inverse is the state after the toggle.
          // This keeps aria-expanded in lockstep with the
          // native <details> behaviour (onToggle timing is not
          // reliable across renderers).
          setOpen(!detailsRef.current?.open);
        }}
      >
        <span className="app-nav-burger" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span className="app-nav-label">Menu</span>
      </summary>
      <div className="app-nav-panel">
        <p className="app-nav-group-title">Command Centre</p>
        <ul className="app-nav-list">
          {COMMAND_CENTRE_LINKS.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={isCurrent(item.href) ? "page" : undefined}
                onClick={() => {
                  setOpen(false);
                  detailsRef.current?.removeAttribute("open");
                }}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
        <p className="app-nav-group-title app-nav-group-title-planned">
          Planned product areas
        </p>
        <ul className="app-nav-list app-nav-list-planned">
          {PLANNED_AREAS.map((label) => (
            <li key={label}>
              <span aria-disabled="true">{label}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}
