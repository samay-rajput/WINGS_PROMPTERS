import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Gemini embedding model identifier
EMBEDDING_MODEL = "models/gemini-embedding-001"


def get_all_embeddings() -> list[GoogleGenerativeAIEmbeddings]:
    """
    Initialise and return a list of GoogleGenerativeAIEmbeddings instances.
    Reads GEMINI_API_KEY_RAG (or fallback GEMINI_API_KEY) from the environment,
    allowing comma-separated multiple keys.
    Automatically filters out dummy/placeholder keys starting with 'AIzaSy_KEY_'.
    """
    api_key_str = os.getenv("GEMINI_API_KEY_RAG") or os.getenv("GEMINI_API_KEY", "")
    # Split, strip, and ignore dummy placeholders
    raw_keys = [k.strip() for k in api_key_str.split(",") if k.strip()]
    
    valid_keys = []
    for k in raw_keys:
        # Ignore obvious placeholders like AIzaSy_KEY_1
        if "_KEY_" in k.upper():
            continue
        valid_keys.append(k)

    if not valid_keys:
        raise EnvironmentError(
            "No valid GEMINI_API_KEY_RAG found. "
            "Please check your .env file and ensure real keys are provided."
        )
        
    return [
        GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=key)
        for key in valid_keys
    ]
