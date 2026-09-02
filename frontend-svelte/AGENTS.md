# Svelte Frontend — Development Guide

Ground-up rewrite of the React dashboard in SvelteKit. Lives on the
`feat/svelte-frontend` branch and runs alongside the existing frontend until it
reaches parity; only then does `frontend/` get deleted.

**Status:** early. Foundations only — container, design tokens, routing shell.
No auth, no API layer, no real pages yet. Read "Current state" before assuming
anything exists.

## Non-negotiable: latest SvelteKit, Svelte 5 runes

This is the single easiest thing to get wrong here, because most Svelte material
in circulation — blog posts, Stack Overflow answers, model training data —
describes **Svelte 4**, and it looks superficially correct.

**Always use the newest SvelteKit and Svelte 5.** Verify before assuming:

```bash
bun pm ls | grep -E 'svelte@|@sveltejs'      # what is installed
bun pm view svelte version                    # what is current
```

Verified current as of 2026-09-02 — all four at latest:

| Package | Installed |
| --- | --- |
| `svelte` | 5.57.0 |
| `@sveltejs/kit` | 2.70.3 |
| `@sveltejs/adapter-node` | 5.5.7 |
| `@sveltejs/vite-plugin-svelte` | 7.3.0 |

Runes mode is **forced on** in [vite.config.ts](vite.config.ts) for every file
outside `node_modules`, so the Svelte 4 component API is not merely discouraged
— it does not compile.

### Svelte 4 → 5 translation

If you catch yourself writing anything in the left column, stop.

| Svelte 4 (do not write) | Svelte 5 runes |
| --- | --- |
| `export let foo` | `let { foo } = $props()` |
| `let count = 0` (reactive by position) | `let count = $state(0)` |
| `$: doubled = count * 2` | `const doubled = $derived(count * 2)` |
| `$: { sideEffect() }` | `$effect(() => { sideEffect() })` |
| `on:click={handler}` | `onclick={handler}` |
| `createEventDispatcher()` | callback props: `let { onsave } = $props()` |
| `<slot />` | `{@render children()}` with `let { children } = $props()` |
| `<slot name="header" />` | snippet prop: `{@render header?.()}` |
| `writable()` + `$store` | `$state` inside a `.svelte.ts` module |

Two mechanical traps:

- Runes only work in `.svelte` files and in modules named **`.svelte.ts`**. A
  plain `.ts` file cannot use `$state`; the rune is a compiler feature, not an
  import.
- `svelte/store` still exists and still works. That is a compatibility path, not
  a reason to reach for it. Prefer runes for new state.

### Documentation for agent sessions

`svelte.dev` publishes machine-readable docs — prefer these over recalled
knowledge, which skews Svelte 4:

- <https://svelte.dev/llms.txt> — index of the available sets
- <https://svelte.dev/llms-medium.txt> — abridged, legacy notes stripped
- <https://svelte.dev/docs/kit/llms.txt> — SvelteKit only
- <https://svelte.dev/docs/svelte/llms.txt> — Svelte only

## Relationship to `frontend/` (React)

`frontend/` is the live product and stays on `main`. Do not change it from this
branch.

This is **not a 1:1 port**. The React app is ~29k LOC across 175 files and
carries dead weight: unused SSR infrastructure, endpoint constants for routes
that were never built, three 800+ line components. Reproducing it faithfully
would reproduce that.

What to reuse and what to rethink:

| Layer | Approach |
| --- | --- |
| `src/lib/api/*`, `src/lib/utils/*` | Plain TypeScript, no React. Port selectively — copy what a slice needs, leave the rest. |
| Type definitions (`api/types.ts`) | Copy the types a slice touches. Don't bulk-import all 881 lines. |
| Endpoint constants | Copy per slice. Several in the React version are marked "may not exist in backend yet" — do not carry those over. |
| Components | Rewrite. Do not transliterate JSX. |
| Data fetching hooks | Rewrite. See "Open decisions". |

The backend contract is unchanged, so `frontend/src/lib/api/` is the reference
for endpoint shapes and response types. Read it; don't copy it wholesale.

## Working agreements

