# License Server Frontend - Production Dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies with proper permissions
RUN npm ci && chmod -R 755 node_modules/.bin

# Copy source code
COPY . .

# Build args for API URL
ARG VITE_API_URL=http://localhost:8090
ENV VITE_API_URL=$VITE_API_URL

# Build the app with proper permissions
RUN chmod -R 755 node_modules/.bin && npm run build

# Stage 2: Production with nginx
FROM nginx:alpine

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
