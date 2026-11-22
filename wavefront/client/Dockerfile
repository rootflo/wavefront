ARG PNPM_VERSION=pnpm@10.13.1+sha512.37ebf1a5c7a30d5fabe0c5df44ee8da4c965ca0c5af3dbab28c3a1681b70a256218d05c81c9c0dcf767ef6b8551eb5b960042b9ed4300c59242336377e01cfad

FROM node:22-alpine AS deps
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION}

COPY wavefront/client/pnpm-lock.yaml wavefront/client/pnpm-workspace.yaml ./
COPY wavefront/client/package.json ./

RUN pnpm install

FROM node:22-alpine AS build
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION}

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/pnpm-workspace.yaml ./
COPY --from=deps /app/package.json ./

COPY wavefront/client/ ./

RUN pnpm build

# Runtime server deps, installed in their own stage so the final image needs no package manager
FROM node:22-alpine AS runtime-deps
WORKDIR /app
RUN npm install --omit=dev --no-audit --no-fund express@^5.1.0 compression@^1.8.1

FROM node:22-alpine
WORKDIR /app

# Patch Alpine packages, and drop npm/corepack (and their bundled dependencies)
# plus Node's C headers, none of which are used at runtime
RUN apk upgrade --no-cache && \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
    /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /usr/local/include/node && \
    chown node:node /app

COPY --from=runtime-deps --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --from=build --chown=node:node /app/server.cjs ./

USER node

EXPOSE 3000

CMD ["node", "server.cjs"]
