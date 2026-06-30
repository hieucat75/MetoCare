# Meto AI — Multimodal Intelligence Layer

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
> **Phase:** 3 — Clinical Intelligence

---

## Tổng quan

Multimodal Intelligence Layer cho phép Meto xử lý nhiều loại đầu vào khác nhau ngoài text — hình ảnh, tài liệu, giọng nói, và trong tương lai là dữ liệu từ thiết bị đeo. Mọi pipeline đều có confidence scoring, fallback graceful, và tuyệt đối tuân thủ privacy policy.

**File backend:**
- `app/ai/multimodal/` — Multimodal core modules
- `app/ai/multimodal/ocr.py` — OCR pipeline
- `app/ai/multimodal/image_understanding.py` — Image analysis
- `app/ai/multimodal/voice.py` — Speech pipeline
- `app/ai/multimodal/document.py` — Document pipeline
- `app/ai/multimodal/wearable.py` — Future wearable integration

---

## 1. Multimodal Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                  MULTIMODAL INTELLIGENCE LAYER                        │
│                                                                      │
│  INPUT CHANNELS                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Camera   │  │ Document │  │ Voice    │  │ Wearable │           │
│  │ / Image  │  │ / PDF    │  │ / Audio  │  │ (future) │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       └─────────────┴──────────────┴─────────────┘                  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  MODALITY ROUTER                                              │  │
│  │  Detect input type → Route to correct pipeline               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│          ┌───────────────────┼───────────────────────┐             │
│          ▼                   ▼                        ▼             │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────────┐    │
│  │  OCR PIPELINE  │  │  IMAGE       │  │  VOICE PIPELINE     │    │
│  │  ├─ Lab PDF    │  │  PIPELINE    │  │  ├─ STT (VI ASR)    │    │
│  │  ├─ Rx parser  │  │  ├─ Skin     │  │  ├─ TTS response    │    │
│  │  ├─ Structured │  │  ├─ Wound    │  │  ├─ Voice quality   │    │
│  │  │  output     │  │  ├─ Nutrition│  │  └─ Fallback        │    │
│  │  └─ User confirm│  │  ├─ Barcode │  └─────────────────────┘    │
│  └────────────────┘  │  └─ Document│                               │
│                       └──────────────┘                              │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  QUALITY SCORER                                               │  │
│  │  Per-modality confidence threshold                            │  │
│  │  Low confidence → Fallback UX (ask user to re-submit)        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  OUTPUT → Structured Data → Context Engine → CRL / RE         │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. OCR Pipeline

### 2.1 Lab Report Parsing — PDF & Image

```python
@dataclass
class OCRPipelineConfig:
    supported_formats: list[str] = field(
        default_factory=lambda: ["jpg", "jpeg", "png", "heic", "pdf", "tiff"]
    )
    max_file_size_mb: int = 20
    min_confidence_threshold: float = 0.70
    enable_preprocessing: bool = True    # Deskew, denoise, contrast enhance
    language: str = "vi+en"             # Tesseract language code

class LabReportOCRPipeline:

    async def process(self, file: UploadedFile, user_id: str) -> OCRResult:
        """
        Full pipeline: preprocess → OCR → parse → validate → structure
        """
        # Step 1: Preprocess
        processed_image = await self._preprocess(file)

        # Step 2: OCR (Provider-agnostic via ProviderAbstractionLayer)
        raw_text = await self.vision_provider.extract_text(
            image=processed_image,
            language="vi+en",
            mode="document"
        )

        # Step 3: Detect document type
        doc_type = await self._detect_document_type(raw_text)

        # Step 4: Route to appropriate parser
        parser = self._get_parser(doc_type)
        parsed = await parser.parse(raw_text)

        # Step 5: Validate parsed fields
        validated = await self._validate_parsed_fields(parsed)

        # Step 6: Compute per-field confidence
        confident_fields = [f for f in validated.fields if f.confidence >= 0.70]
        low_confidence_fields = [f for f in validated.fields if f.confidence < 0.70]

        return OCRResult(
            document_type=doc_type,
            raw_text=raw_text,
            parsed_fields=confident_fields,
            uncertain_fields=low_confidence_fields,
            overall_confidence=self._compute_overall_confidence(validated),
            needs_user_review=len(low_confidence_fields) > 0
        )

    async def _preprocess(self, file: UploadedFile) -> ProcessedImage:
        """Image preprocessing to improve OCR accuracy"""
        steps = [
            ImagePreprocessor.deskew,         # Fix rotation
            ImagePreprocessor.denoise,         # Remove noise
            ImagePreprocessor.enhance_contrast, # Improve text visibility
            ImagePreprocessor.to_grayscale,    # Grayscale for OCR
        ]
        image = await file.to_image()
        for step in steps:
            image = await step(image)
        return ProcessedImage(data=image, original_format=file.content_type)

    def _get_parser(self, doc_type: str) -> DocumentParser:
        PARSERS = {
            "lab_result": LabResultParser(),
            "prescription": PrescriptionParser(),
            "lab_result_pdf": LabResultPDFParser(),
            "handwritten_lab": HandwrittenLabParser(),
            "unknown": GenericDocumentParser(),
        }
        return PARSERS.get(doc_type, GenericDocumentParser())
```

### 2.2 Lab Result Parser

