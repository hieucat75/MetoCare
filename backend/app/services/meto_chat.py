"""Meto AI — Chat Service.

Orchestrates the full Meto chat pipeline:
1. Load/create conversation
2. Check consent
3. Build context (ContextBuilder)
4. Safety check input (SafetyGuard)
5. Assemble prompt (PromptAssembler)
6. Call provider (with fallback via ProviderRegistry)
7. Safety check output
8. Save messages to DB
9. Write audit log
10. Return response

Does NOT directly call any AI provider — uses ProviderRegistry for routing/fallback.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import AsyncGenerator

from sqlalchemy.orm import Session

from app.ai.context.builder import ContextBuilder
from app.ai.context.schemas import AssembledContext, ScreenContext
from app.ai.exceptions import MetoAIError
from app.ai.prompt.assembler import PromptAssembler
from app.ai.prompt.safety import SafetyGuard, SafetyResult
from app.ai.registry import ProviderRegistry
from app.models.meto import MetoAuditLog, MetoConsent, MetoConversation, MetoMessage
from app.schemas.meto import (
    ConsentStatus,
    EscalationInfo,
    MetaChatResponse,
)

logger = logging.getLogger(__name__)

_SAFETY_GUARD = SafetyGuard()
_CONTEXT_BUILDER = ContextBuilder()
_PROMPT_ASSEMBLER = PromptAssembler()


class MetoChatService:
    """Orchestrates Meto chat pipeline: context → safety → prompt → provider → audit."""

    def __init__(self, provider_registry: ProviderRegistry) -> None:
        self._registry = provider_registry

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def chat(
        self,
        db: Session,
        user_id: str,
        conversation_id: str | None,
        message: str,
        screen_context: ScreenContext,
    ) -> MetaChatResponse:
        """Non-streaming chat. Runs full pipeline and returns complete response."""
        request_start = time.monotonic()

        # 1. Load or create conversation
        conversation = self._get_or_create_conversation(db, user_id, screen_context, conversation_id)

        # 2. Build context
        context = _CONTEXT_BUILDER.build(db, user_id, screen_context)

        # 3. Safety check input
        input_safety = _SAFETY_GUARD.check_input(message)

        # If emergency escalation needed, bypass AI call
        if input_safety.escalation_required and input_safety.escalation_tier == "emergency":
            return self._build_escalation_response(
                conversation=conversation,
                message=message,
                safety_result=input_safety,
                db=db,
                user_id=user_id,
                context=context,
                request_start=request_start,
            )

        # 4. Get conversation history
        history = self._get_history_as_dicts(db, conversation.id, limit=20)

        # 5. Assemble prompt
        preferred_address = (context.user_profile or {}).get("preferred_address", "bạn")
        system_prompt, messages = _PROMPT_ASSEMBLER.assemble(
            context=context,
            user_message=message,
            conversation_history=history,
            preferred_address=preferred_address,
        )

        # 6. Call provider with fallback
        fallback_used = False
        ai_response = None

        try:
            settings = _get_settings()
            max_tokens = settings.meto_max_tokens
            temperature = settings.meto_temperature

            async def call_fn(provider):
                return await provider.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            ai_response, actual_provider, fallback_used = await self._registry.call_with_fallback(
                task_type="chat_simple",
                call_fn=call_fn,
            )

        except MetoAIError as exc:
            logger.error("All providers failed for user %s: %s", user_id, exc)
            ai_content = (
                "Mình xin lỗi, Meto đang gặp sự cố kỹ thuật. "
                "Vui lòng thử lại sau ít phút. Nếu cần hỗ trợ khẩn cấp, "
                "hãy liên hệ bác sĩ hoặc gọi 115."
            )
            return self._save_and_return(
                db=db,
                conversation=conversation,
                user_message=message,
                ai_content=ai_content,
                safety_flags=input_safety.flags,
                escalation=None,
                provider_used="meto",
                fallback_used=False,
                context=context,
                input_tokens=0,
                output_tokens=0,
                latency_ms=int((time.monotonic() - request_start) * 1000),
                user_id=user_id,
                screen_context=screen_context,
            )

        ai_content = ai_response.content if ai_response else ""

        # 7. Safety check output
        output_safety = _SAFETY_GUARD.check_output(ai_content)
        all_flags = list(set(input_safety.flags + (output_safety.flags if not output_safety.safe else [])))

        # Build escalation info if needed
        escalation: EscalationInfo | None = None
        if input_safety.escalation_required and input_safety.escalation_tier:
            escalation = EscalationInfo(
                tier=input_safety.escalation_tier,
                message=input_safety.suggested_response or "",
                emergency_contacts=["115"] if "emergency" in (input_safety.escalation_tier or "") else None,
            )

        # 8 & 9. Save messages + audit log
        return self._save_and_return(
            db=db,
            conversation=conversation,
            user_message=message,
            ai_content=ai_content,
            safety_flags=all_flags,
            escalation=escalation,
            provider_used="meto",  # NEVER expose actual provider name
            fallback_used=fallback_used,
            context=context,
            input_tokens=ai_response.input_tokens if ai_response else 0,
            output_tokens=ai_response.output_tokens if ai_response else 0,
            latency_ms=int((time.monotonic() - request_start) * 1000),
            user_id=user_id,
            screen_context=screen_context,
        )

    async def stream_chat(
        self,
        db: Session,
        user_id: str,
        conversation_id: str | None,
        message: str,
        screen_context: ScreenContext,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat — yields SSE-formatted chunks."""
        import json

        request_start = time.monotonic()

        conversation = self._get_or_create_conversation(db, user_id, screen_context, conversation_id)
        context = _CONTEXT_BUILDER.build(db, user_id, screen_context)
        input_safety = _SAFETY_GUARD.check_input(message)

        if input_safety.escalation_required and input_safety.escalation_tier == "emergency":
            response = self._build_escalation_response(
                conversation=conversation,
                message=message,
                safety_result=input_safety,
                db=db,
                user_id=user_id,
                context=context,
                request_start=request_start,
            )
            yield f"data: {json.dumps({'type': 'chunk', 'delta': response.content})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': str(conversation.id)})}\n\n"
            return

        history = self._get_history_as_dicts(db, conversation.id, limit=20)
        preferred_address = (context.user_profile or {}).get("preferred_address", "bạn")
        system_prompt, messages = _PROMPT_ASSEMBLER.assemble(
            context=context,
            user_message=message,
            conversation_history=history,
            preferred_address=preferred_address,
        )

        # Save user message first
        self._save_message(
            db, conversation.id, "user", message,
            screen_context.screen_id, input_tokens=0, output_tokens=0,
            provider=None, fallback_used=False,
        )

        # Stream from provider
        full_content = ""
        provider_used = "meto"
        fallback_used = False
        input_tokens = 0
        output_tokens = 0

        try:
            providers = self._registry.get_available_providers("chat_simple")
            if not providers:
                raise MetoAIError("No providers available")

            settings = _get_settings()
            provider = providers[0]
            fallback_used = provider.provider_name != (providers[0].provider_name if providers else "claude")

            async for chunk in provider.chat_stream(
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=settings.meto_max_tokens,
                temperature=settings.meto_temperature,
            ):
                if chunk.is_final:
                    output_tokens = chunk.total_tokens or 0
                    break
                if chunk.delta:
                    full_content += chunk.delta
                    yield f"data: {json.dumps({'type': 'chunk', 'delta': chunk.delta})}\n\n"

        except Exception as exc:
            logger.error("Stream error for user %s: %s", user_id, exc)
            error_msg = "Meto gặp lỗi kỹ thuật. Vui lòng thử lại."
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            full_content = error_msg

        # Save assistant message
        latency_ms = int((time.monotonic() - request_start) * 1000)
        _SAFETY_GUARD.check_output(full_content)

        assistant_msg_id = self._save_message(
            db, conversation.id, "assistant", full_content,
            screen_context.screen_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider=provider_used,
            fallback_used=fallback_used,
        )

        # Update conversation
        self._update_conversation(db, conversation, 2, input_tokens + output_tokens, provider_used)

        # Audit log
        self._write_audit_log(
            db=db,
            user_id=user_id,
            conversation_id=conversation.id,
            action="chat_request",
            screen_id=screen_context.screen_id,
            context=context,
            provider_used=provider_used,
            fallback_used=fallback_used,
            safety_flags=input_safety.flags,
            escalation=False,
            response_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        yield (
            f"data: {json.dumps({'type': 'done', 'conversation_id': str(conversation.id), 'message_id': str(assistant_msg_id)})}\n\n"
        )

    def get_conversation(
        self, db: Session, user_id: str, conversation_id: str
    ) -> MetoConversation | None:
        return (
            db.query(MetoConversation)
            .filter(
                MetoConversation.id == conversation_id,
                MetoConversation.user_id == user_id,
                MetoConversation.deleted_at.is_(None),
            )
            .first()
        )

    def get_history(
        self, db: Session, conversation_id: str, limit: int = 50
    ) -> list[MetoMessage]:
        return (
            db.query(MetoMessage)
            .filter(MetoMessage.conversation_id == conversation_id)
            .order_by(MetoMessage.created_at.asc())
            .limit(limit)
            .all()
        )

    def list_conversations(
        self, db: Session, user_id: str, limit: int = 20
    ) -> list[MetoConversation]:
        return (
            db.query(MetoConversation)
            .filter(
                MetoConversation.user_id == user_id,
                MetoConversation.deleted_at.is_(None),
                MetoConversation.status != "deleted",
            )
            .order_by(MetoConversation.last_active_at.desc())
            .limit(limit)
            .all()
        )

    def delete_conversation(self, db: Session, user_id: str, conversation_id: str) -> None:
        conv = self.get_conversation(db, user_id, conversation_id)
        if conv:
            conv.deleted_at = dt.datetime.now(dt.UTC)
            conv.status = "deleted"
            db.commit()

    def get_consent(self, db: Session, user_id: str) -> list[ConsentStatus]:
        CONSENT_TYPES = ["health_data", "medications", "labs", "metrics", "care_plan", "chat_history"]
        rows = (
            db.query(MetoConsent)
            .filter(MetoConsent.user_id == user_id)
            .all()
        )
        existing = {r.context_type: r for r in rows}
        result = []
        for ct in CONSENT_TYPES:
            row = existing.get(ct)
            result.append(ConsentStatus(
                context_type=ct,
                granted=row.granted if row else False,
                granted_at=row.granted_at if row else None,
            ))
        return result

    def update_consent(
        self, db: Session, user_id: str, context_type: str, granted: bool
    ) -> None:
        row = (
            db.query(MetoConsent)
            .filter(
                MetoConsent.user_id == user_id,
                MetoConsent.context_type == context_type,
            )
            .first()
        )
        now = dt.datetime.now(dt.UTC)
        if row:
            row.granted = granted
            if granted:
                row.granted_at = now
                row.revoked_at = None
            else:
                row.revoked_at = now
        else:
            row = MetoConsent(
                user_id=user_id,
                context_type=context_type,
                granted=granted,
                granted_at=now if granted else None,
            )
            db.add(row)
        db.commit()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_or_create_conversation(
        self,
        db: Session,
        user_id: str,
        screen_context: ScreenContext,
        conversation_id: str | None,
    ) -> MetoConversation:
        if conversation_id:
            conv = self.get_conversation(db, user_id, conversation_id)
            if conv:
                return conv

        # Create new conversation
        conv = MetoConversation(
            user_id=user_id,
            screen_id=screen_context.screen_id,
            status="active",
            message_count=0,
            total_tokens=0,
            last_active_at=dt.datetime.now(dt.UTC),
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv

    def _get_history_as_dicts(
        self, db: Session, conversation_id: str, limit: int = 20
    ) -> list[dict]:
        messages = self.get_history(db, conversation_id, limit=limit)
        return [{"role": m.role, "content": m.content} for m in messages]

    def _save_message(
        self,
        db: Session,
        conversation_id: str,
        role: str,
        content: str,
        screen_id: str | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int | None = None,
        provider: str | None = None,
        fallback_used: bool = False,
    ) -> str:
        msg = MetoMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            screen_id=screen_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider=provider,
            fallback_used=fallback_used,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg.id

    def _update_conversation(
        self,
        db: Session,
        conv: MetoConversation,
        msg_delta: int,
        token_delta: int,
        provider_used: str,
    ) -> None:
        conv.message_count = (conv.message_count or 0) + msg_delta
        conv.total_tokens = (conv.total_tokens or 0) + token_delta
        conv.last_active_at = dt.datetime.now(dt.UTC)
        conv.provider_used = provider_used
        conv.status = "active"
        db.commit()

    def _write_audit_log(
        self,
        db: Session,
        user_id: str,
        conversation_id: str,
        action: str,
        screen_id: str | None,
        context: AssembledContext,
        provider_used: str,
        fallback_used: bool,
        safety_flags: list[str],
        escalation: bool,
        response_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        try:
            log = MetoAuditLog(
                user_id=user_id,
                conversation_id=conversation_id,
                action=action,
                screen_id=screen_id,
                context_types=context.included_blocks,
                provider_used=provider_used,
                fallback_used=fallback_used,
                safety_flags_detected=bool(safety_flags),
                escalation_triggered=escalation,
                response_time_ms=response_ms,
                token_count_input=input_tokens,
                token_count_output=output_tokens,
                details={"missing_consents": context.missing_consents},
            )
            db.add(log)
            db.commit()
        except Exception as exc:
            logger.error("Failed to write audit log: %s", exc)

    def _build_escalation_response(
        self,
        conversation: MetoConversation,
        message: str,
        safety_result: SafetyResult,
        db: Session,
        user_id: str,
        context: AssembledContext,
        request_start: float,
    ) -> MetaChatResponse:
        """Build a hardcoded escalation response without calling AI."""
        escalation_content = safety_result.suggested_response or (
            _SAFETY_GUARD.get_escalation_response(safety_result.flags, "emergency")
        )

        escalation = EscalationInfo(
            tier=safety_result.escalation_tier or "emergency",
            message=escalation_content,
            emergency_contacts=["115"],
        )

        latency_ms = int((time.monotonic() - request_start) * 1000)

        # Save user message
        self._save_message(db, conversation.id, "user", message, None)
        # Save assistant escalation
        msg_id = self._save_message(db, conversation.id, "assistant", escalation_content, None)
        self._update_conversation(db, conversation, 2, 0, "safety_guard")
        self._write_audit_log(
            db=db,
            user_id=user_id,
            conversation_id=conversation.id,
            action="escalated",
            screen_id=None,
            context=context,
            provider_used="safety_guard",
            fallback_used=False,
            safety_flags=safety_result.flags,
            escalation=True,
            response_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
        )

        return MetaChatResponse(
            conversation_id=conversation.id,
            message_id=msg_id,
            content=escalation_content,
            safety_flags=safety_result.flags,
            escalation=escalation,
            provider_used="meto",
            fallback_used=False,
            quick_follow_ups=[],
        )

    def _save_and_return(
        self,
        db: Session,
        conversation: MetoConversation,
        user_message: str,
        ai_content: str,
        safety_flags: list[str],
        escalation: EscalationInfo | None,
        provider_used: str,
        fallback_used: bool,
        context: AssembledContext,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        user_id: str,
        screen_context: ScreenContext,
    ) -> MetaChatResponse:
        """Save messages, update conversation, write audit log, return response."""
        # Set conversation title from first message
        if not conversation.title and user_message:
            conversation.title = _PROMPT_ASSEMBLER.generate_conversation_title(user_message)
            db.commit()

        # Save user message
        self._save_message(
            db, conversation.id, "user", user_message,
            screen_context.screen_id, input_tokens=0, output_tokens=0,
        )
        # Save assistant message
        msg_id = self._save_message(
            db, conversation.id, "assistant", ai_content,
            screen_context.screen_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider=provider_used,
            fallback_used=fallback_used,
        )

        self._update_conversation(db, conversation, 2, input_tokens + output_tokens, provider_used)

        self._write_audit_log(
            db=db,
            user_id=user_id,
            conversation_id=conversation.id,
            action="chat_request",
            screen_id=screen_context.screen_id,
            context=context,
            provider_used=provider_used,
            fallback_used=fallback_used,
            safety_flags=safety_flags,
            escalation=escalation is not None,
            response_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        screen_id = screen_context.screen_id or "dashboard"
        quick_follow_ups = _PROMPT_ASSEMBLER._get_quick_prompts(screen_id)[:3]

        return MetaChatResponse(
            conversation_id=conversation.id,
            message_id=msg_id,
            content=ai_content,
            safety_flags=safety_flags,
            escalation=escalation,
            provider_used="meto",  # NEVER expose actual provider
            fallback_used=fallback_used,
            quick_follow_ups=quick_follow_ups,
        )


def _get_settings():
    from app.core.config import get_settings
    return get_settings()
