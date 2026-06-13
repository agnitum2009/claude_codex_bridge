# Homepage Hero Asset Strategy

Date: 2026-06-12

## Context

The homepage polish pass introduced `assets/ccb-promo.png`, a generated
annotated promotional screenshot. Reviewer1 identified this as a blocking
pre-implementation choice because the current asset is larger than the existing
README screenshots, contains embedded annotations, and does not fit cleanly
with the existing language-specific README media pattern.

Relevant files:

- `assets/ccb-promo.png`
- `assets/readme_v7/ccb-test2-terminal-annotated.png`
- `assets/readme_v7/ccb-test2-terminal-annotated-en.png`
- [../topics/homepage-showcase-polish.md](../topics/homepage-showcase-polish.md)
- [../history/reviewer1-homepage-polish-2026-06-12.md](../history/reviewer1-homepage-polish-2026-06-12.md)

## Decision

Public READMEs should use canonical language-specific hero assets under
`assets/readme_v7/`.

Planned names:

- `assets/readme_v7/ccb-hero-zh.png` for `README_zh.md`
- `assets/readme_v7/ccb-hero-en.png` for `README.md`

`assets/ccb-promo.png` remains a promotional/reference/social asset and should
not be directly referenced as the public README hero unless a later decision
replaces this policy.

## Consequences

- The next README implementation patch must generate or optimize the canonical
  hero images before changing README references.
- The first-screen hero may reuse the `assets/ccb-promo.png` composition, but
  final assets must live under `assets/readme_v7/` and handle Chinese/English
  parity explicitly.
- Existing `ccb-test2-terminal-annotated*.png` assets remain useful fallback or
  UI Tour detail images.
- README headers should reduce the current badge set to at most four visible
  badges, preferably version, platform, and providers.
- If the hero is strongly annotated, the UI Tour should avoid repeating another
  large screenshot before Quick Start.
