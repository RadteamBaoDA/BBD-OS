'use client';

import { createContext, useCallback, useContext, useEffect, useRef, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';

type NavigationMode = 'push' | 'replace';
export type LeaveGuard = {
  hasUnsavedChanges: () => boolean;
  confirmDiscard: () => boolean;
  acceptLeave: () => void;
};
type GuardedNavigation = {
  registerLeaveGuard: (guard: LeaveGuard) => () => void;
  navigate: (href: string, mode?: NavigationMode) => boolean;
  ensureSourcesDocument: () => boolean;
};

const GuardedNavigationContext = createContext<GuardedNavigation | null>(null);
const sourcePaths = new Set(['/sources', '/settings/sources']);

function isSourcesPath(pathname: string) {
  return sourcePaths.has(pathname);
}

export function GuardedNavigationProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const guardRef = useRef<LeaveGuard | null>(null);
  const documentPath = useRef(pathname);

  const registerLeaveGuard = useCallback((guard: LeaveGuard) => {
    guardRef.current = guard;
    return () => {
      if (guardRef.current === guard) guardRef.current = null;
    };
  }, []);

  const ensureSourcesDocument = useCallback(() => {
    if (!isSourcesPath(pathname) || isSourcesPath(documentPath.current)) return true;
    window.location.replace(window.location.href);
    return false;
  }, [pathname]);

  const navigate = useCallback((href: string, mode: NavigationMode = 'push') => {
    const destination = new URL(href, window.location.href);
    if (destination.origin !== window.location.origin) {
      if (mode === 'replace') window.location.replace(destination.href);
      else window.location.assign(destination.href);
      return true;
    }

    const leavesSources = isSourcesPath(pathname) && destination.pathname !== pathname;
    const guard = guardRef.current;
    if (leavesSources) {
      if (guard?.hasUnsavedChanges() && !guard.confirmDiscard()) return false;
      guard?.acceptLeave();
      window.location.assign(destination.href);
      return true;
    }

    if (isSourcesPath(destination.pathname)) {
      if (mode === 'replace') window.location.replace(destination.href);
      else window.location.assign(destination.href);
      return true;
    }

    const appHref = `${destination.pathname}${destination.search}${destination.hash}`;
    if (mode === 'replace') router.replace(appHref);
    else router.push(appHref);
    return true;
  }, [pathname, router]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest<HTMLAnchorElement>('a[href]');
      if (!anchor || anchor.download || (anchor.target && anchor.target !== '_self')) return;
      const destination = new URL(anchor.href, window.location.href);
      const sameOrigin = destination.origin === window.location.origin;
      const leavesSources = isSourcesPath(window.location.pathname)
        && (!sameOrigin || destination.pathname !== window.location.pathname);
      const entersSources = sameOrigin && isSourcesPath(destination.pathname) && !isSourcesPath(window.location.pathname);
      if (!leavesSources && !entersSources) return;
      if (leavesSources && !sameOrigin) {
        const guard = guardRef.current;
        if (guard?.hasUnsavedChanges() && !guard.confirmDiscard()) {
          event.preventDefault();
          event.stopPropagation();
          event.stopImmediatePropagation();
          return;
        }
        guard?.acceptLeave();
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      navigate(destination.href);
    };
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      const guard = guardRef.current;
      if (!guard?.hasUnsavedChanges()) return;
      event.preventDefault();
      event.returnValue = '';
    };
    const onPageHide = () => guardRef.current?.acceptLeave();
    document.addEventListener('click', onClick, true);
    window.addEventListener('beforeunload', onBeforeUnload);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      document.removeEventListener('click', onClick, true);
      window.removeEventListener('beforeunload', onBeforeUnload);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, [navigate]);

  return <GuardedNavigationContext.Provider value={{ registerLeaveGuard, navigate, ensureSourcesDocument }}>
    {children}
  </GuardedNavigationContext.Provider>;
}

export function useGuardedNavigation() {
  const value = useContext(GuardedNavigationContext);
  if (!value) throw new Error('Guarded navigation is unavailable');
  return value;
}
