```markdown
# Design System Specification: The Stoic Interface

## 1. Overview & Creative North Star
**Creative North Star: The Silent Partner**

In a high-stakes interview, the interface should be a secondary thought. This design system moves away from the "busy" modular look of standard enterprise tools toward a "High-End Editorial" experience. We prioritize **Calm Authority** through intentional asymmetry, massive negative space, and a rejection of traditional structural lines.

Instead of a grid of boxes, we treat the interview room as a curated stage. By leveraging extreme typographic contrast and tonal layering, we create a sense of credible permanence. The video content is the protagonist; the UI is the sophisticated, silent architecture supporting it.

---

## 2. Color & Surface Philosophy
This system replaces the "standard blue" enterprise feel with a deep, layered palette that suggests professional depth.

### The "No-Line" Rule
**Strict Mandate:** Designers are prohibited from using 1px solid borders to define sections.
Boundaries must be defined solely through background color shifts or tonal transitions. To separate a sidebar from the main video feed, use `surface-container-low` (#f3f2ff) against a `surface` (#fbf8ff) background. This creates a "soft edge" that reduces cognitive load and visual noise.

### Surface Hierarchy & Nesting
Think of the UI as layers of fine vellum. We use the Material tiers to create an organic sense of depth:
- **Base Layer:** `surface` (#fbf8ff) for the widest areas.
- **Sectional Layer:** `surface-container-low` (#f3f2ff) for secondary panels (e.g., Chat or Notes).
- **Interactive Layer:** `surface-container-highest` (#dde1ff) for active components or hovered states.

### The "Glass & Signature Texture" Rule
To elevate the "Corporate Blue" (#0052D9), use a subtle linear gradient for primary actions:
- **Primary CTA:** Gradient from `primary` (#003da6) to `primary_container` (#0052d9) at a 135° angle.
- **Floating Controls:** Use Glassmorphism for the video control bar. Apply `surface_container_lowest` (#ffffff) at 70% opacity with a `20px` backdrop-blur. This ensures the controls feel integrated into the environment rather than a heavy overlay.

---

## 3. Typography
We utilize a pairing of **Manrope** (for authoritative, editorial headlines) and **Inter** (for high-utility, functional body text).

| Role | Token | Font | Size | Intent |
| :--- | :--- | :--- | :--- | :--- |
| **Display** | `display-lg` | Manrope | 3.5rem | High-impact candidate names or brand moments. |
| **Headline** | `headline-sm` | Manrope | 1.5rem | Section titles; provides a "published" editorial feel. |
| **Title** | `title-md` | Inter | 1.125rem | Specificity and navigation. Semi-bold for authority. |
| **Body** | `body-md` | Inter | 0.875rem | Primary reading; maximized for legibility during stress. |
| **Label** | `label-sm` | Inter | 0.6875rem | Micro-metadata (e.g., timestamps, status indicators). |

**Editorial Contrast:** Always pair a `display-lg` name with a `label-md` status. The extreme jump in scale suggests a premium, intentional design rather than a generic template.

---

## 4. Elevation & Depth
We eschew the "Drop Shadow" in favor of **Tonal Layering**.

- **The Layering Principle:** Depth is achieved by "stacking." A `surface-container-lowest` (#ffffff) card sitting on a `surface-container-low` (#f3f2ff) background creates a natural lift.
- **Ambient Shadows:** When a modal or pop-over is required, use a shadow with a 48px blur at 6% opacity, tinted with `on_surface` (#131a36). It should feel like a soft glow of light, not a black smudge.
- **The "Ghost Border" Fallback:** If a divider is functionally required for accessibility, use `outline_variant` (#c3c6d7) at **15% opacity**. If you can see the border clearly, it is too heavy.

---

## 5. Component Logic

### Buttons
- **Primary:** Gradient (`primary` to `primary_container`), `xl` (0.75rem) roundedness. No border.
- **Secondary:** `surface-container-high` background with `on_primary_fixed_variant` text.
- **Tertiary:** Pure text with `on_surface_variant`. Use `3` (1rem) spacing for the touch target, but no background until hover.

### Input Fields
- **Style:** Background-filled using `surface_container_low`. 
- **Active State:** Change background to `surface_container_highest` and add a 1px "Ghost Border" using `primary`. 
- **Layout:** Labels should be `label-md`, all-caps, with 0.05em tracking for a sophisticated, "Pro" feel.

### Cards & Lists
- **Rule:** Absolute prohibition of divider lines.
- **Separation:** Use the Spacing Scale `4` (1.4rem) or `6` (2rem) to separate list items. Use a `surface_variant` background on hover to indicate interactivity.

### Interview-Specific Components
- **The Video Stage:** The main video feed should have `xl` (0.75rem) corners. Surround it with `24` (8.5rem) of whitespace on top/bottom to ensure the focus is absolute.
- **Speaker Chips:** Use `secondary_container` (#90efef) with `on_secondary_container` (#006e6e) text for the active speaker. Use a `full` (9999px) radius.

---

## 6. Do's and Don'ts

### Do
- **Do** use asymmetrical margins. If the left sidebar is `spacing-10`, consider the right content area having `spacing-16` to create a dynamic, editorial flow.
- **Do** lean into the Teal (`secondary`) for "Success" or "Live" indicators to provide a calm alternative to aggressive greens.
- **Do** use `surface_dim` for the "dark mode" transition of video overlays to keep contrast low and focus high.

### Don't
- **Don't** use 100% black (#000000) for text. Always use `on_surface` (#131a36) to maintain the "Corporate Blue" tonal harmony.
- **Don't** use "Standard" shadows. If the shadow looks like a default CSS property, it’s a failure of the system.
- **Don't** crowd the video. If the interface feels "full," increase the spacing scale values. The user's face is the most important data point.
- **Don't** use sharp corners. Use the `lg` or `xl` roundedness tokens to maintain a "calm and approachable" enterprise persona.```