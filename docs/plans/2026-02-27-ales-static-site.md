# ALES Static Site Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single self-contained `index.html` marketing + developer reference site for the ALES Manufacturing Pipeline.

**Architecture:** One HTML file, no external dependencies, no build step. Vanilla HTML/CSS with ~30 lines of vanilla JS for tab switching. Seven scroll-sections behind a sticky nav. All content sourced from README.md and CLAUDE.md.

**Tech Stack:** HTML5, CSS custom properties, vanilla JS (tabs only). Dutch language. Deploy target: `docs/index.html` (works with GitHub Pages out of the box).

---

## Task 1: File scaffold + CSS + nav

**Files:**
- Create: `docs/index.html`

**Step 1: Create the file with full CSS and nav**

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ALES Manufacturing Pipeline</title>
  <style>
    :root {
      --bg: #ffffff;
      --text: #111111;
      --muted: #777777;
      --accent: #0066ff;
      --border: #e5e5e5;
      --code-bg: #f5f5f5;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.65;
      font-size: 16px;
    }

    /* ── NAV ─────────────────────────────────────── */
    nav {
      position: sticky; top: 0; z-index: 100;
      background: var(--bg);
      border-bottom: 1px solid var(--border);
      height: 56px;
      display: flex; align-items: center;
      justify-content: space-between;
      padding: 0 48px;
    }
    .nav-logo {
      font-weight: 700; font-size: 15px; letter-spacing: 0.02em;
      text-decoration: none; color: var(--text);
    }
    .nav-links { display: flex; gap: 32px; list-style: none; }
    .nav-links a {
      font-size: 14px; color: var(--muted);
      text-decoration: none; transition: color 0.15s;
    }
    .nav-links a:hover { color: var(--text); }

    /* ── LAYOUT ──────────────────────────────────── */
    section { padding: 96px 48px; max-width: 900px; margin: 0 auto; }
    section + section { border-top: 1px solid var(--border); }
    h1 { font-size: 48px; font-weight: 700; line-height: 1.1; letter-spacing: -0.02em; }
    h2 { font-size: 28px; font-weight: 600; margin-bottom: 32px; }
    h3 { font-size: 17px; font-weight: 600; margin-bottom: 8px; }
    p  { color: var(--muted); max-width: 600px; }
    p + p { margin-top: 12px; }
    a  { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* ── HERO ────────────────────────────────────── */
    #hero { padding-top: 112px; padding-bottom: 112px; }
    .hero-label {
      font-size: 12px; font-weight: 600; letter-spacing: 0.1em;
      text-transform: uppercase; color: var(--accent); margin-bottom: 20px;
    }
    .hero-title { margin-bottom: 24px; }
    .hero-sub { font-size: 19px; color: var(--muted); max-width: 560px; margin-bottom: 40px; }
    .btn-group { display: flex; gap: 12px; flex-wrap: wrap; }
    .btn {
      display: inline-block; padding: 12px 24px; border-radius: 4px;
      font-size: 14px; font-weight: 500; cursor: pointer; transition: opacity 0.15s;
      text-decoration: none;
    }
    .btn:hover { opacity: 0.85; text-decoration: none; }
    .btn-primary { background: var(--text); color: var(--bg); }
    .btn-secondary { border: 1px solid var(--border); color: var(--text); }

    /* ── CODE / PRE ──────────────────────────────── */
    pre {
      background: var(--code-bg); border: 1px solid var(--border);
      border-radius: 6px; padding: 20px 24px; overflow-x: auto;
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 13px; line-height: 1.6; margin: 20px 0;
    }
    code {
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 13px; background: var(--code-bg); padding: 2px 6px; border-radius: 3px;
    }
    pre code { background: none; padding: 0; font-size: inherit; }

    /* ── PIPELINE ASCII ───────────────────────────── */
    .pipeline-wrap { overflow-x: auto; margin: 32px 0; }
    .pipeline-wrap pre { font-size: 12px; background: #fafafa; }

    /* ── FEATURE CARDS ───────────────────────────── */
    .feature-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1px; background: var(--border); border: 1px solid var(--border);
      border-radius: 8px; overflow: hidden; margin-top: 40px;
    }
    .feature-card {
      background: var(--bg); padding: 28px 28px;
    }
    .feature-icon { font-size: 20px; margin-bottom: 12px; }
    .feature-card h3 { font-size: 15px; margin-bottom: 6px; }
    .feature-card p { font-size: 14px; }

    /* ── STEPS ───────────────────────────────────── */
    .steps { margin-top: 40px; }
    .step { display: flex; gap: 24px; margin-bottom: 40px; }
    .step-num {
      flex-shrink: 0; width: 32px; height: 32px;
      border: 1px solid var(--border); border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 13px; font-weight: 600; color: var(--muted);
    }
    .step-body h3 { font-size: 16px; margin-bottom: 4px; }
    .step-body p { font-size: 14px; }

    /* ── TABS ────────────────────────────────────── */
    .tabs { margin-top: 40px; }
    .tab-bar { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
    .tab-btn {
      padding: 10px 20px; font-size: 14px; cursor: pointer;
      background: none; border: none; border-bottom: 2px solid transparent;
      color: var(--muted); transition: all 0.15s; margin-bottom: -1px;
    }
    .tab-btn.active { color: var(--text); border-bottom-color: var(--text); font-weight: 500; }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* ── TABLE ───────────────────────────────────── */
    table { width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 14px; }
    th { text-align: left; padding: 10px 14px; border-bottom: 2px solid var(--border); font-size: 13px; color: var(--muted); font-weight: 500; }
    td { padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
    td code { font-size: 12px; }

    /* ── FOOTER ──────────────────────────────────── */
    footer {
      border-top: 1px solid var(--border); padding: 40px 48px;
      display: flex; justify-content: space-between; align-items: center;
      font-size: 13px; color: var(--muted); max-width: 900px; margin: 0 auto;
    }

    @media (max-width: 600px) {
      nav { padding: 0 20px; }
      .nav-links { gap: 16px; }
      section { padding: 64px 20px; }
      h1 { font-size: 32px; }
      footer { flex-direction: column; gap: 12px; text-align: center; padding: 32px 20px; }
    }
  </style>
</head>
<body>

<nav>
  <a class="nav-logo" href="#hero">ALES</a>
  <ul class="nav-links">
    <li><a href="#features">Features</a></li>
    <li><a href="#gebruik">Gebruik</a></li>
    <li><a href="#technisch">Technisch</a></li>
    <li><a href="#start">Aan de slag</a></li>
  </ul>
</nav>

<!-- SECTIONS GO HERE (Tasks 2–8) -->

<script>
  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.closest('.tabs');
      group.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      group.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      group.querySelector('#' + btn.dataset.tab).classList.add('active');
    });
  });
