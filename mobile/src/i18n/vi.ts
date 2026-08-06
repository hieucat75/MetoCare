/**
 * Vietnamese-first copy for the MetoCare patient mobile app (Journey 1).
 *
 * All user-facing strings live here so screens stay declarative and copy
 * can be reviewed in one place. Vietnamese is the primary (and currently
 * only) locale — ADR-02 keeps Journey 1 email/password only.
 */

export const vi = {
  common: {
    appName: 'MetoCare',
    retry: 'Thử lại',
    loading: 'Đang tải…',
    cancel: 'Huỷ',
    continue: 'Tiếp tục',
    back: 'Quay lại',
    ok: 'Đồng ý',
    email: 'Email',
    password: 'Mật khẩu',
    fullName: 'Họ và tên',
  },
  offline: {
    banner: 'Bạn đang ngoại tuyến. Một số tính năng có thể không hoạt động.',
    title: 'Mất kết nối mạng',
    message: 'Vui lòng kiểm tra kết nối và thử lại.',
  },
  errors: {
    generic: 'Đã có lỗi xảy ra. Vui lòng thử lại.',
    network: 'Không thể kết nối máy chủ. Vui lòng kiểm tra mạng và thử lại.',
    invalidCredentials: 'Email hoặc mật khẩu không đúng.',
    emailRequired: 'Vui lòng nhập email.',
    emailInvalid: 'Email không hợp lệ.',
    passwordRequired: 'Vui lòng nhập mật khẩu.',
    passwordTooShort: 'Mật khẩu phải có ít nhất 6 ký tự.',
    sessionExpired: 'Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.',
    patientsOnly: 'Ứng dụng này chỉ dành cho bệnh nhân. Vui lòng dùng cổng dành cho tài khoản của bạn.',
  },
  auth: {
    loginTitle: 'Chào mừng trở lại',
    loginSubtitle: 'Đăng nhập để tiếp tục theo dõi sức khoẻ chuyển hoá của bạn.',
    loginCta: 'Đăng nhập',
    noAccount: 'Chưa có tài khoản?',
    goRegister: 'Đăng ký ngay',
    registerTitle: 'Tạo tài khoản MetoCare',
    registerSubtitle: 'Bắt đầu hành trình chăm sóc sức khoẻ chuyển hoá của bạn.',
    registerCta: 'Tạo tài khoản',
    haveAccount: 'Đã có tài khoản?',
    goLogin: 'Đăng nhập',
    logout: 'Đăng xuất',
    biometricPrompt: 'Xác thực để mở khoá MetoCare',
    biometricUnlock: 'Mở khoá bằng sinh trắc học',
    usePassword: 'Dùng mật khẩu',
  },
  onboarding: {
    step1Title: 'Theo dõi chỉ số chuyển hoá',
    step1Body: 'Xem đường huyết, huyết áp, mỡ máu và cân nặng ở cùng một nơi.',
    step2Title: 'Kết quả xét nghiệm rõ ràng',
    step2Body: 'Tự động số hoá phiếu xét nghiệm và giải thích ý nghĩa từng chỉ số.',
    step3Title: 'Đồng hành cùng bác sĩ',
    step3Body: 'Nhận hướng dẫn cá nhân hoá và nhắc lịch dùng thuốc mỗi ngày.',
    getStarted: 'Bắt đầu',
    skip: 'Bỏ qua',
    next: 'Tiếp theo',
  },
  dashboard: {
    greeting: 'Xin chào',
    greetingFallback: 'bạn',
    subtitle: 'Tổng quan sức khoẻ chuyển hoá hôm nay của bạn.',
    emptyTitle: 'Chưa có dữ liệu',
    emptyBody: 'Hãy cập nhật chỉ số hoặc tải kết quả xét nghiệm để bắt đầu.',
    sectionMetrics: 'Chỉ số gần đây',
    sectionActions: 'Việc cần làm',
    reload: 'Tải lại',
    addDocument: 'Thêm tài liệu',
    findDoctor: 'Tìm bác sĩ tư vấn',
    myConsultations: 'Lịch tư vấn của tôi',
    chatWithMeto: 'Trò chuyện với Meto',
    myMedications: 'Thuốc của tôi',
    medicationReminders: 'Nhắc dùng thuốc',
  },
  meto: {
    title: 'Meto — Trợ lý sức khoẻ',
    subtitle: 'Hỏi Meto về chỉ số, thuốc và kết quả đã xác nhận của bạn.',
    inputPlaceholder: 'Nhập câu hỏi cho Meto…',
    inputLabel: 'Câu hỏi cho Meto',
    send: 'Gửi',
    typing: 'Meto đang trả lời…',
    emptyTitle: 'Bắt đầu trò chuyện với Meto',
    emptyBody: 'Meto giúp bạn hiểu các chỉ số và kết quả đã xác nhận. Hãy đặt câu hỏi để bắt đầu.',
    quickPromptsTitle: 'Gợi ý câu hỏi',
    fallbackNote: 'Meto đã điều chỉnh câu trả lời để đảm bảo an toàn.',
    disclaimer:
      'Meto chỉ cung cấp thông tin tham khảo, không thay thế cho chẩn đoán hoặc điều trị của bác sĩ.',
    // Consent gate — shown when master `ai_processing` consent is not granted.
    consentGateTitle: 'Bật trợ lý Meto',
    consentGateBody:
      'Để Meto có thể hỗ trợ, bạn cần cho phép Meto xử lý dữ liệu bằng AI trong phần Quyền riêng tư. Bạn có thể tắt lại bất cứ lúc nào.',
    consentGateCta: 'Mở Quyền riêng tư',
    consentRecheck: 'Tôi đã bật — Tải lại',
    // Escalation banner.
    escalationTitle: 'Meto khuyến nghị',
    escalationTier: {
      recommend_checkup: 'Bạn nên đi khám',
      recommend_urgent: 'Bạn nên đi khám sớm',
      emergency: 'Tình huống khẩn cấp',
    } as Record<string, string>,
    emergencyContactsLabel: 'Liên hệ khẩn cấp',
  },
  marketplace: {
    title: 'Tìm bác sĩ',
    subtitle: 'Chọn bác sĩ đã xác minh để đặt lịch tư vấn.',
    searchPlaceholder: 'Tìm theo tên bác sĩ',
    allSpecialties: 'Tất cả',
    empty: 'Chưa có bác sĩ nào phù hợp.',
    feeUnit: 'đ',
    perSession: 'mỗi lượt tư vấn',
    feeUnknown: 'Liên hệ',
    ratingCount: (count: number): string => `${count} đánh giá`,
    noRating: 'Chưa có đánh giá',
    experience: (years: number): string => `${years} năm kinh nghiệm`,
    languages: 'Ngôn ngữ',
    methods: 'Hình thức',
    hospital: 'Bệnh viện',
    bio: 'Giới thiệu',
    noBio: 'Bác sĩ chưa cập nhật phần giới thiệu.',
    bookCta: 'Đặt tư vấn',
    disclaimerFallback:
      'Nội dung tư vấn chỉ mang tính tham khảo và không thay thế cho chẩn đoán hoặc điều trị y khoa trực tiếp.',
  },
  consultations: {
    listTitle: 'Lịch tư vấn của tôi',
    listSubtitle: 'Theo dõi trạng thái và nội dung các lượt tư vấn.',
    empty: 'Bạn chưa có lượt tư vấn nào.',
    findDoctor: 'Tìm bác sĩ',
    bookTitle: 'Đặt lịch tư vấn',
    bookSubtitle: 'Chia sẻ lý do tư vấn để bác sĩ chuẩn bị tốt hơn.',
    chiefComplaintLabel: 'Lý do tư vấn',
    chiefComplaintPlaceholder: 'Ví dụ: đường huyết tăng cao gần đây',
    patientNoteLabel: 'Ghi chú thêm (không bắt buộc)',
    patientNotePlaceholder: 'Triệu chứng, câu hỏi hoặc thông tin khác',
    consentLabel:
      'Tôi đồng ý chia sẻ dữ liệu sức khoẻ của mình với bác sĩ cho lượt tư vấn này.',
    consentRequired: 'Vui lòng đồng ý chia sẻ dữ liệu để tiếp tục.',
    submitBook: 'Xác nhận & thanh toán',
    detailTitle: 'Chi tiết tư vấn',
    chiefComplaint: 'Lý do tư vấn',
    patientNote: 'Ghi chú của bạn',
    notesTitle: 'Nhận xét của bác sĩ',
    noNotes: 'Bác sĩ chưa gửi nhận xét nào.',
    reviewTitle: 'Đánh giá lượt tư vấn',
    ratingLabel: 'Chọn số sao',
    feedbackLabel: 'Nhận xét (không bắt buộc)',
    feedbackPlaceholder: 'Chia sẻ trải nghiệm của bạn',
    submitReview: 'Gửi đánh giá',
    reviewThanks: 'Cảm ơn bạn đã đánh giá.',
    statusLabel: 'Trạng thái',
    status: {
      REQUESTED: 'Đã yêu cầu',
      CONFIRMED: 'Đã xác nhận',
      PAID: 'Đã thanh toán',
      IN_PROGRESS: 'Đang tư vấn',
      COMPLETED: 'Hoàn tất',
      CANCELLED: 'Đã huỷ',
    } as Record<string, string>,
  },
  documents: {
    addTitle: 'Thêm tài liệu y tế',
    addSubtitle: 'Chụp ảnh đơn thuốc, phiếu xét nghiệm hoặc tài liệu y tế — hệ thống sẽ tự trích xuất.',
    typePrescription: 'Đơn thuốc',
    typeLab: 'Phiếu xét nghiệm',
    typeGeneral: 'Tài liệu khác',
    takePhoto: 'Chụp ảnh',
    chooseImage: 'Chọn từ thư viện',
    qaFixture: 'Dùng tài liệu mẫu (QA)',
    uploading: 'Đang tải lên và xử lý…',
    reviewTitle: 'Kiểm tra & xác nhận',
    reviewSubtitle: 'Xác nhận từng mục trước khi lưu vào hồ sơ. Chưa có mục nào được lưu tự động.',
    confirm: 'Xác nhận',
    reject: 'Bỏ qua',
    confirmed: 'Đã xác nhận',
    rejected: 'Đã bỏ qua',
    noCandidates: 'Không trích xuất được mục nào. Vui lòng chụp lại rõ hơn.',
    allReviewed: 'Đã xử lý xong tất cả các mục.',
    done: 'Hoàn tất',
    strength: 'Hàm lượng',
    frequency: 'Cách dùng',
    unnamed: 'Mục chưa rõ tên',
    // ── per-candidate-type review (OCR-F5) ──────────────────────────────────
    // A patient may only confirm what they can SEE: every candidate type must
    // render its own extracted values, and an unhandled type degrades to an
    // honest dump of the raw fields rather than a blank card.
    candidateType: {
      medication: 'Thuốc',
      lab_result: 'Kết quả xét nghiệm',
      diagnosis: 'Chẩn đoán',
      procedure: 'Thủ thuật / chỉ định',
      finding: 'Kết luận',
      recommendation: 'Lời dặn của bác sĩ',
      follow_up: 'Lịch tái khám',
    } as Record<string, string>,
    candidateTypeUnknown: 'Mục khác',
    fieldLabel: {
      // prescription
      name: 'Tên thuốc',
      strength: 'Hàm lượng',
      form: 'Dạng bào chế',
      quantity: 'Số lượng',
      frequency: 'Cách dùng',
      route: 'Đường dùng',
      duration: 'Thời gian dùng',
      instructions: 'Hướng dẫn',
      facility: 'Cơ sở y tế',
      prescriber: 'Bác sĩ kê đơn',
      prescribed_date: 'Ngày kê đơn',
      diagnosis: 'Chẩn đoán',
      // lab
      test_name: 'Tên xét nghiệm',
      original_test_name: 'Tên ghi trên phiếu',
      value: 'Giá trị',
      unit: 'Đơn vị',
      reference_range: 'Khoảng tham chiếu',
      specimen_date: 'Ngày lấy mẫu',
      // general report
      text: 'Nội dung',
      report_date: 'Ngày trên tài liệu',
      summary: 'Tóm tắt tài liệu',
    } as Record<string, string>,
    lowConfidence: 'cần kiểm tra kỹ',
    unreadableTitle: 'Không đọc được nội dung',
    unreadableBody:
      'Hệ thống không trích xuất được nội dung nào cho mục này. Hãy bỏ qua mục này và nhập tay nếu cần.',
    editValues: 'Sửa giá trị',
    cancelEdit: 'Huỷ sửa',
    invalidNumber: 'Giá trị phải là số. Ví dụ: 5.6',
    correctionHint:
      'Nếu số hoặc đơn vị bị nhận sai, hãy sửa lại trước khi xác nhận. Sai số liệu có thể dẫn tới đánh giá sai.',
    // Shown when the backend refuses the document pipeline because the patient
    // has not granted (or has revoked) the "Tài liệu y tế" consent category.
    consentBlockedTitle: 'Cần bật quyền “Tài liệu y tế”',
    consentBlockedBody:
      'Để tải lên và xử lý tài liệu y tế, bạn cần cho phép mục “Tài liệu y tế” trong phần Quyền riêng tư. Bạn có thể tắt lại bất cứ lúc nào.',
    consentBlockedCta: 'Mở Quyền riêng tư',
  },
  medication: {
    // List screen
    listTitle: 'Thuốc của tôi',
    listSubtitle: 'Danh sách thuốc đang dùng và lịch nhắc mỗi ngày.',
    empty: 'Bạn chưa có thuốc nào đang dùng.',
    remindersCta: 'Nhắc dùng thuốc hôm nay',
    doseLabel: 'Liều',
    frequencyLabel: 'Cách dùng',
    noSchedule: 'Chưa thiết lập lịch nhắc.',
    nextDosePrefix: 'Lịch dùng: ',
    // Detail screen
    detailTitle: 'Chi tiết thuốc',
    sourceTitle: 'Nguồn & xác minh',
    sourceLabel: 'Nguồn',
    verificationLabel: 'Trạng thái xác minh',
    schedulesTitle: 'Lịch dùng thuốc',
    scheduleStatusLabel: 'Trạng thái lịch',
    nextDueTitle: 'Liều sắp tới',
    noNextDue: 'Hiện chưa có liều nào tới hạn.',
    adherenceTitle: 'Mức độ tuân thủ',
    adherenceRate: 'Tỷ lệ uống đúng',
    adherenceTaken: 'Đã uống',
    adherenceSkipped: 'Đã bỏ qua',
    adherenceMissed: 'Bỏ lỡ',
    adherenceTotal: 'Tổng số liều',
    adherenceNoData: 'Chưa đủ dữ liệu để tính tỷ lệ.',
    // `reconciled=false` means the DENOMINATOR could not be established — not
    // "no doses yet". Rendering both as "chưa đủ dữ liệu" hides a repairable
    // state behind an inert one, and rendering a percentage from it would
    // publish app-engagement dressed as adherence.
    adherenceUnavailable:
      'Chưa thể tính tỷ lệ tuân thủ cho khoảng thời gian này. ' +
      'Số liệu sẽ xuất hiện khi lịch uống thuốc được cập nhật đầy đủ.',
    adherenceUnavailablePaused:
      'Chưa thể tính tỷ lệ tuân thủ: lịch đang tạm dừng hoặc đã ngừng trong toàn bộ ' +
      'khoảng thời gian này. Không có liều nào được coi là bỏ lỡ.',
    adherenceUnavailableEmpty: 'Lịch này không có liều nào trong khoảng thời gian đang xem.',
    adherencePeriod: 'Khoảng thời gian',
    adherenceUnavailableUntracked:
      'Khoảng thời gian này nằm trước khi MetoCare bắt đầu theo dõi thuốc của bạn, ' +
      'nên chưa thể tính tỷ lệ tuân thủ. Đây không phải là liều bỏ lỡ.',
    // A hold the patient was told to observe is not non-adherence. Subtracting
    // it silently leaves a smaller denominator with no explanation, and the
    // obvious inference from a shrinking total is that something went wrong.
    adherenceExcludedPaused: (n: number) =>
      `Đã loại trừ ${n} liều trong thời gian tạm dừng theo chỉ định. ` +
      'Những liều này không tính là bỏ lỡ.',
    adherenceExcludedCancelled: (n: number) =>
      `Đã loại trừ ${n} liều thuộc lịch đã ngừng hoặc đã thay đổi.`,
    adherenceExcludedUntracked: (n: number) =>
      `${n} liều được kê trước khi MetoCare bắt đầu theo dõi nên không được tính. ` +
      'Đây không phải là liều bỏ lỡ.',
    // Missed-dose correction. Records what happened; never advises whether to
    // take a late dose — that is a clinical decision this app does not make.
    missedDosesTitle: 'Các liều đã lỡ',
    missedDosesIntro:
      'Nếu bạn đã uống hoặc chủ động bỏ một liều nhưng chưa kịp ghi nhận, ' +
      'hãy ghi lại đúng điều đã xảy ra. Việc này chỉ cập nhật số liệu theo dõi.',
    missedDosesEmpty: 'Không có liều nào đang ở trạng thái bỏ lỡ.',
    missedDosesOpen: 'Xem và ghi nhận lại các liều đã lỡ',
    missedDosesQuestion: 'Điều gì đã thực sự xảy ra?',
    correctTaken: 'Tôi đã uống liều này',
    correctSkipped: 'Tôi đã bỏ liều này',
    correctError: 'Không thể ghi nhận lại liều này. Vui lòng thử lại.',
    // Reminders screen
    remindersTitle: 'Nhắc dùng thuốc',
    remindersSubtitle: 'Các liều tới hạn hôm nay. Ghi nhận từng liều bạn đã uống hoặc bỏ qua.',
    remindersEmpty: 'Không có liều nào tới hạn ngay bây giờ.',
    markTaken: 'Đã uống',
    markSkipped: 'Bỏ qua',
    skipReasonLabel: 'Lý do bỏ qua',
    skipReasonPlaceholder: 'Ví dụ: quên, hết thuốc, tác dụng phụ',
    skipConfirm: 'Xác nhận bỏ qua',
    skipCancel: 'Huỷ',
    skipReasonRequired: 'Vui lòng nhập lý do bỏ qua.',
    todaySummary: 'Hôm nay',
    // Shared labels
    scheduleType: {
      fixed_daily: 'Hằng ngày',
      interval: 'Theo chu kỳ',
      days_of_week: 'Theo ngày trong tuần',
      cyclic: 'Chu kỳ nghỉ',
      prn: 'Khi cần',
    } as Record<string, string>,
    doseState: {
      pending: 'Chờ tới hạn',
      notified: 'Đã nhắc',
      taken: 'Đã uống',
      skipped: 'Đã bỏ qua',
      missed: 'Bỏ lỡ',
    } as Record<string, string>,
    scheduleStatus: {
      active: 'Đang áp dụng',
      paused: 'Tạm dừng',
      stopped: 'Đã dừng',
      completed: 'Hoàn tất',
    } as Record<string, string>,
    sourceType: {
      patient_manual: 'Bạn tự nhập',
      prescription_ocr: 'Từ đơn thuốc (số hoá)',
      doctor: 'Bác sĩ kê',
    } as Record<string, string>,
    verification: {
      patient_reported: 'Bạn tự khai báo',
      confirmed: 'Đã xác nhận',
      doctor_verified: 'Bác sĩ xác nhận',
    } as Record<string, string>,
  },
  consent: {
    title: 'Quyền riêng tư — Meto',
    subtitle:
      'Bạn kiểm soát dữ liệu nào được sử dụng. Bật/tắt từng nhóm bất cứ lúc nào.',
    granted: 'Đang cho phép',
    revoked: 'Đang tắt',
    aiDisabledNote:
      'Tắt "Xử lý bằng AI" sẽ vô hiệu hoá trợ lý Meto. Các nhóm khác chỉ giới hạn dữ liệu Meto được dùng.',
    // Category display names keyed by backend context_type. The per-category
    // purpose text comes from the API (`purpose`), never from here.
    category: {
      ai_processing: 'Xử lý bằng AI',
      health_records: 'Hồ sơ sức khoẻ',
      medications: 'Thuốc',
      documents: 'Tài liệu y tế',
      doctor_consultation: 'Tư vấn bác sĩ',
    } as Record<string, string>,
    empty: 'Chưa có mục quyền riêng tư nào.',
    manage: 'Quyền riêng tư & Meto',
  },
  account: {
    // Settings / account screen (WS11-F5): in-app data export + account
    // deletion — required by Google Play's data-deletion policy and Apple
    // Guideline 5.1.1(v) for any app that lets users create an account.
    title: 'Tài khoản & dữ liệu',
    subtitle: 'Tải bản sao dữ liệu của bạn hoặc xoá vĩnh viễn tài khoản.',
    openSettings: 'Tài khoản & dữ liệu',
    signedInAs: 'Đang đăng nhập',
    exportTitle: 'Tải dữ liệu của tôi',
    exportBody:
      'Tạo bản sao dữ liệu sức khoẻ của bạn (chỉ số, xét nghiệm, thuốc, tài liệu, tư vấn).',
    exportCta: 'Tải dữ liệu của tôi',
    exporting: 'Đang chuẩn bị dữ liệu…',
    exportReady: 'Đã tạo bản sao dữ liệu của bạn.',
    exportShare: 'Chia sẻ / lưu bản sao',
    exportShareFailed: 'Không mở được trình chia sẻ. Bản tóm tắt vẫn hiển thị bên dưới.',
    exportSection: {
      profile: 'Hồ sơ cá nhân',
      health_metrics: 'Chỉ số sức khoẻ',
      lab_results: 'Kết quả xét nghiệm',
      lab_batches: 'Phiếu xét nghiệm đã tải lên',
      medications: 'Thuốc',
      meto_consents: 'Thiết lập quyền riêng tư',
      meto_conversations: 'Hội thoại với Meto',
      consultations: 'Lượt tư vấn',
      documents: 'Tài liệu y tế',
    } as Record<string, string>,
    deleteTitle: 'Xoá tài khoản',
    deleteBody:
      'Xoá vĩnh viễn tài khoản MetoCare của bạn và ẩn danh dữ liệu sức khoẻ liên quan.',
    deleteCta: 'Xoá tài khoản',
    deleteWarning:
      'Hành động này KHÔNG THỂ hoàn tác. Sau khi xoá, bạn sẽ mất quyền truy cập vào chỉ số, kết quả xét nghiệm, thuốc, tài liệu và lịch tư vấn của mình. Hãy tải bản sao dữ liệu trước nếu bạn cần giữ lại.',
    deleteConfirmWord: 'XOÁ',
    deleteConfirmLabel: 'Để xác nhận, hãy nhập chữ XOÁ vào ô bên dưới.',
    deleteConfirmPlaceholder: 'XOÁ',
    deleteConfirmCta: 'Tôi hiểu — xoá vĩnh viễn tài khoản',
    deleteConfirmMismatch: 'Vui lòng nhập đúng chữ XOÁ để xác nhận.',
    deleteCancel: 'Giữ tài khoản của tôi',
    deleting: 'Đang xoá tài khoản…',
  },
} as const

export type ViCopy = typeof vi
