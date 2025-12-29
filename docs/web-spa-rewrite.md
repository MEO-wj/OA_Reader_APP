# Web SPA rewrites for iOS Web Clip

Goal: ensure every route returns the same HTML (with
`apple-mobile-web-app-capable=yes`) so iOS "Add to Home Screen" opens
without browser chrome on any path.

## Static hosts that support _redirects

Place this file in the published root (already under `OAP-app/public/`):

```
/* /index.html 200
```

Works for:
- Netlify
- Cloudflare Pages

## Vercel

Add `vercel.json` at the web app root:

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

## Nginx

```
location / {
  try_files $uri /index.html;
}
```

## Apache (.htaccess)

```
RewriteEngine On
RewriteCond %{REQUEST_FILENAME} !-f
RewriteRule . /index.html [L]
```

## Validation checklist

- Any deep link returns the same HTML head (view source to verify meta tags).
- Avoid redirects (`http -> https`, `/path -> /path/`, `www -> non-www`).
- Delete old home screen icon and add again after deploy.
