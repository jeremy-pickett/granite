# Claude Work History

## 2026-03-30 — Homepage CSS Fixes

### Problems
1. **Architecture button contrast**: The "The Architecture" `.btn-primary` link had text and background that appeared the same color in its default (unpressed) state. Root cause: `color: var(--ink)` (#1C1810) was not overriding the anchor tag's inherited `color: var(--amber)`, making it amber text on an amber background.
2. **Excessive vertical negative space**: Padding, margins, and gaps throughout the homepage were roughly double what they needed to be.
3. **Pipeline boxes too large**: The Embed / Compress / Detect / Attribute step boxes and their fonts were oversized.

### Changes Made

**style.css**
- Button fix: changed `.btn-primary` color from `var(--ink)` to `var(--void)` (#07090F) and added an `a.btn-primary` selector to override link color cascade. Added matching hover rule for `a.btn-primary:hover`.
- Section padding: `.section` 6rem -> 3rem, `.section-what` 6rem -> 3rem padding and gap.
- Hero copy padding: 5rem/3rem top/bottom -> 2.5rem/1.5rem.
- Score strip: padding 2rem/3rem -> 1rem/1.5rem, gap 3rem -> 1.5rem.
- Typography spacing: h2 margin 1rem -> 0.5rem, `.lead` margin 2.5rem -> 1.25rem, eyebrow margin 2.2rem -> 1.1rem, subtitle margin 3.5rem -> 1.75rem, tagline margin 3rem -> 1.5rem, quote margin 3.5rem -> 1.75rem.
- Pipeline boxes: min-width 12rem -> 9rem, max-width 16rem -> 12rem, padding 1.5rem -> 0.75rem. Added `h3` rule at 1rem font. Paragraph font 0.9rem -> 0.75rem with tighter line-height.
- Step number circles: 2.5rem -> 1.75rem, font 1.1rem -> 0.85rem, margin 0.75rem -> 0.4rem.
- Pipeline margin: 3rem -> 1.5rem.
- Fuse & Fire: margin-top 3rem -> 1.5rem, padding 2rem -> 1rem.
- Results headline: gap 2rem -> 1rem, margin 3rem -> 1.5rem, stat padding 2rem -> 1rem.
- Results chart / states visual / sub-headers: margins halved from 3rem to 1.5rem.
- Layers section: gap 1.5rem -> 0.75rem, margin-top 2rem -> 1rem, layer padding 1.5rem -> 0.75rem, layer gap 1.5rem -> 1rem.
- Footer: padding 3rem -> 1.5rem, gap 2rem -> 1rem.

**index.html**
- Deep Dives heading inline margin: 4rem -> 2rem.
- Known Limitations grid inline margin: 1rem -> 0.5rem.
- Deep Dives grid inline margin: 1.5rem -> 0.75rem.
- Cache-buster bumped: `style.css?v=4` -> `?v=5`.
