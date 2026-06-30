# Meto AI — UI/UX Specification

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## 1. Meto Aura — Design Specification

### 1.1 Màu sắc

```css
/* Meto Aura Color System */
:root {
  --meto-mint-primary: #5ECBC8;        /* Core color */
  --meto-mint-light: #A8EDEA;          /* Light glow, halo */
  --meto-mint-deep: #3BB8B5;           /* Inner core, depth */
  --meto-mint-pale: #E8F9F9;           /* Background tint */
  --meto-glass-surface: rgba(255, 255, 255, 0.25);  /* Liquid glass */
  --meto-glass-blur: 12px;
  --meto-glow-color: rgba(94, 203, 200, 0.4);
  --meto-shadow: 0 8px 32px rgba(94, 203, 200, 0.3);
}
```

### 1.2 Visual Style

**Liquid Glass Effect:**
```css
.meto-aura {
  background: radial-gradient(
    circle at 35% 35%,
    rgba(255, 255, 255, 0.6) 0%,
    var(--meto-mint-light) 30%,
    var(--meto-mint-primary) 60%,
    var(--meto-mint-deep) 100%
  );
  backdrop-filter: blur(var(--meto-glass-blur));
  -webkit-backdrop-filter: blur(var(--meto-glass-blur));
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 50%;
  box-shadow:
    0 0 0 8px var(--meto-glow-color),
    var(--meto-shadow),
    inset 0 2px 4px rgba(255, 255, 255, 0.3);
}
```

### 1.3 Kích thước theo context

| Context | Width × Height | Glow radius |
|---------|---------------|-------------|
| Floating button | 56 × 56px | 8px |
| Chat header (thu nhỏ) | 40 × 40px | 6px |
| Thinking indicator | 32 × 32px | 4px |
| Splash / welcome screen | 96 × 96px | 16px |
| Empty state | 72 × 72px | 12px |

---

## 2. Animation States (Framer Motion)

### 2.1 Idle — "Thở nhẹ"

```typescript
const idleVariants = {
  animate: {
    scale: [1, 1.04, 1],
    opacity: [0.85, 1, 0.85],
    boxShadow: [
      "0 0 0 8px rgba(94, 203, 200, 0.2)",
      "0 0 0 12px rgba(94, 203, 200, 0.3)",
      "0 0 0 8px rgba(94, 203, 200, 0.2)",
    ],
    transition: {
      duration: 3,
      ease: "easeInOut",
      repeat: Infinity,
    },
  },
};
```

### 2.2 Listening — "Sáng nhẹ"

```typescript
const listeningVariants = {
  animate: {
    scale: [1, 1.06, 1],
    opacity: [0.9, 1, 0.9],
    boxShadow: [
      "0 0 0 10px rgba(94, 203, 200, 0.3)",
      "0 0 0 18px rgba(94, 203, 200, 0.5)",
      "0 0 0 10px rgba(94, 203, 200, 0.3)",
    ],
    filter: ["brightness(1)", "brightness(1.2)", "brightness(1)"],
    transition: {
      duration: 1.5,
      ease: "easeInOut",
      repeat: Infinity,
    },
  },
};
```

### 2.3 Thinking — "Ripple / Pulse"

```typescript
// 3 ripple đồng tâm, staggered
const ThinkingAura = () => (
  <div className="relative">
    {[0, 1, 2].map((i) => (
      <motion.div
        key={i}
        className="absolute inset-0 rounded-full border-2 border-mint-300"
        animate={{
          scale: [1, 1.8, 2.4],
          opacity: [0.6, 0.3, 0],
        }}
        transition={{
          duration: 1.6,
          ease: "easeOut",
          repeat: Infinity,
          delay: i * 0.4,
        }}
      />
    ))}
    <MetoAuraCore />
  </div>
);
```

### 2.4 Answering — "Glow mềm"

