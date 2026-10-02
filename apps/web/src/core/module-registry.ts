export type ShellMessageKey =
  | 'dashboard'
  | 'chat'
  | 'settings'
  | 'dataSources'
  | 'aiRouter'
  | 'dashboardGadgets'
  | 'documents'
  | 'entities'
  | 'search'
  | 'systemStatus';

export type NavigationDestination = {
  id: string;
  href: string;
  messageKey: ShellMessageKey;
};

export const mainNavigation: NavigationDestination[] = [
  { id: 'dashboard', href: '/app', messageKey: 'dashboard' },
  { id: 'chat', href: '/chat', messageKey: 'chat' },
  { id: 'settings', href: '/settings/sources', messageKey: 'settings' },
];

export const settingsGroups: NavigationDestination[] = [
  { id: 'data-sources', href: '/settings/sources', messageKey: 'dataSources' },
  { id: 'ai-router', href: '/settings/ai', messageKey: 'aiRouter' },
  { id: 'dashboard-gadgets', href: '/settings/dashboard', messageKey: 'dashboardGadgets' },
];

export const detailDestinations: NavigationDestination[] = [
  { id: 'documents', href: '/knowledge/documents', messageKey: 'documents' },
  { id: 'entities', href: '/knowledge/entities', messageKey: 'entities' },
  { id: 'search', href: '/search', messageKey: 'search' },
  { id: 'system', href: '/settings/system', messageKey: 'systemStatus' },
];

export const commandDestinations = [...mainNavigation, ...settingsGroups.slice(1), ...detailDestinations];
