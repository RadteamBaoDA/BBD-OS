export type ModuleDescriptor = {
  id: string;
  label: string;
  href: string;
  enabled: boolean;
  settings?: { label: string; href: string };
};

// Navigation mirrors the enabled backend source and document descriptors.
export const modules: ModuleDescriptor[] = [
  { id: 'knowledge.documents', label: 'Documents', href: '/knowledge/documents', enabled: true },
  { id: 'sources', label: 'Sources', href: '/sources', enabled: true },
  { id: 'system', label: 'System', href: '/settings/system', enabled: true, settings: { label: 'System', href: '/settings/system' } },
];
