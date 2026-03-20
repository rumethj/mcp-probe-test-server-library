"""Simple Library Manager — MCP Server.

A minimal MCP server that exposes a hardcoded book catalog through one
Resource, two Tools, and one Prompt.  An optional transport-layer wrapper
routes every outgoing JSON-RPC message through ``defect_injector.apply_defect``
so that protocol-level faults can be injected without touching the core logic.
"""

import json
import os
import sys
from io import TextIOWrapper

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from mcp.server.stdio import stdio_server

from defect_injector import apply_defect

# ---------------------------------------------------------------------------
# In-memory catalog
# ---------------------------------------------------------------------------

CATALOG: dict[str, dict] = {
    "B001": {
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "genre": "Classic",
        "is_available": True,
    },
    "B002": {
        "title": "Dune",
        "author": "Frank Herbert",
        "genre": "Science Fiction",
        "is_available": True,
    },
    "B003": {
        "title": "Murder on the Orient Express",
        "author": "Agatha Christie",
        "genre": "Mystery",
        "is_available": False,
    },
    "B004": {
        "title": "Pride and Prejudice",
        "author": "Jane Austen",
        "genre": "Romance",
        "is_available": True,
    },
}

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Simple Library Manager")

# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------


@mcp.resource("library://catalog/inventory")
def get_inventory() -> str:
    """Return the complete library catalog as formatted JSON."""
    return json.dumps(CATALOG, indent=2)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def checkout_book(book_id: str, user_name: str) -> str:
    """Check out a book from the library.

    Marks the book as unavailable if it exists and is currently available.

    Args:
        book_id: The unique identifier for the book (e.g. "B001").
        user_name: Name of the person checking out the book.
    """
    if book_id not in CATALOG:
        return f"Error: Book '{book_id}' not found in catalog."

    book = CATALOG[book_id]
    if not book["is_available"]:
        return f"Error: '{book['title']}' is already checked out."

    book["is_available"] = False
    return f"Success: '{book['title']}' has been checked out to {user_name}."


@mcp.tool()
def return_book(book_id: str) -> str:
    """Return a previously checked-out book to the library.

    Marks the book as available again if it exists and is currently checked out.

    Args:
        book_id: The unique identifier for the book (e.g. "B001").
    """
    if book_id not in CATALOG:
        return f"Error: Book '{book_id}' not found in catalog."

    book = CATALOG[book_id]
    if book["is_available"]:
        return f"Error: '{book['title']}' is not currently checked out."

    book["is_available"] = True
    return f"Success: '{book['title']}' has been returned to the library."


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


@mcp.prompt()
def recommend_book_by_genre(genre: str) -> list[base.Message]:
    """Ask a librarian LLM to recommend a book from the catalog by genre.

    Args:
        genre: The literary genre to base the recommendation on.
    """
    catalog_snapshot = json.dumps(CATALOG, indent=2)
    return [
        base.AssistantMessage(
            "You are a helpful librarian. The user is looking for a book "
            "recommendation. Analyze the requested genre, review the catalog "
            "provided below, and suggest the most suitable available book.\n\n"
            f"Catalog:\n{catalog_snapshot}"
        ),
        base.UserMessage(
            f"Please recommend an available book in the '{genre}' genre."
        ),
    ]


# ---------------------------------------------------------------------------
# Transport wrapper — defect injection at the stdio layer
# ---------------------------------------------------------------------------


class TransportWrapper:
    """Proxy around the MCP write stream that intercepts every outgoing
    ``SessionMessage``, converts it to a plain dict, passes it through
    ``defect_injector.apply_defect``, and writes the (possibly mutated)
    payload directly to stdout — bypassing the SDK's Pydantic serialisation
    so that deliberately invalid JSON-RPC can be emitted.
    """

    def __init__(self, original_stream, stdout):
        self._original = original_stream
        self._stdout = stdout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._original.aclose()

    async def aclose(self):
        await self._original.aclose()

    async def send(self, session_message):
        message_dict = session_message.message.model_dump(
            by_alias=True, exclude_none=True
        )
        result = apply_defect(message_dict)

        if isinstance(result, str):
            await self._stdout.write(result + "\n")
        else:
            await self._stdout.write(json.dumps(result) + "\n")
        await self._stdout.flush()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def _run() -> None:
    defect = os.environ.get("INJECT_MCP_DEFECT", "").strip()
    if defect:
        print(
            f"[Library Server] Defect injection active: {defect}",
            file=sys.stderr,
        )
    else:
        print(
            "[Library Server] Running in normal mode (no defects)",
            file=sys.stderr,
        )

    # Open /dev/null so the internal stdout_writer in stdio_server has a
    # harmless sink — the TransportWrapper writes to the real stdout instead.
    devnull = open(os.devnull, "w")
    devnull_async = anyio.wrap_file(devnull)
    stdout = anyio.wrap_file(
        TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    )

    try:
        async with stdio_server(stdout=devnull_async) as (
            read_stream,
            write_stream,
        ):
            wrapper = TransportWrapper(write_stream, stdout)
            await mcp._mcp_server.run(
                read_stream,
                wrapper,
                mcp._mcp_server.create_initialization_options(),
            )
    finally:
        devnull.close()


def main() -> None:
    """Run the Simple Library Manager MCP server over stdio."""
    anyio.run(_run)


if __name__ == "__main__":
    main()
