import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";
import { apiRequest } from "@/services/api";
import type { GeneratePreview } from "@/features/logins/api";

const PLATFORMS = [
  { value: "blinkit", label: "Blinkit stores" },
  { value: "zepto", label: "Zepto stores" },
  { value: "all", label: "All platforms" },
];

/** Developer: build the vendor and POC logins from the stores' vendor / POC columns. A preview comes first; nothing is written until you confirm. */
export function GenerateLoginsModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [platform, setPlatform] = useState("blinkit");
  const [preview, setPreview] = useState<GeneratePreview | null>(null);

  const run = useMutation({
    mutationFn: async (dryRun: boolean) =>
      camelize<GeneratePreview>(await apiRequest("/external-accounts/generate", { method: "POST", body: { platform, dry_run: dryRun } })),
  });

  async function doPreview() {
    setPreview(await run.mutateAsync(true));
  }
  async function create() {
    const r = await run.mutateAsync(false);
    void qc.invalidateQueries({ queryKey: ["logins"] });
    pushToast(`${r.applied?.created ?? 0} logins created, ${r.applied?.updated ?? 0} refreshed.`, "success");
    onClose();
  }

  const total = preview ? preview.vendors.accounts + preview.pocs.accounts : 0;
  return (
    <Modal
      open
      onClose={onClose}
      title="Create logins from stores"
      description="Builds a login for every vendor and POC named in the stores. People who already have one keep their password; their store list is refreshed."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" onClick={doPreview} isLoading={run.isPending && !preview}>Preview</Button>
          <Button onClick={create} isLoading={run.isPending && Boolean(preview)} disabled={!preview || total === 0}>Create {total ? total.toLocaleString("en-IN") : ""} logins</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Select label="Which stores" value={platform} onChange={(e) => { setPlatform(e.target.value); setPreview(null); }} options={PLATFORMS} />
        {preview && (
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            {([["Vendors", preview.vendors], ["POCs", preview.pocs]] as const).map(([label, p]) => (
              <div key={label} className="rounded-xl border border-surface-border p-3">
                <p className="text-[11px] font-bold text-gray-500">{label}</p>
                <p className="text-xl font-extrabold tabular-nums text-heading">{p.accounts.toLocaleString("en-IN")}</p>
                <p className="text-xs text-gray-500">{p.skipped} placeholder names skipped · {p.sharedNames} names shared by several people</p>
                <ul className="mt-2 space-y-0.5 text-xs text-gray-700">
                  {p.examples.map((x) => <li key={x.email} className="truncate">{x.email} <span className="text-gray-500">· {x.name} · {x.stores} store{x.stores === 1 ? "" : "s"}</span></li>)}
                </ul>
              </div>
            ))}
          </div>
        )}
        {preview && total === 0 && <p className="text-sm text-status-warning">No vendor or POC names were found in these stores, so there is nothing to create.</p>}
        <p className="text-xs text-gray-500">New logins use the standard first password and must change it at first sign-in.</p>
      </div>
    </Modal>
  );
}
