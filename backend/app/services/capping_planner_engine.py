"""
Smart Capping Planner - the pure calculation (no database, no web): matching the pasted priority list to the store master, choosing which stores to use, and
laying a target difference over their remaining capacity.

This is CAPACITY PLANNING. Nothing here is supply: a proposed allocation is a number a store COULD still take under its capping, never a count that was delivered,
and nothing in this module (or the service around it) writes a single entry.

Remaining capacity of a store = its monthly limit (daily capping x 30) - what is already recorded for the month, never below 0. A store counts only when it is
verified: it has a valid capping and an Outlet ID, and is not one of several identical records (see capping_planner_service). Two modes:
  max_capacity    the stores with the most remaining capacity, whatever the priority list says
  priority_first  the pasted priority stores first, in the order pasted (a store with no capacity is skipped, with the reason), then the rest by remaining capacity
The store limit applies to both. The target is laid over the chosen stores in that same order, each filled up to (never beyond) its remaining capacity.
"""
from __future__ import annotations

MODES = ("max_capacity", "priority_first")


def norm(text: str) -> str:
    """The key used to compare pasted text with the master: trimmed, one space between words, case ignored."""
    return " ".join((text or "").split()).casefold()


# ---------------------------------------------------------------- priority list -> store master

def match_priority(lines: list[str], master: list[dict], project: str) -> list[dict]:
    """One result per non-blank pasted line, in the order pasted. `master` rows carry store_id, crm_code, outlet_id, name, project.
    A line is tried as the system code, then the Outlet ID, then the exact store name. More than one store behind it is `ambiguous` (never guessed); a store that
    exists only outside the chosen project is `other_project`; nothing is `unmatched`; a store already listed earlier is `duplicate`. Only `matched` entries are used."""
    by_code: dict[str, list[dict]] = {}
    by_outlet: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for m in master:
        by_code.setdefault(norm(m["crm_code"]), []).append(m)
        by_outlet.setdefault(norm(m["outlet_id"]), []).append(m)
        by_name.setdefault(norm(m["name"]), []).append(m)

    out: list[dict] = []
    seen: dict[str, int] = {}
    position = 0
    for raw in lines:
        if not raw.strip():
            continue
        position += 1
        key = norm(raw)
        entry = {"position": position, "raw": raw.strip(), "status": "unmatched", "message": "No store has this system code, Outlet ID or name.",
                 "store_id": None, "crm_code": None, "outlet_id": None, "name": None, "project": None, "candidates": []}
        cands = by_code.get(key) or by_outlet.get(key) or by_name.get(key) or []
        if project != "all":
            inside = [c for c in cands if c["project"] == project]
            if cands and not inside:
                entry.update(status="other_project", message=f"This store belongs to {cands[0]['project'].title()}, outside the selected project.",
                             crm_code=cands[0]["crm_code"], name=cands[0]["name"], project=cands[0]["project"])
                out.append(entry)
                continue
            cands = inside
        if len(cands) > 1:
            entry.update(status="ambiguous", message=f"{len(cands)} stores match. Use the system code to choose one.",
                         candidates=[{"crm_code": c["crm_code"], "outlet_id": c["outlet_id"], "name": c["name"], "project": c["project"]} for c in cands])
        elif cands:
            c = cands[0]
            entry.update(status="matched", message="", store_id=c["store_id"], crm_code=c["crm_code"], outlet_id=c["outlet_id"], name=c["name"], project=c["project"])
            if c["store_id"] in seen:
                entry.update(status="duplicate", message=f"Already listed at position {seen[c['store_id']]}; only the first is used.")
            else:
                seen[c["store_id"]] = position
        out.append(entry)
    return out


# ---------------------------------------------------------------- choosing the stores

def is_eligible(row: dict) -> bool:
    """Verified and with something left."""
    return row["exclude_reason"] is None and row["remaining"] > 0


def _by_capacity(row: dict) -> tuple:
    return (-row["remaining"], row["name"].casefold(), row["crm_code"])


def consideration_order(rows: list[dict], mode: str, priority_ids: list[str]) -> list[dict]:
    """Every eligible store in the order it is considered. `priority_ids` is the matched priority stores in the order pasted."""
    ranked = sorted((r for r in rows if is_eligible(r)), key=_by_capacity)
    if mode != "priority_first":
        return ranked
    by_id = {r["store_id"]: r for r in ranked}
    first = [by_id[i] for i in priority_ids if i in by_id]
    taken = {r["store_id"] for r in first}
    return first + [r for r in ranked if r["store_id"] not in taken]


