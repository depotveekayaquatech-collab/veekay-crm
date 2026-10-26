import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { usePermission } from "@/hooks/usePermission";
import { useHolidayMutations, useHolidays } from "@/features/attendance/api";

const longDay = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

/**
 * Company holidays. A holiday is a day nobody is expected to work: nobody is counted absent, salary pays it like a weekly off, a leave does not use a day on
 * it and employees are not expected to mark entries on it. Admins and developers set them here; a month whose salary is already paid cannot be changed.
 */
export function HolidaysView() {
  const canManage = usePermission("attendance.manage");
  const [year, setYear] = useState(new Date().getFullYear());
  const { data, isLoading, isError, refetch } = useHolidays(year);
  const { add, remove } = useHolidayMutations();
  const [day, setDay] = useState("");
  const [name, setName] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!day || !name.trim()) return;
    add.mutate({ holiday_date: day, name: name.trim() }, { onSuccess: () => { setDay(""); setName(""); } });
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-gray-500">
        On a holiday nobody is counted absent, salary pays the day like a weekly off, a leave does not use a day on it, and employees are not expected to mark entries.
      </p>

      {canManage && (
        <form onSubmit={submit} className="grid gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:grid-cols-[12rem_1fr_auto] sm:items-end">
          <Input label="Date" type="date" value={day} onChange={(e) => setDay(e.target.value)} required />
          <Input label="Holiday name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Diwali" maxLength={128} required />
          <Button type="submit" isLoading={add.isPending} disabled={!day || !name.trim()}>Mark holiday</Button>
        </form>
      )}

      <div className="flex items-center gap-1">
        <Button size="sm" variant="secondary" aria-label="Previous year" onClick={() => setYear(year - 1)}>‹</Button>
        <span className="min-w-[5rem] text-center text-base font-extrabold text-heading">{year}</span>
        <Button size="sm" variant="secondary" aria-label="Next year" onClick={() => setYear(year + 1)}>›</Button>
      </div>

      {isLoading && <Skeleton className="h-40" />}
      {isError && <ErrorState message="Couldn't load the holidays." onRetry={() => refetch()} />}
      {data && (
        data.length === 0 ? (
          <p className="rounded-xl border border-dashed border-surface-border bg-surface px-6 py-10 text-center text-sm text-gray-500">No holidays marked for {year}.</p>
        ) : (
          <ul className="divide-y divide-surface-border overflow-hidden rounded-2xl border border-surface-border bg-surface">
            {data.map((h) => (
              <li key={h.date} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div>
                  <p className="text-sm font-bold text-heading">{h.name}</p>
                  <p className="text-xs text-gray-500">{longDay(h.date)}</p>
                </div>
                {canManage && (
                  <Button size="sm" variant="secondary" isLoading={remove.isPending && remove.variables === h.date}
                    onClick={() => { if (window.confirm(`Remove the holiday "${h.name}" on ${longDay(h.date)}?`)) remove.mutate(h.date); }}>
                    Remove
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}
