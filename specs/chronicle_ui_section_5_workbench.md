## 5. Investigation Workbench — Split-Pane THINK/SAYS

### 5.1 Overview

The Investigation Workbench is the primary analytical interface of Chronicle, presenting a split-pane architecture that physically separates the AI's internal reasoning process (THINK pane, left) from its distilled conclusions (SAYS pane, right). This spatial arrangement mirrors the cognitive architecture of the agent itself: raw chain-of-thought on the left feeds into validated findings on the right. A resizable divider between panes allows analysts to allocate screen real estate based on investigation phase — wide THINK during active reasoning, wide SAYS during report assembly. The Evidence panel slides out from the right edge on demand, and a persistent input area at the bottom accepts natural-language direction. Every interaction is keyboard-accessible, every state transition is animated with precise cubic-bezier curves, and every data element is backed by the Chronicle API's memory event stream.

The workbench consumes `GET /api/v1/sessions/:id/memory` for historical events and establishes a `WebSocket /ws/v1/sessions/:id` connection for real-time streaming of `MemoryEvent` objects. Each `MemoryEvent` carries `{id, type, content, trust_level, iteration, timestamp, sources[], flags[]}` and renders as either a Thought Card (THINK pane) or Finding Card (SAYS pane) based on `type ∈ {thought, finding, evidence}`.

### 5.2 Workbench Layout

