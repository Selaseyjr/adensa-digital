"use client";

/**
 * In-page section index for the Investigation Workspace.
 *
 * The section list is computed by the Server Component page
 * from the sections that actually rendered — the index never
 * links to a nonexistent anchor. Active-section tracking is
 * the component's only client state: an IntersectionObserver
 * marks the topmost visible section, and the active link
 * exposes `aria-current="location"`. No state-management
 * library, no scroll hijacking, no animation — the observer
 * is re-created per section-list identity and cleaned up on
 * unmount. Keyboard behavior is native anchor navigation.
 */

import { useEffect, useState } from "react";

export interface WorkspaceSectionRef {
  id: string;
  label: string;
}

export function WorkspaceSectionIndex({
  sections,
}: {
  sections: WorkspaceSectionRef[];
}) {
  const [activeId, setActiveId] = useState<string | null>(
    sections.length > 0 ? sections[0].id : null,
  );

  useEffect(() => {
    if (sections.length === 0) {
      return;
    }

    const elements = sections
      .map((section) => document.getElementById(section.id))
      .filter((element): element is HTMLElement => element !== null);

    if (elements.length === 0) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        // Mark the topmost currently-intersecting section as
        // active; if none intersect, keep the last known.
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      // A slim horizontal band near the top of the viewport:
      // the section whose heading has entered the reading
      // position becomes active.
      { rootMargin: "-72px 0px -78% 0px", threshold: 0 },
    );

    for (const element of elements) {
      observer.observe(element);
    }

    return () => observer.disconnect();
  }, [sections]);

  if (sections.length === 0) {
    return null;
  }

  return (
    <nav className="workspace-index" aria-label="Workspace sections">
      <ul className="workspace-index-list">
        {sections.map((section) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              className="workspace-index-link"
              aria-current={activeId === section.id ? "location" : undefined}
            >
              {section.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
