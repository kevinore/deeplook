# Plan de Despliegue — DeepLook

> Para: Solo developer | Presupuesto ajustado | Stack: FastAPI + React + WAHA PLUS + Supabase

---

## Arquitectura en producción

```
                    ┌─────────────────────────────────┐
                    │     DigitalOcean Droplet         │
                    │          (~$12/mes)               │
                    │                                   │
  GitHub ──────────►│  Coolify (PaaS self-hosted)       │
                    │  ├── [Backend]  :8000             │
                    │  │   FastAPI + APScheduler         │
                    │  │                                 │
                    │  └── [WAHA PLUS] :3000            │
                    │      WhatsApp HTTP API             │
                    └────────────┬────────────┬─────────┘
                                 │            │
                    ┌────────────▼──┐  ┌──────▼──────────────┐
                    │  Supabase     │  │  Vercel              │
                    │  PostgreSQL   │  │  Frontend React SPA  │
                    │  + Storage    │  │  (FREE)              │
                    │  (~$0-25/mes) │  └──────────────────────┘
                    └───────────────┘

  DNS: deeplookapp.com → Caddy (Coolify) → Backend / WAHA
       app.deeplookapp.com → Vercel → Frontend
```

---

## Costos mensuales estimados

| Servicio | Qué corre | Costo/mes | Notas |
|---|---|---|---|
| **DigitalOcean Droplet** | Backend + WAHA | ~$12 | 2 vCPU, 4 GB RAM, 80 GB SSD — acepta PayPal y tarjetas colombianas |
| **Vercel** | Frontend React | **$0** | Free para proyectos hobby/startup |
| **Supabase Free** | PostgreSQL + Storage | **$0** | 500 MB DB, 1 GB storage |
| **Supabase Pro** | PostgreSQL + Storage | $25 | Cuando superes los límites free |
| **Clerk** | Autenticación | **$0** | Free hasta 10.000 MAU |
| **Wompi** | Pagos (Colombia) | ~1.2–2% | Por transacción, sin mensualidad |
| **WAHA PLUS** | Licencia ya pagada | — | Ya tienes el plan |
| **Resend** | Emails transaccionales | **$0** | Free: 3.000 emails/mes. Pro $20 si creces |
| | | | |
| **Total MVP** | | **~$12/mes** | Con Supabase free + Resend free |
| **Total Growth** | | **~$37/mes** | Con Supabase Pro |

---

## Antes de empezar — Checklist de prerequisites

