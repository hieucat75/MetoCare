'use client'

import Link from 'next/link'

export default function StartPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#E8EEE8] px-6 max-w-md mx-auto">
      <div
        className="w-20 h-20 rounded-3xl flex items-center justify-center mb-8"
        style={{
          backgroundColor: 'rgba(15,156,110,0.12)',
          boxShadow: '0 0 0 1px rgba(15,156,110,0.2)',
        }}
      >
        <svg width="44" height="44" viewBox="0 0 52 52" fill="none" aria-label="MetoCare">
          <path
            d="M26 8C16.059 8 8 16.059 8 26s8.059 18 18 18 18-8.059 18-18S35.941 8 26 8zm0 4a14 14 0 1 1 0 28 14 14 0 0 1 0-28z"
            fill="#0F9C6E"
            fillOpacity="0.9"
          />
          <path
            d="M18 26l5 5 11-11"
            stroke="#0F9C6E"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <h1 className="text-[26px] font-extrabold text-[#2B4040] tracking-tight text-center">
        Chào mừng đến MetoCare
      </h1>
      <p className="mt-2 text-[15px] text-[#2B4040]/70 text-center leading-relaxed max-w-[28ch]">
        Quản lý chuyển hoá, theo dõi chỉ số, kết nối bác sĩ.
      </p>

      <div className="mt-10 w-full space-y-3">
        <Link
          href="/login"
          className="w-full flex items-center justify-center text-[16px] font-bold py-4 rounded-[16px] text-white no-underline"
          style={{
            background: 'linear-gradient(160deg,#17AE7B,#0B6B4D)',
            boxShadow: '0 8px 20px -6px rgba(11,107,77,0.45)',
          }}
        >
          Đăng nhập
        </Link>
        <Link
          href="/register"
          className="w-full flex items-center justify-center text-[16px] font-bold py-4 rounded-[16px] border-2 border-[#0F9C6E] text-[#0F9C6E] no-underline"
          style={{ backgroundColor: 'rgba(15,156,110,0.06)' }}
        >
          Tạo tài khoản mới
        </Link>
      </div>

      <p className="mt-8 text-[11px] text-[#2B4040]/50 text-center px-4">
        Bằng cách tiếp tục, bạn đồng ý với Điều khoản dịch vụ và Chính sách bảo mật của MetoCare.
      </p>
    </div>
  )
}
