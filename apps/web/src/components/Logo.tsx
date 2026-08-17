// SPDX-License-Identifier: Apache-2.0

interface LogoProps {
  className?: string
}

export function Logo({ className }: LogoProps) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      role="img"
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient gradientUnits="userSpaceOnUse" id="logo-bg" x1="32" x2="32" y1="2" y2="62">
          <stop stopColor="#1E293B" />
          <stop offset="1" stopColor="#0F172A" />
        </linearGradient>
        <linearGradient gradientUnits="userSpaceOnUse" id="logo-sweep" x1="32" x2="50" y1="32" y2="14">
          <stop stopColor="#38BDF8" stopOpacity="0.55" />
          <stop offset="1" stopColor="#38BDF8" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect fill="url(#logo-bg)" height="60" rx="14" width="60" x="2" y="2" />
      <g transform="translate(32 32)">
        <path d="M0 0 L0 -22 A22 22 0 0 1 19.05 -11 Z" fill="url(#logo-sweep)" />
        <circle fill="none" r="21" stroke="#F8FAFC" strokeOpacity="0.9" strokeWidth="3" />
        <circle fill="none" r="13.5" stroke="#F8FAFC" strokeOpacity="0.45" strokeWidth="2.4" />
        <circle fill="none" r="6" stroke="#F8FAFC" strokeOpacity="0.35" strokeWidth="2" />
        <line stroke="#7DD3FC" strokeLinecap="round" strokeWidth="3" x1="0" x2="0" y1="0" y2="-22" />
        <circle cx="12.4" cy="-12.4" fill="#38BDF8" r="3.6" />
      </g>
    </svg>
  )
}
