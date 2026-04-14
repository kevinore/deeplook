# DeepLook — Complete Metrics & KPIs Framework
## What to Measure, Why It Matters, and LATAM Benchmarks

---

## Why This Document Exists

Every metric DeepLook calculates must help a small business owner in Colombia make a decision. If a metric doesn't lead to an action, it's noise. This document defines every metric, explains why it matters, provides industry benchmarks for LATAM, and specifies exactly how to calculate it from WhatsApp message data.

---

## Metric Categories

1. Speed & Responsiveness — "How fast do we respond?"
2. Volume & Activity — "How busy are we?"
3. Conversation Quality — "How well do we handle conversations?"
4. Conversion & Sales — "Are we closing deals?"
5. Customer Experience — "How do customers feel?"
6. Operational Patterns — "When and how do we work?"
7. Business Health — "How healthy is our WhatsApp operation overall?"

---

## 1. Speed & Responsiveness

These are the most impactful metrics for Colombian small businesses. Research shows that 78% of consumers in LATAM buy from the first business that responds to them, and a first response time over 5 minutes reduces conversion likelihood by 65%.

### 1.1 First Response Time (Tiempo de primera respuesta)

**What:** Time between a customer's first message and the business's first reply, measured in minutes.

**Why it matters:** This is the single most important metric. In LATAM, customers expect responses within minutes, not hours. A slow first response means the customer has already messaged a competitor.

**How to calculate:** For each conversation, find the first INBOUND message and the first subsequent OUTBOUND message. The difference in timestamps is the first response time.

**Edge cases:**
- If the business sends the first message (welcome/greeting), skip to the first customer message and measure from there
- If the conversation starts with multiple customer messages before any business reply, use the first customer message as the start
- If the business never responds, mark as "unanswered" (infinite response time)

**LATAM Benchmarks:**
- Excellent: Under 2 minutes
- Good: 2-5 minutes
- Acceptable: 5-15 minutes
- Poor: 15-60 minutes
- Critical: Over 1 hour

**Action for client:** "Tu tiempo promedio de primera respuesta es de 23 minutos. El 78% de los consumidores en LATAM compran del primer negocio que les responde. Reducir este tiempo a menos de 5 minutos puede aumentar tus ventas significativamente."

### 1.2 Average Response Time (Tiempo promedio de respuesta)

**What:** Average time the business takes to reply to any customer message throughout the entire conversation, measured in minutes.

**Why it matters:** First response time measures the initial engagement, but this metric shows if the business stays responsive throughout the conversation. A business might reply fast initially but then take hours for follow-up questions.

**How to calculate:** For every INBOUND message followed by an OUTBOUND message, calculate the time difference. Average all these times. Exclude intervals where multiple INBOUND messages arrive before any OUTBOUND (only count from the first unanswered INBOUND).

**LATAM Benchmarks:**
- Excellent: Under 5 minutes
- Good: 5-15 minutes
- Acceptable: 15-30 minutes
- Poor: 30-120 minutes
- Critical: Over 2 hours

### 1.3 Median Response Time

**What:** The middle value of all response times (50th percentile).

**Why it matters:** The average can be skewed by a few very slow responses. The median shows what the "typical" experience is. If the average is 45 minutes but the median is 8 minutes, most customers get fast replies but a few outliers are dragging the average up.

### 1.4 P95 Response Time (Percentil 95)

**What:** The 95th percentile response time — 95% of responses are faster than this.

**Why it matters:** Shows the worst-case experience. If P95 is 3 hours, that means 1 in 20 customers waits over 3 hours. Useful for finding patterns of neglect.

### 1.5 Maximum Response Time

**What:** The single longest time a customer waited for a response.

**Why it matters:** Identifies the worst interaction. Often reveals a systemic issue (weekend messages, overnight messages, busy periods).

**Action for client:** "Tu respuesta más lenta fue de 14 horas. Fue un mensaje recibido a las 11:47 PM un sábado. Considera configurar un mensaje automático fuera de horario."

### 1.6 Unanswered Messages Count (Mensajes sin responder)