- [ ] Cuenta en [DigitalOcean](https://cloud.digitalocean.com) — acepta PayPal y tarjetas internacionales. Usa este link para $200 de crédito gratis: [m.do.co/c/deeplook](https://www.digitalocean.com/try/developer-cloud)
- [ ] Cuenta en [Vercel](https://vercel.com)
- [ ] Repo del backend en GitHub (para Coolify auto-deploy)
- [ ] Repo del frontend en GitHub (para Vercel auto-deploy)
- [ ] Dominio `deeplookapp.com` en Cloudflare (ya lo tienes)
- [ ] Clerk production instance creada en [dashboard.clerk.com](https://dashboard.clerk.com)
- [ ] Wompi cuenta en producción en [comercios.wompi.co](https://comercios.wompi.co)
- [ ] Supabase proyecto existente (ya lo tienes)
- [ ] Licencia WAHA PLUS activa (ya la tienes)
- [ ] Cuenta en [resend.com](https://resend.com) creada y dominio `deeplookapp.com` verificado con DKIM/SPF
- [ ] SSH key generada localmente

---

## Paso 1 — Supabase (ya existe, solo configurar)

> **Tiempo estimado: 15 minutos**

### 1.1 Crear bucket para cache de PDFs

1. Ve a tu proyecto en [supabase.com](https://supabase.com)
2. Ve a **Storage** → **New bucket**
3. Nombre: `reports`
4. **Desmarcar** "Public bucket" (debe ser privado — acceso solo con service key)
5. Guardar

### 1.2 Obtener credenciales de producción

Desde **Settings → API** en Supabase, anota:
- `SUPABASE_URL` = `https://xxxx.supabase.co`
- `SUPABASE_KEY` = service_role key (la que empieza con `eyJ...`, **NO** la anon key)
- `DATABASE_URL` = desde **Settings → Database → Connection string** → URI → cambiar `postgres://` a `postgresql+asyncpg://`

### 1.3 Ejecutar migraciones

> Esto se hace DESDE TU MÁQUINA LOCAL apuntando a la DB de producción, o desde el servidor después del deploy.

```bash
# Con DATABASE_URL de producción en .env o como variable
DATABASE_URL="postgresql+asyncpg://..." alembic upgrade head
```

---

## Paso 1.5 — Configurar Resend (emails transaccionales)

> **Tiempo estimado: 15 minutos**
> Resend envía los emails de bienvenida, reportes listos (con PDF adjunto), recordatorios de renovación y alertas de reconexión de WhatsApp.

### 1.5.1 Crear cuenta y verificar dominio

1. Crea cuenta en [resend.com](https://resend.com)
2. Ve a **Domains → Add Domain** → ingresa `deeplookapp.com`
3. Resend te mostrará 3 records DNS a agregar en Cloudflare:

| Tipo | Nombre | Valor |
|---|---|---|
| `TXT` | `@` | `v=spf1 include:amazonses.com ~all` |
| `CNAME` | `resend._domainkey` | `resend._domainkey.deeplookapp.com.dkim.resend.com` |
| `TXT` | `_dmarc` | `v=DMARC1; p=none; rua=mailto:kevinaldana51@gmail.com` |

> ⚠️ Los CNAME de DKIM **DEBEN tener proxy OFF** (nube gris en Cloudflare). Con proxy naranja, la verificación falla.

4. En Cloudflare → agrega los records → espera 5-10 minutos
5. Vuelve a Resend → **Verify** → debe quedar ✅ Verified

### 1.5.2 Crear API Key

1. Resend → **API Keys → Create API Key**
2. Nombre: `deeplook-prod`, permiso: **Full access**
3. Guarda el key — solo se muestra una vez

### 1.5.3 Variables a agregar al backend

```env
RESEND_API_KEY=re_...
EMAIL_FROM=DeepLook <noreply@deeplookapp.com>
EMAIL_REPLY_TO=contacto@deeplookapp.com
EMAIL_ENABLED=true
FRONTEND_BASE_URL=https://app.deeplookapp.com
```

---

## Paso 2 — Provisionar el VPS en DigitalOcean

> **Tiempo estimado: 5 minutos**

1. Ve a [cloud.digitalocean.com](https://cloud.digitalocean.com) → inicia sesión o crea cuenta (puedes pagar con **PayPal** o tarjeta)
2. Menú lateral: **Compute → Droplets → Create Droplet**
3. Configura el Droplet:
   - **Region**: New York 1 o San Francisco 3 (mejor latencia a Colombia, ~80ms)
   - **Image**: Ubuntu 22.04 LTS (x64)
   - **Size**: Plan **Basic → Regular (Intel/AMD) → $12/mes** (2 vCPU, 4 GB RAM, 80 GB SSD)
     > ⚠️ No elijas el de $6 (1 GB RAM) — WAHA + FastAPI juntos necesitan al menos 2-3 GB. El de $12 con 4 GB te da espacio para crecer.
   - **Authentication**: **SSH Keys** → agrega tu llave pública (recomendado) o crea una contraseña
   - **Hostname**: `deeplook-prod`
4. Clic **Create Droplet**
5. Espera ~1 minuto mientras arranca
6. Anota la **IP pública** que aparece en el panel (la necesitas en el paso 4 de DNS)

---

## Paso 3 — Instalar Coolify en el VPS

> **Tiempo estimado: 10 minutos**
> Coolify es un PaaS open-source self-hosted. Te da UI web para deployar, SSL automático, variables de entorno, logs en tiempo real — sin SSH para el día a día.

```bash
# Conectarse al VPS
ssh root@<IP_DEL_SERVIDOR>

# Instalar Coolify (script oficial)
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Coolify instala Docker, configura Caddy (reverse proxy + SSL), y levanta su UI en el puerto 8000 del VPS.

4. Abre `http://<IP_DEL_SERVIDOR>:8000` en tu navegador
5. Completa el setup inicial (email + password del admin)
6. En **Settings → SSH Keys** → agrega tu llave SSH (para que Coolify pueda hacer deploy)

---

## Paso 4 — Configurar dominio DNS

> **Tiempo estimado: 5 minutos config + hasta 24h propagación**

En Cloudflare (ya tienes `deeplookapp.com` ahí) ve a **DNS → Records → Add record**:

| Tipo | Nombre | Valor | Proxy |
|---|---|---|---|
| `A` | `api` | `<IP_DEL_DROPLET>` | **Off** (nube gris) |
| `A` | `waha` | `<IP_DEL_DROPLET>` | **Off** (nube gris) |
| `CNAME` | `app` | `cname.vercel-dns.com` | **Off** (nube gris) |

Esto crea:
- `api.deeplookapp.com` → tu backend FastAPI
- `waha.deeplookapp.com` → WAHA (uso interno, no expuesto a usuarios en el frontend)
- `app.deeplookapp.com` → frontend (Vercel lo configura en el paso 9)

> ⚠️ Los 3 records deben tener el proxy de Cloudflare **OFF** (nube gris, no naranja). Con proxy naranja Coolify no puede generar certificados SSL con Let's Encrypt correctamente.

---

## Paso 5 — Deploy de WAHA PLUS

> **Tiempo estimado: 20 minutos**

### 5.1 En Coolify: crear nuevo servicio Docker

1. **Projects → New Project → New Resource → Docker Image**
2. **Image**: `devlikeapro/waha-plus`
   > ⚠️ CRÍTICO: La imagen de producción es `waha-plus`, no `waha`. La imagen free no tiene NOWEB en producción.
3. **Port**: `3000`
4. **Domain**: `https://waha.deeplookapp.com` (Coolify configura SSL automático con Let's Encrypt)

### 5.2 Variables de entorno para WAHA

```env
WAHA_API_KEY=<genera-un-token-largo-aleatorio>
WHATSAPP_DEFAULT_ENGINE=NOWEB

# ⚠️ CRÍTICO: DEBE ser false en producción.
# Con true, WAHA intenta levantar TODAS las sesiones a la vez al reiniciar el
# contenedor → thundering herd contra WhatsApp + riesgo de ban. Las sesiones
# arrancan on-demand desde el backend cuando se necesitan.
WHATSAPP_RESTART_ALL_SESSIONS=false

# Guardar sesiones en Supabase PostgreSQL (NO en filesystem local).
# Con volumen local, un rebuild del contenedor borra todas las sesiones → todos
# los clientes tienen que re-escanear QR. Con PostgreSQL sobreviven cualquier redeploy.
WHATSAPP_SESSIONS_POSTGRESQL_URL=postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres

# Anti-ban: no emitir presencia online
NOWEB_MARK_ONLINE=false

# Worker ID único (importante si en el futuro escalas a múltiples instancias)
WAHA_WORKER_ID=worker-1
```

> **NOTA IMPORTANTE:** `WHATSAPP_SESSIONS_POSTGRESQL_URL` usa la misma Supabase DB pero con schema separado. WAHA crea sus propias tablas en ese schema. Esto elimina la necesidad de montar un volumen persistente y **es la diferencia entre perder o no las sesiones de tus clientes en un redeploy**.

### 5.3 Deploy

1. Guarda la configuración
2. Clic **Deploy**
3. Verifica en los logs que aparezca `WAHA is running on port 3000`
4. Prueba: `curl https://waha.deeplookapp.com/api/health` → debe retornar `{"status": "ok"}`

---

## Paso 6 — Deploy del Backend (FastAPI)

> **Tiempo estimado: 20 minutos**

### 6.1 Actualizar docker-compose.yml para producción

El `docker-compose.yml` actual tiene `--reload` y no es el correcto para producción. Coolify no usa docker-compose directamente — usa el `Dockerfile`. Asegúrate que el `Dockerfile` ya existente esté correcto (ya lo está).

### 6.2 En Coolify: crear servicio desde GitHub

1. **Projects → New Resource → GitHub Repository**
2. Conecta tu cuenta de GitHub si no está conectada aún
3. Selecciona el repo `deeplook`
4. **Build Pack**: Dockerfile
5. **Port**: `8000`
6. **Domain**: `https://api.deeplookapp.com`
7. **Branch**: `main`

### 6.3 Variables de entorno del Backend

```env
# App
APP_ENV=production
DEBUG=false
API_SECRET_KEY=<genera-32-chars-aleatorios>
CORS_ORIGINS=https://app.deeplookapp.com,https://deeplookapp.com

# Base de datos (Supabase)
DATABASE_URL=postgresql+asyncpg://postgres:<password>@db.<ref>.supabase.co:5432/postgres
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_KEY=<service_role_key>

# AI Provider
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Clerk (production instance)
CLERK_JWKS_URL=https://<clerk-domain>.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://<clerk-domain>.clerk.accounts.dev

# WAHA (URL interna dentro del VPS — comunicación directa, no pasa por internet)
WAHA_BASE_URL=http://waha.deeplookapp.com
WAHA_API_KEY=<mismo-token-que-pusiste-en-WAHA>
WAHA_MULTI_SESSION=false
WAHA_REQUIRE_BUSINESS_ACCOUNT=true
ENABLE_WHATSAPP_SCHEDULER=true
WHATSAPP_SCHEDULER_INTERVAL_MINUTES=15

# Email (Resend)
# Obtén el API key en resend.com → API Keys → Create API Key
# EMAIL_FROM debe usar el dominio verificado con DKIM/SPF en Resend
RESEND_API_KEY=re_...
EMAIL_FROM=DeepLook <noreply@deeplookapp.com>
EMAIL_REPLY_TO=contacto@deeplookapp.com
EMAIL_ENABLED=true
# URL pública del frontend — aparece en los links dentro de los emails
FRONTEND_BASE_URL=https://app.deeplookapp.com

# Wompi (producción)
ENFORCE_BILLING=true
WOMPI_PUBLIC_KEY=pub_prod_...
WOMPI_INTEGRITY_SECRET=<integridad-prod>
WOMPI_EVENTS_SECRET=<eventos-prod>
WOMPI_PRICE_BASIC_CENTS=16000000
WOMPI_PRICE_PLUS_CENTS=25000000
WOMPI_PRICE_ENTERPRISE_CENTS=40000000
WOMPI_REDIRECT_BASE_URL=https://app.deeplookapp.com
```

> **Nota sobre `WAHA_BASE_URL`**: Aunque WAHA y el backend están en el mismo VPS, se comunican via el dominio HTTPS. Si quieres comunicación interna directa (más rápida, sin salir a internet), puedes usar la IP interna de Docker: `http://waha:3000`. Esto requiere que ambos servicios estén en la misma Docker network en Coolify. La forma más simple es usar el dominio público (HTTPS) para empezar.

### 6.4 Deploy

1. Clic **Deploy**
2. Coolify buildea la imagen con el Dockerfile (instala WeasyPrint y libs del sistema)
   > Primera build toma ~3-5 minutos por las dependencias de WeasyPrint
3. Verifica: `curl https://api.deeplookapp.com/health` → `{"status": "ok"}`

---

## Paso 7 — Migraciones de Base de Datos

> **Tiempo estimado: 5 minutos**

Después del primer deploy del backend exitoso, corre las migraciones:

**Opción A — Desde tu máquina local (recomendado para primera vez):**
```bash
# En tu máquina local, apuntando a DB de producción
export DATABASE_URL="postgresql+asyncpg://postgres:<password>@db.<ref>.supabase.co:5432/postgres"
alembic upgrade head
```

**Opción B — Desde Coolify Terminal (si ya está deployado):**
En Coolify → Backend service → **Terminal** → ejecuta:
```bash
alembic upgrade head
```

Verifica que todas las tablas existen en Supabase → Table Editor.

---

## Paso 8 — Deploy del Frontend (Vercel)

> **Tiempo estimado: 10 minutos**

1. Ve a [vercel.com](https://vercel.com) → **New Project**
2. Importa el repo `fe-deeplook` desde GitHub
3. **Framework Preset**: Vite (detecta automáticamente)
4. **Build Command**: `npm run build`
5. **Output Directory**: `dist`

### 8.1 Variables de entorno en Vercel

En **Settings → Environment Variables** del proyecto:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_live_...
VITE_API_URL=https://api.deeplookapp.com
```

> ⚠️ En Vercel las variables de entorno para Vite DEBEN empezar con `VITE_` para que estén disponibles en el browser.

### 8.2 Dominio custom

1. Vercel → Settings → Domains → agrega `app.deeplookapp.com`
2. Vercel te dará un CNAME value → ya lo pusiste en Cloudflare en el Paso 4 (`cname.vercel-dns.com`)

### 8.3 Deploy

1. Clic **Deploy**
2. Cada push a `main` triggerea auto-deploy — zero ops
3. Verifica que `https://app.deeplookapp.com` carga el landing/login

---

## Paso 9 — Configurar Clerk para Producción

> **Tiempo estimado: 15 minutos**

1. En [dashboard.clerk.com](https://dashboard.clerk.com):
   - **Create application** → Production
   - O si ya tienes dev instance: **Switch to Production** (requiere verificar dominio)
2. **Domains** → agrega `app.deeplookapp.com`
3. **API Keys** → copia `Publishable key` (para frontend) y JWKS URL (para backend)
4. **Redirects**: 
   - Sign-in URL: `https://app.deeplookapp.com/login`
   - After sign-in: `https://app.deeplookapp.com/app/inicio`
   - After sign-up: `https://app.deeplookapp.com/app/inicio`
5. **Social logins** (opcional): activa Google si quieres

Actualiza en Coolify (backend):
- `CLERK_JWKS_URL` → la URL de producción
- `CLERK_ISSUER` → el issuer de producción

Actualiza en Vercel (frontend):
- `VITE_CLERK_PUBLISHABLE_KEY` → la llave `pk_live_...` de producción

---

## Paso 10 — Configurar Wompi para Producción

> **Tiempo estimado: 10 minutos**

1. Ve a [comercios.wompi.co](https://comercios.wompi.co) → **Mi cuenta → Llaves de autenticación**
2. Copia las llaves de **producción** (no stagtest)
3. En tu dashboard de Wompi → configura el **webhook URL**:
   `https://api.deeplookapp.com/api/v1/webhooks/wompi`
4. Activa eventos: `transaction.updated`
5. Actualiza las variables en Coolify (backend):
   - `WOMPI_PUBLIC_KEY` = `pub_prod_...`
   - `WOMPI_INTEGRITY_SECRET` = secret de integridad
   - `WOMPI_EVENTS_SECRET` = secret de eventos
   - `WOMPI_PRICE_BASIC_CENTS` = `16000000` (160.000 COP = 16.000.000 centavos)
   - `WOMPI_PRICE_PLUS_CENTS` = `25000000`
   - `WOMPI_PRICE_ENTERPRISE_CENTS` = `40000000`

---

## Paso 11 — Verificación End-to-End

> **Tiempo estimado: 30 minutos**

Checklist de smoke test en producción:

### Backend
- [ ] `GET https://api.deeplookapp.com/health` → `200 OK`
- [ ] `GET https://api.deeplookapp.com/docs` → debe estar disabled en producción (verifica `DEBUG=false`)
- [ ] Logs en Coolify sin errores de startup

### WAHA
- [ ] `GET https://waha.deeplookapp.com/api/health` → `200 OK`
- [ ] `GET https://waha.deeplookapp.com/api/sessions` con `X-Api-Key` header → `[]` (lista vacía)

### Frontend
- [ ] `https://app.deeplookapp.com` carga el landing page
- [ ] Click en "Iniciar sesión" → abre el modal de Clerk
- [ ] Sign-up con email real funciona
- [ ] Onboarding modal aparece y permite crear perfil

### Flujo completo
- [ ] Crear cuenta → onboarding → llega al dashboard
- [ ] Ir a `/app/conectar` → aparece botón "Conectar ahora"
- [ ] Click en conectar → POST /connections funciona → aparece QR
- [ ] Escanear con teléfono → status cambia a WORKING
- [ ] Auto-sync dispara → job aparece en `/app/reports`
- [ ] Download PDF → PDF se genera y descarga

### Billing
- [ ] Plan modal aparece correctamente
- [ ] Proceso de pago Wompi funciona en sandbox (con tarjeta de prueba Wompi)

### Email (Resend)
- [ ] Al hacer onboarding (crear perfil) llega email de bienvenida a la cuenta de prueba
- [ ] Al completar un análisis llega email "Tu reporte está listo" con PDF adjunto
- [ ] En `resend.com` → Dashboard → Logs confirmar que los emails tienen status `delivered` (no `bounced`)
- [ ] En Gmail → "Ver original" del email → `dkim=pass` / `spf=pass` / `dmarc=pass`

### Scheduler (APScheduler)
- [ ] Logs del backend al arrancar muestran: `"Schedulers started — sync=15 min, keepalive=hourly, renewal check daily at 09:00 UTC"`
- [ ] En Coolify → Backend logs → buscar `Keepalive` y `Scheduler` sin errores después de 1 hora

---

## Resumen del orden de deploy

```
1.  Supabase         → Crear bucket "reports" + conseguir credenciales
2.  Resend           → Crear cuenta, verificar dominio deeplookapp.com con DKIM/SPF, conseguir API key
3.  DigitalOcean     → Crear Droplet $12/mes, 2vCPU 4GB RAM, Ubuntu 22.04
4.  Coolify          → Instalar en VPS con curl
5.  DNS              → Configurar A records y CNAME
6.  WAHA PLUS        → Deploy Docker en Coolify + env vars (RESTART_ALL_SESSIONS=false, sessions en PG, dominio waha.deeplookapp.com)
7.  Backend          → Deploy desde GitHub en Coolify + env vars (incluye RESEND_API_KEY, FRONTEND_BASE_URL, dominio api.deeplookapp.com)
8.  Migraciones      → alembic upgrade head contra DB de producción
9.  Frontend         → Deploy en Vercel + env vars + dominio custom
10. Clerk            → Configurar production instance
11. Wompi            → Configurar llaves prod + webhook URL
12. E2E Test         → Smoke test incluyendo emails y scheduler
```

---

## Actualizar en producción (día a día)

### Backend
```bash
# Solo hacer push a main — Coolify auto-deploys si configuraste auto-deploy
git push origin main

# O manualmente desde Coolify UI:
# Tu proyecto → Backend → Deploy
```

### Frontend
```bash
# Solo hacer push a main — Vercel auto-deploys
git push origin main
```

### Migraciones
Siempre que tengas un nuevo archivo en `alembic/versions/`:
```bash
# Desde tu máquina local
export DATABASE_URL="postgresql+asyncpg://..."
alembic upgrade head
```

### WAHA
Solo necesita update cuando saques nueva versión de `devlikeapro/waha-plus`:
- Coolify → WAHA service → **Pull latest image** → Deploy

---

## Monitoreo básico (sin costo adicional)

### Coolify built-in
- Logs en tiempo real de cada servicio
- Alertas de restart del contenedor
- CPU/RAM del VPS

### Supabase built-in
- Query performance en **Reports**
- Conexiones activas en **Database → Connections**

### UptimeRobot (FREE)
1. Crear cuenta en [uptimerobot.com](https://uptimerobot.com)
2. Agregar monitors:
   - `https://api.deeplookapp.com/health` (cada 5 min)
   - `https://app.deeplookapp.com` (cada 5 min)
3. Configura alertas por email/Telegram cuando caiga

---

## Cambios al código para producción

### A. `docker-compose.yml` — imagen WAHA (ya cambiado ✅ si usaste Coolify)

```yaml
# CAMBIAR esto (imagen free sin NOWEB):
image: devlikeapro/waha

# POR esto (imagen PLUS con NOWEB):
image: devlikeapro/waha-plus
```

### B. `docker-compose.yml` — quitar --reload en producción

El docker-compose es solo para desarrollo local. En producción, Coolify usa el `Dockerfile` directamente. El `Dockerfile` ya tiene el comando correcto:
```
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
Sin `--reload` ✅

### C. Variables WAHA correctas en producción (diferente al dev local)

| Variable | Dev (local) | Producción |
|---|---|---|
| `WHATSAPP_RESTART_ALL_SESSIONS` | `true` (conveniente para dev) | **`false`** (obligatorio) |
| `WHATSAPP_SESSIONS_POSTGRESQL_URL` | *(no se usa, volumen local)* | **`postgresql://...`** (obligatorio) |
| `WAHA_BASE_URL` | `http://localhost:3000` | `http://waha.deeplookapp.com` o IP interna |

---

## Path de escalamiento (cuando crezcas)

| Cuando... | Hacer esto | Costo adicional |
|---|---|---|
| Supabase llega al límite free (500MB) | Upgrade a Supabase Pro | +$25/mo |
| Backend lento bajo carga | Upgrade Droplet $12 → $24/mes (4 vCPU, 8 GB RAM) en DigitalOcean | +$12/mo |
| Muchos sync simultáneos | Separar WAHA a su propio Droplet $6/mes (1 vCPU, 1 GB) | +$6/mo |
| Necesitas workers separados | Migrar BackgroundTasks → Celery + Redis | +$5/mo (Redis en Railway/Upstash) |
| Múltiples regiones | Agregar un segundo Droplet en EU o ASIA | +$12/mo por región |

---

## Costos proyectados

| Etapa | Usuarios activos | Costo/mes |
|---|---|---|
| MVP | 0–50 clientes | ~$5 |
| Tracción | 50–200 clientes | ~$30 (Supabase Pro) |
| Crecimiento | 200–500 clientes | ~$40 (VPS upgrade) |
| Scale | 500+ clientes | Rediseñar con Celery + múltiples instancias |
