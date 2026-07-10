"use client";

import { useEffect, useRef } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
  compact?: boolean;
  autoFocus?: boolean;
}

export default function QueryComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Ask a clinical dose question…",
  compact,
  autoFocus,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  return (
    <form
      className={`composer${compact ? " compact" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (!disabled && value.trim()) onSubmit();
      }}
    >
      <textarea
        ref={ref}
        className="composer-input"
        rows={1}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!disabled && value.trim()) onSubmit();
          }
        }}
        aria-label="Clinical query"
      />
      <div className="composer-toolbar">
        <div className="composer-left">
          <span className="composer-pill active">⌕ Search</span>
          <span className="composer-pill">⚙ Allometry × maturation</span>
        </div>
        <button
          type="submit"
          className="composer-submit"
          disabled={disabled || !value.trim()}
          aria-label="Submit query"
          title="Extrapolate dose"
        >
          ↑
        </button>
      </div>
    </form>
  );
}
