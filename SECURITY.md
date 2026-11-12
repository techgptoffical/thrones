# Security

Thrones runs on your own computer. This page explains what it can reach and how to report a problem.

## What Thrones exposes

- The app server listens on **127.0.0.1:8765** only. It is not reachable from other devices on your network. Requests with a `Host` header other than `127.0.0.1`/`localhost` are rejected (protection against DNS rebinding).
- The model engine (`llama-server`) listens on **127.0.0.1:8766** with its built-in web UI disabled. It runs as a child of Thrones inside a Windows job object, so it exits if Thrones exits or crashes.
- There is no authentication between the browser and the local server. Any program already running as your Windows user could call the local API. This is the same trust level as the files in your user folder.

## What Thrones sends over the network

Only when you ask for it:

1. **Deep Research:** search queries go to the selected search provider (DuckDuckGo by default), and the pages it chooses to read are downloaded. Your conversation is not sent; only the queries the research planner writes.
2. **Model downloads:** from huggingface.co when you press Download.

Offline mode blocks both. There is no telemetry, analytics or crash reporting.

## Defences in place

- Web pages are treated as untrusted data. The model has no tools while reading them, and the final report may only cite pages that were actually fetched; other links and citation numbers are removed.
- The fetcher refuses non-http(s) URLs, non-standard ports, URLs with credentials, and any host that resolves to a private, loopback, link-local, carrier-grade-NAT, multicast or reserved address (including after redirects). This prevents a web page or a model from reaching your router, local services or cloud metadata endpoints.
- Robots.txt is respected; requests to each site are spaced out.
- The calculator evaluates a restricted expression grammar, never Python code.
- The **Python tool is off by default**. When enabled it runs model-written code as your user with a 15-second limit in a temporary folder. It is **not a sandbox**; enable it only if you accept that.
- Uploaded files are parsed (text, PDF, DOCX), never executed.
- The Brave API key, if you set one, is stored in the local database and excluded from data exports.

## Reporting a vulnerability

Please do not open a public issue for security problems. Contact the maintainers privately through the repository's security advisory feature, with steps to reproduce. We aim to respond within 7 days.
