import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { usePermission } from "@/hooks/usePermission";
import { getDeviceLocation } from "@/lib/geo";
import { pushToast } from "@/lib/toast";
import { useOfficeMutations, useOffices } from "@/features/attendance/api";

const field = "h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

export function OfficesView() {
  const canManage = usePermission("attendance.manage");
  const { data, isLoading, isError, refetch } = useOffices();
  const { create, update, remove } = useOfficeMutations();

  const [name, setName] = useState("");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [radius, setRadius] = useState("100");
  const [locating, setLocating] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function fillFromDevice() {
    setLocating(true);
    setNote(null);
    const loc = await getDeviceLocation(10000);
    setLocating(false);
    if (!loc) {
      setNote("Couldn't read your location — allow location access in the browser, or type the coordinates in.");
      return;
    }
    setLat(loc.latitude.toFixed(6));
    setLng(loc.longitude.toFixed(6));
    setNote(`Filled from this device (accurate to about ${Math.round(loc.accuracy)} m). Stand inside the office when you do this.`);
  }

  const latN = Number(lat);
  const lngN = Number(lng);
  const radiusN = Number(radius);
  const valid = name.trim() && lat !== "" && lng !== "" && latN >= -90 && latN <= 90 && lngN >= -180 && lngN <= 180 && radiusN >= 10 && radiusN <= 5000;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    create.mutate(
      { name: name.trim(), latitude: latN, longitude: lngN, radius_m: radiusN },
      { onSuccess: () => { setName(""); setLat(""); setLng(""); setRadius("100"); setNote(null); } },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <p className="rounded-lg bg-surface-subtle px-4 py-3 text-sm text-gray-600">
        When someone signs in, their location is compared with these offices. <b>Within the radius</b> (100 m by default) the attendance
        shows the <b>office name</b>; anywhere else it shows their <b>exact coordinates</b> with a map link.
      </p>

      {isLoading && <Skeleton className="h-32" />}
      {isError && <ErrorState message="Couldn't load offices." onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <div className="rounded-xl border border-dashed border-status-warning/40 bg-status-warning-soft/40 px-5 py-4 text-sm text-status-warning">
          <b>No office is set up yet.</b> Until you add one, every sign-in is shown by its exact coordinates.
        </div>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3">Office</th>
                <th className="px-3 py-3">Location</th>
                <th className="px-3 py-3">Radius</th>
                <th className="px-3 py-3">Status</th>
                {canManage && <th className="px-4 py-3 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {data.map((o) => (
                <tr key={o.id} className="border-t border-surface-border/70">
                  <td className="px-4 py-3 font-medium text-gray-900">{o.name}</td>
                  <td className="px-3 py-3">
                    <a href={o.mapUrl} target="_blank" rel="noreferrer" className="font-mono text-xs font-medium text-brand-600 hover:text-brand-700">
                      {o.latitude.toFixed(6)}, {o.longitude.toFixed(6)}
                    </a>
                  </td>
                  <td className="px-3 py-3">
                    {canManage ? (
                      <label className="flex items-center gap-1.5 text-sm">
                        <input
                          type="number"
                          min={10}
                          max={5000}
                          defaultValue={o.radiusM}
                          aria-label={`Radius for ${o.name} in metres`}
                          onBlur={(e) => {
                            const v = Number(e.target.value);
                            if (v !== o.radiusM && v >= 10 && v <= 5000) update.mutate({ id: o.id, radius_m: v });
                            else e.target.value = String(o.radiusM);
                          }}
                          className="h-8 w-20 rounded-md border border-surface-border px-2 text-sm tabular-nums"
                        />
                        m
                      </label>
                    ) : (
                      `${o.radiusM} m`
                    )}
                  </td>
                  <td className="px-3 py-3"><Badge tone={o.isActive ? "success" : "neutral"}>{o.isActive ? "Active" : "Off"}</Badge></td>
                  {canManage && (
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-3 text-sm font-semibold">
                        <button className="text-brand-600 hover:text-brand-700" onClick={() => update.mutate({ id: o.id, is_active: !o.isActive })}>
                          {o.isActive ? "Turn off" : "Turn on"}
                        </button>
                        <button
                          className="text-status-danger hover:opacity-80"
                          onClick={() => window.confirm(`Remove ${o.name}? Past sign-ins keep their label.`) && remove.mutate(o.id)}
                        >
                          Remove
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {canManage ? (
        <form onSubmit={submit} className="rounded-xl border border-surface-border bg-surface p-5 shadow-card">
          <h3 className="text-sm font-bold text-gray-900">Add an office</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500 lg:col-span-2">
              Name
              <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Head office" />
            </label>
            <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
              Latitude
              <input className={field} value={lat} onChange={(e) => setLat(e.target.value)} placeholder="12.971600" inputMode="decimal" />
            </label>
            <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
              Longitude
              <input className={field} value={lng} onChange={(e) => setLng(e.target.value)} placeholder="77.594600" inputMode="decimal" />
            </label>
            <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
              Radius (metres)
              <input className={field} type="number" min={10} max={5000} value={radius} onChange={(e) => setRadius(e.target.value)} />
            </label>
          </div>
          {note && <p className="mt-3 text-xs text-gray-500">{note}</p>}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={() => void fillFromDevice()} isLoading={locating}>
              Use my current location
            </Button>
            <Button type="submit" disabled={!valid} isLoading={create.isPending}>Add office</Button>
          </div>
        </form>
      ) : (
        <p className="text-xs text-gray-400" onClick={() => pushToast("You don't have permission to change offices.", "info")}>
          Only administrators can change offices.
        </p>
      )}
    </div>
  );
}
