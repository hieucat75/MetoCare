# MetoCare Frontend — internal DEV deployment
# Multi-stage: builder → runner (smaller final image)

# ── Stage 1: deps ────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# ── Stage 2: builder ─────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time API URL injected here so Next.js bakes it into the static bundle.
# NO default: NEXT_PUBLIC_* is inlined at build time and cannot be overridden at
# runtime, so a stale dev default would silently ship to prod. CI MUST pass
# --build-arg NEXT_PUBLIC_API_URL=https://<backend-fqdn>/api/v1. If omitted the
# value is empty; the build still succeeds (Next.js tolerates it) and the broken
# URL surfaces in smoke tests instead of masquerading as a working dev IP.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Enable standalone output for minimal runtime image
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 3: runner ──────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# standalone output; no public/ dir in this project so skip that copy
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000

CMD ["node", "server.js"]