```python
class LabResultParser:
    """
    Parse lab report text into structured LabResult objects.
    Vietnamese hospital formats supported.
    """

    # Common VN hospital lab result patterns
    VN_LAB_PATTERNS = {
        "section_header": r"(XÉT NGHIỆM|KẾT QUẢ XÉT NGHIỆM|LAB RESULTS?)",
        "test_line": r"([A-Za-zÀ-ỹ\s\(\)\/]+)\s*:?\s*([\d.,]+)\s*([µmgLdlIUmEq%]+)\s*([\d.,\-]+)?",
        "reference_range": r"([\d.,]+)\s*[-–]\s*([\d.,]+)|(<\s*[\d.,]+)|(>\s*[\d.,]+)",
        "abnormal_flag": r"[HLhñ↑↓\*]",
        "date_collected": r"(Ngày xét nghiệm|Ngày lấy mẫu|Ngày thu thập)\s*:?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
        "ordered_by": r"(Bác sĩ chỉ định|Người chỉ định)\s*:?\s*(.+?)(?:\n|$)",
        "patient_name": r"(Họ và tên|Tên bệnh nhân)\s*:?\s*(.+?)(?:\n|$)",
    }

    async def parse(self, raw_text: str) -> ParsedDocument:
        fields = []

        # Extract test lines
        for match in re.finditer(self.VN_LAB_PATTERNS["test_line"], raw_text):
            analyte_raw = match.group(1).strip()
            value_raw = match.group(2).strip()
            unit_raw = match.group(3).strip() if match.group(3) else None

            # Normalize analyte name
            analyte_canonical = analyte_resolver.resolve(analyte_raw)

            # Parse value
            try:
                value = float(value_raw.replace(",", "."))
            except ValueError:
                value = None

            # Compute confidence
            confidence = self._compute_field_confidence(
                analyte_raw=analyte_raw,
                analyte_canonical=analyte_canonical,
                value_raw=value_raw,
                unit_raw=unit_raw
            )

            fields.append(ParsedField(
                original_text=match.group(0),
                field_name="lab_result",
                analyte_raw=analyte_raw,
                analyte_canonical=analyte_canonical,
                value=value,
                unit=unit_raw,
                confidence=confidence,
                needs_review=analyte_canonical is None or value is None
            ))

        return ParsedDocument(
            document_type="lab_result",
            fields=fields,
            metadata=self._extract_metadata(raw_text)
        )

    def _compute_field_confidence(
        self,
        analyte_raw: str,
        analyte_canonical: str | None,
        value_raw: str,
        unit_raw: str | None
    ) -> float:
        score = 0.5
        if analyte_canonical:
            score += 0.25   # Known analyte
        if value_raw and value_raw.replace(".", "").replace(",", "").isdigit():
            score += 0.15   # Valid numeric value
        if unit_raw:
            score += 0.10   # Unit present
        return min(1.0, score)
```

### 2.3 Prescription Parser

```python
class PrescriptionParser:
    """
    Parse prescription text for medication information.
    Privacy note: prescriptions contain PHI — handle with extra care.
    Only extract: drug name, strength (general). NOT dosing instructions.
    """

    VN_RX_PATTERNS = {
        "drug_line": r"^\d+\.\s+(.+?)(?:\s+\d+[\w/]*)?(?:\s+\d+\s+(?:viên|hộp|lọ))?",
        "doctor_name": r"Bác sĩ\s*:?\s*(.+?)(?:\n|$)",
        "rx_date": r"Ngày\s*(?:kê đơn|kê toa)?\s*:?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
    }

    EXTRACTION_SCOPE = {
        "extract": ["drug_name_raw", "drug_strength_general", "rx_date"],
        "do_not_extract": [
            "specific_dosing_instructions",  # "Uống 1 viên 3 lần/ngày" → NOT extracted
            "dose_adjustment_notes",
            "duration_in_days",              # Clinical decision
        ]
    }
```

### 2.4 Handwritten Document Handling

```python
class HandwrittenLabParser:
    """
    Handwritten lab results are common in VN rural settings.
    Lower confidence expected — always flag for user review.
    """

    HANDWRITTEN_CONFIDENCE_PENALTY = 0.20  # Subtract from all field confidences

    async def parse(self, raw_text: str) -> ParsedDocument:
        # Use parent parser
        result = await LabResultParser().parse(raw_text)

        # Apply penalty
        for field in result.fields:
            field.confidence = max(0.0, field.confidence - self.HANDWRITTEN_CONFIDENCE_PENALTY)
            field.needs_review = True  # Always review handwritten

        result.metadata["handwritten"] = True
        result.metadata["auto_review_required"] = True

        return result
```

### 2.5 Confidence Scoring per Parsed Field

```python
@dataclass
class ParsedField:
    original_text: str
    field_name: str
    analyte_raw: str | None
    analyte_canonical: str | None       # None if unrecognized
    value: float | None                 # None if unparseable
    unit: str | None
    reference_low: float | None
    reference_high: float | None
    abnormal_flag: str | None           # "H", "L", "*"
    confidence: float                   # 0.0-1.0
    needs_review: bool                  # Show to user for confirmation?
    correction_applied: bool = False    # User corrected this field?
    user_corrected_value: float | None = None

CONFIDENCE_THRESHOLDS = {
    "auto_accept": 0.90,               # Accept without user review
    "suggest_review": 0.70,            # Show to user with highlight
    "require_review": 0.50,            # Cannot proceed without user confirmation
    "reject": 0.30,                    # Too low — ask user to re-upload
}
```

