# Adensa Digital — Next.js frontend image (P10.3).
#
# Production packaging for the operational client as a Google
# Cloud Run service. Four stages: a full dependency install
# for the build, the production build itself, a pruned
# production-only dependency tree, and a runtime stage
# containing ONLY production dependencies plus the built
# application — dev dependencies (tests, lint, typecheck) are
# never shipped.
#
# Configuration is runtime-only, by design:
#
#   API_BASE_URL   the deployed FastAPI /v1 origin (env var)
#   API_KEY        the /v1 machine credential (Secret Manager)
#
# Neither value is a Docker build ARG. The build executes no
# API calls (every page is request-rendered or a static shell;
# all fetches are cache: "no-store"), so the production
# credential never exists at build time, in any layer, or in
# the image — it is injected by Cloud Run at container start.
# This mirrors the frontend's browser-never-sees-credentials
# architecture (web/.env.example): both variables are
# server-side only, never NEXT_PUBLIC-prefixed.
#
# The container binds the platform-provided $PORT (8080 on
# Cloud Run; 3000 when unset, e.g. locally): `next start`
# reads PORT natively, so the CMD needs no wrapper.

FROM node:22-slim AS deps
WORKDIR /app

# Deterministic install from the committed lockfile. The full
# dependency tree is needed for the build (TypeScript, the
# Next compiler toolchain).
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS build
WORKDIR /app

# Build with the full dependency tree and the application
# source. Intentionally NO API environment variables here:
# the build must not depend on — or embed — deployment
# configuration.
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-slim AS prod-deps
WORKDIR /app

# Prune to the production dependency tree for the runtime
# image. `next` itself is a production dependency, so
# `next start` remains available without any dev tooling.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM node:22-slim AS runtime
WORKDIR /app

# Production runtime: only the built application and its
# production dependencies (next/react/react-dom). Run as the
# image's non-root `node` user.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY package.json ./

USER node

# `next start` honors PORT (8080 on Cloud Run) and binds
# 0.0.0.0, which is what the platform routes expect.
EXPOSE 8080
CMD ["npm", "start"]
