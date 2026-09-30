import { useSyncExternalStore } from 'react';

const subscribe = () => () => {};
const getSnapshot = () => true;
const getServerSnapshot = () => false;

export function useHasHydrated() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