### 2.6 User Correction Workflow

```
OCR PIPELINE RESULT
        │
        ▼
[Compute overall_confidence]
        │
        ├── ≥ 0.90 ──────────────────────▶ AUTO-ACCEPT → Store → Feed to CRL
        │
        ├── 0.70–0.89 ─────────────────────▶ SHOW REVIEW SCREEN
        │                                    User reviews uncertain fields
        │                                    User corrects or confirms
        │                                    Store with is_user_confirmed=True
        │
        ├── 0.50–0.69 ─────────────────────▶ REQUIRED REVIEW SCREEN
        │                                    Block proceeding until user confirms all
        │                                    highlighted fields
        │
        └── < 0.50 ─────────────────────────▶ REJECT with UX message:
                                             "Meto không đọc được kết quả này rõ ràng.
                                              Thử chụp lại với ánh sáng tốt hơn,
                                              hoặc nhập thủ công."

USER CORRECTION SCREEN:
┌───────────────────────────────────────────────────┐
│  📋 Meto đọc được kết quả sau. Vui lòng kiểm tra │
│                                                    │
│  HbA1c:    [7.8] %    ← Low confidence → HIGHLIGHT│
│  Glucose:  [145] mg/dL ← OK                       │
│  Cholesterol: [??] — Không đọc được → INPUT BOX   │
│                                                    │
│  [✓ Xác nhận tất cả]  [Nhập lại thủ công]        │
└───────────────────────────────────────────────────┘
```

### 2.7 Structured Output Schema

```python
@dataclass
class StructuredLabResult:
    """Final output after OCR + user confirmation"""
    source: str                        # "ocr_pdf" | "ocr_image" | "manual_entry"
    document_id: str                   # UUID for traceability
    is_user_confirmed: bool
    collected_date: date | None
    facility_name: str | None          # Hospital/lab name if extracted
    ordered_by: str | None

    lab_values: list[StructuredLabValue]
    ocr_confidence: float              # Overall OCR confidence
    version: str                       # "1.0"

@dataclass
class StructuredLabValue:
    analyte: str                       # Canonical name
    value: float
    unit: str
    reference_low: float | None
    reference_high: float | None
    abnormal_flag: str | None
    is_user_confirmed: bool
    confidence: float
```

---

## 3. Image Understanding Pipeline

### 3.1 Modality Router

```python
class ImageModalityRouter:

    SUPPORTED_TYPES = {
        "skin_image": {
            "detection_cues": ["rash", "skin", "lesion", "mole", "wound_surface"],
            "pipeline": "SkinImagePipeline",
            "safety": "DESCRIBE_ONLY_ESCALATE_IF_CONCERNED",
        },
        "wound_image": {
            "detection_cues": ["wound", "cut", "bruise", "swelling"],
            "pipeline": "WoundImagePipeline",
            "safety": "DESCRIBE_AND_ASSESS_HEALING",
        },
        "nutrition_photo": {
            "detection_cues": ["food", "meal", "plate", "dish"],
            "pipeline": "NutritionPhotoPipeline",
            "safety": "NUTRITION_ESTIMATION_ONLY",
        },
        "medication_barcode": {
            "detection_cues": ["barcode", "medication_package"],
            "pipeline": "BarcodePipeline",
            "safety": "DRUG_LOOKUP_ONLY",
        },
        "document_scan": {
            "detection_cues": ["id_card", "insurance_card", "document"],
            "pipeline": "DocumentScanPipeline",
            "safety": "CONSENT_REQUIRED",
        },
        "lab_report": {
            "detection_cues": ["lab_results", "blood_test", "xet_nghiem"],
            "pipeline": "LabReportOCRPipeline",
            "safety": "STANDARD_OCR",
        },
    }

    async def route(self, image: UploadedImage, user_context: dict) -> RoutingDecision:
        # Use vision model to detect image type
        detected_type = await self.vision_provider.classify_image_type(
            image=image,
            categories=list(self.SUPPORTED_TYPES.keys())
        )
        return RoutingDecision(
            image_type=detected_type.type,
            pipeline=self.SUPPORTED_TYPES[detected_type.type]["pipeline"],
            safety_policy=self.SUPPORTED_TYPES[detected_type.type]["safety"],
            confidence=detected_type.confidence
        )
```

### 3.2 Skin Image Pipeline

