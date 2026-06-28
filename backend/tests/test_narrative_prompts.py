"""Tests for narrative_prompts.py"""
from __future__ import annotations

import pytest
from app.services.narrative_prompts import (
    ENGINE_VERSION,
    PROMPT_VERSION,
    PromptRegistry,
    PromptTemplate,
)


class TestVersionConstants:
    def test_engine_version_is_string(self):
        assert isinstance(ENGINE_VERSION, str)
        assert len(ENGINE_VERSION) > 0

    def test_prompt_version_is_string(self):
        assert isinstance(PROMPT_VERSION, str)
        assert len(PROMPT_VERSION) > 0

    def test_engine_version_format(self):
        # Should start with 'v'
        assert ENGINE_VERSION.startswith("v")

    def test_prompt_version_format(self):
        assert PROMPT_VERSION.startswith("v")


class TestRegistryGetDefault:
    def test_current_returns_template(self):
        template = PromptRegistry.current()
        assert isinstance(template, PromptTemplate)

    def test_get_default_version(self):
        template = PromptRegistry.get(version=PROMPT_VERSION, language="vi")
        assert template is not None
        assert isinstance(template, PromptTemplate)

    def test_get_unknown_version_raises(self):
        with pytest.raises(KeyError):
            PromptRegistry.get(version="v999", language="vi")

    def test_register_and_get(self):
        custom = PromptTemplate(
            version="test_v99",
            language="vi",
            purpose="test",
            provider="anthropic",
            system_prompt="Test system",
            user_template="Test {report_json}",
            medical_safety_notes="Test safety",
        )
        PromptRegistry.register(custom)
        retrieved = PromptRegistry.get(version="test_v99", language="vi")
        assert retrieved.version == "test_v99"
        assert retrieved.purpose == "test"


class TestTemplateFields:
    def test_template_has_all_required_fields(self):
        template = PromptRegistry.current()
        assert template.version
        assert template.language
        assert template.purpose
        assert template.provider
        assert template.system_prompt
        assert template.user_template
        assert template.medical_safety_notes

    def test_template_language_is_vi(self):
        template = PromptRegistry.current()
        assert template.language == "vi"

    def test_template_provider_is_anthropic(self):
        template = PromptRegistry.current()
        assert template.provider == "anthropic"

    def test_template_purpose(self):
        template = PromptRegistry.current()
        assert template.purpose == "full_report_narrative"

    def test_template_is_frozen(self):
        template = PromptRegistry.current()
        with pytest.raises((AttributeError, TypeError)):
            template.version = "changed"  # type: ignore[misc]


class TestUserTemplate:
    def test_user_template_has_report_json_placeholder(self):
        template = PromptRegistry.current()
        assert "{report_json}" in template.user_template

    def test_user_template_can_be_formatted(self):
        template = PromptRegistry.current()
        # Should not raise
        formatted = template.user_template.format(report_json='{"test": true}')
        assert '{"test": true}' in formatted

    def test_system_prompt_has_safety_rules(self):
        template = PromptRegistry.current()
        # Check for key Vietnamese safety rule phrases
        assert "KHÔNG được" in template.system_prompt
        assert "chẩn đoán" in template.system_prompt

    def test_system_prompt_has_10_rules(self):
        template = PromptRegistry.current()
        # Numbered rules 1-10
        for i in range(1, 11):
            assert str(i) + "." in template.system_prompt

    def test_user_template_requests_10_sections(self):
        template = PromptRegistry.current()
        # Should reference the 10 section keys
        assert "section_1_summary" in template.user_template
        assert "section_10_disclaimer" in template.user_template
