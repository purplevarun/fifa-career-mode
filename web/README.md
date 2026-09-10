# Notts County Career Archive

Minimal Vite/React read-only UI for the validated FIFA career export.

## Run

```sh
cd web
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`.

`predev` runs `sync-data`, which exports the current SQLite data to `web/public/data/career.json` and creates cached WebP previews for the original screenshots. The originals stay in the repository's `raw_data/` folder and are not copied into the web app.

## Views

- Overview with filters, results, form chart, leading scorers and latest evidence.
- Matches with searchable fixture archive and match detail pages.
- Players with appearance, goal, assist, rating and OVR history views.
- Competitions with preseason-aware records and League Two points.
- Career records for transfers and honours.
- Verification for season reconciliation, coverage and unresolved warnings.
- Source images and Data explorer for the complete exported tables.

## Checks

```sh
npm test
npm run lint
npm run build
npm run test:e2e
```

The data tests pass locally. The Playwright suite is included for desktop/mobile regression checks; this corporate environment blocks Playwright browser downloads and the managed Chrome debug launch, so run it in an environment with an available Playwright browser.# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
