"""Deep insight content for patient-facing detail pages.

Each entry maps insight card_id → rich content used to populate InsightCard
rich fields. Content is educational only; never diagnostic; always includes
disclaimer context.

Language: Vietnamese. Patient audience: 45-70 tuổi.
All strings use:
  - "có thể gợi ý", "có thể liên quan", "nên trao đổi bác sĩ"
  - Never: "bạn bị", "bạn có", "chuẩn đoán"
"""

from __future__ import annotations

from typing import TypedDict


class InsightDetailContent(TypedDict, total=False):
    severity_label: str                # "nhẹ" | "cần chú ý" | "quan trọng" | "cần hành động"
    rationale_vi: str                  # Why flagged
    risk_explanation_vi: str           # Health risks
    daily_actions: list[str]           # 3-5 concrete actions
    doctor_questions: list[str]        # Questions to ask
    red_flags: list[str]               # When to see doctor
    not_to_do: list[str]               # What NOT to do
    derived_markers: list[str]         # relevant derived canonicals
    involved_markers: list[str]        # primary biomarker canonicals
    # v2 fields
    biomarker_explainer_vi: str
    reasoning_steps: list[str]
    related_insights: list[str]
    urgency_label: str       # "routine" | "1_month" | "soon" | "immediately"
    urgency_vi: str
    evidence_level: str      # "strong" | "moderate" | "emerging"
    evidence_label_vi: str