These came from the project owner and override general habit.

1. **Just-in-time dependencies.** Do not install a package before the code that
   needs it exists. No "we'll want this later" installs. When you do add one,
   say what it buys and what the alternative was.
2. **Small increments.** One element at a time. Land it, show it, then move on.
   Do not batch a shell, an auth layer and three pages into one change.
3. **Tests alongside the code**, not in a cleanup pass afterwards. The React app
   has three test files, all on utils, and that is the single biggest risk in
   retiring it — do not repeat it here.
4. **Mobile-first.** The React dashboard is effectively unusable on a phone.
   Every layout starts at the small breakpoint and grows, never the reverse.
5. **Explain new concepts** rather than introducing them silently.

## Tech stack

Scaffolded with `sv create` (official Svelte CLI), not hand-written config.

| Concern | Choice |
| --- | --- |
| Framework | SvelteKit 2 / Svelte 5 (runes mode forced on) |
| Build | Vite 8 |
| Language | TypeScript 6, `strict` |
| Styling | Tailwind CSS v4 (no plugins) |
| Adapter | `@sveltejs/adapter-node` |
| Package manager / runtime | Bun 1.4 |
| Unit + component tests | Vitest 4 |
| E2E | Playwright |
| Lint / format | ESLint 10 + Prettier |

### Config lives in `vite.config.ts`

There is **no `svelte.config.js`**. This scaffold puts SvelteKit options —
including `adapter` and `compilerOptions` — inside the `sveltekit()` plugin call
in [vite.config.ts](vite.config.ts). Most SvelteKit documentation and older
answers assume a separate file; they are describing an older layout.

Runes are forced on for all non-`node_modules` files, so `$state`/`$props`/
`$derived` are always available and the legacy `export let` API is not.

## Commands

```bash
bun run dev          # dev server on :3001
bun run build        # production build into build/
bun run preview      # serve the production build
bun run check        # svelte-check — run this before calling anything done
bun run lint         # prettier --check + eslint
bun run format       # prettier --write
bun run test:unit    # vitest (unit + component)
bun run test:e2e     # playwright
bun run test         # both
```

## Testing

The scaffold wires three tiers, distinguished **by filename**. Getting the
suffix wrong sends a test to the wrong runner.

| Pattern | Runner | Use for |
| --- | --- | --- |
| `*.spec.ts` | Vitest, node environment | Pure logic: formatters, parsers, API request building |
| `*.svelte.spec.ts` | Vitest, real Chromium via `vitest-browser-svelte` | Component rendering and interaction |
| `*.e2e.ts` | Playwright against a production build on :4173 | Full flows: login, navigation, a page loading real data |

Component tests run in an actual browser, not jsdom — assert through
`page.getByRole(...)` and await the assertions:

```ts
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

render(MyComponent, { label: 'Save' });
await expect.element(page.getByRole('button', { name: 'Save' })).toBeVisible();
```

`expect.requireAssertions` is on: a test with no assertion fails.

## Design tokens

Defined once in [src/app.css](src/app.css). Components reference semantic names
(`bg-surface`, `text-muted-foreground`), never raw colours.

Colours are **OKLCH**, unlike the React app's HSL. OKLCH lightness is
perceptual, so `0.55` reads as the same brightness at every hue — contrast
becomes predictable and hover/muted states are derived by nudging L rather than
picking a new hex by eye.

Structure:

1. `:root` — light values on `--ow-*` variables.
2. `@media (prefers-color-scheme: dark) :root:not(.light)` — dark overrides.
3. `.dark` — same overrides again, so an explicit class beats the OS setting.
   This is the hook a manual theme toggle will use.
4. `@theme inline` — maps `--ow-*` onto Tailwind's `--color-*` so utilities are
   generated. `inline` matters: it keeps utilities pointing at the variable
   rather than baking in the resolved value.

**The set is deliberately small.** The React app has ~60 colour variables with
`-glow`/`-muted`/`-hover` variants, many unused. Add a token when a component
needs it, and add it to all three theme blocks.

## Docker

| Service | Port | Notes |
| --- | --- | --- |
| `frontend` (React) | 3000 | unchanged |
| `frontend-svelte` | 3001 | this project |

