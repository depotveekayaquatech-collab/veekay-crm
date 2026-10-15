import { useRef } from "react";
import { randomUUID } from "expo-crypto";

/**
 * One key per logical submission of a form. It stays the same while the person retries after a timeout or an error
 * (so the server can recognise the retry and not create a second record) and is renewed once the submission succeeded.
 */
export function useSubmissionKey() {
  const ref = useRef<string | null>(null);
  return {
    get: () => (ref.current ??= randomUUID()),
    renew: () => {
      ref.current = null;
    },
  };
}
