# Stage 1: Build
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Runtime (Node.js for standalone)
FROM node:20-slim AS runtime
WORKDIR /app

# Set production environment
ENV NODE_ENV=production
RUN groupadd -r neuroflow && useradd -r -g neuroflow neuroflow

# Copy standalone build artifacts
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Permissions
RUN chown -R neuroflow:neuroflow /app

USER neuroflow
EXPOSE 3000

# Next.js standalone needs HOST 0.0.0.0 and PORT 3000 by default
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
