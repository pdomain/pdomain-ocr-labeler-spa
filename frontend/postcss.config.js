// PostCSS pipeline for Tailwind 4. Vite picks this up automatically — no
// `css.postcss` reference in vite.config.ts is required. ESM to match
// `"type": "module"` in package.json.
//
// Tailwind 4 ships its own PostCSS plugin package and handles vendor
// prefixing itself, so `autoprefixer` is no longer in the pipeline.
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