</script>
</body>
</html>
```

**Step 2: Verify in browser**

Open `docs/index.html` in a browser. Expected: blank white page with a clean sticky nav showing "ALES" on the left, four links on the right. No errors in console.

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: scaffold static site with CSS and nav"
```

---

## Task 2: Hero section

**Files:**
- Modify: `docs/index.html` — replace `<!-- SECTIONS GO HERE -->` comment

**Step 1: Insert hero section**

Replace `<!-- SECTIONS GO HERE (Tasks 2–8) -->` with:

```html
<!-- ── HERO ──────────────────────────────────────── -->
<section id="hero">
  <div class="hero-label">Manufacturing Pipeline</div>
  <h1 class="hero-title">Analyse STEP-bestanden.<br>Automatisch.</h1>
  <p class="hero-sub">ALES extraheert geometrie, detecteert gaten, zettingen en draad, ontvouwt plaatwerk en genereert productieklare rapporten — volgens Nederlandse en ISO-normen.</p>
  <div class="btn-group">
    <a class="btn btn-primary" href="#start">Aan de slag</a>
    <a class="btn btn-secondary" href="https://github.com/djspilot/alestest" target="_blank">GitHub →</a>
  </div>
</section>

<!-- REMAINING SECTIONS GO HERE -->
```

**Step 2: Verify**

