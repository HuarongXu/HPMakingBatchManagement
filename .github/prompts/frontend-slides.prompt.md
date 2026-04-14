---
description: "Create stunning, animation-rich HTML presentations from scratch. Zero dependencies, viewport-fitted, with visual style discovery. Use when the user wants to build a presentation or create slides for a talk/pitch."
---

# Frontend Slides — VS Code Copilot Prompt

Create zero-dependency, animation-rich HTML presentations that run entirely in the browser.

---

## Core Principles

1. **Zero Dependencies** — Single HTML files with inline CSS/JS. No npm, no build tools.
2. **Show, Don't Tell** — Generate visual previews, not abstract choices. People discover what they want by seeing it.
3. **Distinctive Design** — No generic "AI slop." Every presentation must feel custom-crafted.
4. **Viewport Fitting (NON-NEGOTIABLE)** — Every slide MUST fit exactly within 100vh. No scrolling within slides, ever. Content overflows? Split into multiple slides.

---

## Design Aesthetics

Avoid convergence toward generic, "on distribution" outputs. Make creative, distinctive frontends that surprise and delight.

Focus on:

- **Typography**: Choose fonts that are beautiful, unique, and interesting. Avoid generic fonts like Arial and Inter; opt for distinctive choices that elevate aesthetics. Source from **Fontshare** or **Google Fonts** — never system fonts.
- **Color & Theme**: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes.
- **Motion**: Use CSS animations for effects and micro-interactions. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (`animation-delay`) creates more delight than scattered micro-interactions.
- **Backgrounds**: Create atmosphere and depth rather than solid colors. Layer CSS gradients, use geometric patterns, or add contextual effects.

**Avoid these generic AI patterns:**

- Overused font families (Inter, Roboto, Arial, system fonts)
- Cliched color schemes (purple gradients on white)
- Predictable layouts and component patterns
- Colors: `#6366f1` (generic indigo)
- Everything centered, generic hero sections, identical card grids
- Gratuitous glassmorphism, drop shadows without purpose

---

## Workflow

### Step 1: Understand the Request

Gather from the user:

1. **Purpose** — Pitch deck / Teaching-Tutorial / Conference talk / Internal presentation
2. **Length** — Short (5-10 slides) / Medium (10-20) / Long (20+)
3. **Content** — All content ready / Rough notes / Topic only

If the user has content ready, ask them to share it.

### Step 2: Generate 3 Style Previews (MANDATORY)

**This is the "show, don't tell" phase. Always generate 3 previews — never skip this step.**

Based on the user's content and purpose, select 3 **visually distinct** style presets from the **Style Presets Reference** below. The 3 presets MUST differ in:
- Light vs Dark theme (at least one of each)
- Typography personality (serif vs sans-serif vs mono)
- Visual energy level (bold/dynamic vs calm/elegant)

Use this mood-to-preset mapping as a guide:

| Mood | Suggested Presets |
|------|-------------------|
| Impressed / Confident | Bold Signal, Electric Studio, Dark Botanical |
| Excited / Energized | Creative Voltage, Neon Cyber, Split Pastel |
| Calm / Focused | Notebook Tabs, Paper & Ink, Swiss Modern |
| Inspired / Moved | Dark Botanical, Vintage Editorial, Pastel Geometry |

**For each of the 3 styles, generate a complete, self-contained single-slide HTML file** (50-80 lines) that shows:
- The actual presentation title with real content (not placeholder text)
- Typography, colors, animation, layout, and overall aesthetic
- Signature visual elements of that preset (patterns, shapes, accents)

Save the 3 preview files to the project's output folder:
- `style-preview-A-[PresetName].html`
- `style-preview-B-[PresetName].html`
- `style-preview-C-[PresetName].html`

**Open all 3 previews** in Simple Browser for the user to compare.

Then ask: "Which style do you prefer? A / B / C / Mix elements from multiple"

**Wait for the user to choose before proceeding to Step 3.**

### Step 3: Generate Full Presentation

After the user picks a style, generate the full presentation:

- **Single self-contained HTML file**, all CSS/JS inline
- **Include the FULL contents of the Viewport Base CSS** (below) in the `<style>` block
- Use fonts from **Fontshare** or **Google Fonts** — never system fonts
- Add detailed comments explaining each section: `/* === SECTION NAME === */`
- Apply the chosen style preset's CSS variables, font pairings, and signature elements
- If the user provided images, design slides around them. If not, use CSS-generated visuals (gradients, shapes, patterns)
- Clean up the 3 preview files after generating the final presentation

