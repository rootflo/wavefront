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

FROM node:22-alpine
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION}

COPY --from=build /app/dist ./dist
COPY --from=build /app/server.cjs ./
RUN pnpm install express@4.21.2 compression@^1.8.0

EXPOSE 3000

CMD ["node", "server.cjs"]