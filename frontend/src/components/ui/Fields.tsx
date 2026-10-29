import { useId, type ReactNode } from "react";

const input =
  "w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-muted/70 focus:border-ocean-600 disabled:bg-paper disabled:text-muted";

function Field({ label, hint, id, children }: { label: string; hint?: ReactNode; id: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
  hint,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  hint?: ReactNode;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <Field label={label} hint={hint} id={id}>
      <select id={id} className={input} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  hint,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  hint?: ReactNode;
}) {
  const id = useId();
  const outOfRange = Number.isNaN(value) || value < min || value > max;
  return (
    <Field label={label} hint={outOfRange ? <span className="text-danger">Enter a value from {min} to {max}.</span> : hint} id={id}>
      <input
        id={id}
        type="number"
        className={`${input} ${outOfRange ? "border-danger" : ""}`}
        value={Number.isNaN(value) ? "" : value}
        min={min}
        max={max}
        step={step ?? 1}
        aria-invalid={outOfRange}
        onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
      />
    </Field>
  );
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "search" | "date";
  id?: string;
}) {
  const id = useId();
  return (
    <Field label={label} id={id}>
      <input id={id} type={type} className={input} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

export function ToggleField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  hint?: ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-2">
      <input
        id={id}
        type="checkbox"
        className="mt-1 h-4 w-4 rounded border-line accent-ocean-700"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <label htmlFor={id} className="text-sm text-ink">
        {label}
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </label>
    </div>
  );
}


/** A row of toggle chips for picking several values (for example log levels). */
export function ChipGroup({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (value: string[]) => void;
}) {
  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1 block text-sm font-medium text-ink">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = selected.includes(o.value);
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(o.value)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                on ? "border-ocean-700 bg-ocean-700 text-white" : "border-line bg-surface text-ink hover:bg-ocean-50"
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
