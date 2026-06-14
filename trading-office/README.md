# Hermes Trading Office

> **24/7 Campaign Intelligence Dashboard** — Progressive Web App for algorithmic trading surveillance, journaling, analytics, and risk management.

**Live**: https://trade.miniforex786.win/trading-office/  
**Repository**: https://github.com/miniforex786-png/Hermes (gh-pages branch)

---

## Overview

Single-file HTML PWA (`index.html` ~62KB) with embedded CSS/JS, zero build step, deployed to Cloudflare Pages. Designed for desktop monitoring and mobile access via "Add to Home Screen."

---

## Architecture

### Tech Stack
| Layer | Technology |
|-------|------------|
| Structure | Semantic HTML5 (single file) |
| Styling | CSS Custom Properties, CSS Grid, Tailwind CDN (utility classes only) |
| Fonts | JetBrains Mono (data), Space Grotesk (UI) via Google Fonts |
| Charts | Canvas API (vanilla, no libraries) |
| PWA | Web App Manifest, Service Worker ready, iOS splash screens |
| Deployment | Cloudflare Pages → gh-pages branch → custom domain |

### File Structure
```
trading-office/
├── index.html              # Main dashboard (single file, ~62KB)
├── manifest.json           # PWA manifest with shortcuts
├── icon.svg                # Scalable app icon (hexagon crosshair)
└── splash-*.png            # 8 iOS splash screens (640×1136 → 1536×2048)
```

---

## Layout System

### Responsive CSS Grid Breakpoints
| Breakpoint | Layout | Use Case |
|------------|--------|----------|
| `≥1400px` | 12-col: 280px gutters + 8fr center (cols 2-9), 4 rows | Full desktop |
| `≤1200px` | 6-col grid, side desks paired | Tablet / small laptop |
| `≤768px` | Single column, all desks stacked | Mobile portrait |
| `≤480px` | Compact padding, particles hidden | Small mobile |
| Landscape ≤768px | 2-col grid, P&L spans bottom | Mobile landscape |

