"""
MCP server wrapping the AI Resume Screener's existing scoring/search logic.

Setup:
    pip install mcp

Run standalone (for testing with the MCP Inspector):
    mcp dev server.py

Wire into Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "resume-screener": {
          "command": "python",
          "args": ["/absolute/path/to/server.py"]
        }
      }
    }

--------------------------------------------------------------------------
WHAT TO EDIT: everything under the "# --- WIRE THESE UP ---" markers below.
Replace the placeholder imports/functions with the real ones from your
services/ folder (your FastAPI backend + LangGraph agent microservice).
Nothing else needs to change — the MCP boilerplate is done.
--------------------------------------------------------------------------
"""

from mcp.server.fastmcp import FastMCP

# --- WIRE THESE UP: replace with your actual imports -----------------
# e.g. from services.agents.fit_score import compute_fit_score
# e.g. from services.retrieval.chroma_client import get_chroma_collection
# -----------------------------------------------------------------------

mcp = FastMCP("resume-screener")


@mcp.tool()
def search_resumes(query: str, top_k: int = 5) -> str:
    """
    Semantic search over the resume corpus using the existing SBERT +
    ChromaDB retrieval layer. Returns the top-k matching resume IDs
    with their similarity scores.
    """
    # --- WIRE THIS UP ---
    # collection = get_chroma_collection()
    # results = collection.query(query_texts=[query], n_results=top_k)
    # return format_results(results)
    raise NotImplementedError("Plug in your ChromaDB query call here")


@mcp.tool()
def score_fit(resume_id: str, job_description: str) -> str:
    """
    Run the existing multi-agent Fit Score pipeline (SBERT embeddings +
    RAG layer + deterministic skill matching) for a given resume against
    a job description. Returns the numeric fit score plus a breakdown.
    """
    # --- WIRE THIS UP ---
    # result = compute_fit_score(resume_id, job_description)
    # return f"Fit Score: {result.score}/100\n{result.breakdown}"
    raise NotImplementedError("Plug in your Fit Score agent call here")


@mcp.tool()
def explain_score(resume_id: str) -> str:
    """
    Return the traceable explanation behind a resume's most recent Fit
    Score — which skills matched, which were missing, and which RAG
    context chunks the scoring agent used. This is the explainability
    layer from your original pitch: no black-box output.
    """
    # --- WIRE THIS UP ---
    # explanation = get_last_explanation(resume_id)
    # return explanation
    raise NotImplementedError("Plug in your explanation retrieval here")


@mcp.resource("resumes://corpus/summary")
def corpus_summary() -> str:
    """
    Expose corpus stats as an MCP resource (not a tool) — e.g. total
    resumes indexed, last update time. This demonstrates the
    tools-vs-resources distinction in the MCP spec: resources are data
    a host can read, tools are actions it can invoke.
    """
    # --- WIRE THIS UP ---
    # return f"{get_resume_count()} resumes indexed, last updated {get_last_updated()}"
    return "TODO: wire up corpus stats"


if __name__ == "__main__":
    mcp.run()