```python
class SkinImagePipeline:
    """
    Mô tả quan sát về da — KHÔNG chẩn đoán, KHÔNG phân loại ác tính.
    """

    OBSERVATION_ONLY_POLICY = """
    Mô tả những gì quan sát thấy về màu sắc, kích thước ước tính,
    hình dạng, bờ, và mức độ rõ ràng của hình ảnh.
    KHÔNG nhận định về tính lành hay ác tính.
    KHÔNG đưa ra chẩn đoán da liễu.
    KHÔNG so sánh với bất kỳ bệnh lý cụ thể.
    Nếu bất kỳ đặc điểm nào đáng lo ngại → escalate.
    """

    CONCERNING_FEATURES = [
        "asymmetry",               # Bất đối xứng
        "irregular_border",        # Bờ không đều
        "multiple_colors",         # Nhiều màu
        "diameter_large",          # Đường kính > ~6mm
        "evolving_appearance",     # Thay đổi theo thời gian (nếu user mô tả)
        "bleeding",                # Chảy máu
        "ulceration",              # Loét
    ]

    async def process(self, image: UploadedImage) -> SkinObservation:
        # Check image quality first
        quality = await self._assess_image_quality(image)
        if quality.score < 0.5:
            return SkinObservation(
                quality_too_low=True,
                message="Hình ảnh chưa đủ rõ để Meto mô tả. "
                        "Thử chụp lại với ánh sáng tốt hơn và gần hơn."
            )

        # Get visual description from VisionProvider
        description = await self.vision_provider.describe_image(
            image=image,
            system_prompt=self.OBSERVATION_ONLY_POLICY,
            max_tokens=300
        )

        # Check for concerning features
        concerns = await self._detect_concerning_features(description.text)
        escalation_needed = len(concerns) > 0

        return SkinObservation(
            description=description.text,
            confidence=description.confidence,
            concerning_features=concerns,
            escalation_recommended=escalation_needed,
            response=(
                f"Meto mô tả những gì quan sát được trong hình:\n{description.text}\n\n"
                + (
                    "⚠️ Một số đặc điểm trong hình cần được bác sĩ da liễu đánh giá trực tiếp. "
                    "Hình ảnh không đủ để đánh giá qua chat."
                    if escalation_needed else
                    "Nếu đây là điều mới xuất hiện hoặc thay đổi theo thời gian, "
                    "bác sĩ da liễu có thể xem xét khi khám định kỳ."
                )
            )
        )
```

### 3.3 Nutrition Photo Pipeline

```python
class NutritionPhotoPipeline:
    """
    Nhận dạng thức ăn từ ảnh → ước tính dinh dưỡng cơ bản.
    KHÔNG prescribe chế độ ăn. CHỈ ước tính, không chính xác tuyệt đối.
    """

    async def process(self, image: UploadedImage, user_conditions: list[str]) -> NutritionEstimate:
        # Recognize food items
        foods_detected = await self.vision_provider.recognize_food(
            image=image,
            language="vi"
        )

        if not foods_detected:
            return NutritionEstimate(
                confidence=0.0,
                message="Meto không nhận ra thức ăn trong ảnh. "
                        "Thử chụp gần hơn với đĩa thức ăn."
            )

        # Look up nutrition data for detected foods
        nutrition_data = []
        for food in foods_detected:
            food_info = await knowledge_base.lookup_food_nutrition(food.name_vi)
            if food_info:
                nutrition_data.append(FoodNutritionItem(
                    food_name=food.name_vi,
                    estimated_portion=food.estimated_portion_g,
                    calories_estimate=food_info.calories_per_100g * food.estimated_portion_g / 100,
                    carb_estimate=food_info.carbs_per_100g * food.estimated_portion_g / 100,
                    confidence=food.confidence * food_info.data_confidence,
                ))

        # Generate observation — NOT meal plan
        obs = NutritionObservation(
            foods_identified=nutrition_data,
            overall_confidence=sum(f.confidence for f in nutrition_data) / max(1, len(nutrition_data)),
            context_note=self._generate_context_note(nutrition_data, user_conditions)
        )

        return NutritionEstimate(
            foods=obs.foods_identified,
            confidence=obs.overall_confidence,
            message=(
                f"Meto nhận ra trong bữa ăn của {'{preferred_address}'} có:\n"
                + "\n".join(f"• {f.food_name} (~{f.calories_estimate:.0f} kcal, "
                           f"carbs ~{f.carb_estimate:.0f}g)" for f in nutrition_data)
                + f"\n\n{obs.context_note}"
                + "\n\n*Đây là ước tính — không chính xác tuyệt đối. "
                + "Chuyên gia dinh dưỡng có thể tư vấn chính xác hơn.*"
            )
        )

    def _generate_context_note(
        self,
        foods: list[FoodNutritionItem],
        conditions: list[str]
    ) -> str:
        """Add condition-relevant context without prescribing"""
        if "diabetes_type2" in conditions:
            high_gi_foods = [f for f in foods if knowledge_base.is_high_gi(f.food_name)]
            if high_gi_foods:
                names = ", ".join(f.food_name for f in high_gi_foods)
                return f"Với tiểu đường, lưu ý {names} có thể ảnh hưởng đường huyết sau ăn."
        return ""
```

### 3.4 Barcode Pipeline

```python
class BarcodePipeline:
    """
    Đọc barcode thuốc → lookup drug information.
    Chỉ hiển thị thông tin tham khảo, không kê đơn.
    """

    async def process(self, image: UploadedImage) -> BarcodeResult:
        barcode_data = await self.vision_provider.read_barcode(image)
        if not barcode_data:
            return BarcodeResult(success=False, message="Không đọc được barcode.")

        # Look up in drug database
        drug_info = await knowledge_base.lookup_drug_by_barcode(barcode_data.value)
        if not drug_info:
            return BarcodeResult(
                success=False,
                message=f"Barcode {barcode_data.value} không có trong cơ sở dữ liệu của Meto."
            )

        return BarcodeResult(
            success=True,
            drug_name=drug_info.generic_name,
            drug_class=drug_info.drug_class,
            drug_info_summary=drug_info.mechanism_simple_vi,
            safety_note=drug_info.safety_note,
            message=(
                f"Meto tìm thấy: **{drug_info.generic_name}** ({drug_info.brand_name})\n"
                f"Nhóm thuốc: {drug_info.drug_class_vi}\n"
                f"Thông tin: {drug_info.mechanism_simple_vi}\n\n"
                f"*{drug_info.safety_note}*"
            )
        )
```

