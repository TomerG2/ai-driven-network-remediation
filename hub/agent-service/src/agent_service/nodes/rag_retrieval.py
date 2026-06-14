from loguru import logger


def rag_retrieval_node(state: dict) -> dict:
    logger.info("RAG retrieval node invoked")
    raw_event = state.raw_event
    rag_query = f"incident context for: {raw_event}"
    return {
        "context_snippets": ["placeholder-context-snippet"],
        "rag_query_used": rag_query,
    }
