import { useState, type ReactNode } from "react";
import { Button } from "./ui/Button";

/** A two-step button for deletes: the first click asks, the second click does it. No browser pop-ups. */
export function ConfirmButton({ label, confirmLabel = "Yes, delete", onConfirm, busy, icon }: {
  label: string;
  confirmLabel?: string;
  onConfirm: () => void | Promise<void>;
  busy?: boolean;
  icon?: ReactNode;
}) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return <Button variant="danger" icon={icon} onClick={() => setAsking(true)} aria-label={label}>{label}</Button>;
  }
  return (
    <span className="inline-flex items-center gap-2" role="group" aria-label="Confirm">
      <Button variant="danger" busy={busy} onClick={() => { void Promise.resolve(onConfirm()).finally(() => setAsking(false)); }}>{confirmLabel}</Button>
      <Button variant="secondary" onClick={() => setAsking(false)}>Cancel</Button>
    </span>
  );
}
