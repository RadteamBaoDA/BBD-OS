'use client';

import Link from 'next/link';
import { useRef } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useTheme } from 'next-themes';
import { useTranslations } from 'next-intl';
import { Background, Panel, ReactFlow, useReactFlow, type Edge, type Node, type ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Button } from '@/components/ui/button';
import { entityKeys, getEntityNeighbors } from './api';

const NODE_LIMIT = 100;
const EDGE_LIMIT = 100;
const PAGE_SIZE = 50;

/** Renders keyboard-accessible pan, zoom, reset, fit, and optional expand controls for the graph. */
function GraphActions({ focusId, canExpand, isExpanding, onExpand }: { focusId: string; canExpand: boolean; isExpanding: boolean; onExpand: () => void }) {
  const t = useTranslations('entities');
  const flow = useReactFlow();
  /** Moves the graph viewport by the supplied horizontal and vertical offsets. */
  const pan = (x: number, y: number) => { const viewport = flow.getViewport(); void flow.setViewport({ ...viewport, x: viewport.x + x, y: viewport.y + y }, { duration: 0 }); };
  return <div className="flex flex-wrap gap-2" role="group" aria-label={t('controlsA11yLabel')}>
    <Button type="button" className="secondary" aria-label={t('panLeft')} onClick={() => pan(120, 0)}>← {t('panLeft')}</Button>
    <Button type="button" className="secondary" aria-label={t('panRight')} onClick={() => pan(-120, 0)}>{t('panRight')} →</Button>
    <Button type="button" className="secondary" aria-label={t('panUp')} onClick={() => pan(0, 120)}>↑ {t('panUp')}</Button>
    <Button type="button" className="secondary" aria-label={t('panDown')} onClick={() => pan(0, -120)}>{t('panDown')} ↓</Button>
    <Button type="button" className="secondary" aria-label={t('zoomInA11yLabel')} onClick={() => flow.zoomIn({ duration: 0 })}>{t('zoomIn')}</Button>
    <Button type="button" className="secondary" aria-label={t('zoomOutA11yLabel')} onClick={() => flow.zoomOut({ duration: 0 })}>{t('zoomOut')}</Button>
    <Button type="button" className="secondary" aria-label={t('resetGraph')} onClick={() => flow.fitView({ nodes: [{ id: focusId }], duration: 0 })}>{t('resetGraph')}</Button>
    <Button type="button" className="secondary" aria-label={t('fitViewA11yLabel')} onClick={() => flow.fitView({ padding: 0.2, duration: 0 })}>{t('refocusGraph')}</Button>
    {canExpand && <Button type="button" className="secondary" disabled={isExpanding} onClick={onExpand}>{t('expandGraph')}</Button>}
  </div>;
}

