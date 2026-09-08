export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

/** `key` identifies which icon/label a KPI is — data over the wire never
 * carries a component reference, so the frontend maps key -> icon locally
 * (see features/dashboard/AdminDashboardPage.tsx). */
export type KpiKey = "total_orders" | "pending_orders" | "completed_today" | "open_tickets";

export interface DashboardKpi {
  key: KpiKey;
  label: string;
  value: string;
  delta: string;
  tone: Tone;
}

export interface DashboardAlert {
  id: string;
  title: string;
  region: string;
  severity: "high" | "medium";
}

export interface RegionStat {
  name: string;
  completionPct: number;
  openIssues: number;
}

export interface EmployeeStat {
  name: string;
  region: string;
  assigned: number;
  completed: number;
}

export interface ActivityItem {
  time: string;
  text: string;
  tone: Tone;
}

export interface AdminDashboard {
  kpis: DashboardKpi[];
  alerts: DashboardAlert[];
  regions: RegionStat[];
  employees: EmployeeStat[];
  activity: ActivityItem[];
}

export interface EmployeeDashboard {
  assignedToday: number;
  completedToday: number;
  pending: number;
  tickets: DashboardAlert[];
  activity: ActivityItem[];
}
