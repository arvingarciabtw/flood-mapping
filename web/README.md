# Metro Manila Flood Map

A flood-only map for Manila, Pasig, and Marikina using the UP NOAH 5-year
return-period dataset.

## Stack

- SvelteKit, Svelte 5, TypeScript, and Vite
- MapLibre GL JS
- Vanilla CSS
- Vercel via the SvelteKit Vercel adapter
- pnpm, Vitest, and Playwright

## Development

```bash
pnpm install
pnpm run generate:flood
pnpm run dev
```

The generator reads the default source from
`~/downloads/noah/flood/5yr/metro-manila`. Set `NOAH_DATA_DIR` to use another
NOAH data root.

Run checks in this order:

```bash
pnpm run check
pnpm run build
pnpm run lint
pnpm run test
```

## Data

- Flood data: UP NOAH, Metro Manila 5-year return period
- City and barangay boundaries: OCHA Philippines COD-AB v03
- Base map: OpenFreeMap Liberty
- Elevation: Mapzen Terrain Tiles

The `Var` values are displayed as Mild, Moderate, and Severe. This map shows
modeled flood hazard information, not a live flood warning or a guarantee of
future flooding.