/** Renders an entity’s related graph and emits the selected relationship to its owner. */
export function EntityGraph({ entityId, title, selectedRelationshipId, onSelectRelationship }: {
  entityId: string;
  title: string;
  selectedRelationshipId?: string;
  onSelectRelationship: (relationshipId: string) => void;
}) {
  const t = useTranslations('entities');
  const { resolvedTheme } = useTheme();
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const graph = useInfiniteQuery({
    queryKey: entityKeys.graphNeighbors(entityId),
    initialPageParam: { cursor: undefined as string | undefined, limit: PAGE_SIZE },
    queryFn: ({ pageParam }) => getEntityNeighbors(entityId, pageParam.cursor, pageParam.limit),
    getNextPageParam: (last, pages) => {
      const rows = pages.flatMap((page) => page.items);
      const nodes = new Set(rows.map((row) => row.entity.id).filter((id) => id !== entityId));
      const edges = new Set(rows.map((row) => row.relationship.id));
      const additionalRows = Math.min(PAGE_SIZE, NODE_LIMIT - 1 - nodes.size, EDGE_LIMIT - edges.size, EDGE_LIMIT - rows.length);
      return last.next_cursor && additionalRows > 0 ? { cursor: last.next_cursor, limit: additionalRows + 1 } : undefined;
    },
  });
  const rows = graph.data?.pages.flatMap((page) => page.items) ?? [];
  const nodes = new Map<string, { id: string; name: string | null; type: string }>();
  nodes.set(entityId, { id: entityId, name: title, type: 'focus' });
  for (const row of rows) if (nodes.size < NODE_LIMIT) nodes.set(row.entity.id, row.entity);
  const uniqueEdges = [...new Map(rows.map((row) => [row.relationship.id, row])).values()];
  const edges = uniqueEdges.slice(0, EDGE_LIMIT).filter(({ relationship }) => nodes.has(relationship.source_entity_id) && nodes.has(relationship.target_entity_id));
  const reachedLimit = nodes.size >= NODE_LIMIT || uniqueEdges.length >= EDGE_LIMIT;
  const lastPage = graph.data?.pages.at(-1);
  const truncated = lastPage?.truncated === true || (reachedLimit && !!lastPage?.next_cursor) || (rows.length >= EDGE_LIMIT && !!lastPage?.next_cursor);
  /** Uses the entity’s known name or its localized type label when the name is absent. */
  const entityLabel = (entity: { name: string | null; type: string }) => entity.name ?? t(`type_${entity.type}` as 'type_person');
  const flowNodes: Node[] = [...nodes.values()].map((node, index) => { const label = entityLabel(node); return { id: node.id, position: index === 0 ? { x: 0, y: 0 } : { x: 260 * Math.cos((2 * Math.PI * (index - 1)) / Math.max(1, nodes.size - 1)), y: 180 * Math.sin((2 * Math.PI * (index - 1)) / Math.max(1, nodes.size - 1)) }, data: { label }, ariaLabel: `${t('nodeA11yTitle')}: ${label}`, type: 'default' }; });
  const flowEdges: Edge[] = edges.map(({ relationship }) => ({ id: relationship.id, source: relationship.source_entity_id, target: relationship.target_entity_id, label: relationship.type, ariaLabel: `${t('edgeA11yTitle')}: ${relationship.type}`, selectable: true, focusable: true, style: relationship.id === selectedRelationshipId ? { stroke: 'var(--primary)', strokeWidth: 3 } : undefined }));
  return <section aria-labelledby="entity-graph-heading"><h2 id="entity-graph-heading">{t('graph')}</h2><p className="muted">{nodes.size} {t('selectedSummary')} · {edges.length} {t('relationshipCount')}{truncated ? ` · ${t('graphTruncated')}` : ''}. {t('graphFallback')}</p>
    {graph.isError && <p className="error" role="alert">{t('graphRetry')} <Button className="secondary" onClick={() => graph.refetch()}>{t('retry')}</Button></p>}
    <p id="entity-graph-keyboard-help" className="muted">{t('keyboardGraphHelp')}</p>
    <div className="entity-graph" aria-label={t('viewportA11yLabel')}>
      <ReactFlow nodes={flowNodes} edges={flowEdges} fitView colorMode={resolvedTheme === 'dark' ? 'dark' : 'light'} nodesDraggable={false} nodesConnectable={false} elementsSelectable ariaLabelConfig={{ 'node.a11yDescription.default': t('nodeA11yDescription'), 'node.a11yDescription.keyboardDisabled': t('nodeKeyboardDisabled'), 'node.a11yDescription.ariaLiveMessage': ({ direction, x, y }) => t('graphLiveMessage', { direction, x, y }), 'edge.a11yDescription.default': t('edgeA11yDescription'), 'controls.ariaLabel': t('controlsA11yLabel'), 'controls.zoomIn.ariaLabel': t('zoomInA11yLabel'), 'controls.zoomOut.ariaLabel': t('zoomOutA11yLabel'), 'controls.fitView.ariaLabel': t('fitViewA11yLabel'), 'controls.interactive.ariaLabel': t('controlsA11yLabel'), 'minimap.ariaLabel': t('viewportA11yLabel'), 'handle.ariaLabel': t('handleA11yLabel') }} onInit={(instance) => { flowRef.current = instance; }} onKeyDown={(event) => {
        const flow = flowRef.current;
        if (!flow || (event.target instanceof HTMLElement && event.target.closest('.react-flow__panel'))) return;
        const viewport = flow.getViewport();
        /** Adjusts the graph viewport by the supplied pointer movement. */
        const panBy = (x: number, y: number) => { event.preventDefault(); void flow.setViewport({ ...viewport, x: viewport.x + x, y: viewport.y + y }, { duration: 0 }); };
        if (event.key === 'ArrowLeft') panBy(80, 0);
        else if (event.key === 'ArrowRight') panBy(-80, 0);
        else if (event.key === 'ArrowUp') panBy(0, 80);
        else if (event.key === 'ArrowDown') panBy(0, -80);
        else if (event.key === '+' || event.key === '=') { event.preventDefault(); void flow.zoomIn({ duration: 0 }); }
        else if (event.key === '-') { event.preventDefault(); void flow.zoomOut({ duration: 0 }); }
        else if (event.key === 'Home') { event.preventDefault(); void flow.fitView({ padding: 0.2, duration: 0 }); }
      }} onEdgeClick={(_, edge) => onSelectRelationship(edge.id)}><Background color="var(--line)" /><Panel position="top-right"><GraphActions focusId={entityId} canExpand={!!graph.hasNextPage} isExpanding={graph.isFetchingNextPage} onExpand={() => { void graph.fetchNextPage(); }} /></Panel></ReactFlow>
    </div>
    <ul className="stack" aria-label={t('graphFallback')}>{edges.map(({ entity, relationship }) => <li className="card" key={relationship.id}><span aria-hidden="true">↔</span> <Link href={`/knowledge/entities/${entity.id}`}>{entityLabel(entity)}</Link> <small>{relationship.type}</small> <Button type="button" className="secondary" aria-pressed={selectedRelationshipId === relationship.id} onClick={() => onSelectRelationship(relationship.id)}>{selectedRelationshipId === relationship.id ? t('selectedRelationship') : t('selectRelationship')}</Button></li>)}</ul>
    {truncated && <p className="muted" role="status">{t('graphAtLimit', { limit: NODE_LIMIT })}</p>}
  </section>;
}
