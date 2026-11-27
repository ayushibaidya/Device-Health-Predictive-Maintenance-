FROM node:24.22.1-bookworm-slim@sha256:8579e5fce559544b50072d05cc5d3b84b6a14d0989ae56c331d9e983a36a21f1 AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN test "$(node --version)" = "v24.22.1" && test "$(npm --version)" = "11.19.1"

FROM base AS dependencies
COPY package.json package-lock.json .npmrc ./
RUN npm ci

FROM dependencies AS browser-dependencies
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npx playwright install --with-deps chromium

FROM dependencies AS build
COPY . .
RUN npm run build

FROM browser-dependencies AS test
COPY . .
COPY --from=build /app/.next ./.next
CMD ["sh", "-c", "npm run typecheck && npm run lint && npm run test:unit && npm test"]

FROM base AS runtime
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
USER node
EXPOSE 3000
CMD ["node", "server.js"]