**What:** Number of customer messages that never received a business reply. A conversation where the last message is from the customer and no business reply follows.

**Why it matters:** Every unanswered message is a potential lost sale. This is possibly the most actionable metric — it tells the business exactly how many opportunities they're ignoring.

**How to calculate:** Count conversations where the final message is INBOUND and no OUTBOUND message follows. Also count conversations where an INBOUND message has no OUTBOUND response within 24 hours, even if the conversation continues later.

**Action for client:** "Tienes 12 conversaciones donde el cliente escribió y nunca recibió respuesta. Cada mensaje sin responder es una venta potencial perdida."

### 1.7 Response Time by Hour (Velocidad de respuesta por hora)

**What:** Average response time grouped by the hour of day (0-23) when the customer message was received.

**Why it matters:** Reveals when the business is fast and when it's slow. If response times spike between 12-2 PM (lunch) or after 6 PM (closing), the business can adjust staffing or set up auto-replies for those hours.

**Output format:** A 24-hour heatmap or bar chart showing average response time for each hour.

### 1.8 Response Time by Day of Week

**What:** Average response time per day of the week.

**Why it matters:** Many Colombian small businesses have different availability on weekends. Saturday messages might take 4x longer to get answered. This metric makes that visible.

---

## 2. Volume & Activity

These metrics show how much work is flowing through WhatsApp and help businesses understand their capacity and patterns.

### 2.1 Total Conversations (Total de conversaciones)

**What:** Total number of unique conversation threads analyzed.

**Why it matters:** Baseline number for all other metrics. Also indicates the business's reach — more conversations generally means more opportunities.

### 2.2 Total Messages (Total de mensajes)

**What:** Total messages across all conversations, split by direction (inbound/outbound).

**Why it matters:** Shows overall communication volume. The ratio of inbound to outbound messages is also telling — if the business sends significantly more messages than it receives, it might be over-communicating. If customers send much more, the business might not be providing enough information upfront.

### 2.3 Inbound vs Outbound Ratio

**What:** The ratio of customer messages to business messages.

**Why it matters:** A healthy ratio is typically 1:1 to 1:1.5 (business sends slightly more than it receives, accounting for greetings and follow-ups). A ratio of 3:1 (customer sends 3x more) suggests the business isn't providing enough information per response, forcing customers to ask multiple follow-up questions.

**Benchmark:** Healthy ratio is between 0.8:1 and 1.5:1 (business:customer). If the business sends much less than the customer, they may not be providing enough detail in their responses.

### 2.4 Messages per Conversation (Mensajes por conversación)

**What:** Average number of messages in each conversation.

**Why it matters:** Very short conversations (2-3 messages) might indicate customers leaving quickly. Very long conversations (30+ messages) might indicate an inefficient sales process or unclear information. Customer service conversations on WhatsApp typically resolve in 3-6 message exchanges.

**Benchmarks:**
- Quick inquiry: 3-6 messages
- Sales conversation: 8-15 messages
- Complex consultation: 15-25 messages
- Inefficient/problematic: 30+ messages

**Action for client:** "Tus conversaciones promedian 22 mensajes. Conversaciones de venta efectivas suelen resolverse en 8-15 mensajes. Tus conversaciones más largas son sobre precios — considera enviar tu catálogo de precios al inicio para acortar el proceso."

### 2.5 New Conversations per Day/Week

**What:** How many new conversation threads start each day or week.

**Why it matters:** Shows demand trends. Is the business getting more inquiries over time or fewer? Useful for spotting the effect of marketing campaigns or seasonal changes.

### 2.6 Unique Contacts (Contactos únicos)

**What:** Number of distinct customers who have had conversations.

**Why it matters:** Distinguishes between many conversations with a few repeat customers versus many different customers reaching out. Both patterns are valid but require different strategies.

### 2.7 Returning vs New Contacts

**What:** How many contacts are chatting for the first time vs. returning for additional conversations.

**Why it matters:** High return rate can indicate good customer relationships (they come back for more) or unresolved issues (they keep having to reach out). Context from the AI analysis helps distinguish these.