INSIGHT_DETAIL: dict[str, InsightDetailContent] = {
    # ── Lipid panel ─────────────────────────────────────────────────────────────
    "ldl_elevated": {
        "severity_label": "cần chú ý",
        "rationale_vi": (
            "LDL-C (cholesterol xấu) ở mức cao hơn ngưỡng khuyến cáo. "
            "LDL cao là một trong các yếu tố nguy cơ xơ vữa động mạch được nghiên cứu nhiều nhất. "
            "Mức độ ảnh hưởng thực tế phụ thuộc vào tổng thể nguy cơ tim mạch của từng người."
        ),
        "risk_explanation_vi": (
            "LDL cao kéo dài có thể liên quan đến tích tụ mảng bám trong thành động mạch (xơ vữa). "
            "Khi kết hợp với TG cao hoặc HDL thấp, nguy cơ tim mạch có thể tăng đáng kể. "
            "Nếu TG >4.5 mmol/L, chỉ số LDL tính từ công thức Friedewald có thể kém chính xác — "
            "nên đo LDL trực tiếp."
        ),
        "daily_actions": [
            "Ưu tiên chất béo không bão hòa: dầu ô liu, cá hồi, quả bơ, hạt óc chó",
            "Hạn chế thịt đỏ, thực phẩm chiên, đồ ăn nhanh và sản phẩm từ sữa nguyên kem",
            "Ăn nhiều chất xơ hòa tan: yến mạch, đậu, rau xanh, táo",
            "Đi bộ hoặc vận động nhẹ ít nhất 30 phút, 5 ngày/tuần",
            "Không hút thuốc lá — nicotine làm giảm HDL và tổn thương thành mạch",
        ],
        "doctor_questions": [
            "LDL của tôi ở mức này có cần điều trị không, hay chỉ cần thay đổi lối sống?",
            "Tôi có cần tính điểm nguy cơ tim mạch ASCVD không?",
            "Bao lâu thì tôi nên xét nghiệm lại lipid máu?",
            "Nếu TG của tôi cao, LDL tính được có chính xác không?",
        ],
        "red_flags": [
            "Đau ngực, khó thở đột ngột → đến cấp cứu ngay",
            "Tê tay chân một bên, méo miệng, nói khó → gọi cấp cứu ngay (dấu hiệu đột quỵ)",
            "LDL >5.0 mmol/L hoặc có tiền sử gia đình bệnh tim mạch sớm → gặp bác sĩ sớm",
        ],
        "not_to_do": [
            "Không tự ý dùng statin hoặc thực phẩm chức năng hạ cholesterol mà không có chỉ định bác sĩ",
            "Không bỏ bữa để cố hạ mỡ máu nhanh — phản tác dụng",
            "Không tự tăng hoặc giảm liều thuốc nếu đang điều trị",
        ],
        "derived_markers": ["non_hdl_cholesterol", "ldl_hdl_ratio", "tc_hdl_ratio", "ldl_friedewald"],
        "involved_markers": ["ldl", "total_cholesterol", "hdl", "triglyceride"],
        "biomarker_explainer_vi": "LDL-C (Low-Density Lipoprotein Cholesterol) là dạng cholesterol vận chuyển chất béo từ gan đến các mô trong cơ thể. Khi LDL quá cao trong thời gian dài, cholesterol có thể tích tụ trong thành động mạch, tạo thành mảng xơ vữa làm hẹp lòng mạch. LDL thường được gọi là 'cholesterol xấu' — không phải vì nó vô dụng, mà vì khi dư thừa, nó gây hại.",
        "reasoning_steps": [
            "✓ LDL-C vượt ngưỡng khuyến cáo (<3.40 mmol/L theo ACC/AHA)",
            "✓ Non-HDL Cholesterol tính từ TC − HDL cũng tăng theo",
            "✓ HDL chưa đủ bù trừ cho LDL cao",
            "→ Mẫu hình gợi ý tăng cholesterol đơn thuần (hypercholesterolemia)",
            "→ Nguy cơ xơ vữa động mạch tăng khi kéo dài",
        ],
        "related_insights": ["hdl_low", "triglyceride_elevated", "insulin_resistance"],
        "urgency_label": "1_month",
        "urgency_vi": "Tái khám trong vòng 1 tháng",
        "evidence_level": "strong",
        "evidence_label_vi": "Bằng chứng mạnh — Hướng dẫn ACC/AHA 2019",
    },
    "hdl_low": {
        "severity_label": "cần chú ý",
        "rationale_vi": (
            "HDL-C (cholesterol tốt) ở mức thấp hơn ngưỡng bảo vệ tim mạch. "
            "HDL có vai trò vận chuyển cholesterol từ thành mạch về gan để loại bỏ. "
            "HDL thấp thường đi kèm TG cao và có thể là một phần của rối loạn lipid máu sinh xơ vữa."
        ),
        "risk_explanation_vi": (
            "HDL thấp kết hợp TG cao gợi ý tình trạng rối loạn lipid máu sinh xơ vữa, "
            "có thể liên quan đến đề kháng insulin. "
            "Tỷ lệ TG/HDL và Non-HDL cung cấp thêm thông tin về nguy cơ tim mạch tổng thể."
        ),
        "daily_actions": [
            "Vận động aerobic đều đặn: đi bộ nhanh, đạp xe, bơi lội — HDL tăng theo vận động",
            "Ngừng hoặc giảm hút thuốc lá (nicotine làm giảm HDL đáng kể)",
            "Hạn chế carbohydrate tinh chế: bánh mì trắng, cơm trắng quá nhiều, nước ngọt",
            "Bổ sung chất béo lành mạnh: cá béo, hạt chia, dầu ô liu",
            "Kiểm soát cân nặng — giảm cân giúp tăng HDL",
        ],
        "doctor_questions": [
            "HDL thấp của tôi có liên quan đến các chỉ số khác không?",
            "Tôi có dấu hiệu kháng insulin hoặc hội chứng chuyển hóa không?",
            "Lối sống thay đổi bao lâu thì có thể tác động đến HDL?",
        ],
        "red_flags": [
            "HDL <0.9 mmol/L kèm TG >2.3 mmol/L → gặp bác sĩ để đánh giá toàn diện",
            "Các triệu chứng tim mạch: đau ngực, mệt khi gắng sức → khám ngay",
        ],
        "not_to_do": [
            "Không ăn nhiều chất béo bão hòa để cố tăng HDL — sẽ đồng thời tăng LDL",
            "Không dùng niacin liều cao tự ý — có tác dụng phụ nghiêm trọng",
        ],
        "derived_markers": ["tg_hdl_ratio", "non_hdl_cholesterol", "tc_hdl_ratio"],
        "involved_markers": ["hdl", "triglyceride", "total_cholesterol"],
        "biomarker_explainer_vi": "HDL-C (High-Density Lipoprotein Cholesterol) là dạng cholesterol 'tốt' — nó vận chuyển cholesterol dư thừa từ thành mạch trở về gan để loại bỏ. HDL thấp có nghĩa là cơ thể có ít 'người dọn dẹp' hơn cho cholesterol trong mạch máu. HDL thường giảm khi có lối sống ít vận động, hút thuốc, hoặc kháng insulin.",
        "reasoning_steps": [
            "✓ HDL-C thấp hơn ngưỡng bảo vệ (nam <1.0 mmol/L, nữ <1.3 mmol/L)",
            "✓ Tỷ lệ TG/HDL tăng — gợi ý rối loạn lipid máu sinh xơ vữa",
            "✓ Non-HDL tăng khi HDL thấp cùng TC bình thường hoặc cao",
            "→ Mẫu hình HDL thấp thường đi kèm kháng insulin hoặc hội chứng chuyển hóa",
        ],
        "related_insights": ["triglyceride_elevated", "insulin_resistance", "ldl_elevated"],
        "urgency_label": "1_month",
        "urgency_vi": "Tái khám trong vòng 1 tháng",
        "evidence_level": "strong",
        "evidence_label_vi": "Bằng chứng mạnh — Hướng dẫn ESC/EAS 2019",
    },
    "triglyceride_elevated": {
        "severity_label": "cần chú ý",
        "rationale_vi": (
            "Triglyceride (TG) ở mức cao hơn ngưỡng bình thường. "
            "TG là dạng mỡ dự trữ năng lượng trong máu. "
            "TG cao thường liên quan đến chế độ ăn nhiều đường/tinh bột, ít vận động, "
            "hoặc có thể là dấu hiệu của kháng insulin."
        ),
        "risk_explanation_vi": (
            "TG cao kết hợp HDL thấp là mẫu hình lipid đặc trưng của kháng insulin và hội chứng chuyển hóa. "
            "Khi TG ≥4.5 mmol/L, công thức Friedewald tính LDL không còn chính xác. "
            "TG rất cao (>10 mmol/L) có thể gây viêm tụy cấp — cần điều trị y tế."
        ),
        "daily_actions": [
            "Cắt giảm mạnh đường và carbohydrate tinh chế: nước ngọt, bánh kẹo, cơm trắng lượng lớn",
            "Hạn chế rượu bia — alcohol làm tăng TG đáng kể",
            "Đi bộ 10–15 phút sau mỗi bữa ăn giúp giảm đường và TG sau ăn",
            "Ăn cá béo 2–3 lần/tuần (omega-3 giúp hạ TG)",
            "Ưu tiên protein và rau xanh trước khi ăn tinh bột",
        ],
        "doctor_questions": [
            "TG của tôi có liên quan đến đường huyết hoặc kháng insulin không?",
            "Tôi có cần xét nghiệm thêm HbA1c, insulin lúc đói không?",
            "Nếu TG cao, LDL tính được của tôi có đáng tin không?",
            "Mức TG này có cần dùng thuốc không?",
        ],
        "red_flags": [
            "TG >10 mmol/L → nguy cơ viêm tụy cấp, cần đến bác sĩ ngay",
            "Đau bụng dữ dội kèm nôn → đến cấp cứu",
        ],
        "not_to_do": [
            "Không tự ý dùng omega-3 liều cao mà không có chỉ định",
            "Không nhịn ăn dài ngày để cố hạ TG nhanh",
        ],
        "derived_markers": ["tg_hdl_ratio", "tyg_index", "ldl_friedewald", "non_hdl_cholesterol"],
        "involved_markers": ["triglyceride", "hdl", "fasting_glucose"],
        "biomarker_explainer_vi": "Triglyceride (TG) là dạng mỡ chính được cơ thể dự trữ năng lượng. Sau bữa ăn nhiều đường hoặc tinh bột, gan chuyển hóa lượng dư thừa thành TG và đưa vào máu. TG cao thường phản ánh chế độ ăn nhiều carbohydrate tinh chế, ít vận động, hoặc có thể là dấu hiệu sớm của rối loạn chuyển hóa.",
        "reasoning_steps": [
            "✓ Triglyceride vượt ngưỡng bình thường (<1.70 mmol/L)",
            "✓ Khi TG ≥4.5 mmol/L, công thức Friedewald tính LDL không còn chính xác",
            "✓ TG cao kết hợp HDL thấp → tỷ lệ TG/HDL tăng — tín hiệu tầm soát kháng insulin",
            "→ TG rất cao (>10 mmol/L) có nguy cơ viêm tụy cấp — cần điều trị y tế ngay",
        ],
        "related_insights": ["hdl_low", "insulin_resistance", "glucose_elevated"],
        "urgency_label": "1_month",
        "urgency_vi": "Tái khám trong vòng 1 tháng",
        "evidence_level": "strong",
        "evidence_label_vi": "Bằng chứng mạnh — Hướng dẫn AHA/ACC 2018",
    },
    # ── Glucose / Metabolic ──────────────────────────────────────────────────────
    "glucose_elevated": {
        "severity_label": "quan trọng",
        "rationale_vi": (
            "Đường huyết lúc đói cao hơn ngưỡng bình thường (<100 mg/dL). "
            "Mức 100–125 mg/dL được gọi là tiền tiểu đường (Impaired Fasting Glucose). "
            "Mức ≥126 mg/dL trên 2 lần xét nghiệm riêng biệt là tiêu chí chẩn đoán tiểu đường — "
            "cần bác sĩ xác nhận."
        ),
        "risk_explanation_vi": (
            "Đường huyết cao kéo dài có thể gây tổn thương mạch máu nhỏ (mắt, thận, thần kinh) "
            "và mạch máu lớn (tim, não). "
            "Khi kết hợp TG cao và HDL thấp, chỉ số TyG và TG/HDL gợi ý thêm về kháng insulin."
        ),
        "daily_actions": [
            "Ăn rau và protein trước, tinh bột sau mỗi bữa ăn",
            "Đi bộ 10–15 phút sau ăn chính — giúp hạ đường huyết sau ăn hiệu quả",
            "Tránh nước ngọt, nước ép trái cây đóng chai, bánh kẹo",
            "Ngủ đủ 7–8 tiếng — thiếu ngủ làm tăng đường huyết",
            "Đo đường huyết lúc đói định kỳ theo hướng dẫn bác sĩ",
        ],
        "doctor_questions": [
            "Mức đường huyết này có cần xét nghiệm thêm HbA1c không?",
            "Tôi có trong nhóm tiền tiểu đường không? Cần theo dõi như thế nào?",
            "Có cần đo insulin lúc đói hoặc HOMA-IR không?",
            "Tôi có cần gặp chuyên gia dinh dưỡng không?",
        ],
        "red_flags": [
            "Đường huyết ≥200 mg/dL kèm khát nhiều, tiểu nhiều, mệt → gặp bác sĩ ngay",
            "Đường huyết ≥126 mg/dL trong 2 lần xét nghiệm riêng biệt → cần chẩn đoán chính thức",
            "Hạ đường huyết: run rẩy, vã mồ hôi, chóng mặt → ăn ngay 15g đường đơn",
        ],
        "not_to_do": [
            "Không tự ý bắt đầu thuốc tiểu đường mà không có chỉ định bác sĩ",
            "Không nhịn ăn hoàn toàn — có thể gây hạ đường huyết nguy hiểm",
            "Không dùng thực phẩm chức năng hạ đường không rõ nguồn gốc",
        ],
        "derived_markers": ["tyg_index", "tg_hdl_ratio", "metabolic_syndrome"],
        "involved_markers": ["fasting_glucose", "triglyceride", "hdl"],
        "biomarker_explainer_vi": "Glucose máu lúc đói (Fasting Glucose) đo lượng đường trong máu sau ít nhất 8 giờ không ăn. Đây là xét nghiệm cơ bản để tầm soát tiền tiểu đường và tiểu đường. Glucose cao kéo dài làm tổn thương mạch máu và thần kinh — đặc biệt ở mắt, thận và bàn chân.",
        "reasoning_steps": [
            "✓ Glucose lúc đói ≥100 mg/dL (5.6 mmol/L) — vượt ngưỡng bình thường",
            "✓ Mức 100–125 mg/dL: Tiền tiểu đường (Impaired Fasting Glucose) — ADA 2023",
            "✓ Khi kết hợp TG cao + HDL thấp: mẫu hình gợi ý hội chứng chuyển hóa",
            "✓ Chỉ số TyG tăng nếu cả glucose và TG đều cao",
            "→ Cần xét nghiệm HbA1c để đánh giá toàn diện hơn",
        ],
        "related_insights": ["insulin_resistance", "triglyceride_elevated", "hdl_low"],
        "urgency_label": "1_month",
        "urgency_vi": "Xét nghiệm lại và gặp bác sĩ trong 1 tháng",
        "evidence_level": "strong",
        "evidence_label_vi": "Bằng chứng mạnh — ADA Standards of Care 2023",
    },
    "insulin_resistance": {
        "severity_label": "cần chú ý",
        "rationale_vi": (
            "Mẫu hình kết hợp giữa TG cao, HDL thấp và/hoặc chỉ số TyG cao "
            "có thể gợi ý xu hướng kháng insulin. "
            "Đây không phải chẩn đoán — chỉ là tín hiệu tầm soát dựa trên mẫu hình lipid và glucose."
        ),
        "risk_explanation_vi": (
            "Kháng insulin là tình trạng tế bào cơ thể phản ứng kém với insulin, "
            "khiến tuyến tụy phải sản xuất nhiều hơn. "
            "Kéo dài có thể dẫn đến tiền tiểu đường, tiểu đường type 2, và tăng nguy cơ tim mạch. "
            "Tỷ lệ TG/HDL và chỉ số TyG là các chỉ số tầm soát gián tiếp — "
            "không thay thế HOMA-IR hay xét nghiệm insulin máu."
        ),
        "daily_actions": [
            "Giảm đường và carbohydrate tinh chế là bước quan trọng nhất",
            "Đi bộ sau bữa ăn — tế bào cơ hấp thụ glucose không cần insulin khi vận động",
            "Ưu tiên protein và chất béo lành mạnh để ổn định đường huyết sau ăn",
            "Ngủ đủ giấc: thiếu ngủ làm tăng cortisol và kháng insulin",
            "Giảm mỡ bụng nếu vòng eo >90cm (nam) hoặc >80cm (nữ)",
        ],
        "doctor_questions": [
            "Tôi có nên đo HOMA-IR hoặc insulin lúc đói không?",
            "Chỉ số TyG của tôi có ý nghĩa lâm sàng gì với bác sĩ?",
            "Tôi có cần đo HbA1c không?",
            "Có cần đo vòng eo để đánh giá thêm không?",
        ],
        "red_flags": [
            "Đường huyết lúc đói ≥100 mg/dL trong nhiều lần xét nghiệm → gặp bác sĩ",
            "Vòng eo lớn kèm mệt mỏi mãn tính, khó giảm cân → trao đổi với bác sĩ",
        ],
        "not_to_do": [
            "Không tự chẩn đoán kháng insulin chỉ dựa trên chỉ số TyG hoặc TG/HDL",
            "Không tự dùng metformin hoặc berberine mà không có chỉ định",
            "Không bỏ bữa dài ngày — ảnh hưởng xấu đến đường huyết và insulin",
        ],
        "derived_markers": ["tyg_index", "tg_hdl_ratio", "metabolic_syndrome", "non_hdl_cholesterol"],
        "involved_markers": ["fasting_glucose", "triglyceride", "hdl"],
        "biomarker_explainer_vi": "Kháng insulin là tình trạng tế bào cơ thể (cơ, gan, mỡ) không phản ứng tốt với insulin, khiến tụy phải sản xuất nhiều hơn để duy trì đường huyết. Kháng insulin thường không có triệu chứng rõ ràng ở giai đoạn sớm, nhưng được gợi ý qua mẫu hình lipid: TG cao, HDL thấp, và chỉ số TyG tăng.",
        "reasoning_steps": [
            "✓ Chỉ số TyG = ln(TG × Glucose / 2) vượt ngưỡng 9.0",
            "✓ Tỷ lệ TG/HDL tăng — chỉ số tầm soát gián tiếp kháng insulin",
            "✓ Mẫu hình lipid đặc trưng: TG ↑, HDL ↓, glucose ↑ hoặc borderline",
            "→ TyG và TG/HDL là chỉ số tầm soát — không thay thế HOMA-IR hoặc insulin máu",
            "→ Cần bác sĩ xác nhận bằng insulin lúc đói hoặc HOMA-IR",
        ],
        "related_insights": ["glucose_elevated", "triglyceride_elevated", "hdl_low"],
        "urgency_label": "1_month",
        "urgency_vi": "Gặp bác sĩ trong 1 tháng để đánh giá toàn diện",
        "evidence_level": "moderate",
        "evidence_label_vi": "Bằng chứng trung bình — TyG là chỉ số tầm soát, không chẩn đoán",
    },
    # ── Kidney / Liver ───────────────────────────────────────────────────────────
    "creatinine_elevated": {
        "severity_label": "quan trọng",
        "rationale_vi": (
            "Creatinine máu cao hơn ngưỡng bình thường, có thể gợi ý chức năng thận giảm. "
            "Creatinine là sản phẩm chuyển hóa của cơ, được thận lọc và thải ra nước tiểu. "
            "eGFR (mức lọc cầu thận ước tính) cung cấp thông tin đầy đủ hơn về chức năng thận."
        ),
        "risk_explanation_vi": (
            "eGFR <60 mL/min/1.73m² kéo dài ≥3 tháng là tiêu chí bệnh thận mãn tính (CKD). "
            "Bệnh thận tiến triển từ từ và thường không có triệu chứng rõ ràng ở giai đoạn sớm. "
            "Kiểm soát huyết áp, đường huyết, và protein trong nước tiểu là các yếu tố quan trọng."
        ),
        "daily_actions": [
            "Uống đủ nước (1.5–2 lít/ngày) — tránh mất nước",
            "Hạn chế thuốc kháng viêm không kê đơn (NSAID) như ibuprofen, naproxen",
            "Kiểm soát huyết áp nếu có tăng huyết áp",
            "Không ăn quá nhiều protein động vật — tạo gánh nặng cho thận",
            "Khám định kỳ để theo dõi creatinine và eGFR theo thời gian",
        ],
        "doctor_questions": [
            "eGFR của tôi là bao nhiêu và ở giai đoạn nào?",
            "Tôi có cần xét nghiệm protein niệu (urine albumin) không?",
            "Huyết áp của tôi có ảnh hưởng đến thận không?",
            "Những thuốc nào tôi đang dùng có thể gây hại thận?",
        ],
        "red_flags": [
            "Phù chân, phù mắt cá, khó thở → khám thận ngay",
            "Tiểu ít hoặc nước tiểu sẫm màu bất thường → đến bác sĩ",
            "eGFR <30 → cần theo dõi chuyên khoa thận",
        ],
        "not_to_do": [
            "Không tự ý ngừng thuốc huyết áp hoặc tiểu đường khi đang điều trị",
            "Không dùng thực phẩm chức năng hỗ trợ thận không rõ nguồn gốc",
            "Không nhịn nước — mất nước làm tăng creatinine tạm thời",
        ],
        "derived_markers": ["egfr_ckd_epi"],
        "involved_markers": ["creatinine"],
        "biomarker_explainer_vi": "Creatinine là sản phẩm chuyển hóa của cơ bắp, được thận lọc và thải qua nước tiểu. Creatinine tăng gợi ý thận đang lọc kém hơn bình thường. eGFR (Estimated Glomerular Filtration Rate) tính từ creatinine, tuổi và giới tính — cho biết khả năng lọc của thận chính xác hơn.",
        "reasoning_steps": [
            "✓ Creatinine vượt ngưỡng bình thường (nam <106 µmol/L, nữ <90 µmol/L)",
            "✓ eGFR ước tính từ creatinine + tuổi + giới tính (CKD-EPI 2021)",
            "✓ eGFR <60 mL/min/1.73m² kéo dài ≥3 tháng = tiêu chí Bệnh thận mãn tính (CKD)",
            "→ Một lần creatinine tăng cần xác nhận lại — mất nước cũng làm tăng tạm thời",
        ],
        "related_insights": [],
        "urgency_label": "1_month",
        "urgency_vi": "Xét nghiệm lại trong 1 tháng; gặp bác sĩ nếu tăng liên tục",
        "evidence_level": "strong",
        "evidence_label_vi": "Bằng chứng mạnh — KDIGO CKD Guidelines 2022",
    },
    # ── Blood pressure ───────────────────────────────────────────────────────────
    "blood_pressure_elevated": {
        "severity_label": "quan trọng",
        "rationale_vi": (
            "Huyết áp tâm thu ≥130 mmHg hoặc tâm trương ≥80 mmHg được xếp vào nhóm "
            "tăng huyết áp giai đoạn 1 theo ACC/AHA 2017. "
            "Huyết áp đơn lẻ cần được xác nhận qua nhiều lần đo và trong điều kiện nghỉ ngơi."
        ),
        "risk_explanation_vi": (
            "Tăng huyết áp kéo dài làm tổn thương thành mạch, tăng gánh nặng cho tim và thận. "
            "Là yếu tố nguy cơ chính của đột quỵ và nhồi máu cơ tim. "
            "Khi kết hợp với cholesterol cao hoặc đường huyết cao, nguy cơ tích lũy đáng kể."
        ),
        "daily_actions": [
            "Giảm muối: <5g/ngày (khoảng 1 thìa cà phê) — đọc nhãn thực phẩm đóng gói",
            "Tăng kali: chuối, rau bina, khoai lang, đậu",
            "Hạn chế rượu bia nghiêm ngặt",
            "Vận động đều đặn: 30 phút mỗi ngày, ưu tiên đi bộ hoặc bơi",
            "Quản lý căng thẳng: thiền, yoga nhẹ, ngủ đủ giấc",
        ],
        "doctor_questions": [
            "Tôi cần đo huyết áp bao nhiêu lần để xác nhận?",
            "Tôi có cần điều trị bằng thuốc không hay chỉ thay đổi lối sống?",
            "Huyết áp của tôi có ảnh hưởng đến thận hoặc tim không?",
        ],
        "red_flags": [
            "Huyết áp ≥180/120 mmHg → đến cấp cứu ngay (crisis tăng huyết áp)",
            "Đau đầu dữ dội kèm nhìn mờ, đau ngực → gọi cấp cứu",
            "Tê liệt, nói khó đột ngột → dấu hiệu đột quỵ, gọi ngay 115",
        ],
        "not_to_do": [
            "Không tự ý ngừng thuốc huyết áp — nguy hiểm tính mạng",
            "Không dùng thuốc người khác kê",
            "Không dùng thuốc cảm/dị ứng không kê đơn khi chưa hỏi bác sĩ (có thể tăng HA)",
        ],
        "derived_markers": ["metabolic_syndrome"],
        "involved_markers": ["systolic_bp", "diastolic_bp"],
        "biomarker_explainer_vi": "Huyết áp đo lực máu tác động lên thành động mạch khi tim bơm máu. Huyết áp tâm thu (số trên) phản ánh lực khi tim co bóp. Huyết áp tâm trương (số dưới) phản ánh lực khi tim nghỉ. Tăng huyết áp thường không có triệu chứng — được gọi là 'kẻ giết người thầm lặng'.",
        "reasoning_steps": [
            "✓ Huyết áp tâm thu ≥130 mmHg hoặc tâm trương ≥80 mmHg — Tăng HA Giai đoạn 1 (ACC/AHA 2017)",
            "✓ Cần đo lại nhiều lần ở trạng thái nghỉ để xác nhận",
            "✓ Khi kết hợp TG cao, HDL thấp, glucose cao → nguy cơ tim mạch tích lũy",
            "→ Huyết áp đơn lẻ một lần không đủ để chẩn đoán — cần theo dõi xu hướng",
        ],
        "related_insights": [],
        "urgency_label": "1_month",
        "urgency_vi": "Đo lại và gặp bác sĩ trong 1 tháng",
        "evidence_level": "strong",
        "evidence_label_vi": "Bằng chứng mạnh — ACC/AHA Hypertension Guidelines 2017",
    },
    # ── Liver ────────────────────────────────────────────────────────────────────
    "ast_elevated": {
        "severity_label": "cần chú ý",
        "rationale_vi": (
            "AST (Aspartate Aminotransferase) tăng có thể gợi ý tổn thương tế bào gan hoặc cơ. "
            "AST không đặc hiệu cho gan như ALT — cần xem xét cả hai cùng nhau."
        ),
        "risk_explanation_vi": (
            "AST tăng nhẹ (<3 lần giới hạn trên) thường gặp do mệt cơ sau tập luyện nặng, "
            "uống rượu, hoặc bệnh gan nhiễm mỡ không do rượu (NAFLD). "
            "AST tăng nhiều lần cần loại trừ viêm gan, xơ gan, hoặc nhồi máu cơ tim."
        ),
        "daily_actions": [
            "Hạn chế hoặc ngừng rượu bia",
            "Kiểm soát cân nặng — gan nhiễm mỡ cải thiện rõ khi giảm 5-10% cân nặng",
            "Tránh paracetamol liều cao hoặc kéo dài",
            "Ăn nhiều rau xanh, hạn chế đường và thực phẩm chế biến sẵn",
        ],
        "doctor_questions": [
            "AST tăng của tôi có liên quan đến gan hay cơ không?",
            "Tôi có cần siêu âm bụng không?",
            "Có thuốc nào tôi đang dùng có thể gây tăng AST không?",
        ],
        "red_flags": [
            "Vàng da, mắt vàng, nước tiểu sẫm → khám gan ngay",
            "Đau bụng phải dữ dội kèm sốt → đến cơ sở y tế",
            "AST >10 lần giới hạn trên → cần đánh giá y tế khẩn",
        ],
        "not_to_do": [
            "Không tự ý dùng thực phẩm chức năng 'giải độc gan' — có thể gây hại thêm",
            "Không ngừng đột ngột thuốc đang dùng mà không hỏi bác sĩ",
        ],
        "derived_markers": ["fib4_score"],
        "involved_markers": ["ast", "alt"],
        "biomarker_explainer_vi": "AST (Aspartate Aminotransferase) là enzyme có trong tế bào gan, cơ tim và cơ xương. Khi tế bào bị tổn thương, AST rò rỉ vào máu và nồng độ tăng cao. AST không đặc hiệu cho gan như ALT — cần xem AST cùng với ALT để xác định nguồn gốc.",
        "reasoning_steps": [
            "✓ AST vượt giới hạn trên bình thường (ULN)",
            "✓ AST ít đặc hiệu hơn ALT cho gan — cần xét AST/ALT ratio",
            "✓ AST/ALT >2: gợi ý tổn thương do rượu. AST/ALT <1: gợi ý gan nhiễm mỡ không do rượu",
            "→ Mệt cơ sau tập luyện nặng cũng làm AST tăng — cần loại trừ",
        ],
        "related_insights": ["alt_elevated"],
        "urgency_label": "1_month",
        "urgency_vi": "Gặp bác sĩ trong 1 tháng để đánh giá nguyên nhân",
        "evidence_level": "moderate",
        "evidence_label_vi": "Bằng chứng trung bình — cần kết hợp ALT và siêu âm",
    },
    "alt_elevated": {
        "severity_label": "cần chú ý",
        "rationale_vi": (
            "ALT (Alanine Aminotransferase) tăng là chỉ báo nhạy cảm hơn cho tổn thương tế bào gan so với AST. "
            "ALT tăng thường gặp trong gan nhiễm mỡ, viêm gan, hoặc do thuốc."
        ),
        "risk_explanation_vi": (
            "ALT tăng nhẹ đến vừa (<5 lần giới hạn trên) thường do gan nhiễm mỡ, rượu, "
            "hoặc thuốc. Cần theo dõi xu hướng và kết hợp với siêu âm gan."
        ),
        "daily_actions": [
            "Không uống rượu bia trong thời gian theo dõi",
            "Giảm cân từ từ nếu thừa cân (không nhịn ăn đột ngột)",
            "Tránh thuốc và thực phẩm bổ sung không cần thiết",
            "Vận động nhẹ đều đặn",
        ],
        "doctor_questions": [
            "Tôi có cần xét nghiệm viêm gan B, C không?",
            "ALT tăng của tôi có liên quan thuốc đang dùng không?",
            "Tôi có cần siêu âm gan không?",
        ],
        "red_flags": [
            "Vàng da, mệt nhiều, chán ăn → khám ngay",
            "ALT >5 lần giới hạn trên → đánh giá y tế khẩn",
        ],
        "not_to_do": [
            "Không tự dùng thực phẩm chức năng gan khi chưa biết nguyên nhân",
            "Không uống paracetamol liều cao khi ALT đang cao",
        ],
        "derived_markers": ["fib4_score"],
        "involved_markers": ["alt", "ast"],
        "biomarker_explainer_vi": "ALT (Alanine Aminotransferase) là enzyme đặc hiệu hơn cho tế bào gan so với AST. ALT tăng là dấu hiệu thường gặp đầu tiên của tổn thương gan. Nguyên nhân phổ biến nhất: gan nhiễm mỡ (NAFLD), uống rượu, hoặc do thuốc.",
        "reasoning_steps": [
            "✓ ALT vượt giới hạn trên bình thường (ULN)",
            "✓ ALT đặc hiệu hơn AST cho tổn thương tế bào gan",
            "✓ ALT tăng nhẹ (<3× ULN): thường do gan nhiễm mỡ, rượu, hoặc thuốc",
            "✓ ALT tăng kết hợp TG cao: mẫu hình gan nhiễm mỡ chuyển hóa (MAFLD)",
            "→ Cần loại trừ viêm gan B, C bằng xét nghiệm huyết thanh học",
        ],
        "related_insights": ["ast_elevated"],
        "urgency_label": "1_month",
        "urgency_vi": "Gặp bác sĩ trong 1 tháng",
        "evidence_level": "moderate",
        "evidence_label_vi": "Bằng chứng trung bình — EASL NAFLD Guidelines 2021",
    },
}

def get_insight_detail(card_id: str) -> InsightDetailContent | None:
    """Look up deep content for a given card_id. Returns None if not found."""
    return INSIGHT_DETAIL.get(card_id)
