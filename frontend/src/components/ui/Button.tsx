import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const styles: Record<Variant, string> = {
  primary: "bg-ocean-700 text-white hover:bg-ocean-800 disabled:bg-slate-300",
  secondary: "bg-surface text-ink border border-line hover:bg-ocean-50 disabled:text-muted",
  ghost: "text-ocean-700 hover:bg-ocean-50 disabled:text-muted",
  danger: "bg-surface text-danger border border-danger/40 hover:bg-danger-bg disabled:text-muted",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  busy?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "primary", busy = false, icon, children, className = "", disabled, ...rest }: Props) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles[variant]} ${className}`}
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}