---

## 3. Conversation Quality (AI-Powered)

These metrics require AI analysis and measure how well the business handles its conversations.

### 3.1 Overall Quality Score (Puntaje de calidad - 0 a 10)

**What:** An AI-assessed overall quality rating for each conversation, scoring the business's performance.

**Why it matters:** This is the core AI metric. It tells the business, in a single number, how well they handled each interaction.

### 3.2 Quality Breakdown — Four Dimensions

Each conversation is scored on four dimensions (0-10 each):

**3.2.1 Helpfulness (Utilidad de la respuesta)**
Did the business actually answer the customer's question? Did they provide the information requested? Were they proactive in offering relevant details?

Indicators of low helpfulness: generic responses, not answering the specific question, redirecting without explanation, sending irrelevant information.

**3.2.2 Tone & Professionalism (Tono y profesionalismo)**
Was the business friendly, professional, and appropriate? Did they use proper greeting? Did they maintain a positive and welcoming tone throughout?

Indicators of low tone: cold responses, rude language, overly formal/robotic responses, inconsistent tone (friendly at first then cold).

**3.2.3 Completeness (Completitud)**
Did the business provide all the information the customer needed, or did the customer have to ask multiple follow-up questions for basic information? Did the business anticipate follow-up questions?

Indicators of low completeness: customer asking the same question rephrased, customer asking for details that should have been included in the first response (prices, availability, location, hours).

**3.2.4 Speed Perception (Percepción de velocidad)**
Even if the actual response time is good, does the conversation feel responsive? Did the business set expectations about wait times? Did long gaps occur mid-conversation?

Indicators of low speed perception: abrupt gaps mid-conversation, no acknowledgment when the business needs time to check something, no "un momento" type messages.

### 3.3 Information Completeness Rate

**What:** How often the business provides all essential information in the first response: price, availability, location, hours, next steps.

**Why it matters:** In Colombian WhatsApp commerce, customers often ask a simple question like "¿Cuánto cuesta?" and the business responds with "¿Para qué servicio?" creating unnecessary back-and-forth. The best businesses anticipate what the customer needs and provide it proactively.

### 3.4 Follow-up Rate (Tasa de seguimiento)

**What:** Percentage of conversations where the business proactively follows up with the customer after the initial interaction (e.g., "¿Te decidiste?", "¿Necesitas algo más?").

**Why it matters:** Proactive follow-up is a major differentiator. Many Colombian businesses answer questions but never follow up, leaving potential sales on the table.

---

## 4. Conversion & Sales

These metrics directly tie to revenue and are what business owners care about most.

### 4.1 Conversion Status per Conversation

**What:** AI classification of each conversation into one of these outcomes:
- **Converted:** Customer made a purchase, booked an appointment, or committed to a service
- **Lost:** Customer showed interest but didn't convert (went cold, chose competitor, objected to price)
- **Pending:** Conversation is still active or ended without clear resolution
- **Not applicable:** Informational inquiry, complaint, or support request with no sales intent

**Why it matters:** Knowing the conversion rate is the most business-critical metric. It directly answers: "Of the people who write to me, how many become customers?"

**LATAM Benchmarks:**
- WhatsApp conversion rate with AI assistance: 45-55%
- WhatsApp conversion rate without AI, human only: 35-42%
- Traditional web ecommerce: 1.5-2.1%
- Successful SMBs typically achieve 15-30% inquiry-to-sale conversion

### 4.2 Conversion Rate (Tasa de conversión)

**What:** Percentage of applicable conversations (excluding "not applicable") that resulted in a conversion.

**Formula:** (converted conversations / (converted + lost + pending)) × 100

**Action for client:** "De 45 conversaciones con intención de compra, 18 se convirtieron en ventas (40%). Estás por encima del promedio de tu industria (35%). Las 15 conversaciones perdidas se debieron principalmente a: precio (7), tiempo de respuesta lento (5), falta de disponibilidad (3)."

### 4.3 Lost Opportunity Analysis (Análisis de oportunidades perdidas)