```typescript
const answeringVariants = {
  animate: {
    scale: [1, 1.03, 1],
    filter: [
      "brightness(1) drop-shadow(0 0 8px rgba(94, 203, 200, 0.4))",
      "brightness(1.15) drop-shadow(0 0 20px rgba(94, 203, 200, 0.7))",
      "brightness(1) drop-shadow(0 0 8px rgba(94, 203, 200, 0.4))",
    ],
    transition: {
      duration: 1.5,
      ease: "easeInOut",
      repeat: Infinity,
    },
  },
};
```

### 2.5 Completed — "Burst + Tim nhỏ"

```typescript
const CompletedBurst = () => {
  const particles = Array.from({ length: 6 }, (_, i) => ({
    angle: i * 60,
    delay: i * 0.05,
  }));

  return (
    <motion.div>
      {/* Particle burst */}
      {particles.map(({ angle, delay }) => (
        <motion.div
          key={angle}
          className="absolute w-1.5 h-1.5 rounded-full bg-mint-400"
          style={{ originX: "50%", originY: "50%" }}
          animate={{
            x: Math.cos((angle * Math.PI) / 180) * 24,
            y: Math.sin((angle * Math.PI) / 180) * 24,
            opacity: [1, 0],
            scale: [1, 0.5],
          }}
          transition={{ duration: 0.5, delay, ease: "easeOut" }}
        />
      ))}
      {/* Small heart */}
      <motion.div
        className="absolute inset-0 flex items-center justify-center text-xs"
        animate={{ opacity: [0, 1, 0], scale: [0.5, 1.2, 1] }}
        transition={{ duration: 0.8, delay: 0.3 }}
      >
        ❤️
      </motion.div>
    </motion.div>
  );
};
```

---

## 3. Floating Button Specification

### 3.1 Layout & Position

```css
.floating-meto-button {
  position: fixed;
  bottom: 88px;          /* Trên bottom nav bar (60px) + 28px spacing */
  right: 16px;
  z-index: 1000;         /* Trên tất cả content, dưới modals (1100+) */
  width: 56px;
  height: 56px;
  cursor: pointer;
  touch-action: manipulation;
}

/* Label text "Hỏi Meto" */
.floating-meto-label {
  position: absolute;
  bottom: -20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  font-weight: 600;
  color: var(--meto-mint-primary);
  white-space: nowrap;
  letter-spacing: 0.02em;
}
```

### 3.2 States

| State | Visual |
|-------|--------|
| Default | Aura idle animation |
| Hover (desktop) | Scale 1.05, brighter glow |
| Pressed | Scale 0.95, brief |
| Chat open | Button transforms to "close" (X), Aura shows answering/thinking state |
| Loading | Thinking animation |

### 3.3 Behavior
- Tap để mở ChatSheet (bottom sheet slide up)
- Không disappear khi sheet mở (button biến thành close button)
- Không block scrollable content — tự động ẩn khi scroll down 200px, hiện lại khi scroll up

---

## 4. Chat UI — Bottom Sheet Specification

### 4.1 Container

```css
.chat-sheet {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1100;

  /* Bottom sheet sizing */
  height: 75vh;             /* Default: 75% màn hình */
  max-height: calc(100vh - 56px);  /* Trừ safe area top */
  min-height: 320px;

  /* Visual */
  background: rgba(250, 253, 253, 0.97);
  backdrop-filter: blur(20px);
  border-radius: 24px 24px 0 0;
  box-shadow: 0 -4px 40px rgba(0, 0, 0, 0.12);

  /* Animation */
  transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Drag handle */
.chat-sheet-handle {
  width: 36px;
  height: 4px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 2px;
  margin: 10px auto 0;
}
```

### 4.2 Chat Header

```
┌──────────────────────────────────────────┐
│  ━━━━━  (drag handle)                    │
│                                          │
│  [Aura 40px]  Meto                [X]   │
│               AI Health Companion        │
└──────────────────────────────────────────┘
```

### 4.3 Message Bubbles

