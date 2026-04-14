# DeepLook — Report Design Guide
## Making Data Friendly for Non-Technical Business Owners

---

## Design Philosophy

The DeepLook report is not a data dump. It's a story about the client's business, told through their own conversations. Every page must answer one question in the client's mind, and every visual must be understandable in under 5 seconds without explanation.

### Core Principles

1. **One insight per section.** Don't combine response times and sentiment on the same chart. Each section answers one question.

2. **Lead with the number, explain with the chart.** Every section starts with a large, prominent KPI number (the "headline"), followed by a chart that provides context, followed by a short text explanation in plain Spanish.

3. **Use traffic light colors for status.** Green = good, yellow = needs attention, red = problem. No ambiguity. A Colombian business owner seeing a red number instantly knows something's wrong.

4. **Benchmark everything.** A number alone is meaningless. "23 minutes" means nothing. "23 minutes (el promedio en tu industria es 5 minutos)" tells a story.

5. **Every chart has a title that IS the insight.** Not "Response Time Distribution" but "Respondes más lento los lunes entre 12-2 PM." The title tells them what to see; the chart proves it.

6. **Recommendations are always present.** After showing a problem, immediately show the solution. Never leave the client thinking "so what do I do about it?"

7. **Spanish always.** Everything in the report is in Spanish. No English technical jargon. "Sentimiento" not "Sentiment." "Tasa de conversión" not "Conversion rate."

---

## Color Palette for Reports

| Use | Color | Hex | When |
|-----|-------|-----|------|
| Positive / Good / Success | Teal | #1D9E75 | Good metrics, positive sentiment, conversions |
| Neutral / Normal | Gray-blue | #6B7280 | Neutral sentiment, average metrics |
| Warning / Needs attention | Amber | #EF9F27 | Below benchmark, trending down |
| Negative / Problem / Critical | Coral-red | #D85A30 | Bad metrics, negative sentiment, lost leads |
| Business (outbound) messages | Deep teal | #0F6E56 | In conversation visualizations |
| Customer (inbound) messages | Blue | #378ADD | In conversation visualizations |
| Background / containers | Light gray | #F8F9FA | Card backgrounds, section separators |
| Accent / DeepLook brand | Purple | #534AB7 | Logo, headers, highlights |

---

## Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Page title | Inter or Montserrat | 28px | Bold |
| Section title (the insight) | Inter | 20px | Semibold |
| KPI headline number | Inter | 48-64px | Bold |
| KPI label | Inter | 14px | Regular |
| Chart title | Inter | 16px | Medium |
| Chart labels | Inter | 12px | Regular |
| Body text / explanations | Inter | 14px | Regular |
| Recommendations | Inter | 14px | Regular, with bold action verb |

---

## Page-by-Page Report Design

### Page 1: Cover

**Purpose:** First impression. Establishes credibility and shows the headline metric immediately.

**Layout:**
```
┌──────────────────────────────────────┐
│  [DeepLook Logo]                     │
│                                      │
│  INFORME DE ANÁLISIS                 │
│  DE CONVERSACIONES                   │
│                                      │
│  ┌──────────────────────────────┐    │
│  │                              │    │
│  │      ┌──────────┐           │    │
│  │      │    72     │           │    │
│  │      │  /100     │           │    │
│  │      └──────────┘           │    │
│  │   PUNTAJE DE SALUD           │    │
│  │      ● ● ● ● ○              │    │
│  │       Bueno                  │    │
│  │                              │    │
│  └──────────────────────────────┘    │
│                                      │
│  Negocio: Wellness By Diego Omar     │
│  Período: Nov 1 - Nov 30, 2025      │
│  Conversaciones analizadas: 87       │
│  Generado: Diciembre 2, 2025         │
│                                      │
└──────────────────────────────────────┘
```

**Health Score Display:**
- Large circular gauge or donut chart showing 72/100
- Color-coded: green (85+), light green (70-84), yellow (55-69), orange (40-54), red (0-39)
- Five dots below showing the rating category (like a star rating)
- Word label: "Excelente", "Bueno", "Regular", "Deficiente", "Crítico"

---

### Page 2: Resumen Ejecutivo (Executive Summary)

**Purpose:** The only page busy business owners will read. Everything essential in one view.

