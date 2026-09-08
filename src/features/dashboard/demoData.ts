import type { AdminDashboard, EmployeeDashboard } from "@/types/dashboard";

// Fallback shown ONLY when GET /dashboard/admin or /dashboard/employee
// isn't reachable yet (Phase 3/4 backend work). useDashboardData.ts shows
// a "demo data" banner alongside this so it's never mistaken for live
// numbers. Delete this file once both backend endpoints ship.
export const DEMO_ADMIN_DASHBOARD: AdminDashboard = {
  kpis: [
    { key: "total_orders", label: "Total Orders", value: "1,284", delta: "+8.2% vs last week", tone: "info" },
    { key: "pending_orders", label: "Pending Orders", value: "96", delta: "12 unassigned 2h+", tone: "warning" },
    { key: "completed_today", label: "Completed Today", value: "212", delta: "+12% vs yesterday", tone: "success" },
    { key: "open_tickets", label: "Open Tickets", value: "34", delta: "5 critical", tone: "danger" },
  ],
  alerts: [
    { id: "a1", title: "12 orders unassigned for over 2 hours", region: "Delhi NCR", severity: "high" },
    { id: "a2", title: "Store #4821 reported 3 damaged-bottle tickets today", region: "Gurugram", severity: "medium" },
    { id: "a3", title: "Employee Rahul S. has 0 completions since 9 AM", region: "Delhi NCR", severity: "medium" },
  ],
  regions: [
    { name: "Delhi NCR", completionPct: 92, openIssues: 3 },
    { name: "Mumbai", completionPct: 81, openIssues: 6 },
    { name: "Bengaluru", completionPct: 74, openIssues: 9 },
    { name: "Pune", completionPct: 65, openIssues: 4 },
  ],
  employees: [
    { name: "Rahul Sharma", region: "Delhi NCR", assigned: 24, completed: 21 },
    { name: "Priya Nair", region: "Mumbai", assigned: 18, completed: 17 },
    { name: "Aman Verma", region: "Bengaluru", assigned: 20, completed: 12 },
    { name: "Sana Khan", region: "Pune", assigned: 15, completed: 14 },
  ],
  activity: [
    { time: "11:15 AM", text: "Order #10482 verified by Priya Nair", tone: "success" },
    { time: "10:52 AM", text: "Ticket #2291 marked critical — Store #77, Gurugram", tone: "danger" },
    { time: "10:37 AM", text: "Order #10481 started by Rahul Sharma", tone: "info" },
    { time: "9:58 AM", text: "5 new orders assigned to Bengaluru region", tone: "neutral" },
  ],
};

export const DEMO_EMPLOYEE_DASHBOARD: EmployeeDashboard = {
  assignedToday: 8,
  completedToday: 5,
  pending: 3,
  tickets: [{ id: "t1", title: "Store #77 reported a damaged bottle", region: "Your route", severity: "medium" }],
  activity: [
    { time: "11:02 AM", text: "Order #10481 completed", tone: "success" },
    { time: "10:20 AM", text: "Order #10479 started", tone: "info" },
  ],
};