### Step 4: Deliver

Tell the user:
- File location and slide count
- Navigation: Arrow keys, Space, scroll/swipe, click nav dots
- How to customize: `:root` CSS variables for colors, font link for typography, `.reveal` class for animations

---

## Viewport Fitting Rules

These invariants apply to EVERY slide in EVERY presentation:

- Every `.slide` must have `height: 100vh; height: 100dvh; overflow: hidden;`
- ALL font sizes and spacing must use `clamp(min, preferred, max)` — never fixed px/rem
- Content containers need `max-height` constraints
- Images: `max-height: min(50vh, 400px)`
- Breakpoints required for heights: 700px, 600px, 500px
- Include `prefers-reduced-motion` support
- Never negate CSS functions directly (`-clamp()`, `-min()`, `-max()` are silently ignored) — use `calc(-1 * clamp(...))` instead

### Content Density Limits Per Slide

| Slide Type | Maximum Content |
|------------|----------------|
| Title slide | 1 heading + 1 subtitle + optional tagline |
| Content slide | 1 heading + 4-6 bullet points OR 1 heading + 2 paragraphs |
| Feature grid | 1 heading + 6 cards maximum (2×3 or 3×2) |
| Code slide | 1 heading + 8-10 lines of code |
| Quote slide | 1 quote (max 3 lines) + attribution |
| Image slide | 1 heading + 1 image (max 60vh height) |

**Content exceeds limits? Split into multiple slides. Never cram, never scroll.**

---

## Modification Rules (Enhancing Existing Slides)

When enhancing existing presentations:

1. **Before adding content:** Count existing elements, check against density limits
2. **Adding images:** Must have `max-height: min(50vh, 400px)`. If slide already has max content, split into two slides
3. **Adding text:** Max 4-6 bullets per slide. Exceeds limits? Split into continuation slides
4. **After ANY modification:** Verify `.slide` has `overflow: hidden`, new elements use `clamp()`, images have viewport-relative max-height, content fits at 1280×720
5. **Proactively reorganize:** If modifications will cause overflow, automatically split content and inform the user

---

## HTML Template Structure

Every generated presentation MUST follow this architecture:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[Presentation Title]</title>

    <!-- === FONTS === -->
    <!-- Load from Google Fonts or Fontshare -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=[Display+Font]:wght@700;900&family=[Body+Font]:wght@400;500&display=swap" rel="stylesheet">

    <style>
        /* === VIEWPORT BASE (MANDATORY) === */
        /* Paste full viewport-base.css contents here */

        /* === THEME VARIABLES === */
        :root {
            /* Preset colors, fonts, spacing */
        }

        /* === GLOBAL STYLES === */

        /* === NAVIGATION === */

        /* === SLIDE STYLES === */

        /* === ANIMATIONS === */
        @keyframes fadeInUp { /* ... */ }
        @keyframes slideInLeft { /* ... */ }

        /* === RESPONSIVE OVERRIDES === */
    </style>
</head>
<body>

    <!-- === NAVIGATION DOTS === -->
    <nav class="nav-dots" aria-label="Slide navigation">
        <button class="dot active" data-slide="0" aria-label="Slide 1"></button>
        <!-- one dot per slide -->
    </nav>

    <!-- === SLIDE 1: TITLE === -->
    <section class="slide slide-title" id="slide-0">
        <div class="slide-content">
            <!-- Content here -->
        </div>
    </section>

    <!-- === SLIDE 2: CONTENT === -->
    <section class="slide slide-content-type" id="slide-1">
        <div class="slide-content">
            <!-- Content here -->
        </div>
    </section>

    <!-- More slides... -->

    <script>
        /* === KEYBOARD NAVIGATION === */
        /* === SCROLL/TOUCH NAVIGATION === */
        /* === NAV DOT SYNC === */
        /* === INTERSECTION OBSERVER FOR ANIMATIONS === */
        /* === INLINE EDITING (if enabled) === */
    </script>
</body>
</html>
```

### Required JS Features

- **Keyboard navigation**: Arrow Up/Down, Left/Right, Space, Page Up/Down
- **Scroll snap**: CSS `scroll-snap-type: y mandatory` on html
- **Nav dots**: Auto-sync with current visible slide via IntersectionObserver
- **Animation triggers**: `.reveal` class elements animate on intersection
- **Optional inline editing**: Press E or hover top-left to toggle contenteditable, Ctrl+S to save to localStorage

---

## Animation Patterns

### Effect-to-Feeling Guide

| Feeling | Recommended Animations |
|---------|----------------------|
| Professional / Confident | Smooth fade-in + subtle slide-up, staggered card reveals |
| Energetic / Exciting | Slide-in from sides, scale-up bounces, letter-by-letter typing |
| Calm / Focused | Slow fade-in (800ms+), gentle parallax, opacity transitions |
| Playful / Creative | Rotate-in, bouncy spring easing, staggered color reveals |

### Core CSS Animations

```css
/* Fade in + rise */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Slide from left */
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-50px); }
    to { opacity: 1; transform: translateX(0); }
}