**Layout:**
```
┌──────────────────────────────────────┐
│  RESUMEN EJECUTIVO                   │
│                                      │
│  ┌────────┐ ┌────────┐ ┌────────┐   │
│  │  23m   │ │  40%   │ │  67%   │   │
│  │Tiempo  │ │Tasa de │ │Sentim. │   │
│  │primera │ │conver- │ │positi- │   │
│  │resp.   │ │sión    │ │vo      │   │
│  │🔴      │ │🟢      │ │🟡      │   │
│  └────────┘ └────────┘ └────────┘   │
│                                      │
│  ┌────────┐ ┌────────┐ ┌────────┐   │
│  │  342   │ │   5    │ │  7.2   │   │
│  │Mensajes│ │Sin     │ │Calidad │   │
│  │totales │ │respon- │ │/10     │   │
│  │        │ │der     │ │        │   │
│  │        │ │🔴      │ │🟢      │   │
│  └────────┘ └────────┘ └────────┘   │
│                                      │
│  TOP 3 RECOMENDACIONES               │
│  ─────────────────────               │
│  1. 🔴 Reduce tu tiempo de primera   │
│     respuesta de 23 min a menos de   │
│     5 min. Estás perdiendo clientes. │
│                                      │
│  2. 🔴 Tienes 5 mensajes sin         │
│     responder. Cada uno es una venta │
│     potencial perdida (~$175,000 COP)│
│                                      │
│  3. 🟡 El 38% de las preguntas son   │
│     sobre precios. Crea un catálogo  │
│     de precios para enviar rápido.   │
│                                      │
└──────────────────────────────────────┘
```

**Visual elements:**
- Six KPI cards in a 3×2 grid
- Each card has: large number, small label below, traffic light indicator (colored dot)
- Below: numbered recommendations with colored severity indicators
- No charts on this page — only numbers and text

**KPI Card Design:**
- White card with subtle shadow
- Large number in center (48px, bold)
- Small label below (14px, gray)
- Traffic light dot: green/yellow/red in top-right corner
- Benchmark comparison text in small gray: "Benchmark: <5 min"

---

### Page 3: Velocidad de Respuesta (Response Speed)

**Purpose:** Show how fast the business responds and where the bottlenecks are.

**Section title (the insight, not the category):**
Example: "Respondes en promedio en 23 minutos — tus clientes esperan menos de 5"

**Visual 1: KPI Strip**
```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  23 min  │ │  12 min  │ │  1h 45m  │ │    5     │
│ Promedio │ │ Mediana  │ │ Más lenta│ │Sin resp. │
│ 🔴 >5m  │ │ 🟡 >5m  │ │ 🔴       │ │ 🔴       │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

**Visual 2: Response Time Heatmap by Hour**

**Chart type:** Horizontal bar chart (NOT a traditional heatmap — bars are easier for non-technical users)

**Why this chart type:** A horizontal bar chart with 24 bars (one per hour) clearly shows "at what time are we slowest?" The bars are color-graded from green (fast) to red (slow). This is more intuitive than a grid heatmap for non-technical users.

```
Velocidad de respuesta por hora del día
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 8 AM  ████████░░░░░░░░  8 min    🟢
 9 AM  ██████░░░░░░░░░░  5 min    🟢
10 AM  ████████████░░░░  15 min   🟡
11 AM  ██████████░░░░░░  12 min   🟡
12 PM  ████████████████████████  45 min  🔴
 1 PM  ██████████████████████    38 min  🔴
 2 PM  ██████████████░░  18 min   🟡
 3 PM  ████████░░░░░░░░  8 min    🟢
 4 PM  ██████████░░░░░░  10 min   🟢
 5 PM  ████████████████  22 min   🟡
 6 PM  ████████████████████  35 min  🔴
