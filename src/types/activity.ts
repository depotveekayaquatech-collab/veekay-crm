export interface Activity {
  id: string;
  action: string;
  entityType: string;
  entityId: string;
  actorName: string | null;
  metadata: Record<string, unknown> | null;
  createdAt: string;
}

export interface ActivityWire {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_name: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export function toActivity(w: ActivityWire): Activity {
  return {
    id: w.id,
    action: w.action,
    entityType: w.entity_type,
    entityId: w.entity_id,
    actorName: w.actor_name,
    metadata: w.metadata,
    createdAt: w.created_at,
  };
}