Open in browser. Expected: large bold title, subtitle in muted grey, two buttons side by side.

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add hero section"
```

---

## Task 3: Pipeline diagram section

**Files:**
- Modify: `docs/index.html` — replace `<!-- REMAINING SECTIONS GO HERE -->`

**Step 1: Insert section**

```html
<!-- ── WAT DOET HET ───────────────────────────────── -->
<section id="wat-doet-het">
  <h2>Wat doet het?</h2>
  <p>Geef een STEP-bestand in. ALES parseert de 3D-geometrie, classificeert het onderdeel, detecteert features en exporteert alles in het gewenste formaat.</p>
  <div class="pipeline-wrap">
<pre>
┌─────────────┐     ┌──────────────────────────────────────────────────────┐     ┌──────────────┐
│             │     │            Manufacturing Pipeline                    │     │              │
│  STEP File  │────▶│                                                      │────▶│  Rapporten   │
│  (.step)    │     │  1. Laad & parse 3D-geometrie (CadQuery/OCP)        │     │              │
│             │     │  2. Classificeer onderdeel (plaatwerk/profiel/etc)   │     │  - PDF       │
└─────────────┘     │  3. Detecteer features:                              │     │  - Excel     │
                    │     - Gaten (cilindrisch + vormgaten)                │     │  - XML       │
                    │     - Zettingen (radius, hoek, K-factor)            │     │  - JSON      │
                    │     - Draad (M3–M68, ISO 68-1)                      │     │  - Database  │
                    │  4. Ontvouw plaatwerk (FreeCAD)                      │     │              │
                    │  5. Pas ISO-normen toe                               │     └──────────────┘
                    │  6. Genereer rapporten                               │
                    └──────────────────────────────────────────────────────┘
</pre>
  </div>
</section>

<!-- REMAINING SECTIONS GO HERE -->
```

**Step 2: Verify**

Expected: section with diagram in a scrollable monospace block. Check mobile: box should scroll horizontally, not break layout.

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add pipeline diagram section"
```

---

## Task 4: Features grid

**Files:**
- Modify: `docs/index.html`

**Step 1: Insert section**

```html
<!-- ── FEATURES ──────────────────────────────────── -->
<section id="features">
  <h2>Wat het kan</h2>
  <p>Acht jaar aan ISO-normen, tientallen onderdelen per dag — ALES handelt het af.</p>

  <div class="feature-grid">
    <div class="feature-card">
      <div class="feature-icon">◈</div>
      <h3>Onderdeelclassificatie</h3>
      <p>Herkent automatisch plaatwerk, draaidelen, profielen en samenstellingen.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">○</div>
      <h3>Gatdetectie</h3>
      <p>Cilindrische vlakken én inner wire methode — gaten, sleuven, vormgaten.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">∠</div>
      <h3>Zetanalyse</h3>
      <p>Telt productierelevante zettingen. Sluit profielen en afrondingen automatisch uit.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">⬡</div>
      <h3>Plaatwerk ontvouwen</h3>
      <p>FreeCAD SheetMetal workbench met multi-poging strategie. Exporteert DXF voor laser.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">≡</div>
      <h3>ISO-normen</h3>
      <p>ISO 2768, ISO 286, ISO 1302, ISO 68-1, ISO 13715, EN 10025/573 — allemaal ingebouwd.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">⇄</div>
      <h3>ERP-integratie</h3>
      <p>XML/Excel export in SpaceClaim-formaat. Windows file watcher service voor automatische verwerking.</p>
    </div>
  </div>
</section>

<!-- REMAINING SECTIONS GO HERE -->
```

**Step 2: Verify**