```

**Explanation text below chart:**
"📌 Tu horario más lento es entre 12 PM y 1 PM (hora de almuerzo) y después de las 6 PM. Un mensaje automático durante estas horas puede retener al 60% de los clientes que escriben."

**Visual 3: Response Time by Day of Week**

**Chart type:** Simple vertical bar chart with 7 bars (Lun-Dom). Color-coded green/yellow/red based on benchmark.

**Why this chart type:** Seven bars are easy to compare. The client instantly sees which days they're slow.

---

### Page 4: Análisis de Conversiones (Conversion Analysis)

**Purpose:** Show how many conversations turn into sales and why the lost ones failed.

**Section title:**
Example: "De 52 clientes interesados, 21 compraron (40%). Perdiste 18 ventas potenciales."

**Visual 1: Conversion Funnel**

**Chart type:** Horizontal funnel with 4 stages, showing how many conversations flow through each stage.

**Why this chart type:** Funnels are universally understood in business. They visually show where customers drop off. Even non-technical users understand "the funnel narrows."

```
EMBUDO DE CONVERSIÓN
━━━━━━━━━━━━━━━━━━━━

█████████████████████████████████████  87 conversaciones totales
                                      
███████████████████████████░░░░░░░░░  52 con intención de compra (60%)

████████████████░░░░░░░░░░░░░░░░░░░  21 convertidas (40%)

█████████████░░░░░░░░░░░░░░░░░░░░░░  18 perdidas (35%)

████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  13 pendientes (25%)
```

Each bar is a different shade: total (gray), with intent (blue), converted (green), lost (red), pending (amber).

**Visual 2: Reasons for Lost Sales**

**Chart type:** Horizontal bar chart, sorted from most to least frequent.

**Why this chart type:** Horizontal bars are the best choice when comparing categories. The category labels (reasons) are text-heavy, so horizontal orientation gives room for the Spanish text. Sorted descending so the biggest problem is at the top.

```
¿POR QUÉ SE PERDIERON LAS VENTAS?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Respuesta lenta        ████████████████  7 (39%)
Precio alto            ████████████░░░░  5 (28%)
Sin respuesta          ████████░░░░░░░░  3 (17%)
Sin disponibilidad     ████░░░░░░░░░░░░  2 (11%)
Proceso complicado     ██░░░░░░░░░░░░░░  1 (5%)
```

**Explanation text:**
"📌 La causa #1 de ventas perdidas es la lentitud en la respuesta (39%). Esto significa que 7 clientes estaban listos para comprar pero se fueron porque no les respondiste a tiempo. A un valor promedio de $190,000 COP, esto representa ~$1,330,000 COP en ventas perdidas."

**Visual 3: Example Lost Conversations**

Show 2-3 anonymized lost conversation summaries in a card format:

```
┌─────────────────────────────────────┐
│ 🔴 OPORTUNIDAD PERDIDA #1           │
│                                     │
│ Tema: Limpieza facial               │
│ Valor estimado: $190,000 COP        │
│                                     │
│ Resumen: El cliente preguntó por    │
│ disponibilidad para limpieza facial │
│ a las 8:41 PM. El negocio respondió │
│ 14 horas después. El cliente no     │
│ volvió a escribir.                  │
│                                     │
│ 💡 Acción: Configura una respuesta  │
│ automática fuera de horario.        │
└─────────────────────────────────────┘
```

---

### Page 5: Sentimiento del Cliente (Customer Sentiment)

**Purpose:** Show how customers feel about their interactions.

**Section title:**
Example: "El 67% de tus clientes tienen una experiencia positiva, pero el 15% se va insatisfecho"

**Visual 1: Sentiment Distribution**

**Chart type:** Donut chart with exactly 3 slices (positive/neutral/negative).

**Why this chart type:** A donut chart works here because there are only 3 categories that sum to 100%. The hole in the center can display the dominant percentage. Three slices is the ideal number for a pie/donut chart. Colors: green, gray, coral-red.

```
        ┌─────────┐
       ╱           ╲
      │   67%       │    🟢 Positivo: 67% (58 conv.)
      │  POSITIVO   │    ⚪ Neutral:  18% (16 conv.)
       ╲           ╱     🔴 Negativo: 15% (13 conv.)
        └─────────┘
