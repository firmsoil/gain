# ADR 0014: GAIN MCP Production Transport

**Status:** Accepted  
**Date:** 2026-09-20  
**Deciders:** Lead Architect, GAIN Platform Engineer, GAIN Architect  

---

## 1. Context

MCP defines multiple transports for communication between client hosts and servers:
- `stdio`: Process standard input/output.
- `Streamable HTTP`: The modern MCP HTTP transport with streaming JSON-RPC messages and optional session resumption.
- `HTTP+SSE`: Deprecated legacy transport in MCP v1.

We must define the supported transports for GAIN MCP across development, testing, and production deployments.

---

## 2. Decision

We establish a dual-transport strategy:

1. **Development & Local CLI**:
   - `stdio` transport is supported via `server.run_stdio_async()`.
   - Used for command-line debugging, pipe composition, and desktop MCP hosts (e.g. Claude Desktop, Cursor local execution).
2. **Production & Network Service**:
   - **Streamable HTTP** is the designated production transport via `server.streamable_http_app(...)` mounted as an ASGI Starlette application and served via Uvicorn.
   - Mounted at endpoint path `/mcp`.
3. **No Deprecated Transports**: Legacy HTTP+SSE is explicitly prohibited for new implementations.

---

## 3. Consequences

- **Positive**: Streamable HTTP provides robust, bi-directional streaming over standard HTTP infrastructure, fully compatible with reverse proxies, API gateways, and Kubernetes ingress.
- **Positive**: stdio provides a frictionless local developer experience without network configuration or port binding conflicts.
- **Negative**: Streamable HTTP requires ASGI server lifecycle management (`session_manager.run()`).
