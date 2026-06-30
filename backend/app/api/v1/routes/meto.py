"""Meto AI — API Routes.

All Meto endpoints. Authentication required (patient role).
Provider name is NEVER exposed in any response.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.context.schemas import ScreenContext
from app.api.deps import get_session, require_roles
from app.models.user import UserRole
from app.schemas.meto import (
    ConsentStatus,
    ConsentUpdateRequest,
    ConversationSummary,
    MessageResponse,
    MetaChatResponse,
    MetoChatRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meto"])

_patient_required = require_roles(UserRole.PATIENT)


def _get_chat_service():  # type: ignore[return]  # MetoChatService imported locally
    from app.ai.registry import get_registry
    from app.services.meto_chat import MetoChatService
    return MetoChatService(get_registry())


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------

@router.post("/meto/chat", response_model=MetaChatResponse)
async def chat(
    req: MetoChatRequest,
    current_user=Depends(_patient_required),
    db: Session = Depends(get_session),
) -> MetaChatResponse:
    """Non-streaming Meto chat."""
    from app.ai.readiness import check_provider_readiness

    readiness = check_provider_readiness()
    if not readiness["any_ready"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meto đang được cấu hình. Vui lòng thử lại sau.",
        )

    svc = _get_chat_service()
    screen = ScreenContext(
        screen_id=req.screen_id,
        entity_id=req.entity_id,
        entity_type=req.entity_type,
    )
    return await svc.chat(
        db=db,
        user_id=current_user.id,
        conversation_id=req.conversation_id,
        message=req.message,
        screen_context=screen,
    )


@router.post("/meto/chat/stream")
async def chat_stream(
    req: MetoChatRequest,
    current_user=Depends(_patient_required),
    db: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE streaming Meto chat."""
    svc = _get_chat_service()
    screen = ScreenContext(
        screen_id=req.screen_id,
        entity_id=req.entity_id,
        entity_type=req.entity_type,
    )

    async def event_generator():
        async for chunk in svc.stream_chat(
            db=db,
            user_id=current_user.id,
            conversation_id=req.conversation_id,
            message=req.message,
            screen_context=screen,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Conversation management
# ---------------------------------------------------------------------------

@router.get("/meto/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    current_user=Depends(_patient_required),
    db: Session = Depends(get_session),
) -> list[ConversationSummary]:
    """List all conversations for the current user."""
    svc = _get_chat_service()
    convs = svc.list_conversations(db, current_user.id)
    return [
        ConversationSummary(
            id=c.id,
            title=c.title,
            screen_id=c.screen_id,
            message_count=c.message_count,
            last_active_at=c.last_active_at,
            status=c.status,
        )
        for c in convs
    ]


@router.get(
    "/meto/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def get_messages(
    conversation_id: str,
    current_user=Depends(_patient_required),
    db: Session = Depends(get_session),
) -> list[MessageResponse]:
    """Get conversation message history."""
    svc = _get_chat_service()
    conv = svc.get_conversation(db, current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    msgs = svc.get_history(db, conversation_id)
    return [
        MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            screen_id=m.screen_id,
            created_at=m.created_at,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            fallback_used=m.fallback_used,
        )
        for m in msgs
    ]


@router.delete("/meto/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user=Depends(_patient_required),
    db: Session = Depends(get_session),
) -> None:
    """Soft-delete a conversation."""
    svc = _get_chat_service()
    conv = svc.get_conversation(db, current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    svc.delete_conversation(db, current_user.id, conversation_id)


# ---------------------------------------------------------------------------
# Consent management
# ---------------------------------------------------------------------------

@router.get("/meto/consent", response_model=list[ConsentStatus])
async def get_consent(
    current_user=Depends(_patient_required),
    db: Session = Depends(get_session),
) -> list[ConsentStatus]:
    """Get current consent status for all Meto data types."""
    svc = _get_chat_service()
    return svc.get_consent(db, current_user.id)


@router.post("/meto/consent", status_code=status.HTTP_200_OK)
async def update_consent(
    req: ConsentUpdateRequest,
    current_user=Depends(_patient_required),
    db: Session = Depends(get_session),
) -> dict:
    """Grant or revoke consent for a data type."""
    svc = _get_chat_service()
    svc.update_consent(db, current_user.id, req.context_type, req.granted)
    action = "granted" if req.granted else "revoked"
    return {"status": "ok", "context_type": req.context_type, "action": action}


# ---------------------------------------------------------------------------
# Health / Readiness
# ---------------------------------------------------------------------------

@router.get("/meto/health")
async def meto_health(
    current_user=Depends(_patient_required),
) -> dict:
    """Meto readiness health check. Patient-auth required."""
    from app.ai.readiness import MetoReadinessChecker
    checker = MetoReadinessChecker()
    report = await checker.check_all(fast=True)
    return {
        "status": "ready" if report.deploy_allowed else "not_ready",
        "score": report.score,
        "mode": report.mode,
        "summary": report.summary,
        "gates": [
            {"gate": g.gate, "passed": g.passed, "latency_ms": g.latency_ms}
            for g in report.gates
        ],
    }


# ---------------------------------------------------------------------------
# Quick prompts
# ---------------------------------------------------------------------------

@router.get("/meto/quick-prompts", response_model=list[str])
async def get_quick_prompts(
    screen_id: str = "dashboard",
    current_user=Depends(_patient_required),
) -> list[str]:
    """Get quick prompt suggestions for the current screen."""
    from app.ai.prompt.safety import QUICK_PROMPTS
    return QUICK_PROMPTS.get(screen_id, QUICK_PROMPTS.get("dashboard", []))