```

**Do NOT use a pie chart if there are more than 3-4 categories.** For topics (which can be 8-10 categories), use horizontal bars instead.

**Visual 2: Most Negative Conversations**

**Chart type:** Card list (not a chart — text cards are better for qualitative data).

Show the top 3 most negative conversations as summary cards, similar to the lost opportunity cards. Each card contains: the sentiment score, the reason for negative sentiment, a 2-sentence summary, and a recommended action.

**Visual 3: Sentiment by Topic**

**Chart type:** Grouped horizontal bar chart showing each topic with its sentiment breakdown.

**Why this chart type:** This shows which topics generate negative reactions. If "Precios" has 60% negative sentiment but "Agendar cita" has 90% positive, the business knows their pricing communication is the problem.

```
SENTIMIENTO POR TEMA
━━━━━━━━━━━━━━━━━━━━

Precios        🟢██████░░🟡██░░🔴████████  40% pos / 20% neu / 40% neg
Agendar cita   🟢██████████████████░░🟡██  90% pos / 10% neu / 0% neg
Info servicios 🟢██████████████░░🟡████░░  70% pos / 20% neu / 10% neg
Reclamos       🟢██░░🟡██░░🔴████████████  10% pos / 10% neu / 80% neg
```

---

### Page 6: Temas y Preguntas Frecuentes (Topics & FAQ)

**Purpose:** Show what customers ask about most, so the business can prepare better.

**Section title:**
Example: "El 38% de tus clientes preguntan por precios — ¿tienes la respuesta lista?"

**Visual 1: Topic Distribution**

**Chart type:** Horizontal bar chart, sorted descending.

**Why this chart type:** Topics can have 8-10 categories with long Spanish names. Horizontal bars give room for text labels. Sorted so the most frequent topic is at the top. Color: all bars in teal, with the #1 bar highlighted in deeper teal.

```
¿SOBRE QUÉ PREGUNTAN TUS CLIENTES?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Precios / Cotización    ██████████████████████  38%
Agendar cita            ████████████████░░░░░░  22%
Info de servicios       ████████████░░░░░░░░░░  15%
Ubicación / Horario     ██████░░░░░░░░░░░░░░░░  8%
Seguimiento             ████░░░░░░░░░░░░░░░░░░  6%
Reclamos                ████░░░░░░░░░░░░░░░░░░  5%
Otros                   ████░░░░░░░░░░░░░░░░░░  6%
```

**Visual 2: Top 5 Preguntas Más Frecuentes**

**Chart type:** Numbered list with frequency counts (not a chart — this is text-based).

**Why text instead of a chart:** Questions are qualitative text data. A chart would be meaningless. A clean numbered list is the clearest way to present this.

```
PREGUNTAS MÁS FRECUENTES DE TUS CLIENTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. "¿Cuánto cuesta la limpieza facial?"        — 15 veces
2. "¿Tienen disponibilidad para esta semana?"   — 12 veces
3. "¿Dónde están ubicados?"                     — 8 veces
4. "¿Aceptan tarjeta?"                          — 6 veces
5. "¿Cuánto dura el procedimiento?"             — 5 veces

💡 Estas 5 preguntas representan el 53% de todas las
   consultas iniciales. Crear respuestas rápidas para
   cada una reducirá significativamente tu tiempo de
   respuesta.
```

---

### Page 7: Calidad de Atención (Service Quality)

**Purpose:** Show how well the business handles its conversations.

**Section title:**
Example: "Tu calidad de atención es 7.2/10 — buena, pero con oportunidades de mejora"

**Visual 1: Quality Score Gauge**

**Chart type:** Semi-circular gauge (speedometer style) showing 7.2/10.

**Why this chart type:** Gauges are universally understood as "how well are we doing?" The semi-circle with a needle pointing to the score is intuitive. Color gradient from red (left) to green (right).

**Visual 2: Quality Breakdown by Dimension**

**Chart type:** Horizontal bar chart with 4 bars (one per quality dimension).

**Why NOT a radar/spider chart:** Radar charts look impressive but non-technical users consistently misread them. Four simple horizontal bars with clear labels are far more understandable. Each bar goes from 0 to 10, color-coded green/yellow/red based on score.

```
DESGLOSE DE CALIDAD
━━━━━━━━━━━━━━━━━━━

