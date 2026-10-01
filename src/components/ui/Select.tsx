import type { ChangeEvent, SelectHTMLAttributes } from "react";
import { Dropdown } from "@/components/ui/Dropdown";

interface Option {
  value: string;
  label: string;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "value"> {
  label: string;
  error?: string;
  options: Option[];
  placeholder?: string;
  value?: string;
  onChange?: (e: ChangeEvent<HTMLSelectElement>) => void;
}

/** Labelled form dropdown. Keeps the `<select>` calling convention (`onChange(e)` → `e.target.value`). */
export function Select({ label, error, options, placeholder, id, className = "", value = "", onChange, disabled }: SelectProps) {
  const selectId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <label htmlFor={selectId} className="text-sm font-medium text-gray-700">
        {label}
      </label>
      <Dropdown
        id={selectId}
        value={value}
        options={options}
        placeholder={placeholder}
        disabled={disabled}
        invalid={Boolean(error)}
        onValueChange={(v) => onChange?.({ target: { value: v }, currentTarget: { value: v } } as unknown as ChangeEvent<HTMLSelectElement>)}
      />
      {error && <p className="text-sm text-status-danger">{error}</p>}
    </div>
  );
}