### 3.5 Document Scan Pipeline

```python
class DocumentScanPipeline:
    """
    Quét ID card, bảo hiểm y tế.
    KHÔNG lưu raw image sau khi xử lý.
    CONSENT REQUIRED trước khi xử lý.
    """

    CONSENT_REQUIRED = True
    RETAIN_RAW_IMAGE = False

    async def process(
        self,
        image: UploadedImage,
        doc_type: str,                 # "id_card" | "insurance_card"
        consent: DocumentScanConsent
    ) -> DocumentScanResult:

        if not consent.scan_document_granted:
            raise ConsentRequiredError(
                "Cần đồng ý trước khi Meto xử lý tài liệu này."
            )

        # Extract only needed fields
        if doc_type == "insurance_card":
            extracted = await self.vision_provider.extract_insurance_info(image)
            result = DocumentScanResult(
                doc_type=doc_type,
                extracted_fields={
                    "insurance_id": extracted.get("insurance_id"),
                    "expiry_date": extracted.get("expiry_date"),
                    "hospital_coverage": extracted.get("hospital_list"),
                },
                # NOT extracted: personal address, full ID number (privacy)
            )
        elif doc_type == "id_card":
            # Only extract: name, birth_year (NOT full address, NOT ID number)
            extracted = await self.vision_provider.extract_id_info_limited(image)
            result = DocumentScanResult(
                doc_type=doc_type,
                extracted_fields={
                    "full_name": extracted.get("name"),
                    "birth_year": extracted.get("birth_year"),
                },
            )

        # Delete raw image immediately after processing
        await image.delete_from_processing_cache()
        result.raw_image_deleted = True

        return result
```

---

## 4. Voice Pipeline

### 4.1 Speech-to-Text (STT)

```python
@dataclass
class STTPipelineConfig:
    primary_language: str = "vi-VN"        # Vietnamese
    fallback_language: str = "vi-VN"       # Same — no EN fallback by default
    accent_variants: list[str] = field(
        default_factory=lambda: [
            "vi-VN",    # Standard Hanoi accent
            "vi-vn-south",  # Southern accent (HCMC)
            "vi-vn-central",  # Central VN accent (Huế, Đà Nẵng)
        ]
    )
    max_duration_seconds: int = 120        # 2 minutes max
    min_audio_quality_score: float = 0.6
    noise_cancellation: bool = True

class VoiceSTTPipeline:

    async def transcribe(
        self,
        audio: UploadedAudio,
        user_id: str
    ) -> TranscriptionResult:

        # Step 1: Quality check
        quality = await self._assess_audio_quality(audio)
        if quality.score < 0.4:
            return TranscriptionResult(
                success=False,
                message="Chất lượng âm thanh chưa đủ. "
                        "Thử ghi âm lại ở nơi ít tiếng ồn hơn.",
                confidence=quality.score
            )

        # Step 2: Transcribe via SpeechProvider
        transcript = await self.speech_provider.transcribe(
            audio=audio,
            language="vi-VN",
            enable_punctuation=True,
            enable_speaker_diarization=False  # Single speaker expected
        )

        # Step 3: Post-processing
        cleaned = await self._clean_transcript(transcript.text)
        vn_medical_normalized = await self._normalize_vn_medical_terms(cleaned)

        return TranscriptionResult(
            success=True,
            text=vn_medical_normalized,
            original_text=transcript.text,
            confidence=transcript.confidence,
            language_detected=transcript.language,
            needs_confirmation=transcript.confidence < 0.75
        )

    async def _normalize_vn_medical_terms(self, text: str) -> str:
        """
        Normalize common VN medical speech patterns:
        - "ha-bi-1-xi" → "HbA1c"
        - "lưu lượng máu" → often means "blood flow"
        - "đường huyết" often transcribed as "đường huyệt" → correct
        """
        SPEECH_CORRECTIONS = {
            "đường huyệt": "đường huyết",
            "ha-bi-1-xi": "HbA1c",
            "mét pho min": "metformin",
            "am-lô-đi-pin": "amlodipine",
            "en-sa-gơ-lê-flô-zin": "empagliflozin",
        }
        for wrong, correct in SPEECH_CORRECTIONS.items():
            text = text.replace(wrong, correct)
        return text
```

### 4.2 Text-to-Speech (TTS)

```python
@dataclass
class TTSConfig:
    voice_name: str = "meto_vi_female"  # Custom Meto voice (future)
    fallback_voice: str = "vi-VN-Neural2-A"  # Google/Azure TTS
    speaking_rate: float = 1.0         # Normal speed
    pitch: float = 0.0                 # Natural pitch
    max_text_length: int = 500         # Characters per TTS call
    audio_format: str = "mp3"

class VoiceTTSPipeline:

    async def synthesize(
        self,
        text: str,
        user_id: str,
        style: str = "warm"            # "warm" | "professional" | "neutral"
    ) -> TTSResult:

        # Trim to reasonable length
        if len(text) > self.config.max_text_length:
            text = text[:self.config.max_text_length] + "..."

        # Remove markdown formatting for TTS
        clean_text = self._strip_markdown(text)

        # Synthesize
        audio = await self.speech_provider.synthesize(
            text=clean_text,
            voice=self.config.voice_name,
            language="vi-VN",
            speaking_rate=self.config.speaking_rate,
        )

        return TTSResult(
            audio_data=audio.bytes,
            audio_format=self.config.audio_format,
            duration_seconds=audio.duration,
            text_used=clean_text
        )

    async def handle_voice_quality_issue(self, quality_score: float) -> str:
        if quality_score < 0.4:
            return "Meto không nghe rõ. Bạn có thể nhắn tin thay vì ghi âm không?"
        if quality_score < 0.6:
            return "Meto nghe chưa rõ lắm. Bạn có thể xác nhận: [transcription]?"
        return None
```

