# Design: ALES Static Site

**Date:** 2026-02-27
**Status:** Approved

## Goal

A single self-contained `index.html` marketing + developer reference site for the ALES Manufacturing Pipeline. Targets two audiences: Dutch metalworking shops (customers) and developers/contributors.

## Style

- Minimal & clean ("zen")
- Typography-first: large headings, generous whitespace
- Monospace for code, sans-serif for prose
- Palette: `#ffffff` background, `#111111` text, `#0066ff` accent
- No external dependencies, no build step, works offline

## Language

Dutch (primary audience: NL metalworking shops)

## Structure

Single `index.html` with sticky nav (logo + 4 anchor links) and 7 scroll sections:

1. **Hero** — naam, tagline, twee CTAs (GitHub + installatie)
2. **Wat doet het?** — ASCII pipeline diagram
3. **Features** — 6-card grid
4. **Hoe het werkt** — genummerde stappen met code snippets
5. **Gebruik** — tabbladen: Quick / Full / Batch / API
6. **Technisch** — architectuur, modules, sleutelbestanden (voor devs)
7. **Aan de slag** — installatie blok + GitHub link

## Key Decisions

- Single file: zero build, deploy anywhere (GitHub Pages, Netlify, local open)
- No JS frameworks: vanilla HTML/CSS only, with minimal vanilla JS for tabs
- ASCII diagrams from README reused directly
- All content drawn from README.md, CLAUDE.md, ENGINE.md
