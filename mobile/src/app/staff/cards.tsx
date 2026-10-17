import { ComplianceList } from "@/components/ComplianceList";

/** Store cards: the card slot of the existing compliance records, with "Upload card photo" on every store. */
export default function Cards() {
  return <ComplianceList focus="card" />;
}
