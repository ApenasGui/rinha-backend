# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=custom_ca \
    if [ -s /run/secrets/custom_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/custom_ca; fi; \
    npm ci --no-audit --no-fund
COPY tsconfig*.json ./
COPY src ./src
RUN --mount=type=secret,id=custom_ca \
    if [ -s /run/secrets/custom_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/custom_ca; fi; \
    npm run build && npm prune --omit=dev --no-audit --no-fund

FROM node:24-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --from=build --chown=node:node /app/package.json ./package.json
USER node
EXPOSE 3000
CMD ["node", "--max-old-space-size=256", "dist/main.js"]