Utilidad       ████████████████░░░░  8.1/10  🟢
Tono           ████████████████████  9.0/10  🟢
Completitud    ██████████░░░░░░░░░░  5.2/10  🔴
Velocidad      ██████████████░░░░░░  6.5/10  🟡
```

**Explanation text:**
"📌 Tu equipo tiene un excelente tono y es muy útil en sus respuestas. Sin embargo, la completitud está baja (5.2/10) — esto significa que tus clientes frecuentemente necesitan hacer preguntas adicionales porque la primera respuesta no incluyó toda la información necesaria (precios, disponibilidad, pasos siguientes)."

**Visual 3: Best and Worst Conversations**

Show one card for the best-rated conversation and one for the worst-rated, with summaries.

---

### Page 8: Patrones Operativos (Operational Patterns)

**Purpose:** Show when the business is busiest and where capacity gaps exist.

**Section title:**
Example: "Recibes el 72% de tus mensajes entre 9 AM y 4 PM, pero el 28% llega fuera de horario"

**Visual 1: Message Volume by Hour**

**Chart type:** Vertical bar chart (column chart) with 24 bars.

**Why this chart type:** Time-based data displayed as columns creates a natural "day view." The x-axis is hours (8AM to 10PM), the y-axis is message count. This creates an instant picture of "when are we busiest?"

The chart should have two colors: teal for business hours messages, gray for after-hours messages. This visually separates "covered" from "uncovered" periods.

**Visual 2: Message Volume by Day of Week**

**Chart type:** Vertical bar chart with 7 bars (Lun to Dom).

**Visual 3: Messages Split**

**Chart type:** Simple icon-based stat or two stacked numbers.

```
DISTRIBUCIÓN DE MENSAJES
━━━━━━━━━━━━━━━━━━━━━━━━

    ← 156 mensajes          186 mensajes →
    DE CLIENTES              DEL NEGOCIO

    Ratio: 1:1.2 (saludable ✅)
    
    El 95% de tus mensajes son solo texto.
    💡 Enviar fotos y PDFs puede mejorar
    tu tasa de conversión en un 30%.
```

**Visual 4: Conversation Duration**

**Chart type:** Simple KPI number with context.

```
    DURACIÓN PROMEDIO
    DE CONVERSACIÓN
    
         2.4 días
    
    8-15 mensajes por conversación
    (dentro del rango normal ✅)
