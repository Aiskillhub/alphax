/* AlphaX Icons — ChatGPT-style geometric SVG */

export const SparkIcon = ({ className = "w-6 h-6" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l1.5 5.5L19 7l-4 4 2.5 6L12 13.5 6.5 17 9 11l-4-4 5.5 1.5L12 3z" />
    <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
  </svg>
);

export const AgentIcon = ({ className = "w-6 h-6" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
    <line x1="6.5" y1="10" x2="6.5" y2="14" />
    <line x1="17.5" y1="10" x2="17.5" y2="14" />
    <line x1="10" y1="6.5" x2="14" y2="6.5" />
    <line x1="10" y1="17.5" x2="14" y2="17.5" />
  </svg>
);

export const NetworkIcon = ({ className = "w-6 h-6" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="5" cy="5" r="2.5" />
    <circle cx="19" cy="5" r="2.5" />
    <circle cx="12" cy="19" r="2.5" />
    <line x1="7.2" y1="6.5" x2="10.8" y2="16.5" />
    <line x1="16.8" y1="6.5" x2="13.2" y2="16.5" />
    <line x1="5" y1="7.5" x2="19" y2="7.5" strokeDasharray="2 2" opacity="0.3" />
  </svg>
);

export const ChevronIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 4l4 4-4 4" />
  </svg>
);

export const ArrowLeftIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 4L6 8l4 4" />
  </svg>
);

export const DownloadIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M8 3v8M5 8l3 3 3-3M3 13h10" />
  </svg>
);

export const RefreshIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 8a6 6 0 0111.3-3.3M14 8a6 6 0 01-11.3 3.3" />
    <polyline points="12.5,3.5 14,2 14,5 11,5" />
    <polyline points="3.5,12.5 2,14 5,14 5,11" />
  </svg>
);

export const CheckIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 8l3 3 7-7" />
  </svg>
);

export const TrophyIcon = ({ className = "w-6 h-6" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 4h12v3a4 4 0 01-4 4h-4a4 4 0 01-4-4V4z" />
    <path d="M8 4V3h8v1M6 8H4a2 2 0 000 4h1M18 8h2a2 2 0 010 4h-1M12 11v7M8 18h8" />
  </svg>
);

export const PulseIcon = ({ className = "w-3 h-3" }) => (
  <svg className={className} viewBox="0 0 12 12" fill="currentColor">
    <circle cx="6" cy="6" r="5" opacity="0.3" />
    <circle cx="6" cy="6" r="2.5" />
  </svg>
);
