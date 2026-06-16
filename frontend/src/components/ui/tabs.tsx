// tabs.tsx — Labeler tab strip, built on pdomain-ui primitives.
//
// Composition strategy (Slice 5):
//   - Re-export pdomain-ui's Tabs/TabsList/TabsTrigger/TabsContent directly.
//   - pdomain-ui's TabsList adds '.tabs', TabsTrigger adds '.tab'.
//   - primitives.css has .tab[data-state='active'] bridge so active state works
//     without any Tailwind data-attribute selectors.
//   - Count badges: wrap content in <span className="badge"> — primitives.css
//     provides .tab .badge and .tab[data-state='active'] .badge styling.
//   - appearance prop (pdui): default | underline. Labeler uses 'underline'
//     for the detail-panel tab strips (LineDetail, BlockDetail).
//   - All labeler data-testids pass through via ...props.
//
// @radix-ui/react-tabs dep removed — pdomain-ui bundles Radix internally.
export { Tabs, TabsList, TabsTrigger, TabsContent } from "@pdomain/pdomain-ui/primitives";