The workbench occupies the full viewport minus the global header (56px) and global status bar (28px). The layout is a flex column with four horizontal bands and a sliding overlay.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  WORKBENCH TOOLBAR (48px)                                                             │
│  ┌──────────────────────────┬────────────────────────┬─────────────────────────────┐ │
│  │ [▼ Sessions] [New]       │ Investigation Title    │ [⏻ Evidence] [⬆] [⚙] [...] │ │
│  └──────────────────────────┴────────────────────────┴─────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────┬────┬───────────────────────────────┬────────────────┐ │
│  │                           │ ║  │                               │ EVIDENCE PANEL │ │
│  │      THINK PANE           │ ║  │        SAYS PANE              │ (360px)        │ │
│  │      flex: 1              │ ║  │        flex: 1                │ slide-out      │ │
│  │                           │ ║  │                               │ right          │ │
│  │  ┌─ Thought Card ───────┐ │ ║  │  ┌─ Finding Card ─────────┐  │                │ │
│  │  │ Step 1 · gpt-4o      │ │ ║  │  │ Finding #7 · 14:32:05  │  │ ┌─ Sources ──┐ │ │
│  │  │ ─────────────────── │ │ ║  │  │ ────────────────────── │  │ │ src_42.txt  │ │ │
│  │  │ The suspect's IP     │ │ ║  │  │ Connection established │  │ │ src_87.pdf  │ │ │
│  │  │ address appears in   │ │ ║  │  │ via port 443 to known  │  │ │ src_91.csv  │ │ │
│  │  │ logs at 03:47...     │ │ ║  │  │ C2 server.             │  │ └────────────┘ │ │
│  │  │ ─────────────────── │ │ ║  │  │ Confidence ████░ 82%   │  │                │ │
│  │  │ [📎 src_42] [⚡anom] │ │ ║  │  │ [Approve] [Reject]     │  │ ┌─ Findings ─┐ │ │
│  │  └──────────────────────┘ │ ║  │  └────────────────────────┘  │ │ #5 #6 #7    │ │ │
│  │                           │ ║  │                               │ └────────────┘ │ │
│  │  ┌─ Thought Card ───────┐ │ ║  │  ┌─ Finding Card ─────────┐  │                │ │
│  │  │ Step 2 · gpt-4o      │ │ ║  │  │ Finding #8 · 14:32:22  │  │ [Search...   ] │ │
│  │  │ (streaming ▊)         │ │ ║  │  │ (pending...)           │  │                │ │
│  │  └──────────────────────┘ │ ║  │  └────────────────────────┘  │                │ │
│  └───────────────────────────┴────┴───────────────────────────────┴────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  INPUT AREA (min 64px, auto-grow to 40vh)                                             │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐ │
│  │ [📎] [@Context ▼] [#Model ▼]                              [Tokens: 0/128000]     │ │
│  │ ┌──────────────────────────────────────────────────────────────────────────────┐ │ │
│  │ │ Ask a question or direct the investigation...                          ▊     │ │ │
│  │ └──────────────────────────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Layout CSS grid definition (pseudocode):**
```
.workbench {
  display: grid;
  grid-template-rows: 48px 1fr auto;
  grid-template-columns: 1fr;
  height: calc(100vh - 56px - 28px); /* minus global header + status bar */
  background: var(--color-bg-canvas);
  position: relative;
  overflow: hidden;
}

.workbench-content {
  display: flex;
  flex-direction: row;
  height: 100%;
  overflow: hidden;
}

.think-pane {
  flex: 1;
  min-width: 280px;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--color-bg-canvas);
}

.says-pane {
  flex: 1;
  min-width: 280px;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--color-bg-canvas);
}
```

**Responsive breakpoints:**
- Viewport < 900px: Stack THINK/SAYS vertically. Divider becomes horizontal 8px bar. Collapse to single-pane with tabs.
- Viewport < 600px: Evidence panel becomes full-width bottom sheet. Toolbar collapses to hamburger menu.
- Viewport ≥ 1600px: Optional third pane mode (Evidence pinned left) configurable in Settings.

### 5.3 Resizable Divider

The divider is the primary spatial control between THINK and SAYS panes. It must be discoverable, responsive, and precise.

#### 5.3.1 Dimensions

```
┌────────────────────────────────────────────────────┐
│          THINK PANE          │║│       SAYS PANE   │
│                         2px  │║│  2px              │
│                    invisible │║│  invisible        │
│                     hit area │║│  hit area         │
│                              │║│                   │
│                     ┌──┐     │║│                   │
│                     │●│ 4px  │║│                   │
│                     │●│ grip │║│                   │
│                     │●│      │║│                   │
│                     └──┘     │║│                   │
│                              │║│                   │
└────────────────────────────────────────────────────┘
        Total divider width = 8px
        Grip = 4px wide centered
        Invisible hit areas = 2px each side
```

**CSS:**
```css
.divider {
  width: 8px;
  min-width: 8px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  flex-shrink: 0;
}

.divider::before {
  content: '';
  position: absolute;
  left: 2px;
  right: 2px;
  top: 0;
  bottom: 0;
  background: var(--color-border-default);
  transition: background var(--duration-quick) var(--ease-out-expo);
}

.divider::after {
  content: '';
  position: absolute;
  width: 4px;
  height: 32px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: var(--radius-sm);
  /* Three vertical dots via background-image SVG */
  background-image: url("data:image/svg+xml,..."); /* 3 dots, 2px diameter, 4px spacing */
  background-repeat: no-repeat;
  background-position: center;
  opacity: 0;
  transition: opacity var(--duration-quick) var(--ease-out-expo);
}
```

#### 5.3.2 States

**DEFAULT:** Transparent background. `::before` in `var(--color-border-default)` at 40% opacity. `::after` (grip dots) at 0% opacity. Cursor: `col-resize`.

**HOVER:** On divider hover OR divider `:hover`:
- `::before` → `var(--color-border-hover)` at 100% opacity, `--duration-quick` (150ms) `--ease-out-expo`
- `::after` → opacity 60%, same timing
- `::before` width expands from 4px to 8px (full divider) via `transform: scaleX(2)` centered
- Parent `.workbench-content` shows a subtle 1px overlay line at divider position in `var(--color-accent-primary)` at 10% opacity

**ACTIVE (dragging):**
- `::before` → `var(--color-accent-primary)` at 100% opacity
- `::after` → opacity 100%, dots color shifts to `var(--color-accent-primary)`
- `::before` width stays at 8px
- Entire viewport cursor forced to `col-resize` via `body { cursor: col-resize !important; }`
- A vertical guide line (1px dashed, `var(--color-accent-primary)`, 60% opacity) spans the full workbench height at the current drag position
- Tooltip appears above grip: "THINK 62% · SAYS 38%", font 11px, `var(--color-text-secondary)`, `var(--color-bg-surface)`, border `var(--color-border-default)`, `border-radius: var(--radius-sm)`, `padding: 2px 8px`, offset 8px above grip center, fades in 150ms

**FOCUS:** When divider receives keyboard focus (Tab key):
- `::before` → `var(--color-border-focus)`
- `::after` → opacity 100%, dots color `var(--color-accent-primary)`
- 2px focus ring `var(--color-accent-primary)` with 2px offset, `border-radius: var(--radius-sm)`, opacity 50%
- Focus ring pulses once (scale 0.95→1.05→1.0, 600ms `--ease-spring`)

**DISABLED:** When workbench is locked (Settings toggle):
- Cursor: `not-allowed`. All interactions blocked.
- `::before` → `var(--color-border-default)` at 20% opacity
- `::after` → opacity 0%

#### 5.3.3 Interactions

**Mouse Drag:**
1. `mousedown` on divider → state → ACTIVE
2. `mousemove` → update `--divider-position` custom property (clamped to [280px, `viewportWidth - 280px - 8px`])
3. THINK pane width = `--divider-position`; SAYS pane = remaining
4. `mouseup` → state → DEFAULT. Snaps to nearest 1% for clean ratios.
5. If released at < 50px from left edge → animate collapse THINK (400ms `--ease-out-expo`)
6. If released at < 50px from right edge → animate collapse SAYS (400ms `--ease-out-expo`)
7. Drag velocity tracked; if flick > 500px/s toward edge → instant snap-collapse

**Double-Click:**
- Double-click grip area → reset to 50/50 split
- Animated transition: current ratio → 50/50 over 300ms `--ease-out-expo`
- Brief pulse on grip dots (scale 1.3 → 1.0, 200ms) as acknowledgment

**Keyboard Shortcuts:**
- `Ctrl+Shift+Left` → nudge divider left by 40px (expand SAYS)
- `Ctrl+Shift+Right` → nudge divider right by 40px (expand THINK)
- `Ctrl+Shift+0` → reset to 50/50 (same animation as double-click)
- `Ctrl+Shift+[` → collapse THINK pane
- `Ctrl+Shift+]` → collapse SAYS pane
- When divider focused, Left/Right arrows → nudge 40px per press (with key repeat)
- When divider focused, Home → collapse THINK; End → collapse SAYS
- Nudge clamped to min pane width (280px)

**Minimum Pane Width:** 280px. When a pane would shrink below 280px, the divider locks and the constrained pane stops shrinking. Visual feedback: constrained pane border-left (or border-right) flashes `var(--color-accent-warning)` for 150ms.

**Collapse Behavior:**
- Collapsed THINK: SAYS expands to full width. A 40px wide vertical tab appears at left edge.
  - Tab: 40px wide, full height, `var(--color-bg-surface)`, vertical text "THINK" rotated -90deg, 12px font, `var(--color-text-tertiary)`
  - Tab hover: background → `var(--color-bg-hover)`, text → `var(--color-accent-purple)`, cursor pointer
  - Tab click: expand THINK to previous width (or 50% if no previous), 400ms `--ease-out-expo`
  - Tab shows unread thought count badge: `var(--color-accent-purple)` pill, white text, top-right of tab
- Collapsed SAYS: same mirrored — 40px tab at right edge with "SAYS" label
- Both collapsed is not allowed — at least one pane must be visible

**Persistence:** Divider position saved to `localStorage` key `chronicle.workbench.dividerRatio` as float (0.0 to 1.0). Restored on session load. Per-session override via `chronicle.workbench.{sessionId}.dividerRatio`.

#### 5.3.4 Touch Support

- Touch drag: identical behavior. Hit area expanded to 20px total (10px invisible each side) on touch devices via `@media (pointer: coarse)`.
- Double-tap → reset to 50/50
- Swipe from edge → collapse

### 5.4 THINK Pane

The THINK pane displays the AI agent's chain-of-thought reasoning as a vertical stream of Thought Cards. Each card represents one reasoning step (one `MemoryEvent` with `type: "thought"`). Cards flow top→bottom, newest at bottom. Auto-scroll follows streaming content unless user has scrolled up (scroll anchor detection).

#### 5.4.1 Thought Card Anatomy

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ┌──────┐ ┌─────────────────────┐                     ┌────────────────────┐  │
│ │Step 3│ │ ◆ claude-sonnet-4  │                     │  14:32:17.423      │  │
│ │ #8C3E  │ └─────────────────────┘                     └────────────────────┘  │
│ └──────┘                                                                       │
│                                                                                │
│ ┌─ Source Badges ────────────────────────────────────────────────────────────┐ │
│ │ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐            │ │
│ │ │ 📎 evidence_42   │ │ 📎 log_17.csv    │ │ 📎 witness_A.mp4 │            │ │
│ │ │   cited · 94%    │ │   cited · 67%    │ │   cited · 88%    │            │ │
│ │ └──────────────────┘ └──────────────────┘ └──────────────────┘            │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│ The suspect's IP address (192.168.1.47) appears in the firewall logs at       │
│ 03:47:22 UTC, which correlates with the timestamp of the unauthorized         │
│ database access. The connection originated from subnet 192.168.1.0/24,        │
│ which is the internal corporate network, suggesting an insider threat         │
│ rather than external compromise. The source port 58432 maps to a known        │
│ ephemeral range, and the TTL value of 64 confirms local origin.               │
│                                                                                │
│ I should cross-reference this with the HR badge reader logs to determine      │
│ which employee was in the building at 03:47. The MAC address OUI prefix       │
│ 3C:15:C2 maps to a Dell Latitude 7490, which is the standard-issue            │
│ corporate laptop.                                                             │
│                                                                                │
│ ┌─ Flags ────────────────────────────────────────────────────────────────────┐ │
│ │ ⚠ CONTRADICTION  │ 🔗 CORRELATION  │ ⚡ ANOMALY  │                         │ │
│ │ w/ Step 2 badge   │ w/ Finding #3  │ TTL=64 on    │                         │ │
│ │ reader timestamps │ access pattern │ external pkt │                         │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│ ┌─ Actions ──────────────────────────────────────────────────────────────────┐ │
│ │ [🔗 Show linked findings]  [📋 Copy]  [⭐ Bookmark]  [⋯ More]              │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Component tree (pseudocode):**
```
ThoughtCard {
  header: {
    stepBadge: StepBadge { number: int, colorHex: string }
    modelPill: ModelPill { modelName: string, providerIcon: string }
    timestamp: Timestamp { iso8601: string, relative: string }
  }
  sourceBadges: SourceBadge[] {
    icon: "📎" | "📊" | "📝" | "🔊" | "🖼️"
    name: string
    trustLabel: "cited" | "inferred" | "speculative"
    confidence: float (0.0-1.0)
  }
  reasoningText: string (markdown rendered, max-height 600px collapsed, scrollable when expanded)
  flags: Flag[] {
    type: "contradiction" | "correlation" | "anomaly" | "hallucination" | "uncertainty"
    label: string
    linkedStepOrFinding: string | null
    severity: "info" | "warning" | "critical"
  }
  actions: {
    showLinked: () → scrollToLinked
    copy: () → clipboard
    bookmark: () → toggleBookmark
    more: () → contextMenu
  }
}
```

**Step Badge:**
- 36×24px rounded pill, `border-radius: var(--radius-md)`
- Background: computed from a deterministic color function `hsl(hash(stepNumber) * 360, 70%, 45%)`
- Text: "Step N", 10px weight 600, white, centered
- Right edge has a small decorative notch (2px × 8px cutout) at vertical center
- Hover: scale 1.05, transition 150ms `--ease-out-expo`
- Click: copies step number to clipboard, brief flash pulse

**Model Pill:**
- 24px height, `border-radius: var(--radius-full)`
- Background: `var(--color-bg-surface)`, border: 1px `var(--color-border-default)`
- Contains: provider icon (16px, left, 4px padding) + model name (11px, weight 500, `var(--color-text-secondary)`)
- Provider icons: ◆ (Anthropic), ◈ (OpenAI), ◇ (Google), ✦ (Meta), ⬡ (custom)
- Hover: border → `var(--color-border-hover)`, background → `var(--color-bg-hover)`
- Click: opens model info tooltip with context window, cost, version

**Timestamp:**
- 11px, `var(--color-text-tertiary)`, monospace (`'JetBrains Mono', 'Fira Code', monospace`)
- Format: `HH:MM:SS.mmm` (millisecond precision)
- Hover: shows relative time tooltip ("2m 14s ago")
- Fades in on card completion (see animations)

**Source Badges:**
- Height: 28px, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`
- Background: `var(--color-bg-surface)`, border: 1px `var(--color-border-default)`
- Layout: icon (16px) + source name (11px, truncated at 120px, ellipsis) + confidence dot
- Confidence dot: 6px circle, right-aligned within badge
  - ≥90%: `var(--color-accent-success)`
  - 70-89%: `var(--color-accent-warning)`
  - 50-69%: `var(--color-accent-warning)` at 60% opacity
  - <50%: `var(--color-accent-error)` at 40% opacity
- Hover: expands to show full source name (width transitions 300ms `--ease-out-expo`), confidence as percentage number
- Click: scrolls Evidence panel to that source and highlights it
- Drag: badge can be dragged to Input Area to cite the source in a new query
- Badge row wraps if >3 badges; overflow shows "+N more" pill

**Reasoning Text:**
- Font: 13px, line-height 1.6, `var(--color-text-primary)`
- Rendered as inline markdown: `**bold**`, `*italic*`, `` `code` ``, ```code blocks```, [links](), bullet lists
- Code blocks: 12px monospace, `var(--color-bg-surface)` background, `var(--radius-sm)`, 1px `var(--color-border-default)`, `padding: var(--space-2) var(--space-3)`
- Links: `var(--color-text-link)`, underline on hover
- Default state: max-height 600px, overflow hidden with fade-out gradient at bottom (40px, white→transparent)
- Expanded state: max-height removed, full content visible
- "Show more" / "Show less" toggle at bottom of fade gradient: 12px, `var(--color-text-link)`, centered

**Flags:**
Each flag is a compact inline chip:
- Height: 24px, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`
- Border-left: 2px solid type-color
- Type colors:
  - Contradiction (⚠): `var(--color-accent-error)`
  - Correlation (🔗): `var(--color-accent-success)`
  - Anomaly (⚡): `var(--color-accent-warning)`
  - Hallucination (💭): `var(--color-accent-purple)`
  - Uncertainty (❓): `var(--color-text-tertiary)`
- Background: type-color at 8% opacity
- Icon: 14px emoji, left
- Label: 11px, `var(--color-text-secondary)`, max 200px truncated
- Each flag is clickable:
  - Contradiction: scrolls THINK to contradicted step, highlights both with error-color glow
  - Correlation: scrolls SAYS to correlated finding, highlights both with success-color glow
  - Anomaly: opens detail tooltip with anomaly explanation
  - Hallucination: opens verification panel showing source-vs-claim diff

**Actions Row:**
- 32px height, horizontal flex, `gap: var(--space-2)`
- Action buttons: 28px height, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`, 11px weight 500, `var(--color-text-secondary)`
- Default: transparent background
- Hover: `var(--color-bg-hover)`, text → `var(--color-text-primary)`
- Active/pressed: `var(--color-bg-selection)`, scale 0.97
- Icons: 14px, left of text
- "⋯ More": opens context menu at cursor position
  - Menu items: "Flag for review", "Create finding from step", "Copy step ID", "Link to evidence", "Hide this step", "Report hallucination"
  - Menu: 200px wide, `var(--color-bg-surface-raised)`, `box-shadow: var(--shadow-lg)`, `border-radius: var(--radius-md)`, `border: 1px solid var(--color-border-default)`
  - Menu items: 32px height, 12px font, hover `var(--color-bg-hover)`, 4px left padding
  - Keyboard: Up/Down arrows navigate, Enter selects, Escape closes

**Empty State:**
When no thoughts exist yet:
- Centered vertically in THINK pane
- Large icon: 64px, thinking face emoji or stylized brain, 30% opacity
- Text: "Awaiting agent reasoning..." 14px, `var(--color-text-tertiary)`
- Subtext: "Submit a question or directive below to begin." 12px, `var(--color-text-tertiary)`
- Subtle breathing animation: icon scales 1.0→1.03→1.0 over 3s loop, `--ease-out-expo`

**Loading State:**
- Skeleton cards: 3 placeholder cards
- Each: height 120px, `var(--color-bg-surface)`, shimmer animation
- Shimmer: linear gradient (transparent → `var(--color-bg-hover)` → transparent) sweeps left→right, 1.5s cycle, `cubic-bezier(0.4, 0, 0.2, 1)`
- Skeleton elements: 80% width header bar, 60% width text line, 90% width text line, 40% width text line, spaced 8px apart

#### 5.4.2 Thought Card States

**DEFAULT (Collapsed):**
- Background: `var(--color-bg-surface)`
- Border-left: 3px solid `var(--color-accent-purple)`
- Border-radius: `var(--radius-md)`
- Padding: `var(--space-3)` top/bottom, `var(--space-4)` left/right
- Margin: `var(--space-2)` bottom (between cards)
- Box-shadow: `var(--shadow-sm)`
- Reasoning text: max-height 600px with bottom fade
- Model pill visible, timestamp visible
- Flags row visible if flags exist

**THINKING (Streaming):**
- Border-left: 3px solid, animated gradient. Linear gradient sweeps: `var(--color-accent-purple)` → `var(--color-accent-cyan)` → `var(--color-accent-purple)`, 3s cycle, background-position animates 0%→200%.
  ```css
  .thought-card.streaming {
    border-left: 3px solid transparent;
    background: 
      linear-gradient(var(--color-bg-surface), var(--color-bg-surface)) padding-box,
      linear-gradient(180deg, var(--color-accent-purple), var(--color-accent-cyan), var(--color-accent-purple)) border-box;
    background-size: 100% 100%, 100% 200%;
    animation: border-sweep 3s linear infinite;
  }
  @keyframes border-sweep {
    0% { background-position: 0% 0%, 0% 0%; }
    100% { background-position: 0% 0%, 0% 200%; }
  }
  ```
- A blinking cursor (▊) appears at end of reasoning text:
  - 12px height, 2px width, `var(--color-accent-purple)`
  - Blink cycle: 500ms visible, 500ms hidden, infinite
  - Cursor color matches model: purple (Anthropic), green (OpenAI), blue (Google)
- Box-shadow: `var(--shadow-glow-blue)` (subtle purple glow at bottom edge)
- Timestamp: hidden (shows "Streaming..." placeholder in 11px italic, `var(--color-text-tertiary)`)
- Badge shows pulsing dot: 6px circle, `var(--color-accent-purple)`, pulse animation scale 0.8→1.2→0.8, 1s `--ease-out-expo`
- Auto-scroll: pane scrolls to keep streaming card's cursor visible unless user has scrolled up >100px from bottom (tracked via IntersectionObserver on a sentinel div)

**COMPLETED:**
- Transition from THINKING → COMPLETED:
  - Border-left: color snaps to `var(--color-border-default)` (200ms `--ease-out-expo`)
  - Gradient animation stops; border becomes solid
  - Cursor fades out (150ms opacity 1→0) and is removed from DOM
  - Timestamp fades in (300ms opacity 0→1, delayed 150ms after cursor removal)
  - Box-shadow returns to `var(--shadow-sm)`
  - If card has flags, they animate in from below (slideUp 200ms each, staggered 50ms)
- Completed cards are sorted by timestamp descending (newest first within each iteration group)
- A completed card never re-enters streaming state

**EXPANDED:**
- Trigger: click on card body (not on interactive elements), or "Show more" button
- Background: `var(--color-bg-surface-raised)` (slightly elevated)
- Border-left: 3px solid `var(--color-accent-primary)`
- Box-shadow: `var(--shadow-md)`
- Reasoning text: max-height removed (from 600px to full content height)
- Animation: `max-height` transition 400ms `--ease-out-expo`, content revealed
- Fade gradient at bottom: removed (opacity 1→0 over 200ms before max-height expansion)
- Scroll: card scrolls itself if content exceeds viewport (internal `overflow-y: auto`)
- "Show less" appears at bottom
- Other cards dim slightly: `opacity: 0.6`, transition 300ms `--ease-out-expo`
- Click outside or press Escape → collapse card

**FLAGGED (Contradiction):**
- Border-left: 3px solid `var(--color-accent-error)`
- Background: `var(--color-accent-error)` at 4% opacity (tinted)
- Top-right corner: small error icon (⚠, 16px) fixed position within card
- Contradiction flag(s) highlighted with error-color background at 15% opacity
- When contradiction flag clicked → both this card and linked card highlight simultaneously:
  - Both cards get temporary border pulse: `var(--color-accent-error)` glow, 2 pulses of 300ms each
  - Target card scrolled into view (smooth, `scroll-behavior: smooth`)
  - If target card is in collapsed SAYS pane → auto-expand SAYS, then scroll
  - Connection line drawn: SVG overlay connecting the two cards with dashed `var(--color-accent-error)` line

**LINKED (Correlation):**
- Border-left: 3px solid `var(--color-accent-success)`
- Background: `var(--color-accent-success)` at 4% opacity
- Small link icon (🔗, 16px) in top-right corner
- Clicking link icon scrolls SAYS pane to correlated finding
- Connection visualization identical to FLAGGED but with `var(--color-accent-success)` color

**SELECTED:**
- Trigger: click card header area or Ctrl+click
- Border: 2px solid `var(--color-accent-primary)`, all sides
- Background: `var(--color-accent-primary)` at 6% opacity
- Used for multi-select operations (copy multiple, bookmark multiple)
- Shift+click: range select (all cards between previous selection and clicked card)
- Ctrl+A: select all cards in current pane
- Selected count shown in a floating toolbar: "3 selected · [Copy] [Bookmark] [Create Finding] [Deselect]"

**DISABLED (Hidden/Filtered):**
- Card hidden entirely (`display: none`) when filtered out by search or flag filter
- Transition: opacity 1→0 + max-height to 0 + margin to 0 over 300ms `--ease-out-expo`, then `display: none`
- Re-appearance: reverse animation

#### 5.4.3 Animations

**Entry Animation (new card appears):**
- Slide up from below + fade in: `transform: translateY(20px)`, `opacity: 0` → `transform: translateY(0)`, `opacity: 1`
- Duration: 300ms
- Easing: `--ease-out-expo` (0.16, 1, 0.3, 1)
- Delay: 0ms for first card in batch, 50ms stagger for subsequent cards
- Cards that appear above the fold (not in viewport) skip animation; they simply appear
- Cards below the fold animate when scrolled into view (IntersectionObserver, threshold 0.1)

**Expand Animation:**
- `max-height`: current (600px) → full content height (measured via `scrollHeight`)
- Duration: 400ms
- Easing: `--ease-out-expo`
- Fade gradient: opacity 1→0 over first 200ms
- Other cards: opacity 1→0.6 over 300ms `--ease-out-expo`
- If content height > viewport: card gets `overflow-y: auto` after expansion completes

**Collapse Animation:**
- Reverse of expand:
- `max-height`: full → 600px
- Duration: 300ms
- Easing: `--ease-in-out-quint` (0.83, 0, 0.17, 1) — slightly snappier closing
- Fade gradient reappears at 200ms mark
- Other cards: opacity 0.6→1 over 300ms

**Streaming Animation (text appearing character-by-character):**
- NOT character-by-character DOM updates (too expensive)
- Batched updates: DOM updated every 16ms (60fps), appending the delta since last batch
- Implementation: requestAnimationFrame loop reads from a SharedArrayBuffer/stream buffer
- Delta applied as: `cardElement.textContent += delta`
- Cursor element always appended after last character
- Auto-scroll: `cardElement.scrollIntoView({ block: 'nearest', behavior: 'instant' })` if user is at bottom
- If delta exceeds 500 chars in one frame, batch into 100-char chunks across 5 frames to prevent jank
- Connection status indicator: if WebSocket buffers > 200ms of unrendered text, show small spinner (12px) next to model pill

**Cursor Blink:**
- Pure CSS animation (no JS timer):
  ```css
  @keyframes cursor-blink {
    0%, 49% { opacity: 1; }
    50%, 100% { opacity: 0; }
  }
  .thought-card .cursor {
    animation: cursor-blink 1s step-end infinite;
  }
  ```
- Cursor element: inline `<span>` with 2px width, current model color, `display: inline-block`, `vertical-align: text-bottom`

**Flag Entry Animation:**
- Flags enter after card completion:
- Each flag: `transform: translateY(8px)`, `opacity: 0` → `transform: translateY(0)`, `opacity: 1`
- Duration: 200ms per flag
- Stagger: 50ms between flags
- Easing: `--ease-out-expo`

**Remove Animation (card dismissed via "Hide this step"):**
- Height collapse: `max-height` current → 0
- Opacity: 1 → 0
- Margin: current → 0
- Padding: current → 0
- Duration: 250ms
- Easing: `--ease-out-quint`
- Below cards slide up to fill gap (via margin collapse)

**Connection Line Animation (when link clicked):**
- SVG overlay: `<svg>` element absolutely positioned over both panes, `pointer-events: none`, `z-index: 100`
- Line drawn from source card center-right to target card center-left
- Line style: 2px dashed, color matches flag type
- Draw animation: `stroke-dasharray` + `stroke-dashoffset` animated from full length to 0, 400ms `--ease-out-expo`
- Line persists for 2s then fades (opacity 1→0, 500ms)
- If user hovers line, it persists and shows labels at both ends

**Pane Scroll Behavior:**
- Smooth scrolling: `scroll-behavior: smooth` on pane (overridden to `auto` during initial load to prevent animation)
- Scroll anchoring: `overflow-anchor: auto` to prevent content jumping when cards above resize
- Scroll-to-bottom button: appears when user scrolls up >200px from bottom
  - 36px circle, `var(--color-bg-surface-raised)`, `box-shadow: var(--shadow-md)`, bottom-right of pane
  - Contains ↓ icon, 16px, `var(--color-text-secondary)`
  - Fade in 200ms, fade out 200ms
  - Click: smooth scroll to bottom
  - Shows unread count badge if new cards appeared while scrolled up

### 5.5 SAYS Pane

The SAYS pane displays the AI agent's validated conclusions as Finding Cards. Findings are derived from reasoning steps but are distinct entities — they represent assertions the agent has verified and is willing to stand behind. Each finding maps to a `MemoryEvent` with `type: "finding"`.

#### 5.5.1 Finding Card Anatomy

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Finding #7     │  APPROVED ✓              │             14:32:05.892         │
│                │  by kara · 14:33:12      │                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ The unauthorized database access at 03:47:22 UTC originated from internal    │
│ IP 192.168.1.47 (corporate subnet), confirming an insider threat. The        │
│ connection used port 443 to external IP 203.0.113.45, identified as a        │
│ known command-and-control server (C2) per threat intelligence feed TLP:AMBER.│
│                                                                              │
│ ┌─ Confidence ──────────────────────────────────────────────────────────────┐ │
│ │ ████████████████████████████████████████░░░░░░  82%  HIGH                  │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─ Sources ─────────────────────────────────────────────────────────────────┐ │
│ │ Based on: Step 3 · Step 5 · Step 8           │ [Show reasoning]           │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─ Actions ─────────────────────────────────────────────────────────────────┐ │
│ │ [✓ Approve]  [✗ Reject]  [📋 Copy]  [⭐ Bookmark]  [🔗 Link]  [⋯ More]  │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Component tree:**
```
FindingCard {
  header: {
    findingNumber: int (sequential, global per session)
    approvalBadge: ApprovalBadge | null
    timestamp: Timestamp
  }
  conclusionText: string (markdown, same rendering as Thought Card text)
  confidenceBar: {
    percentage: float (0-100)
    level: "LOW" | "MEDIUM" | "HIGH" | "VERIFIED"
  }
  sources: {
    basedOnSteps: int[] (referenced thought step numbers)
    evidenceRefs: string[] (evidence item IDs)
  }
  actions: FindingActions
}
```

**Finding Header:**
- Height: 36px, flex row, `align-items: center`, `gap: var(--space-2)`
- Finding number: "Finding #N" in 13px weight 600, `var(--color-entity-finding)`
- Divider dot: 4px circle, `var(--color-border-default)`
- Approval badge (if approved/rejected): see below
- Spacer
- Timestamp: 11px monospace, `var(--color-text-tertiary)`, format `HH:MM:SS.mmm`

**Approval Badge:**
- 24px height, `border-radius: var(--radius-full)`, `padding: 0 var(--space-2)`
- States:
  - DRAFT (no badge shown): just plain status
  - APPROVED: background `var(--color-accent-success)` at 12% opacity, border 1px `var(--color-accent-success)`. Text "✓ Approved" 11px weight 600, `var(--color-accent-success)`. Plus "by {username} · {timestamp}" in 10px `var(--color-text-tertiary)`.
  - REJECTED: background `var(--color-accent-error)` at 12% opacity, border 1px `var(--color-accent-error)`. Text "✗ Rejected" 11px weight 600, `var(--color-accent-error)`. Plus "by {username} · {timestamp} · {reason}" in 10px `var(--color-text-tertiary)`.

**Conclusion Text:**
- Identical rendering to Thought Card reasoning text
- 13px, line-height 1.6, markdown
- Default max-height: 400px with bottom fade (shorter than THINK since findings should be concise)
- Expanded: removed max-height, 400ms `--ease-out-expo`

**Confidence Bar:**
- Height: 20px total (16px bar + 4px below for label)
- Bar: 16px height, `border-radius: var(--radius-sm)`, background `var(--color-bg-input)`
- Fill: height 100%, `border-radius: var(--radius-sm)`, width = confidence%, min-width 2px
- Fill colors:
  - 0-25%: `var(--color-accent-error)`
  - 26-50%: `var(--color-accent-warning)` 
  - 51-75%: `var(--color-accent-warning)` (lighter shade)
  - 76-90%: `var(--color-accent-success)` at 70% opacity
  - 91-100%: `var(--color-accent-success)`
- Label: right-aligned, 11px weight 600, `--color-text-secondary`. Format: "82%  HIGH"
- Fill animates on load: width 0%→target% over 600ms `--ease-out-expo` (staggered 200ms after card entry)
- Hover: shows detailed confidence breakdown tooltip
  - "Source reliability: 94% · Logical coherence: 78% · Cross-validation: 71% · Combined: 82%"

**Sources Row:**
- 28px height, `padding: 0 var(--space-2)`, `var(--color-bg-surface)`, `border-radius: var(--radius-sm)`
- Text: "Based on: Step 3 · Step 5 · Step 8" in 11px, `var(--color-text-secondary)`
- Step numbers are clickable links: `var(--color-text-link)`, underline on hover
- Click → THINK pane scrolls to that step and highlights it (green glow pulse)
- Right side: "[Show reasoning]" button, 11px, `var(--color-text-link)`, toggles inline display of linked thought text
- Inline reasoning: expands below source row, indented 24px, 12px font, `var(--color-text-tertiary)`, max-height 300px scrollable, border-left 2px `var(--color-border-default)`

**Context Menu (⋯ More):**
- Items: "Edit finding", "Request re-evaluation", "Export as report snippet", "Add tag", "Link to investigation timeline", "View change history", "Delete finding"
- Delete: requires confirmation dialog (see 5.5.3)

#### 5.5.2 Finding States

**DRAFT:**
- Border: 1px solid `var(--color-border-default)`
- Background: `var(--color-bg-surface)`
- Border-radius: `var(--radius-md)`
- Padding: `var(--space-3)` top/bottom, `var(--space-4)` left/right
- Box-shadow: `var(--shadow-sm)`
- No approval badge visible (or subtle "Draft" text badge: 20px pill, `var(--color-bg-input)`, 10px `var(--color-text-tertiary)`)
- Actions row shows [Approve] and [Reject] buttons
- Finding can be edited inline (double-click text area → contenteditable, save on blur or Ctrl+Enter)

**APPROVED:**
- Border-left: 3px solid `var(--color-accent-success)`
- Background: `var(--color-bg-surface)`
- Approval badge visible with green check, approver name, and timestamp
- Approve button hidden; Reject button changes to "Revoke Approval"
- Card locked from editing (unless user has `editor` role)
- Slight green tint overlay: `background: linear-gradient(90deg, var(--color-accent-success) at 0% opacity 3%, transparent 10%)`
- Approved findings appear in exported reports

**REJECTED:**
- Border-left: 3px solid `var(--color-accent-error)`
- Background: `var(--color-bg-surface)`
- Opacity: 60% (entire card)
- Rejection badge visible with red X, rejecter name, timestamp, and reason
- Reason text: 11px italic, `var(--color-text-tertiary)`, max 1 line truncated, expandable
- Actions: [Re-evaluate] button replaces Approve/Reject. Sends finding back to agent for re-analysis.
- Rejected findings are excluded from exports by default (toggleable)

**OUTDATED (Superseded):**
- Dashed border: 1px dashed `var(--color-border-default)` (instead of solid)
- Background: `var(--color-bg-canvas)` (darker than surface)
- Opacity: 75%
- Badge: yellow "Superseded by #N" with link to newer finding, 11px, `var(--color-accent-warning)`
- Confidence bar: hidden
- Actions: only [⋯ More] with "View history" and "Restore" options
- Superseded findings are auto-detected when agent produces a finding that contradicts or subsumes an earlier one

**EXPANDED:**
- Same behavior as Thought Card EXPANDED (background raised, border accent, shadow-md, 400ms animation)
- Other findings dim to 0.6 opacity

**HIGHLIGHTED (via correlation link):**
- Green glow: `box-shadow: var(--shadow-glow-blue)` tinted green, 2 pulses 300ms each
- Background: `var(--color-accent-success)` at 6% opacity for 2 seconds, then fades to normal
- Finding scrolls into view if not visible

**LOADING (pending generation):**
- Skeleton card: 180px height, shimmer animation (identical to Thought Card loading)
- Text: "Generating finding from reasoning..." 12px, `var(--color-text-tertiary)`, centered
- Spinner: 20px, `var(--color-accent-primary)`, centered above text
- Auto-replaced by real finding when WebSocket delivers `type: "finding"` event

**ERROR (generation failed):**
- Border: 1px solid `var(--color-accent-error)`
- Background: `var(--color-accent-error)` at 4% opacity
- Icon: ⚠ 24px, centered
- Text: "Finding generation failed" 13px, `var(--color-accent-error)`
- Subtext: error message from API, 11px, `var(--color-text-secondary)`
- Actions: [Retry] button → POST `/api/v1/sessions/:id/message` with re-generation prompt
- [Dismiss] button → removes card with collapse animation

**EMPTY (no findings yet):**
- Centered in SAYS pane:
- Icon: 64px, magnifying glass or checkmark, 30% opacity
- Text: "No findings yet" 14px, `var(--color-text-tertiary)`
- Subtext: "Approved conclusions will appear here as the investigation progresses." 12px, `var(--color-text-tertiary)`
- Breathing animation (identical to THINK empty state)

#### 5.5.3 Approval Workflow

**Approve Action:**
1. User clicks [✓ Approve] button on a DRAFT finding
2. **Confirmation dialog** appears:
   - Modal overlay: `rgba(0,0,0,0.4)` backdrop, `backdrop-filter: blur(2px)`
   - Dialog: 400px wide, `var(--color-bg-surface-raised)`, `box-shadow: var(--shadow-lg)`, `border-radius: var(--radius-lg)`, centered
   - Title: "Approve Finding #N?" 16px weight 600, `var(--color-text-primary)`
   - Body: finding text preview (first 150 chars), 13px, `var(--color-text-secondary)`
   - Optional comment field: 60px textarea, placeholder "Add approval note (optional)..."
   - Buttons: [Cancel] (secondary, right) [Confirm Approval] (primary, green, rightmost)
   - Dialog enters with scale 0.95→1.0 + opacity 0→1, 200ms `--ease-spring`
3. User clicks [Confirm Approval]:
   - Dialog closes (reverse animation, 150ms `--ease-out-quint`)
   - Finding card border-left animates to green: sweep left→right over 400ms `--ease-out-expo`
     - Implementation: pseudo-element `::before` with green background, width 0%→100%, left-aligned
   - Approval badge fades in (300ms, delayed 200ms)
   - Checkmark icon (✓) animates: scale 0→1.2→1.0, 400ms `--ease-spring`
   - API call: `PATCH /api/v1/sessions/:id/findings/:findingId` body `{status: "approved", approved_by: "kara", comment: "..."}`
   - On success → toast notification
   - On failure → error state, revert animation

**Success Toast:**
- Position: bottom-center, 48px above input area
- 320px wide, 48px height, `var(--color-bg-surface-raised)`, `box-shadow: var(--shadow-lg)`, `border-radius: var(--radius-md)`
- Border-left: 3px solid `var(--color-accent-success)`
- Content: "✓ Finding #7 approved" 13px, `var(--color-text-primary)`
- Enter: slide up 20px + fade in, 300ms `--ease-spring`
- Auto-dismiss: after 4 seconds
- Exit: slide down 20px + fade out, 200ms `--ease-out-quint`
- On hover: dismiss timer pauses
- Action: [Undo] link in toast → reverses approval, 200ms `--ease-out-expo`

**Reject Action:**
1. User clicks [✗ Reject] button
2. Confirmation dialog appears (identical structure to Approve)
   - Title: "Reject Finding #N?"
   - Required: rejection reason from dropdown ["Inaccurate", "Incomplete", "Misleading", "Out of scope", "Needs more evidence", "Other"]
   - If "Other" selected: required text field appears (120px textarea, slides open 200ms)
3. On confirm:
   - Red sweep animation left→right, 400ms `--ease-out-expo`
   - Card opacity drops to 60% over 300ms
   - Rejection badge fades in
   - API: `PATCH /api/v1/sessions/:id/findings/:findingId` body `{status: "rejected", rejected_by: "kara", reason: "..."}`
   - Toast: "✗ Finding #7 rejected" with red border-left

**Revoke Approval:**
- Available on APPROVED findings
- Button: "Revoke Approval" (replaces Approve)
- Confirmation: "Revoke approval for Finding #N? This will return it to draft status."
- On confirm: green border fades back to default (400ms), badge fades out, actions revert to Approve/Reject
- API: `PATCH ...` body `{status: "draft"}`
- Toast: "Approval revoked for Finding #7"

**Keyboard Shortcuts for Approval:**
- `Ctrl+Enter` → approve currently selected/expanded finding
- `Ctrl+Backspace` → reject currently selected/expanded finding
- `Escape` → close confirmation dialog

**Memory Event on Approval:**
When a finding is approved, the system emits a `MemoryEvent`:
```json
{
  "id": "uuid",
  "type": "finding_status_change",
  "content": "Finding #7 approved by kara",
  "trust_level": 1.0,
  "iteration": 0,
  "timestamp": "2026-06-23T14:33:12.000Z",
  "metadata": {
    "finding_id": "uuid",
    "previous_status": "draft",
    "new_status": "approved",
    "actor": "kara",
    "comment": "Looks solid, matches the server logs."
  }
}
```
This event appears in the investigation timeline and can trigger webhooks.

#### 5.5.4 Reasoning Links

Bidirectional linking between SAYS (findings) and THINK (reasoning steps) is the core navigational affordance of the workbench.

**SAYS → THINK (Finding sources):**
- Each finding card has a "Based on: Step N · Step M" row
- Each step number is a clickable link styled as `var(--color-text-link)` with underline on hover
- **Click behavior:**
  1. THINK pane scrolls to the referenced thought card
  2. Smooth scroll: `element.scrollIntoView({ behavior: 'smooth', block: 'center' })`
  3. If THINK pane is collapsed → auto-expand to previous width (or 50%), then scroll
  4. Target thought card highlights:
     - Green glow pulse: `box-shadow: 0 0 20px var(--color-accent-success)` → 0, 2×300ms
     - Background: `var(--color-accent-success)` at 6% opacity for 1.5s, then fades
  5. A brief connection indicator: thin green line drawn from finding to thought via SVG overlay (see 5.4.3 Connection Line Animation)
  6. If multiple steps linked and user clicks one, others dim slightly (opacity 0.7, 200ms)

**THINK → SAYS (Finding derived from thought):**
- Thought cards that contributed to a finding show a link row: "→ Finding #7 · Finding #12"
- Link appears as: 28px row below reasoning text, `var(--color-bg-surface)`, `border-radius: var(--radius-sm)`
- Icon: → arrow, 14px, `var(--color-accent-success)`
- Finding number(s): 11px, `var(--color-text-link)`, clickable
- **Click behavior:**
  1. SAYS pane scrolls to referenced finding
  2. If SAYS collapsed → expand, then scroll
  3. Target finding highlights with green glow pulse (same as above)
  4. SVG connection line drawn

**Bidirectional Highlight:**
When user is viewing a link relationship:
- Both linked cards get a subtle persistent indicator: 2px colored bar on the inner edge (thought's right edge, finding's left edge) in `var(--color-accent-success)`, 40% opacity
- This indicator persists while either card is in viewport
- Removed when user clicks elsewhere or after 30s timeout
- In the Evidence panel, linked evidence items also highlight

**"Show Linked" Action:**
- Button at bottom of Thought Card actions: "🔗 Show linked findings"
- Click: filters SAYS pane to show only findings derived from this thought
- SAYS pane header shows: "Filtered: 3 findings from Step 7 · [Clear filter ✕]"
- THINK pane shows the originating thought at top with indicator
- Clear filter: click ✕ or press Escape

**Link Graph Mini-Map (accessibility alternative):**
- Available via button in toolbar or `Ctrl+L`
- Small floating panel (300×200px, bottom-right corner of workbench content area)
- Shows a force-directed mini graph of thought↔finding links
- Nodes: circles (thought=purple, finding=green), edges: lines
- Click a node → scroll main pane to that card
- Drag to reposition panel
- Close: ✕ button or Escape

### 5.6 Input Area

The input area is the primary interaction surface for directing the AI agent. It occupies a fixed band at the bottom of the workbench, always visible regardless of pane scroll position.

#### 5.6.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ TOOLBAR (40px)                                                                    │
│ ┌──────────────────────────┬────────────────────────────────────────────────────┐ │
│ │ [📎 Attach] [@Context ▼] │ [#Model ▼]                    [Tokens: 0/128000]  │ │
│ └──────────────────────────┴────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────┤
│ TEXTAREA (min 64px, max 40vh, auto-grow)                                          │
│ ┌──────────────────────────────────────────────────────────────────────────────┐ │
│ │                                                                              │ │
│ │  Ask a question or direct the investigation...                         ▊     │ │
│ │                                                                              │ │
│ └──────────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────┤
│ STATUS BAR (24px, appears when processing)                                        │
│ ┌──────────────────────────────────────────────────────────────────────────────┐ │
│ │ ⟳ Processing... Step 3 of 8 · 2.4s elapsed · 1,247 tokens generated         │ │
│ └──────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Container CSS:**
```css
.input-area {
  border-top: 1px solid var(--color-border-default);
  background: var(--color-bg-canvas);
  display: flex;
  flex-direction: column;
  min-height: 64px;
  max-height: 40vh;
  flex-shrink: 0;
  transition: border-color var(--duration-quick) var(--ease-out-expo);
}

.input-area:focus-within {
  border-top-color: var(--color-border-focus);
  box-shadow: 0 -1px 8px rgba(99, 102, 241, 0.08);
}
```

#### 5.6.2 Input Toolbar

**Height:** 40px, horizontal flex, `padding: 0 var(--space-3)`, `gap: var(--space-2)`, `align-items: center`

**📎 Attach Button:**
- 32px height, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`
- Icon: 📎 16px + "Attach" 11px weight 500, `var(--color-text-secondary)`
- Default: transparent background
- Hover: `var(--color-bg-hover)`
- Click: opens file picker OR paste zone
  - File picker: OS-native dialog, accepts `.pdf,.csv,.txt,.json,.png,.jpg,.mp4,.wav,.log,.pcap`
  - Also supports: drag-and-drop files onto input area (visual feedback: dashed border `var(--color-accent-primary)`, "Drop files to attach" text)
  - Paste: Ctrl+V with file in clipboard auto-attaches
  - After attach: file appears as chip in input area, 28px height, with filename, size, ✕ remove button
- Attached files uploaded to `POST /api/v1/sessions/:id/evidence` (multipart)
- Upload progress: chip shows progress bar (thin, 2px, bottom of chip), `var(--color-accent-primary)`
- Max files: 20 per message, 100MB total, enforced client-side and server-side

**@Context Dropdown:**
- 32px height, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`
- Text: "@Context" 11px weight 500, `var(--color-text-secondary)`
- Down chevron: ▼ 8px, right
- Click: opens dropdown (240px wide, `var(--color-bg-surface-raised)`, `box-shadow: var(--shadow-lg)`, `border-radius: var(--radius-md)`)
- Dropdown items:
  - "This finding" (references currently expanded/selected finding)
  - "Recent thoughts" (last 10 thought cards)
  - "All approved findings" (all approved findings in session)
  - "Evidence panel selection" (currently selected evidence items)
  - "Custom date range..." (opens date picker)
  - "Entire session" (full context, subject to token limits)
- Each item: 32px height, 12px font, hover `var(--color-bg-hover)`, checkmark on selected
- Selected contexts shown as chips next to @Context button: e.g., "@Finding #7 ✕", "@All approved ✕"
- Keyboard: `@` key in textarea opens context picker at cursor position (auto-complete style)

**#Model Selector:**
- 32px height, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`
- Shows current model: "◆ claude-sonnet-4" 11px weight 500, `var(--color-text-secondary)`
- Click: dropdown with available models grouped by provider
  - Anthropic: claude-opus-4, claude-sonnet-4, claude-haiku-4
  - OpenAI: gpt-4o, gpt-4o-mini, o4-mini
  - Google: gemini-2.5-pro, gemini-2.5-flash
  - Each item: provider icon + model name + context window size + estimated cost per 1M tokens
  - Current model: highlighted with `var(--color-bg-selection)`
  - Keyboard: `Ctrl+M` opens model selector
- Model change persists per session, saved to `localStorage` key `chronicle.session.{id}.model`

**Token Counter:**
- Right-aligned in toolbar
- Text: "Tokens: 0/128000" 11px monospace, `var(--color-text-tertiary)`
- Updates on every keystroke (debounced 100ms) using client-side tokenizer (tiktoken for OpenAI models, approximate for others)
- Color changes at thresholds:
  - 0-75%: `var(--color-text-tertiary)`
  - 75-90%: `var(--color-accent-warning)`
  - 90-100%: `var(--color-accent-error)`, weight 600
- Over 100%: textarea border turns red, submit blocked, tooltip "Message exceeds token limit"

#### 5.6.3 Textarea

**Dimensions:**
- Min height: 64px (2 lines at 13px font + padding)
- Max height: 40vh
- Auto-grow: height adjusts on input, smooth transition 100ms `--ease-out-expo`
- Width: 100% minus `var(--space-3)` padding each side

**Styling:**
```css
.input-area textarea {
  width: 100%;
  min-height: 64px;
  max-height: 40vh;
  padding: var(--space-3) var(--space-4);
  border: none;
  outline: none;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 13px;
  font-family: inherit;
  line-height: 1.6;
  resize: none;
  overflow-y: auto;
}

.input-area textarea::placeholder {
  color: var(--color-text-tertiary);
  font-style: italic;
}

.input-area textarea:focus {
  outline: none;
}
```

**Placeholder:** "Ask a question or direct the investigation..." (varies by state):
- Default: "Ask a question or direct the investigation..."
- After finding approved: "Great. What should we investigate next?"
- After error: "The last operation failed. Try rephrasing or check the error details."
- Active streaming: "Agent is processing... (new input will queue)"

**Keyboard Shortcuts within Textarea:**
- `Enter` → submit (unless Shift+Enter for newline)
- `Shift+Enter` → newline
- `Ctrl+Enter` → submit regardless
- `Escape` → blur textarea (if not in middle of composition)
- `Ctrl+Z` / `Ctrl+Shift+Z` → undo/redo
- `Ctrl+K` → clear textarea
- `@` → open context auto-complete
- `#` → open model selector if at start of line
- `/` → open command palette (slash commands: /search, /summarize, /compare, /timeline, /export)
- `Ctrl+Up` / `Ctrl+Down` → cycle through previous messages (message history, last 20)
- `Ctrl+.` → stop streaming generation (same as stop button)

**Slash Commands:**
When `/` is typed at the start of a line (or after whitespace):
- Dropdown appears above textarea: 240px wide, `var(--color-bg-surface-raised)`, `box-shadow: var(--shadow-lg)`, `border-radius: var(--radius-md)`
- Commands:
  - `/search` → "Search connected data sources for specific information"
  - `/summarize` → "Summarize the current state of the investigation"
  - `/compare` → "Compare two or more findings or evidence items"
  - `/timeline` → "Generate a chronological timeline of events"
  - `/hypothesis` → "Propose and evaluate a hypothesis"
  - `/export` → "Export findings as a report"
  - `/link` → "Find connections between selected items"
  - `/verify` → "Fact-check a specific claim against evidence"
- Each command shows: icon + name + short description + keyboard shortcut (if any)
- Filter as user types: fuzzy match on name and description
- Select: click or Enter
- After selection: command name inserted as text, cursor positioned for arguments

**Disabled State:**
- When agent is processing: textarea `opacity: 0.5`, `pointer-events: none`
- Placeholder: "Agent is processing... (new input will queue)"
- However: user can still type (queued mode). A "Queue" badge appears: 20px pill, "1 queued", `var(--color-accent-warning)`
- When current processing completes, queued message auto-submits
- Max queue: 5 messages. Additional messages blocked with tooltip.

#### 5.6.4 Submission & Streaming Flow

**Submit (Enter press or click send icon — no send button visible, Enter is primary):**
1. Textarea content captured. If empty, submit blocked.
2. Client-side validation:
   - Token count ≤ model limit
   - At least 1 non-whitespace character
   - No blocked patterns (configurable, e.g., PII regex)
3. If validation passes:
   - Textarea clears immediately (slide up animation, 150ms `--ease-out-quint`)
   - Message appears in THINK pane as a user message card:
     - Distinct style: right-aligned, `var(--color-bg-surface-raised)`, `border-radius: var(--radius-lg) var(--radius-lg) 0 var(--radius-lg)` (speech bubble pointing right-bottom)
     - 13px, `var(--color-text-primary)`, max-width 70%
     - Timestamp: right-aligned, 10px, `var(--color-text-tertiary)`
     - Fade in + slide up 10px, 200ms `--ease-out-expo`
   - Loading state begins (see below)
4. API call: `POST /api/v1/sessions/:id/message`
   - Body: `{content: string, model: string, context_refs: string[], attachments: string[], metadata: {}}`
   - Attachments sent as multipart in same request if present
5. Response: `202 Accepted` with `{message_id: uuid, status: "processing"}`
6. WebSocket stream begins delivering `MemoryEvent` objects

**Loading/Processing State:**
- Input area toolbar transforms:
  - [📎 Attach] and [@Context ▼] and [#Model ▼] hide (fade out 150ms)
  - A "Stop" button appears in their place: ■ icon + "Stop" 11px weight 600, `var(--color-accent-error)`, 32px height
  - Click Stop → `POST /api/v1/sessions/:id/stop` → WebSocket sends final event, streaming halts
  - Token counter changes to live token stream: "Streaming: 1,247 tokens"
- Status bar appears below textarea (24px height, `var(--color-bg-surface)`, border-top 1px `var(--color-border-default)`):
  - Spinner: 12px, `var(--color-accent-primary)`, spinning (CSS animation, 0.8s linear infinite)
  - Text: "⟳ Processing... Step 3 of 8 · 2.4s elapsed · 1,247 tokens generated"
  - Updates every 500ms via WebSocket heartbeat
  - If step count unknown: "⟳ Processing... 2.4s elapsed"
- THINK pane:
  - First thought card appears with THINKING state (gradient border, cursor, streaming)
  - Subsequent thought cards appear as agent progresses through reasoning steps
- SAYS pane:
  - Finding card appears in LOADING state (skeleton)
  - When agent completes reasoning and generates finding, skeleton replaced with DRAFT finding
  - Finding card enters with slide-up+fade animation (300ms `--ease-out-expo`)

**Streaming Details (60fps batched DOM):**
- WebSocket messages arrive as chunks: `{event: "thought_chunk", thought_id: uuid, chunk: string, chunk_index: int}`
- Chunks buffered in a ring buffer (max 50 chunks, ~25KB)
- requestAnimationFrame loop:
  - Every 16ms frame: drain buffer, concatenate chunks, update DOM
  - `thoughtCardElement.textContent += newText` (plain text) or `innerHTML` (sanitized markdown)
  - Cursor element maintained at end
  - If no new chunks in 3 frames (48ms): no DOM update
- Backpressure: if buffer exceeds 50 chunks, WebSocket pauses (send `{action: "pause"}`), resumes at 25 chunks
- Connection lost: cursor turns red, "Reconnecting..." status appears, auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)

**Streaming Completion:**
- WebSocket sends: `{event: "thought_complete", thought_id: uuid, metadata: {tokens: int, duration_ms: int}}`
- Thought card transitions THINKING → COMPLETED (see 5.4.2)
- Cursor fades out and is removed
- Timestamp fades in
- If agent produces finding: WebSocket sends `{event: "finding", finding_id: uuid, ...}`
  - SAYS skeleton replaced with real finding card (entry animation)
- Status bar updates: "✓ Completed · 8 steps · 12,847 tokens · 8.3s"
- Status bar auto-dismisses after 5s (slide down + fade out, 300ms)
- Input area returns to default state:
  - Toolbar buttons reappear (fade in 150ms)
  - Stop button fades out
  - Textarea enabled (opacity returns to 1, pointer-events restored)
  - Token counter resets to 0
  - Any queued messages auto-submit (with 500ms delay for smooth transition)

**Error State:**
- If API returns 4xx/5xx or WebSocket errors:
  - Status bar turns red: background `var(--color-accent-error)` at 10% opacity
  - Text: "✗ Error: {message}" 12px, `var(--color-accent-error)`
  - Error persists until dismissed (✕ button) or new message submitted
  - Thought cards that were streaming: border turns red, cursor removed, error icon (⚠) appears
  - Input area re-enabled immediately
  - Error details expandable: click status bar → expands to show full error response (200px max-height, scrollable)

#### 5.6.5 Message History

The input area maintains a history of submitted messages:
- Store: `localStorage` key `chronicle.session.{id}.messageHistory`, max 50 entries
- Each entry: `{content, timestamp, model, contextRefs}`
- Ctrl+Up: navigate to previous message (fills textarea)
- Ctrl+Down: navigate to next message
- At most recent message, Ctrl+Down clears textarea to blank
- At oldest message, Ctrl+Up stays (wraps only if setting enabled)
- Navigating away from a modified textarea saves current draft to history (as unsent)
- Unsent drafts marked with pencil icon (✎) in history browser

### 5.7 Evidence Panel

The Evidence panel is a slide-out drawer from the right edge of the workbench, providing access to all evidence items (documents, logs, images, etc.) associated with the current investigation.

#### 5.7.1 Layout

```
┌─────────────────────────────────────┐
│ EVIDENCE                  [✕ Close] │  ← Header 48px
├─────────────────────────────────────┤
│ ┌─────────────────────────────────┐ │
│ │ 🔍 Search evidence...           │ │  ← Search bar 36px
│ └─────────────────────────────────┘ │
├─────────────────────────────────────┤
│ FILTER: [All ▼] [Documents] [Logs]  │  ← Filter chips 32px
│ [Images] [Audio] [Video]            │
├─────────────────────────────────────┤
│ ┌─ SOURCES (12) ──────────────────┐ │
│ │ ┌─────────────────────────────┐ │ │
│ │ │ 📄 firewall_logs.csv     ▸ │ │ │  ← Source item 40px
│ │ │   2.4 MB · 14:22 uploaded │ │ │
│ │ │ ┌─────────────────────────┐ │ │ │
│ │ │ │ ████████████░░░░░ 73%   │ │ │ │  ← AI relevance score
│ │ │ └─────────────────────────┘ │ │ │
│ │ └─────────────────────────────┘ │ │
│ │ ┌─────────────────────────────┐ │ │
│ │ │ 🖼️ office_layout.png    ▸ │ │ │
│ │ │   1.1 MB · 13:47 uploaded │ │ │
│ │ │ ┌─────────────────────────┐ │ │ │
│ │ │ │ ██████████░░░░░░░ 62%   │ │ │ │
│ │ │ └─────────────────────────┘ │ │ │
│ │ └─────────────────────────────┘ │ │
│ │ ┌─────────────────────────────┐ │ │
│ │ │ 📝 witness_statement.txt ▸ │ │ │
│ │ │   48 KB · 14:05 uploaded  │ │ │
│ │ │ ┌─────────────────────────┐ │ │ │
│ │ │ │ ████████████████░ 91%   │ │ │ │
│ │ │ └─────────────────────────┘ │ │ │
│ │ └─────────────────────────────┘ │ │
│ └────────────────────────────────┘ │
├─────────────────────────────────────┤
│ ┌─ LINKED FINDINGS ───────────────┐ │
│ │ Finding #3 · Finding #7 ·       │ │  ← Finding links 28px each
│ │ Finding #12                      │ │
│ └────────────────────────────────┘ │
└─────────────────────────────────────┘
    360px wide
```

**Panel container:**
```css
.evidence-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 360px;
  height: 100%;
  background: var(--color-bg-canvas);
  border-left: 1px solid var(--color-border-default);
  box-shadow: var(--shadow-lg);
  z-index: 20;
  display: flex;
  flex-direction: column;
  transform: translateX(0);
  transition: transform var(--duration-slow) var(--ease-out-expo);
}

.evidence-panel.collapsed {
  transform: translateX(100%);
}
```

#### 5.7.2 Panel States

**COLLAPSED (default):**
- Panel translated off-screen right: `transform: translateX(100%)`
- Workbench content area expands to full width
- Evidence toggle button in toolbar shows panel is closed: icon ⏻ with no dot

**EXPANDED:**
- Panel slides in from right: `transform: translateX(0)`
- Duration: 400ms, easing `--ease-out-expo`
- Workbench content area width reduces by 360px (THINK+SAYS flex within remaining space)
- Evidence toggle button shows active state: icon ⏻ with green dot
- Panel gets `box-shadow: var(--shadow-lg)` on left edge
- If viewport < (current pane widths + 360px), panes compress to minimum 280px each

**RESIZING:**
- Left edge of panel is draggable (similar to divider in 5.3)
- Width range: 280px min, 600px max
- Drag behavior: cursor `col-resize` (reversed), identical interaction model to main divider
- Double-click left edge → reset to default 360px
- Width persisted in `localStorage` key `chronicle.evidence.width`

**FOCUSED:**
- Panel gets `z-index: 25` when user interacts with it (click, focus search)
- Border-left color: `var(--color-border-focus)`

#### 5.7.3 Evidence Panel Header

- Height: 48px, horizontal flex, `padding: 0 var(--space-3)`, `align-items: center`
- Background: `var(--color-bg-surface)`, border-bottom: 1px `var(--color-border-default)`
- Left: "EVIDENCE" 13px weight 600, `var(--color-text-primary)`, letter-spacing 0.5px
- Count badge: "(12)" 11px, `var(--color-text-tertiary)`
- Right: ✕ Close button
  - 28px square, `border-radius: var(--radius-sm)`
  - Icon: ✕ 14px, `var(--color-text-secondary)`
  - Hover: `var(--color-bg-hover)`, icon → `var(--color-text-primary)`
  - Click: collapse panel (400ms slide out)
  - Keyboard: `Ctrl+E` or `Escape` when panel focused

#### 5.7.4 Search Bar

- Height: 36px, `margin: var(--space-2) var(--space-3)`
- Input: 100% width, `border-radius: var(--radius-sm)`, `border: 1px solid var(--color-border-default)`, `padding: 0 var(--space-3)`, 12px font, `var(--color-bg-input)` background
- Placeholder: "🔍 Search evidence..." with magnifying glass icon
- Focus: border → `var(--color-border-focus)`, box-shadow `0 0 0 3px var(--color-accent-primary)` at 15% opacity
- Search behavior:
  - Filters evidence items in real-time (debounced 150ms)
  - Searches: filename, file type, content preview (first 500 chars of text files, OCR text for images)
  - Match highlighting: matching text wrapped in `<mark>` with `var(--color-accent-warning)` at 30% opacity background
  - No results: "No evidence matches '{query}'" 12px, `var(--color-text-tertiary)`, centered
- Clear button (✕) appears when input not empty: right-aligned inside input, 16px
- Keyboard: `Ctrl+F` when panel open → focus search

#### 5.7.5 Filter Chips

- Row: 32px height, `padding: 0 var(--space-3)`, `gap: var(--space-1)`, horizontal scroll if overflow
- "All" chip (default selected): 24px height, `border-radius: var(--radius-full)`, `padding: 0 var(--space-2)`, 11px weight 500
  - Selected: `var(--color-accent-primary)` background, white text
  - Unselected: `var(--color-bg-surface)`, `var(--color-text-secondary)`, border 1px `var(--color-border-default)`
- Type chips: same style for "Documents", "Logs", "Images", "Audio", "Video", "Other"
- Click: selects that filter, deselects others (single-select)
- Count shown subtly: "Documents (5)"

#### 5.7.6 Source List

- Scrollable area: flex-grow 1, `overflow-y: auto`, `padding: 0 var(--space-2)`
- Virtualized list for performance (react-window or equivalent, renders only visible items + 5 buffer)

**Source Item:**
- 40px height (collapsed), `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`, `margin-bottom: 2px`
- Layout: horizontal flex, `align-items: center`, `gap: var(--space-2)`
- Default: transparent background
- Hover: `var(--color-bg-hover)`, cursor pointer
- Selected: `var(--color-bg-selection)`, left-border 2px `var(--color-accent-primary)`
- Content:
  - File type icon: 20px, left. Icons: 📄 (doc), 📊 (csv/log), 🖼️ (image), 🔊 (audio), 🎬 (video), 📝 (text), 🗂️ (other)
  - Filename: 12px weight 500, `var(--color-text-primary)`, truncated with ellipsis after 200px
  - Metadata: 10px, `var(--color-text-tertiary)`, "2.4 MB · 14:22 uploaded"
  - Relevance bar: 28px wide, 4px height, `var(--color-bg-input)` background, fill `var(--color-accent-success)` at width = relevance%
    - Relevance from API: `GET /api/v1/sessions/:id/evidence/:evidenceId/relevance`
    - Shows on hover or always (setting-dependent)
  - Expand chevron: ▸ 12px, right, rotates 90° when expanded

**Source Item Expanded:**
- Height: auto (up to 300px)
- Below filename row:
  - Content preview: first 500 chars of text, or thumbnail for images (200×150px), or waveform for audio (200×30px)
  - Preview background: `var(--color-bg-input)`, `border-radius: var(--radius-sm)`, `padding: var(--space-2)`, 11px monospace
  - Actions row: [View Full] [Download] [Cite in Input] [Remove] [Refresh Metadata]
  - "Cited in: Step 3 · Step 5 · Finding #7" — links to those cards
  - Tags: editable tag chips (if user added tags)

**Context Menu (right-click on source item):**
- Menu items:
  - "Open in new tab" → opens evidence viewer (full-screen overlay)
  - "Download" → triggers browser download
  - "Cite in current input" → inserts reference into input textarea
  - "Find related thoughts" → highlights THINK cards citing this source
  - "Find related findings" → highlights SAYS cards citing this source
  - "Re-analyze" → sends source back to agent for re-analysis
  - "Add tag..." → inline tag editor
  - "Remove from investigation" → confirmation dialog, then `DELETE /api/v1/sessions/:id/evidence/:evidenceId`
- Menu: same style as all context menus (200px wide, raised surface, shadow-lg, 32px items)

#### 5.7.7 Drag to Input

Evidence items are draggable:
- Drag handle: grip icon (⋮⋮) on left of source item, appears on hover
- Drag initiation: `mousedown` on grip, 100ms hold, then drag
- Drag ghost: semi-transparent copy of source item (opacity 0.8), follows cursor, 200×40px
- Valid drop target: Input area (highlights with dashed border `var(--color-accent-primary)`, "Drop to cite" text)
- On drop: inserts `@[source:filename]` reference at cursor position in textarea
- Invalid drop: ghost returns to origin with spring animation (400ms `--ease-spring`)

#### 5.7.8 Linked Findings Section

- Below source list, separated by 1px `var(--color-border-default)` divider
- Header: "LINKED FINDINGS" 11px weight 600, `var(--color-text-tertiary)`, letter-spacing 0.5px, `padding: var(--space-2) var(--space-3)`
- List: compact finding links, 28px height each
  - "Finding #3" 12px, `var(--color-text-link)`, click to scroll SAYS pane
  - First line of conclusion: 10px, `var(--color-text-tertiary)`, truncated 80px
  - Status dot: 6px circle, green (approved), gray (draft), red (rejected)
- Sorted by finding number descending
- Empty: "No linked findings" 11px italic, `var(--color-text-tertiary)`

#### 5.7.9 Evidence Viewer (Full-Screen Overlay)

When "Open in new tab" or "View Full" is clicked:
- Full-screen overlay: `rgba(0,0,0,0.6)` backdrop, z-index 100
- Content area: centered, max-width 90vw, max-height 90vh, `var(--color-bg-surface)`, `border-radius: var(--radius-lg)`, `box-shadow: var(--shadow-lg)`
- Header: filename + file type + close button
- Body:
  - Text files: full content rendered with syntax highlighting (auto-detected), monospace 12px, line numbers, scrollable
  - CSV/logs: virtualized table view, sortable columns, filter per column
  - Images: full-resolution with zoom (pinch + scroll wheel), pan (drag)
  - Audio: waveform + playback controls (play/pause, seek, speed 0.5×-3×)
  - Video: player with same controls as audio + frame stepping
  - PDF: embedded viewer with page navigation, text selection, search
- Footer: actions bar [Download] [Cite] [Close]
- Close: ✕ button, Escape key, or click backdrop
- Enter/exit animation: scale 0.95→1.0 + opacity 0→1, 250ms `--ease-spring`

### 5.8 Workbench Toolbar

The toolbar is a 48px horizontal bar spanning the full width of the workbench, providing session-level controls and status indicators.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ┌─────────────────────────┐ ┌──────────────────────────────────┐ ┌─────────────────┐ │
│ │ [▼] Session switcher    │ │ 🔍 Investigation Title          │ │ [⏻] [⬆] [⚙]   │ │
│ │ [New Session +]         │ │ ● Active · 8 steps · 3 findings │ │ Evidence Export │ │
│ └─────────────────────────┘ └──────────────────────────────────┘ └─────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

#### 5.8.1 Layout & Styling

```css
.workbench-toolbar {
  height: 48px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-3);
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border-default);
  gap: var(--space-3);
  flex-shrink: 0;
  z-index: 15;
}
```

#### 5.8.2 Left Section — Session Switcher

**Session Dropdown Button:**
- 36px height, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`, `gap: var(--space-1)`
- Icon: ▼ 10px (rotates 180° when open), `var(--color-text-tertiary)`
- Text: current session title, 13px weight 500, `var(--color-text-primary)`, max 200px truncated
- Default: transparent background
- Hover: `var(--color-bg-hover)`
- Active (dropdown open): `var(--color-bg-selection)`

**Dropdown Panel:**
- Width: 320px, `var(--color-bg-surface-raised)`, `box-shadow: var(--shadow-lg)`, `border-radius: var(--radius-md)`, `border: 1px solid var(--color-border-default)`
- Header: "Sessions" 13px weight 600 + [New Session +] button (right)
- Session list (scrollable, max-height 400px):
  - Each session item: 44px height, `padding: 0 var(--space-3)`, `border-radius: var(--radius-sm)`
  - Layout: status dot (left, 8px circle) + title (13px) + metadata line (10px, `var(--color-text-tertiary)`)
  - Status dots: green (active), gray (paused), blue (completed), yellow (queued)
  - Metadata: "8 steps · 3 findings · 2h ago"
  - Hover: `var(--color-bg-hover)`
  - Active session: `var(--color-bg-selection)`, left-border 2px `var(--color-accent-primary)`
  - Click: switch to that session (see 5.9)
  - Right-click: context menu (Rename, Duplicate, Archive, Delete)
- Footer: "View all sessions →" link, opens sessions management page
- Close: click outside or Escape

**New Session Button:**
- 28px height, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`, 11px weight 500
- Text: "+ New Session" or just "+" icon in compact mode
- `var(--color-accent-primary)` color, transparent background
- Hover: `var(--color-accent-primary)` at 8% opacity background
- Click: opens new session dialog (modal)
  - Title: "New Investigation" 16px weight 600
  - Fields: Title (required), Goal/description (textarea), Agent persona (dropdown), Model (dropdown), Initial context (optional, evidence selector)
  - Cancel / Create buttons
  - On create: `POST /api/v1/sessions` body `{title, goal, agent_name, model_id, initial_context}`
  - Returns `Session` object, switches to new session
- Keyboard: `Ctrl+Shift+N`

#### 5.8.3 Center Section — Title & Status

**Investigation Title:**
- 14px weight 600, `var(--color-text-primary)`
- Editable inline: double-click → text input (preserves styling), Enter to save, Escape to cancel
- Max 120 chars, truncated with ellipsis
- Update: `PATCH /api/v1/sessions/:id` body `{title: "New Title"}`

**Status Line (below title):**
- 11px, `var(--color-text-tertiary)`
- Format: "● Active · 8 steps · 3 findings" or "⏸ Paused · 12 steps · 5 findings" or "✓ Completed · 24 steps · 11 findings"
- Status dot: 6px circle, animated pulse for Active (scale 0.8→1.2, 2s `--ease-out-expo`)
- Live updates as steps/findings change via WebSocket

**Processing Indicator:**
- When agent is actively working, status line shows: "⟳ Processing step 3 of 8..."
- Spinner: 10px, `var(--color-accent-primary)`, inline with text
- Progress bar: 2px height, full toolbar width, positioned at bottom of toolbar
  - Background: `var(--color-border-default)`
  - Fill: `var(--color-accent-primary)`, animated width 0%→100% over estimated duration
  - When progress unknown, shows indeterminate animation: 30% width bar sliding left→right, 2s cycle

#### 5.8.4 Right Section — Action Buttons

All buttons: 32px height, `border-radius: var(--radius-sm)`, `padding: 0 var(--space-2)`, 11px weight 500, `var(--color-text-secondary)`, transparent background, hover `var(--color-bg-hover)`, icon 14px left of text.

**Evidence Toggle (⏻):**
- Toggles Evidence panel visibility (see 5.7)
- Active state: `var(--color-accent-primary)` color, green dot indicator
- Inactive: `var(--color-text-secondary)`
- Badge: shows evidence count "(12)" in 10px, `var(--color-text-tertiary)`
- Keyboard: `Ctrl+E`

**Export (⬆):**
- Opens export dialog (modal)
- Options:
  - Format: PDF, Markdown, JSON, DOCX
  - Scope: "All approved findings", "Selected findings", "Entire investigation", "Summary only"
  - Include: evidence references, thought chain (optional), confidence scores, timeline
  - Template: "Standard Report", "Executive Summary", "Technical Brief", "Custom..."
- Preview button: generates preview in right panel
- Export button: triggers download or sends to configured destination (email, API webhook)
- Keyboard: `Ctrl+Shift+E`

**Share (🔗):**
- Opens share dialog
- Options: "Copy link", "Invite collaborator (email)", "Set permissions (view/edit/admin)"
- Link generation: `GET /api/v1/sessions/:id/share-link` returns `{url, expires_at, permissions}`
- Collaborator management: list current collaborators with role badges, remove button, add field

**Settings (⚙):**
- Opens workbench settings panel (slide-out from right, 320px wide, overlays evidence panel if open)
- Settings:
  - **Appearance**: "Thought card density: Compact/Comfortable", "Show confidence bars", "Show timestamps", "Color scheme: Match system/Dark/Light", "Font size: 11/12/13/14px"
  - **Behavior**: "Auto-scroll on new content", "Auto-expand findings", "Confirm before approval", "Show connection lines", "Streaming speed: Normal/Fast (skip animation)"
  - **Pane Defaults**: "Default THINK/SAYS ratio", "Default evidence panel state", "Collapse completed thoughts after: Never/1min/5min/30min"
  - **Keyboard**: link to full shortcuts reference
  - **Advanced**: "Enable experimental features", "WebSocket endpoint override", "Clear local cache"
- Changes saved immediately to `localStorage` + user preferences API `PATCH /api/v1/users/me/preferences`

**⋯ More Menu:**
- Items: "Investigation timeline", "Export session log", "Duplicate investigation", "Archive investigation", "Delete investigation"
- Delete: requires typing investigation title to confirm (destructive action prevention)

#### 5.8.5 Toolbar States

**DEFAULT:** All controls visible and enabled.

**PROCESSING:** Session switcher and New disabled (tooltip: "Wait for current processing to complete"). Export and Share enabled. Settings enabled.

**EMPTY (no session loaded):**
- Session switcher shows "No investigation loaded"
- Center: "Chronicle" 14px weight 600 (brand placeholder)
- Status: "Create or select an investigation to begin"
- Actions: only [New Session +] and [Settings] enabled
- THINK and SAYS panes show empty states
- Input area disabled

**ERROR (session load failed):**
- Toolbar turns red tint: `var(--color-accent-error)` at 6% opacity background
- Status: "⚠ Failed to load investigation" 13px, `var(--color-accent-error)`
- Actions: [Retry] button, [Dismiss] button

### 5.9 Multi-Investigation Switching

Chronicle supports multiple concurrent investigations. Switching between them preserves full state including pane ratios, scroll positions, and expanded cards.

#### 5.9.1 Investigation Switcher Overlay

**Trigger:** `Ctrl+Shift+I` or click session dropdown → "View all sessions"

**Overlay:**
- Full-viewport overlay: `rgba(0, 0, 0, 0.5)` backdrop, `backdrop-filter: blur(4px)`
- Content: centered grid, max-width 1200px, max-height 80vh
- Entry animation: scale 0.95→1.0 + opacity 0→1, 200ms `--ease-spring`
- Exit animation: reverse, 150ms `--ease-out-quint`
- Close: Escape, click backdrop, or ✕ button (top-right, 32px)

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ 🔍 Search investigations...    [+ New Investigation]    │  ← Header 48px
├─────────────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐     │
│ │ ● Active     │ │ ⏸ Paused    │ │ ✓ Completed  │     │  ← Cards in CSS Grid
│ │              │ │              │ │              │     │   (3 columns, 1fr each,
│ │ Corp Breach  │ │ Supply Chain │ │ Phishing     │     │   gap var(--space-3))
│ │ Investigation│ │ Risk Analysis│ │ Campaign     │     │
│ │              │ │              │ │              │     │
│ │ 8 steps      │ │ 12 steps     │ │ 24 steps     │     │
│ │ 3 findings   │ │ 5 findings   │ │ 11 findings  │     │
│ │ just now      │ │ 2h ago       │ │ yesterday    │     │
│ │              │ │              │ │              │     │
│ │ [Switch]     │ │ [Resume]     │ │ [Review]     │     │
│ └──────────────┘ └──────────────┘ └──────────────┘     │
│                                                         │
│ ┌──────────────┐ ┌──────────────┐                       │
│ │ ⏳ Queued    │ │ 📦 Archived  │                       │
│ │ ...          │ │ ...          │                       │
│ └──────────────┘ └──────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

**Investigation Card:**
- 280×180px, `var(--color-bg-surface)`, `border-radius: var(--radius-md)`, `border: 1px solid var(--color-border-default)`, `padding: var(--space-3)`
- Hover: `box-shadow: var(--shadow-md)`, border → `var(--color-border-hover)`, translateY(-2px), 200ms `--ease-out-expo`
- Active session: border 2px `var(--color-accent-primary)`, subtle glow `box-shadow: 0 0 12px var(--color-accent-primary)` at 15% opacity
- Layout:
  - Status badge: top-left, 20px pill. Green (active), gray (paused), blue (completed), yellow (queued), dark-gray (archived)
  - Title: 14px weight 600, `var(--color-text-primary)`, 2 lines max
  - Stats: 11px, `var(--color-text-tertiary)`. "8 steps · 3 findings"
  - Agent/model line: 10px, `var(--color-text-tertiary)`. "◆ claude-sonnet-4"
  - Relative time: 10px, `var(--color-text-tertiary)`. "just now" / "2h ago"
  - Action button: bottom-right, 28px height, `border-radius: var(--radius-sm)`, context-dependent:
    - Active: disabled (current session)
    - Paused/Queued: "Resume" → `PATCH /api/v1/sessions/:id` body `{status: "active"}`
    - Completed: "Review" → opens in read-only mode
    - Archived: "Restore" → moves back to active
- Right-click context menu: "Rename", "Duplicate", "Change model", "Archive", "Delete"

**Search/Filter:**
- Search bar at top: filters cards by title, agent name, model, status
- Debounced 200ms, real-time filtering
- Tags: user-assigned tags shown on cards, filterable via tag chips below search bar
- Sort: dropdown with "Most recent", "Alphabetical", "Status", "Findings count"

#### 5.9.2 State Persistence During Switch

When switching from session A to session B:

1. **Save session A state:**
   - Scroll positions of THINK and SAYS panes → `localStorage`
   - Divider ratio → `localStorage`
   - Expanded card IDs (both panes) → `localStorage`
   - Evidence panel state (open/closed, width, scroll position, expanded items) → `localStorage`
   - Input textarea content → `localStorage` (draft preservation)
   - Active filter states → `localStorage`

2. **Load session B state:**
   - API call: `GET /api/v1/sessions/:id` (session metadata)
   - API call: `GET /api/v1/sessions/:id/memory?limit=50` (recent memory events)
   - WebSocket connection: close session A WS, open session B WS
   - Restore UI state from `localStorage`
   - If no saved state: default layout (50/50 divider, scroll to bottom, nothing expanded)

3. **Transition animation:**
   - Session A content fades out: opacity 1→0, 150ms `--ease-out-quint`
   - Brief loading skeleton (200ms)
   - Session B content fades in: opacity 0→1, 200ms `--ease-out-expo`
   - Overall switch time target: < 500ms for cached sessions

4. **URL Update:**
   - Browser URL updates: `/investigations/:id` (pushState, no page reload)
   - Browser back/forward buttons work: popstate handler triggers session switch
   - Deep linking: navigating directly to `/investigations/:id` loads that session

#### 5.9.3 Concurrent Session Management

- Max active sessions: 5 (configurable server-side)
- Attempting to activate a 6th: confirmation dialog "Pause '{currentSession}' to activate '{newSession}'?"
- Paused sessions: agent stops processing, WebSocket closes, state saved
- Queued sessions: created but not yet started, appear in switcher with "Start" button
- Session lifecycle states:
  ```
  queued → active ↔ paused
                ↓
            completed
                ↓
            archived
  ```
- Auto-pause: sessions inactive for 30 minutes (no user interaction) auto-pause (configurable)
- Auto-archive: completed sessions older than 7 days auto-archive (configurable)

#### 5.9.4 Cross-Session Operations

- Copy finding from session A to session B: drag finding card from SAYS pane to session card in switcher overlay
- Compare sessions: select 2+ sessions in switcher (Ctrl+click), click "Compare" → opens diff view
- Merge sessions: select 2+ sessions, click "Merge" → creates new session combining evidence and findings
- Global search: `Ctrl+Shift+F` searches across all sessions' findings and thoughts

### 5.10 API Contract Reference

#### 5.10.1 Sessions

```
GET    /api/v1/sessions              → Session[]           (list, ?status=active&limit=20&offset=0)
POST   /api/v1/sessions              → Session             (create, body: {title, goal, agent_name, model_id, initial_context?})
GET    /api/v1/sessions/:id          → Session             (get single)
PATCH  /api/v1/sessions/:id          → Session             (update, body: partial<Session>)
DELETE /api/v1/sessions/:id          → {deleted: true}     (requires confirmation, archives first)
POST   /api/v1/sessions/:id/stop     → {status: "stopped"} (stop active processing)
POST   /api/v1/sessions/:id/pause    → {status: "paused"}  (pause active processing)
POST   /api/v1/sessions/:id/resume   → {status: "active"}  (resume from paused)
GET    /api/v1/sessions/:id/share-link → {url, expires_at, permissions}
```

**Session object:**
```json
{
  "id": "uuid",
  "title": "string",
  "status": "queued|active|paused|completed|archived|error",
  "agent_name": "string",
  "goal": "string",
  "model_id": "string",
  "iteration": 0,
  "finding_count": 0,
  "thought_count": 0,
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "created_by": "string",
  "collaborators": ["uuid"],
  "tags": ["string"]
}
```

#### 5.10.2 Memory Events

```
GET    /api/v1/sessions/:id/memory            → MemoryEvent[]  (?type=thought|finding|evidence&limit=50&before=uuid&after=uuid)
GET    /api/v1/sessions/:id/memory/:eventId   → MemoryEvent
WS     /ws/v1/sessions/:id                    → MemoryEvent stream
```

**WebSocket protocol:**
```
Client → Server:
  {action: "subscribe", session_id: "uuid"}
  {action: "pause"}                    // backpressure
  {action: "resume"}                   // resume stream
  {action: "unsubscribe"}

Server → Client:
  {event: "thought_start", thought_id: "uuid", iteration: int}
  {event: "thought_chunk", thought_id: "uuid", chunk: "string", chunk_index: int}
  {event: "thought_complete", thought_id: "uuid", metadata: {tokens: int, duration_ms: int}}
  {event: "finding", finding_id: "uuid", content: "string", confidence: float, sources: [int]}
  {event: "finding_update", finding_id: "uuid", changes: {...}}
  {event: "evidence_processed", evidence_id: "uuid", relevance: float}
  {event: "error", code: "string", message: "string"}
  {event: "heartbeat", timestamp: "ISO8601"}
  {event: "session_status", status: "string", iteration: int}
```

**MemoryEvent object:**
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "type": "thought|finding|evidence|finding_status_change|user_message|system",
  "content": "string (markdown)",
  "trust_level": 0.0-1.0,
  "iteration": 0,
  "timestamp": "ISO8601",
  "sources": [
    {
      "evidence_id": "uuid",
      "filename": "string",
      "relevance": 0.0-1.0
    }
  ],
  "flags": [
    {
      "type": "contradiction|correlation|anomaly|hallucination|uncertainty",
      "severity": "info|warning|critical",
      "description": "string",
      "linked_event_id": "uuid|null",
      "linked_type": "thought|finding|null"
    }
  ],
  "metadata": {
    "model": "string",
    "tokens_used": 0,
    "duration_ms": 0,
    "finding_id": "uuid|null",
    "finding_status": "draft|approved|rejected|outdated|null"
  }
}
```

#### 5.10.3 Evidence

```
POST   /api/v1/sessions/:id/evidence                  → Evidence         (upload, multipart)
GET    /api/v1/sessions/:id/evidence                  → Evidence[]       (list)
GET    /api/v1/sessions/:id/evidence/:evidenceId       → Evidence         (get single + content)
GET    /api/v1/sessions/:id/evidence/:evidenceId/relevance → {relevance: float} (AI relevance score)
DELETE /api/v1/sessions/:id/evidence/:evidenceId       → {deleted: true}
PATCH  /api/v1/sessions/:id/evidence/:evidenceId       → Evidence         (update metadata/tags)
```

#### 5.10.4 Findings

```
PATCH  /api/v1/sessions/:id/findings/:findingId        → Finding          (approve/reject/update)
POST   /api/v1/sessions/:id/findings/:findingId/re-evaluate → {status: "queued"} (re-send to agent)
```

#### 5.10.5 Messages

```
POST   /api/v1/sessions/:id/message                    → {message_id: uuid, status: "processing"} (submit user directive)
POST   /api/v1/sessions/:id/message/stop               → {status: "stopped"} (stop processing)
```

### 5.11 Keyboard Shortcuts Reference

| Shortcut | Action | Context |
|---|---|---|
| `Ctrl+E` | Toggle Evidence panel | Global |
| `Ctrl+Shift+I` | Open investigation switcher | Global |
| `Ctrl+Shift+N` | New investigation | Global |
| `Ctrl+Shift+F` | Global search (all sessions) | Global |
| `Ctrl+L` | Show link graph mini-map | Workbench |
| `Ctrl+Enter` | Submit input / Approve finding | Input area / Finding card |
| `Ctrl+Backspace` | Reject finding | Finding card focused |
| `Ctrl+Shift+Left` | Nudge divider left (expand SAYS) | Workbench |
| `Ctrl+Shift+Right` | Nudge divider right (expand THINK) | Workbench |
| `Ctrl+Shift+0` | Reset divider to 50/50 | Workbench |
| `Ctrl+Shift+[` | Collapse THINK pane | Workbench |
| `Ctrl+Shift+]` | Collapse SAYS pane | Workbench |
| `Left/Right arrows` | Nudge divider 40px | Divider focused |
| `Home` | Collapse THINK | Divider focused |
| `End` | Collapse SAYS | Divider focused |
| `Ctrl+M` | Open model selector | Input area |
| `Ctrl+K` | Clear textarea | Input area |
| `Ctrl+Up/Down` | Navigate message history | Input area |
| `Ctrl+.` | Stop streaming | Input area (during processing) |
| `@` | Open context auto-complete | Input area |
| `/` | Open slash command palette | Input area (start of line) |
| `Ctrl+F` | Focus evidence search | Evidence panel |
| `Escape` | Close modal/dropdown/dialog / Blur input | Global |
| `Ctrl+Shift+E` | Export investigation | Global |
| `Tab` | Move focus to next interactive element | Workbench |
| `Shift+Tab` | Move focus to previous | Workbench |
| `Ctrl+A` | Select all cards in current pane | THINK/SAYS pane |
| `Shift+Click` | Range select cards | THINK/SAYS pane |
| `Ctrl+Click` | Multi-select individual cards | THINK/SAYS pane |

### 5.12 Accessibility

**Screen Reader:**
- Each Thought Card: `role="article"`, `aria-label="Thought step {N}, model {name}, {relativeTime}"`
- Each Finding Card: `role="article"`, `aria-label="Finding {N}, status {draft|approved|rejected}, confidence {percent}%"`
- Divider: `role="separator"`, `aria-valuenow={ratio}`, `aria-valuemin=0`, `aria-valuemax=100`, `aria-label="Pane divider at {percent}%"`
- Evidence panel: `role="complementary"`, `aria-label="Evidence panel"`
- Live regions: streaming content updates `aria-live="polite"` for THINK cards, `aria-live="assertive"` for errors
- Status bar: `role="status"`, `aria-live="polite"`
- All buttons: descriptive `aria-label` if icon-only

**Keyboard Navigation:**
- Full Tab order: Toolbar → THINK pane cards → Divider → SAYS pane cards → Input toolbar → Textarea → Evidence panel (if open)
- Arrow key navigation within card lists (when pane focused)
- Skip links: hidden "Skip to input" link visible on first Tab

**Color & Contrast:**
- All text meets WCAG AA contrast ratios (4.5:1 for normal text, 3:1 for large text)
- Status indicators use shape + color (dots, badges, borders) — never color alone
- Confidence bar includes percentage text
- Streaming cursor visible against all backgrounds
- Focus indicators: 2px solid `var(--color-accent-primary)` outline with 2px offset on all interactive elements

**Reduced Motion:**
- `@media (prefers-reduced-motion: reduce)` disables:
  - Entry/exit animations (instant appear/disappear)
  - Streaming cursor blink (static)
  - Gradient border animation (static purple border)
  - Progress bar animation (static at current width)
  - Pulse animations
  - Spring easing (replaced with `ease-out`)
- Transition durations capped at 100ms

### 5.13 Performance Budgets

| Metric | Target | Measurement |
|---|---|---|
| Initial load (uncached) | < 1.5s | Lighthouse TTI |
| Initial load (cached session) | < 500ms | Custom timing |
| Session switch | < 500ms | Custom timing |
| Card render (single) | < 16ms | React Profiler |
| Batch render (50 cards) | < 100ms | React Profiler |
| Stream chunk → DOM update | < 16ms (1 frame) | rAF timing |
| Divider drag FPS | 60fps sustained | rAF counter |
| Evidence panel open | < 300ms | Transition timing |
| Memory (idle) | < 80MB heap | performance.memory |
| Memory (1000 cards loaded) | < 150MB heap | performance.memory |
| Virtual list scroll FPS | 60fps | rAF counter |
| WebSocket reconnect | < 2s (first attempt) | Custom timing |