Expected: 6 cards in a 2-3 column grid (responsive). Cards separated by 1px borders, clean and uniform.

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add features grid section"
```

---

## Task 5: How it works — steps

**Files:**
- Modify: `docs/index.html`

**Step 1: Insert section**

```html
<!-- ── HOE HET WERKT ─────────────────────────────── -->
<section id="hoe-het-werkt">
  <h2>Hoe het werkt</h2>
  <p>Van STEP-bestand naar productierapport in zes stappen.</p>

  <div class="steps">
    <div class="step">
      <div class="step-num">1</div>
      <div class="step-body">
        <h3>Laad het STEP-bestand</h3>
        <p>CadQuery/OCP parseert de geometrie. Ondersteunt enkelvoudige onderdelen en assemblages.</p>
      </div>
    </div>
    <div class="step">
      <div class="step-num">2</div>
      <div class="step-body">
        <h3>Classificeer het onderdeel</h3>
        <p>Bepaalt automatisch: plaatwerk, draaideel, gekocht profiel, of samengesteld onderdeel.</p>
      </div>
    </div>
    <div class="step">
      <div class="step-num">3</div>
      <div class="step-body">
        <h3>Detecteer features</h3>
        <p>Gaten via cilindrische vlakken én inner wires. Zettingen op radius, hoek en K-factor. Draad op ISO 68-1. AAG-topologie voor robuuste herkenning.</p>
      </div>
    </div>
    <div class="step">
      <div class="step-num">4</div>
      <div class="step-body">
        <h3>Ontvouw plaatwerk</h3>
        <p>FreeCAD SheetMetal workbench met meerdere pogingen. Bij falen: theoretisch ontvouwen op basis van zetgeometrie.</p>
      </div>
    </div>
    <div class="step">
      <div class="step-num">5</div>
      <div class="step-body">
        <h3>Pas ISO-normen toe</h3>
        <p>Toleranties (ISO 2768), passingen (ISO 286), oppervlakteruwheid (ISO 1302), draad (ISO 68-1), materiaal (EN 10025/573).</p>
      </div>
    </div>
    <div class="step">
      <div class="step-num">6</div>
      <div class="step-body">
        <h3>Genereer rapporten</h3>
        <p>PDF, Excel (SpaceClaim-formaat), XML voor ERP-import, JSON voor integratie, SQLite voor historiek.</p>
      </div>
    </div>
  </div>
</section>

<!-- REMAINING SECTIONS GO HERE -->
```

**Step 2: Verify**

Expected: numbered steps with clean alignment. Numbers in small circles.

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add how-it-works steps section"
```

---

## Task 6: Usage — tabbed code blocks

**Files:**
- Modify: `docs/index.html`

**Step 1: Insert section**

```html
<!-- ── GEBRUIK ───────────────────────────────────── -->
<section id="gebruik">
  <h2>Gebruik</h2>
  <p>Vier modi — van snelle dagelijkse analyse tot volledig geautomatiseerde ERP-integratie.</p>

  <div class="tabs">
    <div class="tab-bar">
      <button class="tab-btn active" data-tab="tab-quick">Quick</button>
      <button class="tab-btn" data-tab="tab-full">Full ISO</button>
      <button class="tab-btn" data-tab="tab-batch">Batch</button>
      <button class="tab-btn" data-tab="tab-api">API</button>
    </div>

    <div class="tab-panel active" id="tab-quick">
      <p style="margin-bottom:12px">Snelle analyse met PDF-rapport. Ideaal voor dagelijkse werkvoorbereiding.</p>
<pre>
# Interactieve bestandsselectie
python run.py

# Specifiek bestand analyseren
python run.py -f onderdeel.step

# Met AAG topologie-analyse (nauwkeuriger)
python run.py -f onderdeel.step --aag -v

# Excel export in SpaceClaim-formaat
python run.py -f onderdeel.step --excel

# Vergeleken met SpaceClaim-referentie
python run.py -f onderdeel.step --excel --reference ref.xlsx</pre>
    </div>

    <div class="tab-panel" id="tab-full">
      <p style="margin-bottom:12px">Volledige ISO pipeline met database-opslag en alle normcontroles.</p>
<pre>
# Volledige pipeline
python run.py -f onderdeel.step --full

# Met productietabel
python run.py -f onderdeel.step --full --production-info

# Cache-status bekijken
python run.py --full --status

# Hervat vanaf een specifieke stage
python run.py -f onderdeel.step --full --from threads

# Toon alle stages
python run.py --full --list-stages</pre>
    </div>

    <div class="tab-panel" id="tab-batch">
      <p style="margin-bottom:12px">Verwerk hele mappen parallel. Resultaten worden gecacht voor snelle heranalyse.</p>
<pre>
# Alle bestanden in data/input/
python run.py --batch

# Parallel verwerking (4 workers)
python run.py -f ./map --batch -p 4

# JSON output voor ERP-integratie
python run.py --batch --json

# Excel + SpaceClaim-vergelijking
python run.py --batch --excel --reference spaceclaim.xml

# Forceer heranalyse (negeer cache)
python run.py --batch --no-cache</pre>
    </div>

    <div class="tab-panel" id="tab-api">
      <p style="margin-bottom:12px">Deploy als REST API via Docker. Analyseer op afstand, haal resultaten op in meerdere formaten.</p>
<pre>
# Start de API
docker compose up -d

# Upload en analyseer een STEP-bestand
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: jouw-key" \
  -F "file=@onderdeel.step"

# Resultaten ophalen
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "X-API-Key: jouw-key"

# Als Excel
curl "http://localhost:8000/api/v1/jobs/{job_id}?format=excel"

# Als SpaceClaim XML
curl "http://localhost:8000/api/v1/jobs/{job_id}?format=xml"</pre>
    </div>
  </div>
</section>

<!-- REMAINING SECTIONS GO HERE -->
```

