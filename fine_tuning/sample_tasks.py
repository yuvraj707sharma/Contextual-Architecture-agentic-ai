"""
Sample coding tasks for generating synthetic training data.

These tasks cover common real-world scenarios that MACRO's Planner
should learn to handle. Each task includes the request, expected
complexity, and target language.
"""

SAMPLE_TASKS = [
    # ── Simple tasks ──────────────────────────────────────
    {
        "request": "Add a /health endpoint that returns JSON with status and uptime",
        "language": "python",
        "complexity": "simple",
    },
    {
        "request": "Add input validation to the user registration endpoint",
        "language": "python",
        "complexity": "simple",
    },
    {
        "request": "Create a logging utility that writes to both console and file",
        "language": "python",
        "complexity": "simple",
    },
    {
        "request": "Add a retry decorator with exponential backoff",
        "language": "python",
        "complexity": "simple",
    },
    {
        "request": "Create a configuration loader that reads from env vars and .env file",
        "language": "python",
        "complexity": "simple",
    },
    {
        "request": "Add rate limiting middleware using a token bucket algorithm",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Create a caching decorator that uses Redis with TTL support",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Add pagination support to the list users endpoint",
        "language": "python",
        "complexity": "simple",
    },
    {
        "request": "Create a database migration script for adding a roles table",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Add CORS middleware with configurable allowed origins",
        "language": "python",
        "complexity": "simple",
    },
    
    # ── Medium tasks ──────────────────────────────────────
    {
        "request": "Add JWT authentication middleware with token refresh",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Create a webhook handler that validates signatures and processes events",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Add file upload endpoint with size limits and type validation",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Create a background task queue using asyncio",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Add search functionality with full-text search and filtering",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Create an audit log system that tracks all data modifications",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Add API versioning with v1 and v2 route prefixes",
        "language": "python",
        "complexity": "medium",
    },
    {
        "request": "Create a notification service with email and SMS channels",
        "language": "python",
        "complexity": "medium",
    },
    
    # ── Complex tasks ─────────────────────────────────────
    {
        "request": "Add OAuth2 social login with Google and GitHub providers",
        "language": "python",
        "complexity": "complex",
    },
    {
        "request": "Create a role-based access control system with permissions inheritance",
        "language": "python",
        "complexity": "complex",
    },
    {
        "request": "Add real-time notifications using WebSocket connections",
        "language": "python",
        "complexity": "complex",
    },
    {
        "request": "Create a multi-tenant data isolation layer",
        "language": "python",
        "complexity": "complex",
    },
    
    # ── JavaScript/TypeScript tasks ───────────────────────
    {
        "request": "Add form validation with real-time error messages",
        "language": "typescript",
        "complexity": "simple",
    },
    {
        "request": "Create a custom React hook for API calls with loading state",
        "language": "typescript",
        "complexity": "medium",
    },
    {
        "request": "Add infinite scroll with intersection observer",
        "language": "javascript",
        "complexity": "medium",
    },
    
    # ── Go tasks ──────────────────────────────────────────
    {
        "request": "Add a middleware chain with logging, auth, and rate limiting",
        "language": "go",
        "complexity": "medium",
    },
    {
        "request": "Create a graceful shutdown handler for the HTTP server",
        "language": "go",
        "complexity": "simple",
    },
    
    # ── C++ tasks ─────────────────────────────────────────
    {
        "request": "Implement a thread-safe singleton pattern with lazy initialization",
        "language": "cpp",
        "complexity": "medium",
    },
    {
        "request": "Add a binary search tree with insert, delete, and traversal",
        "language": "cpp",
        "complexity": "medium",
    },
    {
        "request": "Create a memory pool allocator for fixed-size objects",
        "language": "cpp",
        "complexity": "complex",
    },
]
