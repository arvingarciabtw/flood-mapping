# Repository Instructions

## Architecture

- Single-package SvelteKit app using TypeScript, Svelte 5 runes, MapLibre GL JS, and the Vercel adapter. Use `pnpm@11.20.0`.
- `src/routes/+page.svelte` owns local view state, barangay search, and mobile drawer coordination. `Sidebar.svelte` owns flood information presentation; `MapControls.svelte` remains controlled through callbacks.
- There is no page server load, share-link state, URL synchronization, live feed, or external hazard request.
- `HazardMap.svelte` dynamically imports MapLibre in `onMount`. Keep WebGL and DOM map work browser-only; use `$effect` only to synchronize reactive state with MapLibre.
- Keep map setup and layer managers under `src/lib/map`; keep testable map/data logic in TypeScript covered by Vitest.
- Put separate type-only imports before all value imports in TypeScript and Svelte scripts.

## Commands and Verification

- Verify in order: `pnpm run check`, `pnpm run build`, `pnpm run lint`, `pnpm run test`.
- Deploy through Vercel's Git integration or CLI.
- Browser checks require `pnpm exec playwright install chromium`, then `pnpm run test:browser`. Playwright starts Vite and depends on external map and terrain assets.
- Before treating network-related browser failures as regressions, rerun with `pnpm exec playwright test --workers=1`.
- Focused example: `pnpm exec playwright test tests/browser/map.smoke.spec.ts --workers=1`.

## Data and Provenance

- `pnpm run generate:flood` expects the Metro Manila 5-year NOAH shapefile under `~/downloads/noah/flood/5yr/metro-manila`; override the root with `NOAH_DATA_DIR`.
- Do not hand-edit generated `static/metro-manila-flood-5yr-tiles/`, `metro-manila-flood-summaries.json`, or `flood-data-manifest.json`; use their package scripts.
- Boundary inputs are the pinned OCHA COD-AB city and barangay GeoJSON snapshots under `src/lib/data`.
- Before publishing refreshed data, review source freshness, coverage, licensing, and verification status. Preserve source/date/license notes. `sourceDate` is source metadata; `preparedAt` and `generatedAt` are local timestamps.
- The flood layer is source-provided hazard-proneness data, not a live warning or site-specific building assessment. Keep that distinction clear.

## License

- Keep contributions compatible with `LICENSE` (GPL-3.0).
