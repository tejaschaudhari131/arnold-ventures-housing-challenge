# Security Policy

## Reporting a vulnerability

If you discover a security issue in this project, please report it privately rather than opening a public issue. Use GitHub's **Private vulnerability reporting** (the "Report a vulnerability" button under the repository's Security tab), which the team has enabled per the challenge setup guide.

Please include enough detail to reproduce the issue. We will acknowledge the report and respond as the challenge timeline allows.

## Handling of secrets

This repository has secret scanning and push protection enabled. If a credential is ever committed, it must be rotated (invalidated) immediately — removing it from history alone is not sufficient once it has been pushed.

## HTTP surface

The server binds to 127.0.0.1 by default, uses a fixed route map, caps JSON bodies at 64 KB, and clamps assumption overrides to the published band. Responses send `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`. Lab acquisition reaches only www2.census.gov, data.wprdc.org, and www.huduser.gov. On Vercel, `GET /api/lab/results` reads committed files and does not run the envelope.