```bash
docker compose watch          # both frontends + backend, with sync
docker compose build frontend-svelte
```

- [Dockerfile.dev](Dockerfile.dev) — Vite dev server, driven by compose sync.
  Sets `DOCKER=1`, which switches Vite's watcher to polling (inotify does not
  fire reliably across the compose sync boundary).
- [Dockerfile](Dockerfile) — two stage, runs `bun ./build/index.js`.

### Environment

`PUBLIC_API_URL` — backend base URL. The `PUBLIC_` prefix is required by
SvelteKit for anything the browser may read.

Read it through `$env/dynamic/public`, never `$env/static/public`. Dynamic keeps
it a **runtime** value, so one prebuilt image can be pointed at any backend
without a rebuild — a property the React app has and we must not lose.

## Current state

```
src/
├── app.css              # design tokens + base styles
├── app.html
├── lib/assets/
└── routes/
    ├── +layout.svelte   # imports app.css
    └── +page.svelte     # TEMPORARY theme-check page — replace
```

`clsx` and `tailwind-merge` are installed but **not yet used** — they were added
ahead of need, against agreement 1. The `cn()` helper that combines them should
land with the first component that accepts a `class` override prop. If that
doesn't happen soon, uninstall them.

## Open decisions

Do not settle these unilaterally; they are the owner's calls.

### Auth transport

The React app stores the JWT in `localStorage`. That is readable by any XSS and
makes SSR useless, since the server never sees the token.

- **A — mirror today:** `localStorage` + `ssr = false`. Zero backend change,
  simplest, matches the current contract exactly.
- **B — `httpOnly` cookie:** SvelteKit server route sets the cookie on login and
  proxies API calls. Token unreachable from JS, SSR becomes viable, faster first
  paint. Costs a node hop on every request and makes the node server
  load-bearing.

Whichever wins, keep it contained in one module so the other stays reachable.

### Data fetching

Not chosen. SvelteKit `load` + `invalidate` covers the first slices with no
dependency. `@tanstack/svelte-query` becomes justified at the first real need —
sync-status polling, optimistic updates, or a cache shared across routes. The
React app has 16 hook files built on react-query, so this will likely be
revisited; wait for the concrete trigger.

### Component primitives

`bits-ui` + `shadcn-svelte` are the equivalents of Radix + shadcn/ui, and the
component mapping is close to 1:1. Not installed yet: buttons, cards, inputs and
badges are plain styled elements. Add them at the first component needing real
focus management — a dialog, select, or dropdown.

## Decision log

Choices already made, with reasons, so they are not re-litigated.

- **SvelteKit over plain Svelte** — 33 route files, nested layouts, an auth
  guard and dynamic segments. Plain Svelte means bolting on a router and losing
  typed routes.
- **`adapter-node`** — matches the container deployment model. Revisit only if
  the app becomes fully static.
- **No `experimental` add-on** (async / remote functions) — moving target, and
  this project is meant to be developed slowly over months.
- **Playwright from day zero** — e2e is the safety net for deleting `frontend/`.
- **Bun** — package manager and runtime. Build still goes through Vite, so the
  gain is install and boot speed, not bundle output.
- **System font stack, not Google Fonts** — the React app blocks first render on
  a `fonts.googleapis.com` stylesheet. If the Inter brand face is wanted,
  self-host it (`@fontsource-variable/inter`) rather than reintroducing the
  external request.

## Baseline measurements

Taken 2026-09-02, for judging whether the rewrite is paying off. React figures
are a full application; Svelte figures are near-empty. They are not a
feature-for-feature comparison — they measure the **floor** each framework
imposes, which is the part that never goes away.

| | React (`frontend/`) | Svelte (foundations only) |
| --- | --- | --- |
| Client JS | 532 KB gzip, 93 chunks | 31 KB gzip, 9 chunks |
| CSS | 137 KB raw / 20 KB gzip | 9.6 KB raw / 2.8 KB gzip |

Re-measure at parity before declaring a win:

```bash
find .svelte-kit/output/client -name '*.js' -exec cat {} + | wc -c
```
