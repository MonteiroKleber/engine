# Console Deployment Runbook — Libervia Console

Version: 1.0 | Last Updated: 2026-01-30

## Overview

This runbook covers deploying the Libervia Console frontend application for SaaS production environments.

---

## 1. Prerequisites

### 1.1 Build Environment

- Node.js 18+ (LTS)
- npm 9+
- Access to `/home/bazari/libervia-console` repository

### 1.2 Target Environment

- Static file hosting (nginx, Caddy, S3+CloudFront, Vercel, etc.)
- HTTPS certificate configured
- Engine API accessible (for CORS configuration)

---

## 2. Build Configuration

### 2.1 Environment Variables

Create `.env.production` in the project root:

```bash
# Engine API URL (public-facing, via reverse proxy)
VITE_ENGINE_BASE_URL=https://api.example.com

# Institution ID (for single-tenant deployments)
# Leave empty for multi-tenant (institution selected at runtime)
VITE_INSTITUTION_ID=

# IMPORTANT: Do NOT include admin credentials here!
# Admin operations should go through a backend proxy
VITE_ENGINE_ADMIN_KEY=
VITE_ENGINE_ADMIN_TOKEN=
```

### 2.2 Security Warning

**NEVER include admin credentials in frontend builds!**

The `VITE_` prefix makes variables available in the browser bundle, exposing them to users.

For admin operations, implement one of:
1. **Backend proxy**: Console calls your backend, which calls Engine with admin credentials
2. **Session-based auth**: Use Engine's console session endpoints (cookie-based)
3. **User tokens**: Each user authenticates with their own actor token

---

## 3. Build Process

### 3.1 Install Dependencies

```bash
cd /home/bazari/libervia-console

# Install dependencies
npm ci

# Verify installation
npm ls
```

### 3.2 Type Check

```bash
# Run TypeScript check
npm run typecheck
# or
npx tsc --noEmit
```

Note: You may see errors about `import.meta.env` if Vite types aren't configured. These are build-time only and don't affect the production bundle.

### 3.3 Build for Production

```bash
# Build production bundle
npm run build

# Output is in dist/
ls -la dist/
```

### 3.4 Verify Build

```bash
# Check bundle size
du -sh dist/

# Check for source maps (should NOT exist in production)
find dist/ -name "*.map"
# Expected: no results

# Check index.html exists
cat dist/index.html | head -20
```

---

## 4. Deployment Options

### 4.1 Option A: nginx Static Hosting

```nginx
# /etc/nginx/sites-available/console
server {
    listen 443 ssl http2;
    server_name console.example.com;

    ssl_certificate /etc/ssl/certs/example.com.pem;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    root /var/www/libervia-console;
    index index.html;

    # SPA routing - serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://api.example.com" always;
}
```

Deploy:
```bash
# Copy built files
sudo rsync -av --delete dist/ /var/www/libervia-console/

# Reload nginx
sudo nginx -t && sudo systemctl reload nginx
```

### 4.2 Option B: Caddy

```caddyfile
# Caddyfile
console.example.com {
    root * /var/www/libervia-console
    file_server

    # SPA routing
    try_files {path} /index.html

    # Security headers
    header {
        X-Frame-Options "SAMEORIGIN"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

### 4.3 Option C: Docker

```dockerfile
# Dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

```bash
# Build and run
docker build -t libervia-console .
docker run -d -p 80:80 libervia-console
```

---

## 5. Engine CORS Configuration

The Engine must allow requests from the Console domain.

### 5.1 Configure CORS

In `/etc/engine/engine.env`:
```bash
ENGINE_CORS_ORIGINS=https://console.example.com,https://admin.example.com
```

### 5.2 Verify CORS

```bash
# Test CORS preflight
curl -X OPTIONS https://api.example.com/health \
  -H "Origin: https://console.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -v 2>&1 | grep -i "access-control"

# Expected headers:
# Access-Control-Allow-Origin: https://console.example.com
# Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
# Access-Control-Allow-Headers: ...
```

---

## 6. Verification

### 6.1 Health Check

```bash
# Check Console is accessible
curl -s -o /dev/null -w "%{http_code}" https://console.example.com/
# Expected: 200

# Check SPA routing works
curl -s -o /dev/null -w "%{http_code}" https://console.example.com/chat
# Expected: 200 (served by index.html)
```

### 6.2 Browser Check

1. Open `https://console.example.com` in browser
2. Open DevTools → Network tab
3. Verify:
   - [ ] Page loads without errors
   - [ ] No mixed content warnings
   - [ ] API requests go to correct Engine URL
   - [ ] No CORS errors in console

### 6.3 Functional Check

- [ ] Navigation works (Chat, Approvals, Audit)
- [ ] Chat page loads pending approvals
- [ ] Audit page shows ledger events
- [ ] Approve/Reject actions work (with valid auth)

---

## 7. Rollback

### 7.1 Keep Previous Build

```bash
# Before deploy, backup current
sudo mv /var/www/libervia-console /var/www/libervia-console.bak.$(date +%Y%m%d%H%M%S)

# Deploy new
sudo rsync -av --delete dist/ /var/www/libervia-console/
```

### 7.2 Rollback Steps

```bash
# If issues found
sudo rm -rf /var/www/libervia-console
sudo mv /var/www/libervia-console.bak.<timestamp> /var/www/libervia-console
sudo systemctl reload nginx
```

---

## 8. Monitoring

### 8.1 Error Monitoring

Integrate browser error tracking (Sentry, etc.):

```typescript
// In main.tsx or App.tsx
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: "https://xxx@sentry.io/xxx",
  environment: import.meta.env.MODE,
});
```

### 8.2 Analytics

Track page views and key actions:
- Page navigation
- Approval actions (approve/reject)
- Error occurrences

---

## 9. Checklist

### Pre-Deploy

- [ ] `.env.production` configured (NO admin credentials!)
- [ ] `npm ci` completed successfully
- [ ] `npm run build` completed without errors
- [ ] `dist/` folder created with expected files
- [ ] No `.map` files in production build

### Deploy

- [ ] Previous build backed up
- [ ] Files copied to web server
- [ ] nginx/Caddy reloaded
- [ ] CORS configured on Engine

### Post-Deploy

- [ ] Console accessible via HTTPS
- [ ] No console errors in browser
- [ ] API calls reach Engine
- [ ] Navigation works
- [ ] Approve/Reject functional

---

## Quick Reference

### Build Commands

```bash
npm ci                  # Install dependencies
npm run typecheck       # Type check
npm run build           # Production build
npm run preview         # Preview production build locally
```

### Environment Variables

```bash
VITE_ENGINE_BASE_URL=https://api.example.com  # Required
VITE_INSTITUTION_ID=                           # Optional
```

### File Locations

| Item | Path |
|------|------|
| Source | `/home/bazari/libervia-console/` |
| Build output | `/home/bazari/libervia-console/dist/` |
| Production deploy | `/var/www/libervia-console/` |
| nginx config | `/etc/nginx/sites-available/console` |