**What:** For each "lost" conversation, the AI identifies why the customer didn't convert. Categories include:
- **Precio (Price):** Customer found it too expensive or asked for discounts
- **Tiempo de respuesta (Response time):** Business took too long and customer lost interest
- **Sin respuesta (No response):** Business never replied
- **Competencia (Competition):** Customer mentioned going with another provider
- **Disponibilidad (Availability):** Desired product/service/time wasn't available
- **Información insuficiente (Insufficient information):** Business didn't provide enough info to decide
- **Proceso complicado (Complicated process):** Too many steps to book/buy
- **Otro (Other):** Other reasons

**Why it matters:** This is the highest-value insight DeepLook provides. It tells the business exactly what's costing them money and what to fix.

### 4.4 Revenue Impact Estimation (Impacto estimado en ingresos)

**What:** Estimated revenue lost from unconverted conversations, based on the business's average transaction value.

**How to calculate:** The client provides their average order/transaction value during setup. Multiply lost conversations × average value × estimated recovery rate (30%).

**Why it matters:** Puts a dollar amount on the problem. "You lost approximately $2,400,000 COP this month from 15 conversations where the customer went cold because of slow response times" is much more impactful than "your response time is slow."

---

## 5. Customer Experience (AI-Powered)

### 5.1 Sentiment Analysis (Análisis de sentimiento)

**What:** AI classification of overall customer sentiment in each conversation: Positive, Neutral, or Negative. Plus a numeric score from -1.0 (very negative) to 1.0 (very positive).

**Why it matters:** Shows how customers feel about interacting with the business. Trending negative sentiment is an early warning sign.

**Additional detail:** Include the AI's reasoning for the sentiment. Not just "negative" but "negative — customer expressed frustration about waiting 2 hours for a price quote."

### 5.2 Sentiment Distribution (Distribución de sentimiento)

**What:** Percentage breakdown of positive/neutral/negative across all conversations.

**Benchmark:** A healthy distribution for a Colombian small business would be: 60-70% positive, 20-30% neutral, 5-15% negative. If negative exceeds 20%, there's a systemic problem.

### 5.3 Sentiment Trend (Tendencia de sentimiento)

**What:** How sentiment changes over time (daily, weekly). Is customer satisfaction improving or declining?

**Why it matters:** A sudden spike in negative sentiment could indicate a product issue, staff change, or external problem. Catching this early prevents damage.

### 5.4 Topic Classification (Clasificación de temas)

**What:** AI identification of what each conversation is primarily about. Common topics for Colombian small businesses:
- Precios / Cotización (Pricing / Quotes)
- Disponibilidad (Availability)
- Agendar cita (Scheduling / Appointments)
- Información de servicios (Service information)
- Pedido / Orden (Orders)
- Reclamo / Queja (Complaint)
- Ubicación / Cómo llegar (Location / Directions)
- Horarios (Business hours)
- Seguimiento de pedido (Order follow-up)
- Consulta general (General inquiry)
- Pagos / Facturación (Payments / Billing)
- Garantía / Devolución (Warranty / Returns)

**Why it matters:** Reveals what customers ask about most. If 40% of conversations are about pricing, the business should probably have a price list ready to send instantly. If 25% are about location/hours, they should include that in their auto-welcome message.

**Action for client:** "El 38% de tus conversaciones son preguntas sobre precios. Recomendamos crear un catálogo de precios en PDF que puedas enviar inmediatamente. Esto reducirá los mensajes de ida y vuelta en un 50% estimado."

### 5.5 Common Questions (Preguntas frecuentes)

**What:** AI extraction of the most frequently asked questions by customers, grouped and ranked by frequency.

**Why it matters:** Directly informs what the business should put in their auto-responses, welcome message, or FAQ. If 30 different customers all ask "¿Cuánto cuesta la limpieza facial?", that question should be answered before it's asked.

### 5.6 Customer Effort Score (Esfuerzo del cliente)

**What:** AI assessment of how much effort the customer had to put in to get what they needed. Scale 1-5 (1 = very easy, 5 = very difficult).