/* Slide from right */
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(50px); }
    to { opacity: 1; transform: translateX(0); }
}

/* Scale up */
@keyframes scaleIn {
    from { opacity: 0; transform: scale(0.8); }
    to { opacity: 1; transform: scale(1); }
}

/* Typewriter effect (for headings) */
@keyframes typewriter {
    from { width: 0; }
    to { width: 100%; }
}

/* Pulse glow (for accents) */
@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 20px rgba(var(--accent-rgb), 0.3); }
    50% { box-shadow: 0 0 40px rgba(var(--accent-rgb), 0.6); }
}
```

### Staggered Reveal Pattern

```css
.reveal { opacity: 0; transform: translateY(20px); }
.reveal.visible { animation: fadeInUp 0.6s ease forwards; }
.reveal:nth-child(1) { animation-delay: 0.1s; }
.reveal:nth-child(2) { animation-delay: 0.2s; }
.reveal:nth-child(3) { animation-delay: 0.3s; }
.reveal:nth-child(4) { animation-delay: 0.4s; }
.reveal:nth-child(5) { animation-delay: 0.5s; }
.reveal:nth-child(6) { animation-delay: 0.6s; }
```

### IntersectionObserver Trigger

```js
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
        }
    });
}, { threshold: 0.1 });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
```

---

## Style Presets Reference

### Dark Themes

#### 1. Bold Signal
- **Vibe:** Confident, bold, modern, high-impact
- **Fonts:** `Archivo Black` (900) + `Space Grotesk` (400/500) — Google
- **Colors:**
  ```css
  --bg-primary: #1a1a1a;
  --bg-gradient: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 50%, #1a1a1a 100%);
  --card-bg: #FF5722;
  --text-primary: #ffffff;
  --text-on-card: #1a1a1a;
  ```
- **Signature:** Bold colored card as focal point, large section numbers (01, 02), nav breadcrumbs, grid-based layout

#### 2. Electric Studio
- **Vibe:** Bold, clean, professional, high contrast
- **Fonts:** `Manrope` (800 / 400) — Google
- **Colors:**
  ```css
  --bg-dark: #0a0a0a;
  --bg-white: #ffffff;
  --accent-blue: #4361ee;
  --text-dark: #0a0a0a;
  --text-light: #ffffff;
  ```
- **Signature:** Two-panel vertical split, accent bar on panel edge, quote typography as hero, minimal spacing

#### 3. Creative Voltage
- **Vibe:** Bold, creative, energetic, retro-modern
- **Fonts:** `Syne` (700/800) + `Space Mono` (400/700) — Google
- **Colors:**
  ```css
  --bg-primary: #0066ff;
  --bg-dark: #1a1a2e;
  --accent-neon: #d4ff00;
  --text-light: #ffffff;
  ```
- **Signature:** Electric blue + neon yellow contrast, halftone textures, neon badges, script typography

#### 4. Dark Botanical
- **Vibe:** Elegant, sophisticated, artistic, premium
- **Fonts:** `Cormorant` (400/600) + `IBM Plex Sans` (300/400) — Google
- **Colors:**
  ```css
  --bg-primary: #0f0f0f;
  --text-primary: #e8e4df;
  --text-secondary: #9a9590;
  --accent-warm: #d4a574;
  --accent-pink: #e8b4b8;
  --accent-gold: #c9b896;
  ```
- **Signature:** Abstract soft gradient circles (blurred, overlapping), warm accents (pink, gold, terracotta), thin vertical accent lines, italic signature typography. **No illustrations — only abstract CSS shapes.**

### Light Themes

#### 5. Notebook Tabs
- **Vibe:** Editorial, organized, elegant, tactile
- **Fonts:** `Bodoni Moda` (400/700) + `DM Sans` (400/500) — Google
- **Colors:**
  ```css
  --bg-outer: #2d2d2d;
  --bg-page: #f8f6f1;
  --text-primary: #1a1a1a;
  --tab-1: #98d4bb; /* Mint */
  --tab-2: #c7b8ea; /* Lavender */
  --tab-3: #f4b8c5; /* Pink */
  --tab-4: #a8d8ea; /* Sky */
  --tab-5: #ffe6a7; /* Cream */
  ```
- **Signature:** Paper container with subtle shadow, colorful section tabs on right edge (vertical text), binder hole decorations. Tab text: `font-size: clamp(0.5rem, 1vh, 0.7rem)`

#### 6. Pastel Geometry
- **Vibe:** Friendly, organized, modern, approachable
- **Fonts:** `Plus Jakarta Sans` (700/800 + 400/500) — Google
- **Colors:**
  ```css
  --bg-primary: #c8d9e6;
  --card-bg: #faf9f7;
  --pill-pink: #f0b4d4;
  --pill-mint: #a8d4c4;
  --pill-sage: #5a7c6a;
  --pill-lavender: #9b8dc4;
  --pill-violet: #7c6aad;
  ```
- **Signature:** Rounded card with soft shadow, vertical pills on right edge with varying heights

#### 7. Split Pastel
- **Vibe:** Playful, modern, friendly, creative
- **Fonts:** `Outfit` (700/800 + 400/500) — Google
- **Colors:**
  ```css
  --bg-peach: #f5e6dc;
  --bg-lavender: #e4dff0;
  --text-dark: #1a1a1a;
  --badge-mint: #c8f0d8;
  --badge-yellow: #f0f0c8;
  --badge-pink: #f0d4e0;
  ```
- **Signature:** Split background colors, playful badge pills with icons, grid pattern overlay, rounded CTA buttons

#### 8. Vintage Editorial
- **Vibe:** Witty, confident, editorial, personality-driven
- **Fonts:** `Fraunces` (700/900) + `Work Sans` (400/500) — Google
- **Colors:**
  ```css
  --bg-cream: #f5f3ee;
  --text-primary: #1a1a1a;
  --text-secondary: #555;
  --accent-warm: #e8d4c0;
  ```
- **Signature:** Abstract geometric shapes (circle outline + line + dot), bold bordered CTA boxes, witty conversational copy. **No illustrations — only geometric CSS shapes.**

### Specialty Themes

#### 9. Neon Cyber
- **Vibe:** Futuristic, techy, confident
- **Fonts:** `Clash Display` + `Satoshi` — Fontshare
- **Colors:** Deep navy `#0a0f1c`, cyan accent `#00ffcc`, magenta `#ff00aa`
- **Signature:** Particle backgrounds, neon glow, grid patterns