### Grid Architecture (≥1400px)
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Header (sticky, backdrop blur)                                              │
├──────┬──────────────────────────────────────────────────────┬────────────────┤
│      │                                                      │                │
│ Obs  │            CENTRAL P&L SCREEN (60vh)                │  Analyst       │
│      │  ┌──────────────────────────────────────────────┐   │                │
│ Jour │  │  +$12,847.32  │  Realized  Unrealized  DD   │   │  Researcher    │
│      │  │  [ equi-ty curve chart ]                     │   │                │
├──────┼──────────────────────────────────────────────────┼────────────────┤
│      │  SHARPE   │  MAX DD   │  PROFIT F  │  WIN RATE  │                │
│ Coach│  (card)   │  (card)   │  (card)    │  (card)    │     Auto       │
├──────┼──────────────────────────────────────────────────┼────────────────┤
│      │            RISK GUARDIAN (spans cols 2-9)       │                │
└──────┴──────────────────────────────────────────────────┴────────────────┘
Row 1: 60vh P&L          Row 2: Stat cards (auto)    Row 3: Risk (auto)   Row 4: spacer
```

### Desk Modules (7 Total)
| Desk | Position | Color | Monitors | Purpose |
|------|----------|-------|----------|---------|
| **Observer** | Left col, row 1 | Teal | Session State, Edge Metrics | Market surveillance |
| **Trading Journal** | Left col, row 2 | Blue | Today's Log, Execution Quality | Execution archive |
| **Campaign Analyst** | Right col, row 1 | Purple | Active Campaigns, Attribution | Performance attribution |
| **Pattern Researcher** | Right col, row 2 | Amber | Hypothesis Queue, Backtest Results | Edge discovery |
| **Trading Coach** | Left col, row 3 | Pink | Behavioral Alerts, Coaching Queue | Behavioral feedback |
| **Risk Guardian** | Center, row 3 | Red | Hard Limits, Escalation Ladder | Hard limits & escalation |
| **Semi-Auto Assistant** | Right col, row 3 | Teal | Pending Orders, Execution Engine | Order execution |

**All side desks stack monitors vertically** (1-col) for readability. Risk Guardian keeps 2-col layout per user preference.

---

## Features

### 1. Central P&L Wall Screen
- **Primary metric**: Net P&L (realized + unrealized) with color-coded glow
- **Sub-metrics**: Realized, Unrealized, Max Drawdown, Risk Used %
- **Equity curve**: Real-time animated Canvas chart (200 data points, 60fps throttled)
- **Live updates**: Simulated P&L drift every 2s (replace with MT5/Parquet feed)

### 2. Bottom Stat Cards (4)
| Card | Metric | Source |
|------|--------|--------|
| Sharpe Ratio (30D) | 2.34 | Backtest / live |
| Max Drawdown (30D) | -8.2% | Risk Guardian |
| Profit Factor | 1.87 | Campaign Analyst |
| Win Rate (Session) | 64.3% | Trading Journal |

### 3. Observer Desk
- **Session State**: Asia/London/NY session status + volatility regime
- **Edge Metrics**: Spread, slippage, fill rate, latency (milliseconds)

### 4. Trading Journal
- **Today's Log**: Trades, wins, losses, win rate
- **Execution Quality**: Avg entry/exit R, MFE capture %, MAE control %

### 5. Campaign Analyst
- **Active Campaigns**: Probe/Discretionary campaigns with R-multiples
- **Attribution**: Directional, mean reversion, breakout, scalp P&L

### 6. Pattern Researcher
- **Hypothesis Queue**: H1/H4/D1/M12 hypotheses with VALIDATED/TESTING/PENDING/CONFIRMED status
- **Backtest Results**: Sharpe, Max DD, Profit Factor, Trades/Year

### 7. Trading Coach
- **Behavioral Alerts**: Oversizing, revenge trade, FOMO, hesitation flags
- **Coaching Queue**: Next review time, focus area, priority, data sources

### 8. Risk Guardian
- **Hard Limits**: Daily loss, position size, correlation, drawdown (current vs limit)
- **Escalation Ladder**: L1 Warning (50%), L2 Reduce (75%), L3 Flatten (90%), L4 Lockdown (100%)

### 9. Semi-Auto Assistant
- **Pending Orders**: Limit buys, stop losses, take profits, OCO brackets
- **Execution Engine**: Latency, queue depth, retries, mode (ASSIST/AUTO)

---

## PWA Features

### Manifest (`manifest.json`)
```json
{
  "name": "Hermes Trading Office",
  "short_name": "Hermes Office",
  "start_url": "./index.html",
  "display": "standalone",
  "background_color": "#0a0e14",
  "theme_color": "#0a0e14",
  "shortcuts": [
    { "name": "P&L Dashboard", "url": "./index.html#pnl" },
    { "name": "Risk Guardian", "url": "./index.html#risk" }
  ]
}
```

### iOS Splash Screens (8 sizes)
| Size | Device |
|------|--------|
| 640×1136 | iPhone 5/SE |
| 750×1334 | iPhone 6/7/8 |
| 828×1792 | iPhone XR/11 |
| 1125×2436 | iPhone X/11 Pro |
| 1179×2556 | iPhone 12/13/14 Pro |
| 1284×2778 | iPhone 12/13/14 Pro Max |
| 1290×2796 | iPhone 15 Pro |
| 1536×2048 | iPad Pro 12.9" |

Generated via Canvas API, linked with precise `media` queries.

### Mobile Interactions
- **Swipe navigation**: Horizontal swipe between desks (focus + scroll into view)
- **Pull-to-refresh**: Custom spinner, reloads P&L + chart + desk data
- **Viewport height fix**: `--vh` CSS variable updated on resize/orientationchange
- **Touch targets**: Minimum 44px (`.desk-action`, `.stat-card`)
- **Focus management**: Keyboard accessible, ARIA labels, focus-visible outlines

### Performance Guards
- **Low-end detection**: `navigator.hardwareConcurrency ≤ 4` OR `deviceMemory ≤ 4`
- **Auto-disables**: Grid animation, glow orbs, particles, desk transitions
- **IntersectionObserver**: Pauses off-screen monitor animations
- **`prefers-reduced-motion`**: Respected globally

---

## Visual Design

### Color System (CSS Custom Properties)
| Token | Value | Use |
|-------|-------|-----|
| `--bg` | `#0a0e14` | Page background |
| `--bg-elevated` | `#111820` | Header, panels |
| `--panel` | `#161d26` | Card backgrounds |
| `--panel-border` | `#1e2a38` | Borders |
| `--ink` | `#e8edf2` | Primary text |
| `--ink-muted` | `#7a8a9a` | Secondary text |
| `--ink-dim` | `#4a5a6a` | Labels |
| `--accent` | `#00d4aa` | Primary brand (teal) |
| `--accent-glow` | `rgba(0,212,170,0.35)` | Glows, shadows |
| `--danger` | `#ff4757` | Risk, losses |
| `--warning` | `#ffa502` | Warnings, pending |
| `--info` | `#3742fa` | Info, campaigns |
| `--success` | `#2ed573` | Success, positive |

