FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN mkdir -p public && npm run build

FROM dependencies AS test
COPY . .
RUN mkdir -p /tmp/test-results && npm run test:ci

FROM scratch AS test-results
COPY --from=test /tmp/test-results /

FROM node:22-alpine AS runner
ENV NODE_ENV=production \
    PORT=3007 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER node
EXPOSE 3007
CMD ["node", "server.js"]