```

---

### Page 9: Recomendaciones Detalladas

**Purpose:** Specific, actionable steps the business should take.

**Format:** Numbered cards, each with a priority indicator, the problem, the data, and the action.

```
┌─────────────────────────────────────────────┐
│ 🔴 PRIORIDAD ALTA                           │
│                                             │
│ 1. Reduce tu tiempo de primera respuesta    │
│                                             │
│ Problema: Tu tiempo promedio de primera     │
│ respuesta es 23 minutos.                    │
│                                             │
│ Dato: El 78% de los consumidores en LATAM   │
│ compran del primer negocio que les responde. │
│ Una respuesta mayor a 5 minutos reduce la   │
│ conversión en un 65%.                       │
│                                             │
│ Impacto estimado: Reducir este tiempo       │
│ podría recuperar ~$1,330,000 COP/mes en     │
│ ventas perdidas.                            │
│                                             │
│ ✅ Acción: Configura respuestas rápidas     │
│ para las 5 preguntas más frecuentes.        │
│ Asigna a alguien para cubrir el horario     │
│ de 12-2 PM cuando eres más lento.           │
└─────────────────────────────────────────────┘
```

Each recommendation follows this structure: priority color → problem statement → supporting data → estimated impact → specific action. Maximum 5-7 recommendations, sorted by impact.

---

### Page 10: Apéndice (Appendix)

**Purpose:** Technical details for those who want them.

Include: parse quality summary, data period, files processed, AI model used, methodology notes, glossary of terms, disclaimer about AI-generated analysis.

This page is simpler in design — just clean text with minimal formatting.

---

## Chart Type Selection Guide

| Data to Show | Chart Type | Why This Type |
|-------------|-----------|---------------|
| Sentiment split (3 categories summing to 100%) | Donut chart | Perfect for 3-category part-to-whole. Hole shows main percentage. |
| Topics distribution (8-10 categories) | Horizontal bar chart, sorted | Too many categories for a pie chart. Horizontal gives room for Spanish labels. Sorted so biggest is on top. |
| Response time by hour (24 hours) | Horizontal bar chart, color-graded | Shows "when are we slow" at a glance. Green-to-red coloring adds meaning. |
| Response time by day (7 days) | Vertical bar chart | Seven bars are easy to compare. Natural left-to-right week flow. |
| Message volume by hour | Vertical bar chart (column) | Creates a natural "day profile." Two colors for business hours vs after-hours. |
| Conversion funnel | Horizontal funnel | Universally understood in business. Shows drop-off clearly. |
| Lost sale reasons | Horizontal bar chart, sorted | Categories with text labels. Sorted by frequency. Most important problem at top. |
| Quality breakdown (4 dimensions) | Horizontal bar chart | NOT a radar chart. Four simple bars are clearer for non-technical users. |
| Health score | Semi-circular gauge | Speedometer metaphor is universally understood. |
| KPI numbers | Large number cards | Numbers are the fastest way to communicate a single data point. |
| Best/worst conversations | Text summary cards | Qualitative data is best as text, not charts. |
| Common questions | Numbered text list | Questions are text — a chart would be forced. |
| Sentiment by topic | Stacked horizontal bars | Shows which topics have positive/negative sentiment. Two-dimensional comparison. |
| Conversation examples | Text cards with icons | Anecdotal evidence that makes data real. |

---

## What NOT to Do in the Report

| Bad Practice | Why It Fails | What to Do Instead |
|-------------|-------------|-------------------|
| 3D charts of any kind | Distorts proportions, looks unprofessional | Always use flat 2D charts |
| Pie charts with 8+ slices | Impossible to read, slices blur together | Use horizontal bars |
| Radar/spider charts | Non-technical users can't read them | Use horizontal bars for each dimension |
| Charts without titles | Client doesn't know what they're looking at | Title IS the insight: "Respondes más lento los lunes" |
| Raw numbers without context | "23 minutes" means nothing alone | Always include the benchmark and color |
| English terminology | Client doesn't understand "conversion rate" | Always use Spanish: "tasa de conversión" |
| Data tables with many rows | Overwhelming for non-technical readers | Show top 5 only, summarize the rest |
| Multiple charts per section | Information overload | One main chart per section, one clear message |
| No recommendations after problems | Client sees the problem but not the solution | Always pair a problem with an action |
| Decimal numbers with many digits | 23.4567 minutes looks technical | Round to one decimal: 23.5 min |
| Percentages that don't sum to 100% | Confuses part-to-whole understanding | Always check that pie/donut slices sum correctly |

---

## Explanation Text Templates

Every chart or KPI should have a brief explanation below it. These templates show the format:

**For metrics that are good:**
"✅ Tu [metric] es [value]. Estás [above/at] el promedio de tu industria ([benchmark]). ¡Sigue así!"

**For metrics that need attention:**
"🟡 Tu [metric] es [value]. El promedio de tu industria es [benchmark]. Mejorar esto puede [specific benefit]."

**For metrics that are problematic:**
"🔴 Tu [metric] es [value]. El promedio de tu industria es [benchmark]. Esto está costándote aproximadamente [impact]. Recomendación: [specific action]."

**For insights:**
"📌 [Observation from the data]. Esto significa que [interpretation]. Te recomendamos [action]."

---

## Report Implementation Notes

### Technical Implementation

- Use WeasyPrint with Jinja2 HTML templates
- Charts generated with matplotlib (set style to 'seaborn-v0_8-whitegrid' for clean look)
- Export charts as PNG at 200 DPI, embed in HTML as base64 data URIs
- Use CSS @page rules for proper page breaks
- Print-optimized CSS: avoid background colors that waste ink, use borders instead
- Each page is a separate HTML section with page-break-after: always

### Chart Generation Settings (matplotlib)

```
Font: Inter or system sans-serif
Background: white (#FFFFFF)
Grid: light gray (#F0F0F0), horizontal only
Bars: rounded edges (set_capstyle('round'))
Colors: use the palette defined above
Labels: always include value at end of each bar
Title: left-aligned, bold, 16px — the title IS the insight
Remove: top and right spines (ax.spines['top'].set_visible(False))
Legend: only when strictly necessary (prefer direct labels)
```

### Responsiveness

The PDF is designed for A4 paper (210mm × 297mm) with 20mm margins. All charts must fit within the content width (170mm). Use landscape orientation only for the hourly heatmap if needed — all other pages are portrait.