### Desk Accent Colors
| Desk | `--desk-color` | `--desk-color-dark` |
|------|----------------|---------------------|
| Observer | `#00d4aa` | `#00b894` |
| Journal | `#3742fa` | `#2d3ae8` |
| Analyst | `#7c5cff` | `#6a4ce8` |
| Researcher | `#ffa502` | `#ff9f1c` |
| Coach | `#ff6b9d` | `#e85a8a` |
| Risk | `#ff4757` | `#e8414f` |
| Auto | `#00d4aa` | `#00b894` |

### Animations
- **Grid move**: 20s linear infinite (background)
- **Orb float**: 15-22s ease-in-out (3 glow orbs)
- **Particle rise**: 6-12s staggered (20 particles)
- **Pulse**: 2s status indicators
- **Desk hover**: 200ms transform + shadow + border
- **Chart**: 60fps throttled (every 3rd frame)

---

## Data Integration Points

### Current (Mock/Simulated)
- P&L values: Random walk with positive drift
- Chart data: Generated sine+noise, animated
- Desk monitors: Static demo values
- Time: Client-side UTC clock

### Ready for Real Data
Replace these functions with MT5/Parquet feed:

```javascript
// In index.html script section:
function updatePnl()           // ← Hook to real P&L WebSocket / REST
function generatePnlData()     // ← Load from Parquet equity curve
function drawChart()           // ← Already Canvas, feed real data
// Desk monitors: update .monitor-value elements from live data
```

### Suggested Integration
| Data Source | Endpoint | Update Freq | Desks |
|-------------|----------|-------------|-------|
| MT5 EA | Named pipe / HTTP | 100ms - 1s | Observer, Journal, Risk, Auto |
| Parquet (H1/H4/D1) | File watch / API | 1-5 min | Analyst, Researcher, Coach |
| Campaign DB | SQLite / API | On trade close | Analyst, Journal |

---

## Deployment

### Cloudflare Pages Config
| Setting | Value |
|---------|-------|
| Framework | None |
| Build command | (empty) |
| Output directory | `trading-office` |
| Production branch | `gh-pages` |
| Custom domain | `trade.miniforex786.win` |
| Path routing | `/trading-office/*` → `trading-office/` |

### Deploy Commands
```bash
cd /c/Hermes
git add trading-office/
git commit -m "Descriptive message"
git push origin gh-pages
# Cloudflare auto-deploys on push
```

### Clean gh-pages Branch (if needed)
```bash
cd /c/Hermes
git checkout gh-pages
git rm -r --cached .          # Remove all
git add trading-office/       # Add only output folder
git commit -m "Clean deploy"
git push origin gh-pages
```

---

## Browser Support
| Feature | Chrome | Firefox | Safari | Edge |
|---------|--------|---------|--------|------|
| CSS Grid | ✅ | ✅ | ✅ | ✅ |
| CSS Custom Properties | ✅ | ✅ | ✅ | ✅ |
| Canvas API | ✅ | ✅ | ✅ | ✅ |
| PWA Manifest | ✅ | ✅ | ✅ | ✅ |
| `viewport-fit=cover` | ✅ | ✅ | ✅ | ✅ |
| `prefers-reduced-motion` | ✅ | ✅ | ✅ | ✅ |
| IntersectionObserver | ✅ | ✅ | ✅ | ✅ |

**iOS Safari**: Full PWA support via manifest + splash screens + `apple-touch-startup-image`.

---

## Accessibility
- Semantic HTML: `<header>`, `<main>`, `<article>`, `<section>`, `<aside>`
- ARIA labels on all interactive desks
- Focus-visible outlines (2px accent, 2px offset)
- `prefers-reduced-motion` disables all animations
- `prefers-contrast: high` doubles border widths
- Color-blind safe palette (teal/red/orange/blue distinct)
- Keyboard navigable (Tab, Enter/Space on desks)

---

## Known Limitations / Future Work
- [ ] Service Worker for offline caching
- [ ] Real MT5 data feed integration
- [ ] Campaign persistence (IndexedDB / backend)
- [ ] WebSocket live P&L updates
- [ ] Multi-symbol support (currently XAUUSD only)
- [ ] Dark/light theme toggle (currently dark-only)
- [ ] Export dashboard as PNG/PDF
- [ ] Alert sound notifications

---

## License
Proprietary — Hermes Trading Office, part of the Hermes Agent ecosystem.

---

## Credits
Built with Hermes Agent (Nous Research) • Deployed on Cloudflare Pages • Fonts: JetBrains Mono, Space Grotesk