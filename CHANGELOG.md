---
## 5. CHANGELOG (template)
*File: `CHANGELOG.md`*
```markdown
# Changelog

All notable changes to **intrabus** will be documented here.

## [0.1.0] – 2025‑07‑24
### Added
- Synchronous, single‑host **TopicBroker** (XSUB↔XPUB forwarder).
- Synchronous **CentralBroker** (ROUTER request/reply router).
- Thread‑safe **BusInterface** exposing `publish/subscribe` + `send_request`.
- Environment‑overrideable default addresses.
- Context‑manager support (`with BusInterface(...)`).
- Examples and unit tests for pub/sub and req/rep patterns.