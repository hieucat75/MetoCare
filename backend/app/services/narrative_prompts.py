"""Prompt Registry for Medical Narrative Layer.

All prompts are versioned. Never hardcode prompts in business logic.
Supports future A/B testing and localization.
"""
from __future__ import annotations

from dataclasses import dataclass

ENGINE_VERSION = "v4"  # bump when E1–E20 logic changes
PROMPT_VERSION = "v1"  # bump when prompts change

_SYSTEM_PROMPT_VI = """\
Bạn là trợ lý sức khỏe của MetoCare. Nhiệm vụ của bạn là chuyển đổi kết quả phân tích lâm sàng thành lời giải thích thân thiện, cá nhân hóa cho bệnh nhân người Việt Nam.

QUY TẮC TUYỆT ĐỐI — Vi phạm bất kỳ quy tắc nào dẫn đến từ chối phản hồi:
1. KHÔNG được thay đổi, mâu thuẫn, hoặc đặt lại bất kỳ giá trị xét nghiệm nào đã cung cấp.
2. KHÔNG được thay đổi mức độ nghiêm trọng (severity) hoặc thứ tự ưu tiên (priority) đã phân loại.
3. KHÔNG được đặt chẩn đoán bệnh.
4. KHÔNG được đề nghị bắt đầu, thay đổi, hoặc dừng thuốc.
5. KHÔNG được dùng ngôn ngữ gây hoảng loạn nếu severity không phải urgent/critical.
6. KHÔNG được nói "bình thường" nếu bất kỳ chỉ số nào ở trạng thái high/borderline.
7. Luôn dùng ngôn ngữ: "có thể gợi ý", "nên trao đổi với bác sĩ", "đáng theo dõi".
8. Tone: ấm áp, bình tĩnh, khích lệ, không phán xét.
9. KHÔNG được bịa thêm thông tin không có trong JSON được cung cấp.
10. Luôn kết thúc bằng disclaimer: "Giải thích này chỉ hỗ trợ hiểu thông tin sức khỏe, không thay thế đánh giá, chẩn đoán hoặc điều trị từ chuyên gia y tế."\
"""

_MEDICAL_SAFETY_NOTES_VI = """\
- Không thay đổi hoặc mâu thuẫn với dữ liệu lâm sàng đã cung cấp
- Không đặt chẩn đoán, không tư vấn thuốc
- Không tạo ra con số xét nghiệm không có trong nguồn
- Không dùng ngôn ngữ hoảng loạn cho trạng thái không nguy cấp
- Luôn đưa ra disclaimer ở section_10\
"""

_USER_TEMPLATE_VI = """\
Dưới đây là kết quả phân tích sức khỏe của bệnh nhân từ hệ thống Rule Engine MetoCare:

```json
{report_json}
```

Dựa trên dữ liệu trên, hãy tạo giải thích cá nhân hóa cho bệnh nhân. Trả về JSON với ĐÚNG 10 khóa sau (không thêm, không bớt):

{{
  "section_1_summary": "Một đoạn tổng quan ngắn gọn (3-5 câu) về tình trạng sức khỏe hiện tại theo phân tích AI.",
  "section_2_what_happened": "Giải thích điều gì đang xảy ra với các chỉ số, tại sao chúng quan trọng (3-5 câu, ngôn ngữ dễ hiểu).",
  "section_3_reasoning": "Mô tả cách AI đã suy luận từ các chỉ số để đưa ra nhận định (2-4 câu).",
  "section_4_personal_context": "Điều này có ý nghĩa gì với riêng bệnh nhân, liên hệ với lối sống và mục tiêu sức khỏe (2-4 câu).",
  "section_5_if_nothing_changes": "Nếu không có thay đổi gì, điều gì có thể xảy ra về lâu dài (2-3 câu, không gây hoảng loạn).",
  "section_6_most_important_today": "Một việc quan trọng nhất bệnh nhân nên làm hôm nay hoặc tuần này (1-2 câu cụ thể).",
  "section_7_monthly_plan": ["Mục tiêu hàng tháng 1 (cụ thể, thực hiện được)", "Mục tiêu hàng tháng 2", "Mục tiêu hàng tháng 3"],
  "section_8_what_ai_doesnt_know": ["Thông tin còn thiếu mà AI chưa có 1", "Thông tin còn thiếu 2"],
  "section_9_doctor_questions": ["Câu hỏi nên hỏi bác sĩ 1", "Câu hỏi nên hỏi bác sĩ 2", "Câu hỏi nên hỏi bác sĩ 3"],
  "section_10_disclaimer": "Giải thích này chỉ hỗ trợ hiểu thông tin sức khỏe, không thay thế đánh giá, chẩn đoán hoặc điều trị từ chuyên gia y tế."
}}

Chỉ trả về JSON hợp lệ. Không thêm bất kỳ văn bản nào ngoài JSON.\
"""


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    language: str        # "vi"
    purpose: str         # "full_report_narrative"
    provider: str        # "anthropic"
    system_prompt: str
    user_template: str   # format string; receives {report_json}
    medical_safety_notes: str


class PromptRegistry:
    _registry: dict[str, PromptTemplate] = {}

    @classmethod
    def register(cls, template: PromptTemplate) -> None:
        key = f"{template.version}:{template.language}"
        cls._registry[key] = template

    @classmethod
    def get(cls, version: str = PROMPT_VERSION, language: str = "vi") -> PromptTemplate:
        key = f"{version}:{language}"
        template = cls._registry.get(key)
        if template is None:
            raise KeyError(f"No prompt registered for version={version!r}, language={language!r}")
        return template

    @classmethod
    def current(cls) -> PromptTemplate:
        return cls.get(version=PROMPT_VERSION, language="vi")


# ---------------------------------------------------------------------------
# Register default prompt at module load
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE = PromptTemplate(
    version=PROMPT_VERSION,
    language="vi",
    purpose="full_report_narrative",
    provider="anthropic",
    system_prompt=_SYSTEM_PROMPT_VI,
    user_template=_USER_TEMPLATE_VI,
    medical_safety_notes=_MEDICAL_SAFETY_NOTES_VI,
)

PromptRegistry.register(_DEFAULT_TEMPLATE)
