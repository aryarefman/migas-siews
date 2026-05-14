FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . ./
RUN mkdir -p public

# NEXT_PUBLIC vars must be set at build time for Next.js to inline them
ENV NEXT_PUBLIC_API_URL=http://localhost:8001
ENV NEXT_PUBLIC_WS_URL=ws://localhost:8001

RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000
ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=http://localhost:8001
ENV NEXT_PUBLIC_WS_URL=ws://localhost:8001

CMD ["npm", "start"]