**Step 2: Verify**

Open in browser. Click each tab — code block should switch. Only one panel visible at a time.

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add usage tabbed section"
```

---

## Task 7: Technical section (for developers)

**Files:**
- Modify: `docs/index.html`

**Step 1: Insert section**

```html
<!-- ── TECHNISCH ────────────────────────────────── -->
<section id="technisch">
  <h2>Technisch</h2>
  <p>Voor ontwikkelaars die de pipeline willen begrijpen, uitbreiden of integreren.</p>

  <h3 style="margin-top:40px;margin-bottom:16px">Architectuur</h3>
<pre>
run.py ──────────────────────▶ manufacturing_pipeline/cli.py
                                          │
                   ┌──────────────────────┼──────────────────────┐
                   ▼                      ▼                      ▼
              core/                  analysis/             reporting/
              ├── config.py          ├── step_processing   ├── report_generator (PDF)
              ├── models.py          ├── sheetmetal_analysis├── excel_exporter
              └── utils.py           ├── part_analyzer      ├── xml_exporter
                                     ├── iso_standards      └── cli_output
                                     ├── freecad_unfold
                                     └── aag_analyzer

api/app.py ──▶ routes.py ──▶ manufacturing_pipeline (zelfde engine)
file_watcher ──▶ map monitoren ──▶ manufacturing_pipeline
</pre>

  <h3 style="margin-top:40px;margin-bottom:16px">Sleutelmodules</h3>
  <table>
    <thead>
      <tr><th>Module</th><th>Verantwoordelijkheid</th></tr>
    </thead>
    <tbody>
      <tr><td><code>analysis/step_processing.py</code></td><td>STEP-parsing, gat/zetdetectie, vlakclassificatie</td></tr>
      <tr><td><code>analysis/sheetmetal_analysis.py</code></td><td>Dikte, profielclassificatie, zetentelling voor ERP</td></tr>
      <tr><td><code>analysis/part_analyzer.py</code></td><td>Onderdeelclassificatie, bedrijfslogica, redeneerssysteem</td></tr>
      <tr><td><code>analysis/iso_standards.py</code></td><td>ISO 2768, ISO 286, ISO 1302, ISO 68-1, ISO 13715</td></tr>
      <tr><td><code>analysis/freecad_unfold.py</code></td><td>FreeCAD SheetMetal integratie, DXF-export</td></tr>
      <tr><td><code>scripts/aag_analyzer.py</code></td><td>Attributed Adjacency Graph, topologie-feature herkenning</td></tr>
      <tr><td><code>reporting/report_generator.py</code></td><td>PDF-rapporten met ISO-secties en afbeeldingen</td></tr>
      <tr><td><code>data/cache_manager.py</code></td><td>Stage-gebaseerd caching, MD5 bestandsdetectie</td></tr>
      <tr><td><code>api/app.py</code></td><td>FastAPI REST API, job management</td></tr>
    </tbody>
  </table>

  <h3 style="margin-top:40px;margin-bottom:16px">Pipeline stages (Full Mode)</h3>
  <table>
    <thead>
      <tr><th>Stage</th><th>Beschrijving</th></tr>
    </thead>
    <tbody>
      <tr><td><code>load_step</code></td><td>STEP-bestand laden en parsen</td></tr>
      <tr><td><code>detect_holes</code></td><td>Cilindrische gaten detecteren</td></tr>
      <tr><td><code>geometry_analysis</code></td><td>Volume, oppervlak, bounding box</td></tr>
      <tr><td><code>face_analysis</code></td><td>Vlaktypes classificeren</td></tr>
      <tr><td><code>component_classification</code></td><td>Onderdeeltype bepalen</td></tr>
      <tr><td><code>manufacturing_requirements</code></td><td>ISO 2768 toleranties, oppervlakteafwerking</td></tr>
      <tr><td><code>holes_with_fits</code></td><td>ISO 286 passingen</td></tr>
      <tr><td><code>threads</code></td><td>ISO 68-1 draaddetectie</td></tr>
      <tr><td><code>mass_properties</code></td><td>Materiaalgewicht berekeningen</td></tr>
      <tr><td><code>complete</code></td><td>Pipeline afgerond</td></tr>
    </tbody>
  </table>