Factors that increase effort:
- Customer had to repeat their question
- Customer had to ask for basic information that should have been provided
- Long wait times between messages
- Customer had to clarify what they meant multiple times
- Complex process to book/order

**Why it matters:** Low-effort experiences lead to more conversions and repeat customers. High-effort experiences lead to churn and negative word-of-mouth.

---

## 6. Operational Patterns

These metrics help businesses optimize their operations and staffing.

### 6.1 Peak Hours (Horas pico)

**What:** The hours of the day with the highest inbound message volume.

**Why it matters:** Helps the business ensure they have staff available during peak times. In Colombia, typical peak hours for small businesses on WhatsApp are 9-11 AM and 2-4 PM, with a dip during lunch (12-1 PM).

### 6.2 Peak Days (Días pico)

**What:** Days of the week with the highest message volume.

**LATAM benchmark:** Mondays typically account for 18-22% of weekly volume. Weekends represent 15-20% of total volume.

### 6.3 After-Hours Message Volume (Mensajes fuera de horario)

**What:** Percentage of customer messages that arrive outside typical business hours (before 8 AM, after 6 PM, weekends).

**Why it matters:** If 28% of messages arrive after hours (LATAM average), the business needs an auto-reply strategy for those times.

**Action for client:** "El 32% de tus mensajes llegan fuera de horario laboral. Un mensaje automático de fuera de horario puede retener al 60% de estos clientes hasta el día siguiente."

### 6.4 Conversation Duration (Duración de conversación)

**What:** Time from first message to last message in a conversation.

**Why it matters:** Shows how long the typical sales cycle is. Very long conversations (spread over days) might indicate indecision or a complex product. Very short conversations might indicate quick resolutions or early drop-offs.

### 6.5 Messages to Resolution (Mensajes hasta resolución)

**What:** How many message exchanges are needed before the conversation reaches its outcome (sale, appointment, resolution).

**Benchmark:** WhatsApp customer service typically resolves in 3-6 exchanges. Sales conversations typically need 8-15 exchanges. If your business consistently needs 20+ exchanges, the process is likely inefficient.

### 6.6 Business Initiation Rate

**What:** Percentage of conversations initiated by the business vs. by the customer.

**Why it matters:** Businesses that proactively reach out (follow-ups, promotions, updates) tend to have higher sales. If 100% of conversations are customer-initiated, the business is purely reactive and missing proactive sales opportunities.

### 6.7 Media Usage Analysis

**What:** Breakdown of message types used by the business: text only, images, audio notes, videos, documents, locations.

**Why it matters:** Businesses that use rich media (product photos, price list PDFs, location pins, audio notes) tend to have higher conversion rates. If the business only sends text, they might be missing opportunities to sell visually.

**Action for client:** "El 95% de tus mensajes son solo texto. Los negocios que envían fotos de productos junto con los precios tienen un 30% más de conversión. Considera enviar imágenes de tus servicios/productos."

---

## 7. Business Health Score (Puntaje de salud — 0 a 100)

The ultimate metric: a single number that tells the business how well their WhatsApp operation is performing.

### Calculation

Weighted average of six sub-scores:

| Component | Weight | Calculation |
|-----------|--------|-------------|
| Response Speed | 25% | Based on average first response time. Under 2 min = 100, under 5 min = 85, under 15 min = 65, under 30 min = 45, under 1 hour = 25, over 1 hour = 10 |
| Response Coverage | 15% | Based on unanswered rate. 0% unanswered = 100, under 5% = 85, under 10% = 65, under 20% = 40, over 20% = 15 |
| Customer Sentiment | 20% | (positive% × 100) + (neutral% × 50) + (negative% × 0) |
| Conversation Quality | 15% | Average quality_score × 10 (converts 0-10 to 0-100) |
| Conversion Effectiveness | 15% | Conversion rate as percentage (converted / applicable × 100) |
| Operational Coverage | 10% | Based on after-hours coverage. Has auto-reply = 100, responds after hours = 80, no after-hours coverage = 30 |