#### 10. Terminal Green
- **Vibe:** Developer-focused, hacker aesthetic
- **Fonts:** `JetBrains Mono` (monospace only) — JetBrains
- **Colors:** GitHub dark `#0d1117`, terminal green `#39d353`
- **Signature:** Scan lines, blinking cursor, code syntax styling

#### 11. Swiss Modern
- **Vibe:** Clean, precise, Bauhaus-inspired
- **Fonts:** `Archivo` (800) + `Nunito` (400) — Google
- **Colors:** Pure white, pure black, red accent `#ff3300`
- **Signature:** Visible grid, asymmetric layouts, geometric shapes

#### 12. Paper & Ink
- **Vibe:** Editorial, literary, thoughtful
- **Fonts:** `Cormorant Garamond` + `Source Serif 4` — Google
- **Colors:** Warm cream `#faf9f7`, charcoal `#1a1a1a`, crimson accent `#c41e3a`
- **Signature:** Drop caps, pull quotes, elegant horizontal rules

---

## Viewport Base CSS (MANDATORY — Include in Full)

```css
/* =========================================
   VIEWPORT FITTING: MANDATORY BASE STYLES
   Include this ENTIRE block in every presentation.
   ========================================= */

/* 1. Lock html/body to viewport */
html, body {
    height: 100%;
    overflow-x: hidden;
}

html {
    scroll-snap-type: y mandatory;
    scroll-behavior: smooth;
}

/* 2. Each slide = exact viewport height */
.slide {
    width: 100vw;
    height: 100vh;
    height: 100dvh;
    overflow: hidden;
    scroll-snap-align: start;
    display: flex;
    flex-direction: column;
    position: relative;
}

/* 3. Content container with flex for centering */
.slide-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    max-height: 100%;
    overflow: hidden;
    padding: var(--slide-padding);
}

/* 4. ALL typography uses clamp() for responsive scaling */
:root {
    --title-size: clamp(1.5rem, 5vw, 4rem);
    --h2-size: clamp(1.25rem, 3.5vw, 2.5rem);
    --h3-size: clamp(1rem, 2.5vw, 1.75rem);
    --body-size: clamp(0.75rem, 1.5vw, 1.125rem);
    --small-size: clamp(0.65rem, 1vw, 0.875rem);
    --slide-padding: clamp(1rem, 4vw, 4rem);
    --content-gap: clamp(0.5rem, 2vw, 2rem);
    --element-gap: clamp(0.25rem, 1vw, 1rem);
}

/* 5. Cards/containers use viewport-relative max sizes */
.card, .container, .content-box {
    max-width: min(90vw, 1000px);
    max-height: min(80vh, 700px);
}

/* 6. Lists auto-scale with viewport */
.feature-list, .bullet-list {
    gap: clamp(0.4rem, 1vh, 1rem);
}
.feature-list li, .bullet-list li {
    font-size: var(--body-size);
    line-height: 1.4;
}

/* 7. Grids adapt to available space */
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
    gap: clamp(0.5rem, 1.5vw, 1rem);
}

/* 8. Images constrained to viewport */
img, .image-container {
    max-width: 100%;
    max-height: min(50vh, 400px);
    object-fit: contain;
}

/* =========================================
   RESPONSIVE BREAKPOINTS
   ========================================= */

/* Short viewports (< 700px height) */
@media (max-height: 700px) {
    :root {
        --slide-padding: clamp(0.75rem, 3vw, 2rem);
        --content-gap: clamp(0.4rem, 1.5vw, 1rem);
        --title-size: clamp(1.25rem, 4.5vw, 2.5rem);
        --h2-size: clamp(1rem, 3vw, 1.75rem);
    }
}

/* Very short viewports (< 600px height) */
@media (max-height: 600px) {
    :root {
        --slide-padding: clamp(0.5rem, 2.5vw, 1.5rem);
        --content-gap: clamp(0.3rem, 1vw, 0.75rem);
        --title-size: clamp(1.1rem, 4vw, 2rem);
        --body-size: clamp(0.7rem, 1.2vw, 0.95rem);
    }
    .nav-dots, .keyboard-hint, .decorative {
        display: none;
    }
}

/* Extremely short (landscape phones, < 500px height) */
@media (max-height: 500px) {
    :root {
        --slide-padding: clamp(0.4rem, 2vw, 1rem);
        --title-size: clamp(1rem, 3.5vw, 1.5rem);
        --h2-size: clamp(0.9rem, 2.5vw, 1.25rem);
        --body-size: clamp(0.65rem, 1vw, 0.85rem);
    }
}

/* Narrow viewports (< 600px width) */
@media (max-width: 600px) {
    :root {
        --title-size: clamp(1.25rem, 7vw, 2.5rem);
    }
    .grid {
        grid-template-columns: 1fr;
    }
}

/* =========================================
   REDUCED MOTION
   ========================================= */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.2s !important;
    }
    html {
        scroll-behavior: auto;
    }
}
```