### 4.3 Voice Quality Scoring

```python
class AudioQualityScorer:
    def assess(self, audio: AudioData) -> AudioQualityResult:
        metrics = {
            "snr": self._compute_snr(audio),           # Signal-to-noise ratio
            "clipping": self._detect_clipping(audio),  # Audio clipping
            "silence_ratio": self._compute_silence(audio),
            "duration": audio.duration_seconds,
        }

        score = 1.0
        if metrics["snr"] < 10:       score -= 0.3   # High noise
        if metrics["clipping"] > 0.1: score -= 0.2   # Clipping detected
        if metrics["silence_ratio"] > 0.7: score -= 0.2
        if metrics["duration"] < 0.5:  score -= 0.3   # Too short

        return AudioQualityResult(
            score=max(0.0, score),
            metrics=metrics,
            recommendation=self._get_recommendation(score)
        )
```

---

## 5. Camera Pipeline

### 5.1 Full Camera Capture Flow

```
[User taps camera icon in Meto]
        │
        ▼
[Camera opens — UI shows mode selection]
  ┌──────────────┬───────────────────┬───────────────┐
  │ Chụp kết quả│ Chụp thức ăn      │ Chụp vết thương│
  │ xét nghiệm  │ (ước tính dinh dưỡng│ / da          │
  └──────┬───────┴─────────┬─────────┴───────┬────────┘
         │                 │                 │
         ▼                 ▼                 ▼
   [OCR Pipeline]    [Nutrition       [Skin/Wound
                      Pipeline]       Pipeline]
```

```python
class CameraCapturePipeline:

    async def process(
        self,
        image: UploadedImage,
        selected_mode: str,       # User-selected mode
        user_context: dict
    ) -> CameraProcessResult:

        # Preprocessing
        processed = await ImagePreprocessor.standard_preprocess(image)

        # Route to correct pipeline based on mode
        if selected_mode == "lab_result":
            result = await LabReportOCRPipeline().process(processed, user_context["user_id"])
        elif selected_mode == "food":
            result = await NutritionPhotoPipeline().process(
                processed, user_context.get("conditions", [])
            )
        elif selected_mode == "skin_wound":
            result = await SkinImagePipeline().process(processed)
        elif selected_mode == "medication_barcode":
            result = await BarcodePipeline().process(processed)
        else:
            # Auto-detect
            routing = await ImageModalityRouter().route(processed, user_context)
            pipeline = self._get_pipeline(routing.pipeline)
            result = await pipeline.process(processed)

        # Apply quality score
        if result.confidence < self.config.min_confidence_threshold:
            return CameraProcessResult(
                success=False,
                low_confidence=True,
                message=self._generate_retry_message(selected_mode),
                retry_suggested=True
            )

        return CameraProcessResult(
            success=True,
            mode=selected_mode,
            result=result,
            confidence=result.confidence,
            requires_user_review=result.needs_user_review
        )
```

---

## 6. Document Pipeline

### 6.1 Full Document Upload Flow

```
[User uploads document]
        │
        ▼
[Detect document type]
  ┌─────────────────────────────────────────────────────┐
  │ PDF lab report │ Image lab result │ Prescription PDF│
  └────────┬───────┴────────┬─────────┴────────┬────────┘
           │                │                  │
           ▼                ▼                  ▼
   [PDF Extractor]   [OCR Pipeline]    [Rx Parser]
           │                │                  │
           └────────────────┴──────────────────┘
                            │
                            ▼
                   [Structured Output]
                            │
                            ▼
                   [User Confirmation]
                            │
                            ▼
                   [Store + Feed to Context Engine]
```

```python
class DocumentPipeline:

    async def process(
        self,
        file: UploadedFile,
        user_id: str
    ) -> DocumentProcessResult:

        # Step 1: Detect format
        format_info = await self._detect_format(file)

        # Step 2: Extract text
        if format_info.is_pdf:
            raw_text = await self._extract_pdf_text(file)
        else:
            raw_text = await LabReportOCRPipeline().process(file, user_id)

        # Step 3: Parse
        doc_type = await self._detect_document_type(raw_text)
        parsed = await self._parse_by_type(doc_type, raw_text)

        # Step 4: Validate
        validated = await self._validate(parsed)

        # Step 5: User confirmation if needed
        if validated.needs_review:
            return DocumentProcessResult(
                status="needs_review",
                parsed_fields=validated.fields,
                review_prompt=self._build_review_prompt(validated)
            )

        # Step 6: Store and feed to context
        stored = await self._store_extracted_data(validated, user_id)

        return DocumentProcessResult(
            status="success",
            document_id=stored.document_id,
            parsed_fields=validated.confident_fields,
            message=f"Meto đã đọc được {len(validated.confident_fields)} kết quả "
                    f"từ tài liệu. Muốn Meto giải thích không?"
        )

    async def _extract_pdf_text(self, file: UploadedFile) -> str:
        """
        PDF extraction strategy:
        1. Try direct text extraction (if PDF is text-based, not scanned)
        2. Fallback to OCR if text extraction yields < 100 chars
        """
        direct_text = await PDFTextExtractor().extract(file)
        if len(direct_text.strip()) > 100:
            return direct_text

        # Fallback: convert PDF pages to images → OCR
        images = await PDFToImageConverter().convert(file)
        all_text = []
        for img in images:
            page_text = await self.vision_provider.extract_text(img)
            all_text.append(page_text)
        return "\n".join(all_text)
```

