# README Design Non-Drift Contract

Date: 2026-06-12

## Context

The README v7 redesign has accumulated several design corrections after the
first implementation: the homepage was still too text-heavy, the hero asset
strategy needed language-specific canonical images, new installs should be
npm-first, and the README must visibly explain `ccb_self` as CCB's built-in
self-understanding expert. These rules should not drift back into older
release-first, rationale-first, or screenshot-late layouts.

This decision stabilizes the public README design direction. It supersedes
older release-first wording in earlier planning notes and should be read before
editing `README_zh.md` or `README.md`.

Related files:

- [../topics/homepage-showcase-polish.md](../topics/homepage-showcase-polish.md)
- [004-homepage-hero-asset-strategy.md](004-homepage-hero-asset-strategy.md)
- [../history/reviewer1-homepage-polish-2026-06-12.md](../history/reviewer1-homepage-polish-2026-06-12.md)

## Decision

The public README first-read path must stay product-first:

1. Product name and one-line positioning.
2. Quiet badges, preferably three and never more than four visible badges.
3. Language switch plus short navigation, including user and developer docs.
4. One dominant canonical hero image from `assets/readme_v7/`.
5. Three compact value points.
6. npm-first Quick Start.
7. Interface tour.
8. Multi-agent rationale and solution comparison.
9. Daily operation, tmux basics, configuration, collaboration, install details,
   FAQ, credits, and release notes.

Stable homepage claims:

- CCB is a visible, controllable multi-agent CLI workspace.
- CCB shows real provider CLIs in real terminal panes.
- CCB can mix Codex, Claude, Gemini, OpenCode, Antigravity, and related
  providers in one project-owned tmux workspace.
- `ccb_self` is CCB's built-in self-understanding expert for usage guidance,
  active layout explanation, config design, runtime diagnostics, recovery, and
  workflow repair.
- New installs should recommend `npm install -g @seemseam/ccb`; subsequent
  updates should use `ccb update`; GitHub release packages and source checkout
  install are fallback/development paths.

## Must Preserve

- Bilingual parity: `README_zh.md` and `README.md` must preserve the same
  section order, asset roles, install path, and `ccb_self` positioning.
- Canonical hero assets: public README hero references should use
  `assets/readme_v7/ccb-hero-zh.png` and
  `assets/readme_v7/ccb-hero-en.png` once generated.
- `assets/ccb-promo.png` remains promotional/reference material unless a later
  decision replaces the canonical hero policy.
- User and developer manual links must remain discoverable near the top:
  `docs/manuals/user-guide/` and `docs/manuals/developer-guide/`.
- The first screen should show CCB before asking readers to process long
  rationale, comparison, config, changelog, or troubleshooting content.
- Advanced explanation should be folded or moved below the first action path
  when it competes with the hero, three values, or Quick Start.

## Must Avoid

- Do not put "Why multi agents" or the long approach comparison before the hero
  and Quick Start.
- Do not re-expand the header to seven badges or let badges dominate the first
  screen.
- Do not return to release-first installation wording as the recommended
  default.
- Do not use `seemseam@ccb` as an npm install command; the verified package
  name is `@seemseam/ccb`.
- Do not tell normal users to update CCB with
  `npm install -g @seemseam/ccb@latest`; after installation, the update command
  is `ccb update`.
- Do not directly use `assets/ccb-promo.png` as the public README hero without
  a replacement decision.
- Do not duplicate multiple large screenshots before Quick Start.
- Do not let release notes, detailed config examples, or tmux reference tables
  dominate the homepage.

## Change Control

Any future patch that changes one of these surfaces must update this decision
or add a replacement decision in the same patch:

- first-screen section order;
- recommended install/update path;
- hero image policy or canonical asset names;
- top navigation/manual links;
- `ccb_self` positioning;
- visible/folded split for rationale, comparison, config, tmux, or release
  notes.

If a future README patch intentionally violates this contract, the patch should
state why the old rule no longer applies and link the replacement decision.

## Drift Checks

Before landing README homepage changes, run or manually verify:

```bash
rg -n "release-first|Release first|Release 优先|seemseam@ccb|@seemseam/ccb@latest|New users should start from a release package|首次安装推荐使用 \\[GitHub Releases\\]" README.md README_zh.md docs/plantree/plans/readme-v7-redesign/README.md docs/plantree/plans/readme-v7-redesign/roadmap.md docs/plantree/plans/readme-v7-redesign/topics
rg -n "@seemseam/ccb|docs/manuals/user-guide|docs/manuals/developer-guide|ccb_self" README.md README_zh.md
git diff --check -- README.md README_zh.md docs/plantree/plans/readme-v7-redesign
```

Expected result:

- no stale release-first default wording;
- npm package name is `@seemseam/ccb`;
- updates use `ccb update`;
- manual links remain present;
- `ccb_self` remains positioned as the built-in CCB expert;
- Markdown diff has no whitespace errors.