---

## CSS Gotchas

### Negating CSS Functions

**WRONG — silently ignored by browsers:**
```css
right: -clamp(28px, 3.5vw, 44px);      /* Browser ignores this */
margin-left: -min(10vw, 100px);         /* Browser ignores this */
```

**CORRECT — wrap in `calc()`:**
```css
right: calc(-1 * clamp(28px, 3.5vw, 44px));   /* Works */
margin-left: calc(-1 * min(10vw, 100px));      /* Works */
```

CSS does not allow a leading `-` before function names. The browser silently discards the entire declaration. **Always use `calc(-1 * ...)` to negate CSS function values.**

---

## Font Pairing Quick Reference

| Preset | Display Font | Body Font | Source |
|--------|-------------|-----------|--------|
| Bold Signal | Archivo Black | Space Grotesk | Google |
| Electric Studio | Manrope | Manrope | Google |
| Creative Voltage | Syne | Space Mono | Google |
| Dark Botanical | Cormorant | IBM Plex Sans | Google |
| Notebook Tabs | Bodoni Moda | DM Sans | Google |
| Pastel Geometry | Plus Jakarta Sans | Plus Jakarta Sans | Google |
| Split Pastel | Outfit | Outfit | Google |
| Vintage Editorial | Fraunces | Work Sans | Google |
| Neon Cyber | Clash Display | Satoshi | Fontshare |
| Terminal Green | JetBrains Mono | JetBrains Mono | JetBrains |
| Swiss Modern | Archivo | Nunito | Google |
| Paper & Ink | Cormorant Garamond | Source Serif 4 | Google |