---

## 7. Future Wearable Integration

### 7.1 Wearable Device Support Plan

```python
WEARABLE_SUPPORT_ROADMAP = {
    "phase_1_current": {
        "status": "manual_entry",
        "supported": ["blood_pressure_manual", "glucose_manual", "weight_manual"],
        "note": "User enters readings manually"
    },
    "phase_2_api": {
        "status": "planned",
        "timeline": "Q3 2026",
        "devices": {
            "Apple Watch": {
                "data_types": ["heart_rate", "hrv", "spo2", "steps", "sleep"],
                "integration": "HealthKit API",
                "consent_required": "health_metrics_granted",
            },
            "Garmin": {
                "data_types": ["heart_rate", "hrv", "steps", "sleep", "stress_score"],
                "integration": "Garmin Connect API",
                "consent_required": "health_metrics_granted",
            },
            "Omron BP Monitor": {
                "data_types": ["systolic", "diastolic", "pulse", "irregular_heartbeat_flag"],
                "integration": "Omron Connect API or Bluetooth direct",
                "consent_required": "health_metrics_granted",
            },
            "Accu-Chek CGM": {
                "data_types": ["glucose_continuous", "glucose_trend"],
                "integration": "Accu-Chek API",
                "consent_required": "health_metrics_granted",
                "note": "CGM data unlocks real-time glucose coaching"
            },
        }
    },
    "phase_3_advanced": {
        "status": "future",
        "timeline": "2027+",
        "devices": ["on_device_inference", "wearable_ecg", "continuous_bp"],
    }
}

@dataclass
class WearableDataPoint:
    """Future-ready data schema for wearable integration"""
    device_type: str               # "apple_watch" | "garmin" | "omron" | "accu_chek"
    metric_type: str               # "heart_rate" | "hrv" | "spo2" | "glucose" | etc.
    value: float
    unit: str
    measured_at: datetime
    device_id: str                 # Anonymous device identifier
    confidence: float              # Device-reported accuracy if available
    raw_payload: dict | None       # Original API response (for debugging)
```

### 7.2 Wearable Data Processing Interface

```python
class WearableDataProcessor:
    """
    Interface for wearable data processing.
    Implement per-device connector.
    """

    async def ingest(
        self,
        user_id: str,
        device_type: str,
        data_points: list[WearableDataPoint]
    ) -> WearableIngestionResult:

        # Validate consent
        consent = await get_user_consent(user_id)
        if not consent.metrics_granted:
            raise ConsentRequiredError("Health metrics consent required for wearable data")

        # Validate data quality
        validated = [
            dp for dp in data_points
            if self._is_physiologically_plausible(dp)
        ]

        # Store to health_metrics table
        stored = await health_metrics_repo.bulk_insert(
            user_id=user_id,
            metrics=validated
        )

        # Trigger context refresh
        await context_cache.invalidate(user_id, "recent_metrics")

        return WearableIngestionResult(
            accepted=len(stored),
            rejected=len(data_points) - len(stored),
            next_recommended_sync=timedelta(minutes=30)
        )
```

---

## 8. Quality Scoring — Per Modality

```python
QUALITY_THRESHOLDS = {
    "ocr_lab_report": {
        "auto_accept": 0.90,
        "suggest_review": 0.70,
        "require_review": 0.50,
        "reject": 0.30,
    },
    "ocr_handwritten": {
        "auto_accept": 0.85,           # Higher bar for handwritten
        "suggest_review": 0.65,
        "require_review": 0.45,
        "reject": 0.30,
    },
    "image_skin": {
        "sufficient_for_description": 0.60,
        "reject": 0.40,
    },
    "image_nutrition": {
        "sufficient_for_estimation": 0.55,
        "reject": 0.30,
    },
    "voice_transcription": {
        "auto_proceed": 0.80,
        "confirm_first": 0.60,
        "fallback_to_text": 0.40,
    },
    "barcode": {
        "accept": 0.95,                # Barcodes are usually clear
        "retry": 0.80,
        "reject": 0.70,
    },
}
```

---

## 9. Fallback UX

### 9.1 Fallback Messages per Scenario