</section>

<!-- REMAINING SECTIONS GO HERE -->
```

**Step 2: Verify**

Expected: two tables render cleanly, ASCII architecture diagram in monospace block. No horizontal overflow issues.

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add technical reference section"
```

---

## Task 8: Getting started + footer

**Files:**
- Modify: `docs/index.html` — replace last `<!-- REMAINING SECTIONS GO HERE -->` comment

**Step 1: Insert section and footer**

```html
<!-- ── AAN DE SLAG ───────────────────────────────── -->
<section id="start">
  <h2>Aan de slag</h2>
  <p>Vereisten: Python 3.10+ en optioneel FreeCAD (voor plaatwerk ontvouwen).</p>

<pre>
# Kloon de repository
git clone https://github.com/djspilot/alestest.git
cd alestest

# Installeer dependencies
pip install -r requirements.txt

# Analyseer een STEP-bestand
python run.py -f data/input/mijnonderdeel.step

# Of met AAG voor nauwkeurigere herkenning
python run.py -f mijnonderdeel.step --aag -v</pre>

  <p style="margin-top:24px">Output verschijnt in <code>data/output/&lt;onderdeelnaam&gt;/</code> — PDF-rapport, SVG-afbeeldingen en analysedata.</p>

  <div class="btn-group" style="margin-top:40px">
    <a class="btn btn-primary" href="https://github.com/djspilot/alestest" target="_blank">Bekijk op GitHub</a>
    <a class="btn btn-secondary" href="https://github.com/djspilot/alestest/blob/main/docs/ENGINE.md" target="_blank">Engine documentatie</a>
  </div>
</section>

<footer>
  <span>ALES Manufacturing Pipeline</span>
  <span><a href="https://github.com/djspilot/alestest" target="_blank">GitHub</a> · <a href="https://github.com/djspilot/alestest/blob/main/docs/ENGINE.md" target="_blank">Docs</a></span>
</footer>
```

**Step 2: Verify complete site**

Open `docs/index.html` in browser. Check:
- [ ] Nav links all scroll to correct sections
- [ ] All 7 sections visible end-to-end
- [ ] Tab switching works (click all 4 tabs)
- [ ] Page looks correct on narrow window (resize to ~375px wide)
- [ ] No horizontal scrollbar on body (only inside pre blocks)

**Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: add getting started section and footer, complete static site"
```

---

## Done

The site lives at `docs/index.html`. GitHub Pages serves it automatically from the `docs/` folder if enabled in repo settings (Settings → Pages → Source: main branch, /docs folder).