```css
/* User bubble */
.chat-bubble-user {
  background: var(--meto-mint-primary);
  color: white;
  border-radius: 18px 18px 4px 18px;
  padding: 12px 16px;
  max-width: 80%;
  font-size: 15px;
  line-height: 1.5;
  align-self: flex-end;
}

/* Meto bubble */
.chat-bubble-meto {
  background: white;
  color: #1A1A2E;
  border-radius: 18px 18px 18px 4px;
  padding: 14px 16px;
  max-width: 88%;       /* Rộng hơn — response thường dài hơn */
  font-size: 15px;
  line-height: 1.6;     /* Dễ đọc hơn */
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  align-self: flex-start;
}
```

### 4.4 Input Area

```css
.chat-input-container {
  padding: 12px 16px;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
  background: white;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.chat-input {
  flex: 1;
  min-height: 44px;       /* Touch target minimum */
  max-height: 120px;
  border-radius: 22px;
  border: 1.5px solid rgba(94, 203, 200, 0.3);
  padding: 10px 44px 10px 16px;
  font-size: 15px;
  background: #F8FFFE;
  resize: none;
}

.chat-send-button {
  width: 44px;
  height: 44px;
  border-radius: 22px;
  background: var(--meto-mint-primary);
  /* Disabled state khi input empty */
}
```

---

## 5. Quick Prompt Chips

### Design

```css
.quick-prompt-chip {
  display: inline-flex;
  align-items: center;
  padding: 8px 14px;
  border-radius: 20px;
  border: 1.5px solid var(--meto-mint-primary);
  background: rgba(94, 203, 200, 0.08);
  color: var(--meto-mint-deep);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  min-height: 36px;     /* Đảm bảo tap target ≥ 44px khi kết hợp với padding */
  touch-action: manipulation;
  transition: background 0.15s;
}

.quick-prompt-chip:active {
  background: rgba(94, 203, 200, 0.2);
  transform: scale(0.98);
}
```

### Layout

```
┌─────────────────────────────────────────────┐
│  Meto ở đây để giúp bạn! Hôm nay bạn       │
│  muốn hỏi gì?                               │
│                                             │
│  [Hôm nay cần chú ý gì?] [Tóm tắt sức...] │
│  [Việc cần làm hôm nay]                     │
│                                             │
│  ─────────────────────────────────────────  │
│  [Input placeholder: "Nhập câu hỏi..."] [→]│
└─────────────────────────────────────────────┘
```

Quick prompts scroll horizontally (single row) với `overflow-x: auto; scroll-snap-type: x`.

---

## 6. Medical Disclaimer

### Vị trí
- **Lần đầu mở chat:** Banner trên cùng của chat sheet, dismissible
- **Sau mỗi response:** Micro-disclaimer ở cuối mỗi message block (nhỏ, mờ)

### Design — Banner (lần đầu)

```
┌─────────────────────────────────────────────┐
│ ℹ️  Thông tin từ Meto chỉ để tham khảo,    │
│    không thay thế tư vấn y tế.              │
│    Tìm hiểu thêm                        [X]│
└─────────────────────────────────────────────┘
```

```css
.disclaimer-banner {
  background: rgba(94, 203, 200, 0.08);
  border-left: 3px solid var(--meto-mint-primary);
  padding: 8px 12px;
  font-size: 12px;
  color: #5a6a6a;
  line-height: 1.4;
}
```

### Design — Micro-disclaimer (mỗi response)

```
Thông tin tham khảo · Không thay thế tư vấn bác sĩ
```

```css
.micro-disclaimer {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
  margin-top: 6px;
  font-style: italic;
}
```

---

## 7. Mobile Viewport Requirements

### Target viewports
- iPhone SE (375 × 667px) — minimum
- iPhone 14 / 15 (390 × 844px) — primary
- iPhone 14 Plus / 15 Plus (430 × 932px) — large
- iPad Mini (768px) — tablet

