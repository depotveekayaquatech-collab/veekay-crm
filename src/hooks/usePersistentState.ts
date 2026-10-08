import { useCallback, useState } from "react";

/** useState that remembers its value across visits (localStorage). Falls back to plain state if storage is blocked. */
export function usePersistentState<T extends string>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      return (localStorage.getItem(key) as T | null) ?? initial;
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (v: T) => {
      setValue(v);
      try {
        localStorage.setItem(key, v);
      } catch {
        /* private mode: still works for this visit */
      }
    },
    [key],
  );
  return [value, set];
}
