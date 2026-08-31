# VALORANT Scout — Design System

Generated from [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) guidelines for **Gaming / Esports Analytics**.

## Pattern

**Dashboard + Comparison Cards** — data-first layout with player roster grid, system status strip, and side-by-side stat comparison.

## Style

**Dark Tactical UI** — high contrast, subtle depth, sharp geometry. Esports broadcast feel without neon overload.

- Keywords: tactical, data-dense, competitive, precise, broadcast-ready
- Effects: soft panel borders, accent glow on hover, 150ms transitions
- Avoid: AI purple/pink gradients, emoji icons, harsh animations, decorative clutter

## Colors

| Token | Value | Usage |
| --- | --- | --- |
| `--background` | `#0B0D10` | Page background |
| `--surface` | `#12161D` | Cards, panels |
| `--surface-raised` | `#1A2030` | Elevated panels |
| `--foreground` | `#ECE8E1` | Primary text |
| `--muted` | `#8B95A5` | Secondary text |
| `--accent` | `#FF4655` | Valorant red — CTAs, highlights |
| `--accent-soft` | `rgba(255, 70, 85, 0.12)` | Accent backgrounds |
| `--success` | `#3DDC97` | Positive stats, online |
| `--warning` | `#F5A623` | Degraded state |
| `--border` | `rgba(255, 255, 255, 0.08)` | Panel borders |

## Typography

- **Display / headings:** Barlow Condensed (600–700)
- **Body:** DM Sans (400–600)
- **Stats / mono:** JetBrains Mono (400–500)

## Components

- **Player card:** region + rating badge, name, team, 2×2 stat grid, hover border accent
- **Status badge:** semantic color + icon (not color alone)
- **Stat cell:** label above, mono value below
- **System panel:** compact info grid for API / DB / provider

## Pre-delivery checklist

- [x] SVG icons only (Lucide-style inline SVG)
- [x] `cursor-pointer` on interactive elements
- [x] Visible focus rings for keyboard nav
- [x] `prefers-reduced-motion` respected
- [x] Text contrast ≥ 4.5:1 on body copy
- [x] Responsive: 375px, 768px, 1024px, 1440px