### Score Interpretation

| Score | Rating | Meaning |
|-------|--------|---------|
| 85-100 | Excelente | WhatsApp operation is highly effective. Minor optimizations possible. |
| 70-84 | Bueno | Good operation with clear areas for improvement. |
| 55-69 | Regular | Significant room for improvement. Losing sales due to operational gaps. |
| 40-54 | Deficiente | Serious issues affecting customer experience and sales. Immediate action needed. |
| 0-39 | Crítico | WhatsApp channel is hurting the business more than helping. Fundamental changes needed. |

### Visual Presentation

Display as a large gauge/dial on the report cover page. Color-coded: green (85+), light green (70-84), yellow (55-69), orange (40-54), red (0-39).

---

## 8. Metrics Summary — What Goes in the Report

### Page 1: Cover + Health Score
- DeepLook logo + client business name
- Large health score number with color and rating
- Analysis period and total conversations analyzed

### Page 2: Executive Summary
- Health score with the six sub-scores as a mini breakdown
- Three headline stats: first response time, conversion rate, sentiment split
- Top 3 recommendations (most impactful actions)

### Page 3: Speed & Responsiveness
- First response time (average, median)
- Response time by hour chart (24h heatmap)
- Unanswered messages count and list
- Comparison to LATAM benchmarks

### Page 4: Conversion Analysis
- Conversion funnel: total conversations → with sales intent → converted / lost / pending
- Conversion rate with benchmark comparison
- Lost opportunity breakdown (pie chart by reason)
- Estimated revenue impact
- Top 3 lost conversations with AI summaries

### Page 5: Customer Sentiment
- Sentiment distribution pie chart (positive/neutral/negative)
- Top 5 negative conversations with reasons and summaries
- Common customer complaints or frustrations
- Sentiment by topic (which topics have worst sentiment)

### Page 6: Topics & Common Questions
- Topic distribution bar chart (top 10)
- Most common customer questions (ranked list)
- Recommendations for auto-responses based on frequent questions

### Page 7: Conversation Quality
- Average quality score with breakdown by dimension
- Best and worst conversations (by quality score) with summaries
- Information completeness analysis
- Media usage breakdown

### Page 8: Operational Patterns
- Peak hours chart
- Peak days chart
- After-hours message percentage
- Average conversation duration and messages to resolution

### Page 9: Recommendations
- 5-7 specific, actionable recommendations
- Each recommendation includes: the problem, the data supporting it, the specific action to take, and the expected impact
- Prioritized by estimated impact

### Page 10: Appendix
- Data quality report (parse confidence, warnings)
- Methodology note
- Glossary of terms

---

## 9. Metrics That Require Client Input (at Upload Time)

Some metrics cannot be calculated from chat data alone. The client should provide these at upload time or during setup:

| Input | Why | Default if not provided |
|-------|-----|------------------------|
| Business identifiers (names/phones) | To distinguish business vs customer messages | Auto-detect (lower confidence) |
| Average transaction value (COP) | To estimate revenue impact of lost opportunities | Skip revenue estimation |
| Business hours | To calculate after-hours metrics | Assume 8 AM - 6 PM Mon-Sat |
| Industry/business type | To select appropriate benchmarks | Use general benchmarks |
| Number of people who respond on WhatsApp | To assess per-person workload | Assume 1 |

---

## 10. Metrics NOT to Include (and Why)

| Metric | Why Skip |
|--------|----------|
| Message delivery rate | We don't have this from .txt exports. Only available via Meta API. |
| Read receipts / open rate | Not available in chat exports. Blue ticks are not exported. |
| Click-through rate | No links in most small business conversations. |
| Revenue per recipient | Requires e-commerce integration we don't have. |
| Customer lifetime value | Requires long-term data across multiple interactions. |
| Agent-specific performance | Most small businesses have 1-2 people answering. Phase 2 feature when we can identify individual agents. |
| A/B test results | Requires controlled experiments. Not applicable to conversation analysis. |
| Opt-out rate | Only relevant for broadcast messaging via API. |
