# Simple Library Manager — MCP Test Server

A minimal MCP server that exposes a hardcoded book catalog through standard MCP primitives. It is designed as a **testing target** for automated MCP compliance and resilience tools, and ships with an optional defect injection mechanism that corrupts outgoing JSON-RPC responses at the transport layer.

## Prerequisites

- Python 3.10+
- Dependencies listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

## Running the Server

The server communicates over **standard I/O** (stdin/stdout):

```bash
python server.py
```

## MCP Primitives

### Resource

| URI | Description |
|---|---|
| `library://catalog/inventory` | Returns the full library catalog as formatted JSON. |

### Tools

| Name | Parameters | Description |
|---|---|---|
| `checkout_book` | `book_id` (string), `user_name` (string) | Marks a book as unavailable if it exists and is currently available. |
| `return_book` | `book_id` (string) | Marks a checked-out book as available again. |

### Prompt

| Name | Parameters | Description |
|---|---|---|
| `recommend_book_by_genre` | `genre` (string) | Returns a multi-turn prompt instructing an LLM to act as a librarian and recommend a book from the catalog matching the given genre. |

## Catalog

The server starts with four hardcoded books:

| ID | Title | Author | Genre | Available |
|---|---|---|---|---|
| B001 | The Great Gatsby | F. Scott Fitzgerald | Classic | Yes |
| B002 | Dune | Frank Herbert | Science Fiction | Yes |
| B003 | Murder on the Orient Express | Agatha Christie | Mystery | No |
| B004 | Pride and Prejudice | Jane Austen | Romance | Yes |

## Defect Injection

Set the `INJECT_MCP_DEFECT` environment variable **before** launching the server to activate a specific transport-level fault. The defect logic lives entirely in `defect_injector.py` and is applied to every outgoing JSON-RPC message via a `TransportWrapper` that intercepts the stdio write stream.

### Available Defect Modes

| Value | Effect |
|---|---|
| *(unset or empty)* | No defect — responses are forwarded normally. |
| `missing_id` | Removes the `"id"` key from every JSON-RPC response. |
| `invalid_version` | Changes the `"jsonrpc"` field from `"2.0"` to `"1.0"`. |
| `artificial_error` | Replaces the `"result"` payload with a JSON-RPC error object (code `-32000`). |
| `garbage_data` | Emits an unparseable string (`{bad_json: true, ]`) instead of valid JSON. |

### Usage Examples

```bash
# Normal operation
python server.py

# Strip the id field from all responses
INJECT_MCP_DEFECT=missing_id python server.py

# Emit an invalid JSON-RPC version
INJECT_MCP_DEFECT=invalid_version python server.py

# Replace all results with fake error objects
INJECT_MCP_DEFECT=artificial_error python server.py

# Send garbage instead of JSON
INJECT_MCP_DEFECT=garbage_data python server.py
```

## Architecture

```
┌────────────────────────────────────┐
│  server.py                         │
│                                    │
│  FastMCP("Simple Library Manager") │
│    ├── Resource (catalog)          │
│    ├── Tool (checkout_book)        │
│    ├── Tool (return_book)          │
│    └── Prompt (recommend_book)     │
│                                    │
│  TransportWrapper                  │
│    └── intercepts .send()          │
│        ├── model_dump() → dict     │
│        ├── apply_defect(dict)      │ ──► defect_injector.py
│        └── json.dumps → stdout     │       reads INJECT_MCP_DEFECT
└────────────────────────────────────┘
```