### Responsive rules
```css
/* Bottom sheet height theo viewport */
@media (max-height: 700px) {
  .chat-sheet { height: 85vh; }
}

@media (min-width: 768px) {
  /* Tablet: sheet biến thành side panel */
  .chat-sheet {
    width: 400px;
    height: 100vh;
    top: 0;
    right: 0;
    left: auto;
    border-radius: 0;
  }
}
```

### Safe area handling

```css
/* iOS notch/home indicator */
.chat-sheet {
  padding-bottom: env(safe-area-inset-bottom);
}
.floating-meto-button {
  bottom: calc(88px + env(safe-area-inset-bottom));
}
```

---

## 8. Accessibility

### Touch Target
- **Minimum:** 44 × 44px cho tất cả interactive elements
- Floating button: 56 × 56px ✅
- Send button: 44 × 44px ✅
- Quick prompt chips: min-height 44px ✅
- Close button (X): 44 × 44px ✅

### Font Size
- Chat messages: 15px minimum (không dưới 14px)
- Timestamps: 12px (grey, secondary)
- Disclaimers: 11–12px
- Input: 15px (iOS không zoom khi ≥ 16px — check on device)

### Color Contrast
- User bubble: white text trên `#5ECBC8` → ratio ~3.5:1 (AA for large text)
- Meto bubble: `#1A1A2E` trên white → ratio 17:1 (AAA)
- Disclaimer text: `#5a6a6a` trên white → ratio ~5.7:1 (AA)

### Screen Reader
```tsx
<button
  aria-label="Mở Meto - AI Health Companion"
  aria-expanded={isOpen}
  role="button"
>
  <MetoAura state={auraState} aria-hidden="true" />
  <span className="sr-only">Hỏi Meto</span>
</button>

<div
  role="dialog"
  aria-modal="true"
  aria-label="Trò chuyện với Meto"
  aria-live="polite"
>
  {/* Chat content */}
</div>
```

---

## 9. Component List (Frontend)

### New components cần tạo

| Component | File path | Mô tả |
|-----------|-----------|-------|
| `MetoAura` | `components/meto/MetoAura.tsx` | Quả cầu ánh sáng, nhận prop `state` |
| `FloatingMetoButton` | `components/meto/FloatingMetoButton.tsx` | Fixed button + label |
| `ChatSheet` | `components/meto/ChatSheet.tsx` | Bottom sheet container |
| `ChatBubble` | `components/meto/ChatBubble.tsx` | Message bubble (user + meto) |
| `QuickPromptChips` | `components/meto/QuickPromptChips.tsx` | Horizontal scroll chips |
| `MetoTypingIndicator` | `components/meto/TypingIndicator.tsx` | 3 dots + thinking aura |
| `DisclaimerBanner` | `components/meto/DisclaimerBanner.tsx` | Dismissible banner |
| `ConsentModal` | `components/meto/ConsentModal.tsx` | Consent flow modal |
| `MemoryOptInSheet` | `components/meto/MemoryOptInSheet.tsx` | Memory opt-in flow |
| `MetoProvider` | `contexts/MetoContext.tsx` | Context: chat state, screen_id |

### Modified components

| Component | Thay đổi |
|-----------|---------|
| `DashboardScreen` | Inject `FloatingMetoButton` + `MetoProvider` |
| `LabsScreen` | Inject floating button + inline "Hỏi Meto" per result |
| `MedicationsScreen` | Inject floating button + inline per medication |
| `MetricsScreen` | Inject floating button + tooltip on chart tap |
| `NutritionScreen` | Inject floating button |
| `CarePlanScreen` | Inject floating button |
| `ProfileScreen` | Inject floating button |
| `AppLayout` | Wrap với `MetoProvider` if global state needed |

---

*Xem thêm: 06_IMPLEMENTATION_PLAN.md (phase triển khai), 07_ACCEPTANCE_TESTS.md (UX test cases)*
