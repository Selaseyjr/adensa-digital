"use client";

/**
 * Manager Lookup (Command Centre v2): the entry point for a
 * manager question about a shipment, exception or operational
 * situation. Shipment/exception identifiers are first-class:
 * the input's own grammar matches the domain's identifier
 * vocabulary, and the entry point is styled as operational
 * command — "Ask about a shipment…" — not a search box.
 *
 * This milestone ships the UX entry point only. The future
 * Advisor capability plugs in at exactly one seam, marked
 * ADVISOR INTEGRATION POINT below: the submitted identifier
 * resolves locally today (EXC-* into the investigation
 * workspace; anything else into the Exception Inbox search,
 * whose haystack already covers IDs, shipment, order, type,
 * location, impact and mode) — no AI backend is invented.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

export function ManagerLookup() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    if (value === "") return;

    // ADVISOR INTEGRATION POINT: a future Advisor backend takes
    // the raw manager question here. Until it exists, the
    // identifier routes through the real operational surfaces.
    if (/^EXC-\d+$/i.test(value)) {
      router.push(`/exceptions/${encodeURIComponent(value.toUpperCase())}`);
      return;
    }
    router.push(`/exceptions?q=${encodeURIComponent(value)}`);
  }

  return (
    <section className="manager-lookup" aria-labelledby="manager-lookup-title">
      <h2 id="manager-lookup-title" className="manager-lookup-title">
        Ask about a shipment, exception, or operational situation
      </h2>
      <form className="manager-lookup-form" onSubmit={submit} role="search">
        <label className="visually-hidden" htmlFor="manager-lookup-input">
          Shipment or exception identifier, or a location or mode
        </label>
        <input
          id="manager-lookup-input"
          className="manager-lookup-input"
          type="text"
          name="lookup"
          autoComplete="off"
          placeholder="EXC-001529 · SHP-001529 · a location, mode or order"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="action-button manager-lookup-submit" type="submit">
          Look up
        </button>
      </form>
      <p className="manager-lookup-note">
        Exception identifiers open their investigation workspace directly;
        anything else searches the Exception Inbox.
      </p>
    </section>
  );
}