```python
FALLBACK_MESSAGES = {
    "ocr_low_confidence": (
        "Meto không đọc rõ kết quả này ({confidence:.0%} độ chắc chắn). "
        "Anh/chị có thể:\n"
        "1. Chụp lại với ánh sáng tốt hơn và không rung\n"
        "2. Nhập thủ công từng giá trị\n"
        "3. Crop ảnh để chỉ chứa phần kết quả xét nghiệm"
    ),
    "voice_too_noisy": (
        "Meto nghe không rõ do tiếng ồn xung quanh. "
        "Thử nhắn tin thay vì ghi âm nhé! 💬"
    ),
    "voice_too_short": (
        "Tin nhắn thoại quá ngắn. Giữ nút ghi âm lâu hơn và nói rõ nhé."
    ),
    "skin_image_blurry": (
        "Hình ảnh bị mờ. Giữ điện thoại cố định và đảm bảo có đủ ánh sáng trước khi chụp."
    ),
    "food_not_recognized": (
        "Meto không nhận ra rõ thức ăn trong ảnh. "
        "Thử chụp từ trên xuống và chụp cả đĩa để nhìn rõ hơn."
    ),
    "barcode_not_read": (
        "Không đọc được barcode. Đảm bảo barcode không bị nhàu và chụp thẳng."
    ),
    "pdf_no_text": (
        "File PDF này có vẻ là ảnh scan. "
        "Meto sẽ dùng OCR để đọc — có thể cần thêm vài giây."
    ),
    "general_multimodal_error": (
        "Meto gặp sự cố khi xử lý file này. "
        "Thử lại sau hoặc nhập thông tin thủ công nhé."
    ),
}
```

---

## 10. Privacy — Multimodal Data Retention Policy

### 10.1 Per-Modality Retention Rules

```python
MULTIMODAL_RETENTION_POLICY = {
    "raw_image": {
        "retention": "DELETE_IMMEDIATELY_AFTER_PROCESSING",
        "exception": "User explicitly consents to image storage (future feature)",
        "what_is_stored": "Structured parsed output only (e.g., lab values)",
    },
    "ocr_raw_text": {
        "retention": "NOT_STORED",
        "what_is_stored": "Parsed structured fields only",
    },
    "audio_recording": {
        "retention": "DELETE_IMMEDIATELY_AFTER_TRANSCRIPTION",
        "what_is_stored": "Transcription text only (with consent)",
    },
    "transcription_text": {
        "retention": "Same as chat history (90 days or user delete)",
        "scope": "Treated as part of conversation",
    },
    "nutrition_estimate": {
        "retention": "Optional — stored if user confirms",
        "what_is_stored": "Food items + macro estimates",
    },
    "document_scan": {
        "retention": "RAW: DELETE_IMMEDIATELY. Extracted fields: optional storage with consent",
        "phi_protection": "Mask before storage: only store needed fields",
    },
    "wearable_data": {
        "retention": "Up to 2 years for trend analysis (user-configurable)",
        "scope": "health_metrics table",
    },
}

class MultimodalPrivacyGuard:
    async def cleanup_after_processing(self, processing_job: ProcessingJob):
        """Ensure raw data deleted after processing"""
        if processing_job.file_type in ("image", "audio", "document"):
            await storage.delete_temp_file(processing_job.temp_file_id)
            await audit_log.record({
                "action": "multimodal_raw_deleted",
                "job_id": processing_job.id,
                "file_type": processing_job.file_type,
            })
```

### 10.2 Consent per Modality

```python
MULTIMODAL_CONSENT_REQUIREMENTS = {
    "lab_report_ocr": "lab_results_granted",
    "prescription_scan": "medications_granted",
    "nutrition_photo": None,           # No special consent (not health data)
    "skin_image": None,                # Described, not stored
    "document_scan_id": "document_scan_granted",  # Extra consent required
    "voice_input": None,               # Transcription = chat, same consent as chat
    "voice_output": None,              # TTS = accessibility feature
    "wearable_data": "metrics_granted",
}
```

---

## 11. Acceptance Criteria

### AC-MM-001: OCR Pipeline
- [ ] Lab report OCR: ≥70% field extraction accuracy on standard VN lab formats (test set)
- [ ] Handwritten report: always flags for user review
- [ ] User correction workflow: corrections persist and are used as ground truth
- [ ] Low confidence (<0.50): user prompted to re-upload, not silently dropped

### AC-MM-002: Image Understanding
- [ ] Skin image: never outputs diagnosis, only description
- [ ] Skin image: concerning features → escalation message triggered
- [ ] Nutrition photo: disclaimer always included in response
- [ ] Barcode: correct drug lookup for top 50 VN medications

### AC-MM-003: Voice Pipeline
- [ ] STT accuracy ≥80% on clean Vietnamese audio (test set)
- [ ] Southern accent support tested and working
- [ ] Audio quality < 0.4 → fallback to text prompt
- [ ] TTS: no markdown symbols in audio output

### AC-MM-004: Privacy
- [ ] Raw images deleted from temp storage within 60 seconds of processing
- [ ] Audio files deleted immediately after transcription
- [ ] Document scans: only structured fields stored
- [ ] Audit log created for every multimodal data deletion

### AC-MM-005: Quality
- [ ] Confidence threshold enforced: items below threshold never auto-fed to CRL
- [ ] Each modality has tested fallback UX messages
- [ ] User review screen shown for any field with confidence 0.50-0.89

---

*Xem thêm: 14_CLINICAL_REASONING.md (structured OCR output feeds CRL), 16_KNOWLEDGE_BASE.md (food database, drug barcode lookup), 20_PROVIDER_ABSTRACTION.md (VisionProvider, SpeechProvider interfaces)*