def _priority_outcome(entry: dict, row: dict | None, selected_ids: set[str], mode: str, limit: int | None) -> str:
    """What happened to one matched priority entry, in words."""
    if row is None:
        return "Not in the selected project or month."
    if row["exclude_reason"]:
        return f"Skipped: {row['exclude_reason']}."
    if row["remaining"] <= 0:
        why = f"already over its limit by {row['over_by']:,}" if row["over_by"] else f"no remaining capacity (limit {row['monthly_limit']:,}, used {row['used']:,})"
        return f"Skipped: {why}."
    if row["store_id"] in selected_ids:
        return "Included."
    if mode == "max_capacity":
        return "Not included: priority does not override capacity ranking in Maximum Capacity mode."
    return f"Not included: the store limit ({limit:,}) was reached before this priority store."


def plan(rows: list[dict], *, mode: str, store_limit: int | None, target: int, priority: list[dict], allocation_allowed: bool = True) -> dict:
    """Choose the stores and lay `target` over them. `rows` are the verified-or-excluded store rows (see the service); `priority` is match_priority's result.
    Returns {"rows": rows with the plan fields filled in, "priority": entries with their outcome, "totals": {...}}. Never allocates beyond remaining capacity."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    matched = [e for e in priority if e["status"] == "matched"]
    priority_ids = [e["store_id"] for e in matched]
    order = consideration_order(rows, mode, priority_ids)
    chosen = order[:store_limit] if store_limit else order
    chosen_ids = {r["store_id"] for r in chosen}
    rank = {r["store_id"]: i + 1 for i, r in enumerate(chosen)}
    priority_rank = {sid: i + 1 for i, sid in enumerate(priority_ids)}

    left = target if allocation_allowed else 0
    allocation: dict[str, int] = {}
    for r in chosen:
        take = min(r["remaining"], left)
        allocation[r["store_id"]] = take
        left -= take

    out_rows = []
    for r in rows:
        sid = r["store_id"]
        alloc = allocation.get(sid, 0)
        out_rows.append({**r, "selected": sid in chosen_ids, "selection_rank": rank.get(sid), "priority_rank": priority_rank.get(sid),
                         "proposed": alloc, "final_planned": r["used"] + alloc, "capacity": r["remaining"] if is_eligible(r) else 0})

    by_id = {r["store_id"]: r for r in rows}
    out_priority = []
    for e in priority:
        if e["status"] != "matched":
            out_priority.append({**e, "outcome": "Excluded until resolved." if e["status"] != "duplicate" else "Duplicate: only the first is used.", "included": False})
            continue
        outcome = _priority_outcome(e, by_id.get(e["store_id"]), chosen_ids, mode, store_limit)
        out_priority.append({**e, "outcome": outcome, "included": outcome == "Included."})

    chosen_capacity = sum(r["remaining"] for r in chosen)
    matchable = min(target, chosen_capacity)
    needed = None
    if target > chosen_capacity:                         # how many stores, in the same order, it would take
        running = 0
        for i, r in enumerate(order, start=1):
            running += r["remaining"]
            if running >= target:
                needed = i
                break
    eligible_all = [r for r in rows if is_eligible(r)]
    totals = {
        "stores": len(rows), "eligible": len(eligible_all), "excluded": sum(1 for r in rows if r["exclude_reason"]),
        "selected": len(chosen), "store_limit": store_limit,
        "current_total": sum(r["used"] for r in rows), "target": target,
        "available_capacity": sum(r["remaining"] for r in eligible_all), "selected_capacity": chosen_capacity,
        "matchable": matchable, "unmatched": target - matchable, "unused_capacity": chosen_capacity - matchable,
        "percent_covered": round(matchable * 100 / target, 1) if target else None,
        "stores_required": needed,                        # None = the target fits, or no number of eligible stores can cover it
        "coverable": target <= sum(r["remaining"] for r in order),
        "fits": target <= chosen_capacity,
        "allocation_allowed": allocation_allowed,
        "proposed_total": sum(allocation.values()),
        "priority_total": len(priority), "priority_matched": len(matched), "priority_included": sum(1 for e in out_priority if e["included"]),
        "priority_exceeds_limit": bool(store_limit and len(matched) > store_limit),
    }
    totals["desired_total"] = totals["current_total"] + target
    return {"rows": out_rows, "priority": out_priority, "totals": totals}
