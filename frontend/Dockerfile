FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . ./
RUN mkdir -p public
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./
RUN npm install --omit=dev

EXPOSE 3000
ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=http://localhost:8001

CMD ["npm", "start"]
