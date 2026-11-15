from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from src.pipeline import SagePipeline

# Global singleton pipeline instance for high performance
_PIPELINE = None

def get_pipeline():
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = SagePipeline()
    return _PIPELINE


@api_view(['POST'])
def ask_question(request):
    """
    POST /ask
    Endpoint for asking payment and billing questions to the Sage Assistant.
    Payload:
      {
        "question": "string (required)",
        "conversation_id": "string (optional)"
      }
    """
    data = request.data
    question = data.get("question")
    if not question or not isinstance(question, str) or not question.strip():
        return Response(
            {"error": "Field 'question' is required and must be a non-empty string."},
            status=status.HTTP_400_BAD_REQUEST
        )

    conversation_id = data.get("conversation_id")
    pipeline = get_pipeline()
    
    result = pipeline.ask(question.strip(), conversation_id=conversation_id)

    # Format output strictly matching the assignment REST specifications
    clean_citations = [
        {"doc_id": c["doc_id"], "passage": c["passage"]}
        for c in result.get("citations", [])
    ]
    
    response_payload = {
        "answer": result.get("answer"),
        "status": result.get("status"),
        "citations": clean_citations,
        "conflicts": result.get("conflicts", []),
        "reasoning_summary": result.get("reasoning_summary", ""),
        "model": result.get("model", "unknown"),
        "latency_ms": result.get("latency_ms", 0),
    }

    return Response(response_payload, status=status.HTTP_200_OK)


@api_view(['GET'])
def health_check(request):
    """Health check endpoint."""
    return Response({
        "status": "healthy",
        "service": "Paperkite Sage QA Knowledge System",
        "version": "1.0.0",
        "endpoints": ["POST /ask", "GET /health"]
    }, status=status.HTTP_200_OK)
