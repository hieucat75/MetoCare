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

# All three deploy workflows have passed --build-arg NEXT_PUBLIC_APP_ENV since
# the environment banner was written, and every one of them was DISCARDED: an
# undeclared ARG is silently ignored by Docker. `EnvironmentBanner` is a Server
# Component, so it read the value at runtime instead — which staging happens to
# set on its container and production does not.
#
# The result reached real users on 2026-08-10: production served
# "MÔI TRƯỜNG THỬ NGHIỆM (không xác định) — dữ liệu ở đây không phải dữ liệu
# thật" on app.metocare.me. Failing to non-production when the value is unset is
# the right default; what was wrong is that the value never arrived. Statically
# prerendered pages bake it at BUILD time, so a runtime variable cannot repair
# them — it has to be declared here.
ARG NEXT_PUBLIC_APP_ENV=
ENV NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV
ARG NEXT_PUBLIC_BUILD_SHA=
ENV NEXT_PUBLIC_BUILD_SHA=$NEXT_PUBLIC_BUILD_SHA

# Enable standalone output for minimal runtime image
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 3: runner ──────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000

CMD ["node", "server.js"]
