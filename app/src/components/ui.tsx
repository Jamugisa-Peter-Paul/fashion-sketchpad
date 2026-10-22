"use client";

import { ChevronLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white active:bg-accent-strong disabled:bg-accent/40",
  secondary: "bg-surface text-ink border border-line active:bg-canvas disabled:text-muted",
  ghost: "text-ink active:bg-line/60 disabled:text-muted",
  danger: "bg-surface text-danger border border-danger/30 active:bg-danger/5",
};

export function Button({
  variant = "primary",
  loading = false,
  block = false,
  icon,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  loading?: boolean;
  block?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 text-[15px] font-medium transition-colors",
        VARIANTS[variant],
        block && "w-full",
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="size-5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Chip({
  selected,
  onClick,
  children,
  disabled,
  className,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "min-h-11 rounded-full border px-4 text-sm font-medium transition-colors",
        selected ? "border-ink bg-ink text-white" : "border-line bg-surface text-ink active:bg-canvas",
        disabled && "opacity-40",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex rounded-xl bg-line/60 p-1" role="radiogroup">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          role="radio"
          aria-checked={option.id === value}
          onClick={() => onChange(option.id)}
          className={cx(
            "min-h-10 flex-1 rounded-lg px-3 text-sm font-medium transition-colors",
            option.id === value ? "bg-surface text-ink shadow-sm" : "text-muted",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-muted">{title}</h2>
        {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

const STEPS = ["Start", "Sketch", "Style", "Generate"];

export function TopBar({
  title,
  back,
  step,
  right,
}: {
  title: string;
  /** href to go to, or true for history back */
  back?: string | true;
  step?: number;
  right?: ReactNode;
}) {
  const router = useRouter();
  return (
    <header className="safe-top sticky top-0 z-20 border-b border-line bg-canvas/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-2">
        {back ? (
          back === true ? (
            <button type="button" aria-label="Back" onClick={() => router.back()} className="grid size-11 place-items-center rounded-full active:bg-line/60">
              <ChevronLeft className="size-6" />
            </button>
          ) : (
            <Link href={back} aria-label="Back" className="grid size-11 place-items-center rounded-full active:bg-line/60">
              <ChevronLeft className="size-6" />
            </Link>
          )
        ) : (
          <span className="w-3" />
        )}
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[17px] font-semibold">{title}</h1>
          {step !== undefined && (
            <p className="text-xs text-muted">
              Step {step + 1} of {STEPS.length} · {STEPS[step]}
            </p>
          )}
        </div>
        {right}
      </div>
      {step !== undefined && (
        <div className="mx-auto flex max-w-6xl gap-1 px-4 pb-2">
          {STEPS.map((name, index) => (
            <span key={name} className={cx("h-1 flex-1 rounded-full", index <= step ? "bg-accent" : "bg-line")} />
          ))}
        </div>
      )}
    </header>
  );
}

export function BottomBar({ children }: { children: ReactNode }) {
  return (
    <div className="safe-bottom sticky bottom-0 z-20 border-t border-line bg-canvas/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl gap-3 px-4 pt-3">{children}</div>
    </div>
  );
}

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <main className={cx("mx-auto w-full max-w-6xl flex-1 px-4 py-5", className)}>{children}</main>;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error" | "warn"; children: ReactNode }) {
  const tones = {
    info: "bg-surface border-line text-ink",
    warn: "bg-amber-50 border-amber-200 text-amber-900",
    error: "bg-red-50 border-red-200 text-danger",
  };
  return <div className={cx("rounded-xl border px-4 py-3 text-sm", tones[tone])}>{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-muted">
      <Loader2 className="size-5 animate-spin" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}
