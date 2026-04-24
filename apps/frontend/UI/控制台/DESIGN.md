# Design System Document: The Intelligence of Precision

## 1. Overview & Creative North Star: "The Digital Curator"
This design system moves away from the sterile, boxy constraints of traditional HR software. Our Creative North Star is **The Digital Curator**. We aim to present complex AI-driven data not as a chaotic ledger, but as a high-end editorial experience. 

The system breaks the "template" look by utilizing **intentional asymmetry** and **tonal depth**. By prioritizing white space and organic layering over rigid lines, we create an environment that feels intelligent and calm—positioning the AI not as a tool, but as a sophisticated advisor.

---

## 2. Colors & Surface Philosophy
The palette is rooted in deep professional blues and clinical whites, but its soul lies in the "interstitial" greys and subtle tonal shifts.

### The "No-Line" Rule
To achieve a premium, modern feel, **1px solid borders are prohibited for sectioning.** Boundaries must be defined through background color shifts.
*   **Method:** A section utilizing `surface-container-low` should sit directly against the `background` or `surface`.
*   **Result:** A layout that feels fluid and integrated rather than fragmented.

### Surface Hierarchy & Nesting
We treat the UI as a series of physical layers, similar to stacked sheets of vellum or fine paper.
*   **Base:** `surface` (#f7fafe) for the widest application area.
*   **Structural Sections:** `surface-container-low` (#f1f4f8) for secondary navigation or sidebar backgrounds.
*   **Interactive Containers:** `surface-container-lowest` (#ffffff) for the primary content cards and data modules.
*   **Nested Elements:** Use `surface-container-high` (#e5e8ec) for small inset elements like code snippets or metadata buckets within a white card.

### The "Glass & Gradient" Rule
For floating elements (modals, dropdowns, or AI insight popovers), use **Glassmorphism**:
*   **Background:** `surface` at 80% opacity.
*   **Effect:** `backdrop-filter: blur(12px)`.
*   **Signature Texture:** Main CTAs or AI-specific indicators should use a linear gradient from `primary` (#003aa2) to `primary-container` (#004fd5) at a 135-degree angle to provide a "liquid intelligence" feel.

---

## 3. Typography: Editorial Authority
We utilize a dual-typeface system to balance modern efficiency with authoritative intelligence.

*   **Display & Headlines (Manrope):** Chosen for its geometric precision. Use `display-lg` and `headline-md` with tight letter-spacing (-0.02em) to create a bold, editorial impact.
*   **Body & Labels (Inter):** The workhorse of the system. `body-md` is the standard for data. Use `label-md` in all-caps with increased letter-spacing (+0.05em) for category headers to create a "professional blueprint" aesthetic.
*   **Hierarchy Tip:** Large `headline-lg` titles should often be paired with significantly smaller `label-sm` metadata to create high-contrast, sophisticated layouts.

---

## 4. Elevation & Depth: Tonal Layering
Traditional drop shadows are too "heavy" for a modern AI interface. We define depth through light and tone.

*   **The Layering Principle:** Place a `surface-container-lowest` card on a `surface-container-low` section to create a soft, natural lift.
*   **Ambient Shadows:** If a "floating" effect is required (e.g., a hovering AI Insight card), use:
    *   `box-shadow: 0 12px 32px -4px rgba(24, 28, 31, 0.06)`.
    *   The shadow is tinted with the `on-surface` color to feel like natural light, not a "dark smudge."
*   **The Ghost Border:** If accessibility requires a stroke, use `outline-variant` (#c3c6d6) at **15% opacity**. This provides a "suggestion" of a boundary without cluttering the visual field.

---

## 5. Components

### AI Insight Cards
*   **Visual Style:** Never use a standard card. Use a `surface-container-lowest` background with a 2px vertical accent bar on the left using the `tertiary` (#004a55) color.
*   **Content:** Forbid divider lines. Use 24px of vertical padding to separate the header from the insight body.

### Data Tables
*   **Structure:** No vertical or horizontal lines. Use `surface-container-low` for the header row and alternating `surface-container-lowest` and `background` for rows if necessary.
*   **Typography:** Column headers must be `label-sm` in `on-surface-variant` (#434654).

### Buttons
*   **Primary:** Gradient (Primary to Primary-Container). `lg` (0.5rem) roundedness.
*   **Secondary:** Ghost style. No border. Use `on-primary-fixed-variant` text on a transparent background.
*   **States:** On hover, primary buttons should shift 1px upward with an Ambient Shadow; they do not simply "get darker."

### Status Badges & Progress Indicators
*   **Badges:** Use a "Soft Fill" approach. For a "Success" state, use a very pale blue/green background with high-contrast text. No borders.
*   **AI Progress:** Use a non-linear, "breathing" animation for progress bars, cycling subtly between `primary` and `tertiary_fixed_dim` (#43d8f2).

---

## 6. Do’s and Don’ts

### Do:
*   **Use Asymmetric Padding:** Allow for more breathing room at the top of a layout than at the sides to create an "upward" energy.
*   **Rely on `surface-container` tiers:** Always check if a background color shift can replace a line or a shadow.
*   **Embrace "Large" Type:** Don't be afraid to use `display-sm` for key metrics; let the numbers tell the story.

### Don't:
*   **Don't use 100% Black:** Never use #000000. Use `on-surface` (#181c1f) to maintain the premium, soft-touch feel.
*   **Don't use dividers:** If you feel the urge to add a `<hr>` or a border, double the spacing instead.
*   **Don't crowd the AI:** AI insights need 1.5x the white space of standard data to signify their importance and "intelligence."