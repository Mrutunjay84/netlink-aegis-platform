FROM node:24-slim AS builder
# Heap ceiling tuned for low-RAM build hosts (this VM has ~7.7GB). A 10GB heap
# (the upstream CI default) lets V8 grow past physical RAM and get OOM-killed
# (exit 137) during the adapter-node step. A smaller ceiling forces earlier GC
# so the build fits in memory. Override with --build-arg NODE_BUILD_HEAP_MB.
ARG NODE_BUILD_HEAP_MB=8192
ENV NODE_OPTIONS="--max-old-space-size=${NODE_BUILD_HEAP_MB}"
WORKDIR /app

ENV PUBLIC_BACKEND_API_URL=foo

# Community frontend first, then the Netlink overlay on top (overlay wins).
COPY frontend/package*.json ./
COPY frontend/project.inlang .
COPY frontend/ .
COPY netlink/frontend .

# White-label the copied tree (i18n + hardcoded literals). Never touches the
# committed community source, so it survives upstream merges.
RUN node brand-patch.mjs

# Make the auth cookies' Secure flag runtime-controllable (SECURE_COOKIES env)
# so the same image works for both HTTPS (default) and plain-HTTP deployments.
RUN node deploy-patch.mjs

# Wire Netlink overlay features that need a small edit to a community file
# (sidebar nav entry + i18n keys for the Policy Builder). Runs against the copy.
RUN node feature-patch.mjs

RUN npm install -g pnpm
RUN pnpm install --frozen-lockfile
RUN pnpm run build
RUN pnpm prune

FROM node:24-slim
ENV NODE_OPTIONS="--max-old-space-size=10240"
WORKDIR /app
COPY --from=builder /app/build build/
COPY --from=builder /app/server server/
COPY --from=builder /app/node_modules node_modules/
COPY frontend/package.json .
EXPOSE 3000
ENV NODE_ENV=production
ENV BODY_SIZE_LIMIT=25000000

RUN groupadd -g 1001 app && useradd -u 1001 -g 1001 -m -s /bin/bash app
# USER app  # not activated by default to keep compatibility

CMD [ "node", "server" ]
