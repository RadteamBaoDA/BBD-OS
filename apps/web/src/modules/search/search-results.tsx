import Link from 'next/link';
import type { SearchHit } from './api';

function displayDate(hit: SearchHit) {
  const date = hit.published_at ?? hit.observed_at;
  return date ? new Date(date).toLocaleString() : 'Date unknown';
}

export function SearchResults({ items }: { items: SearchHit[] }) {
  return <ul className="record-list" aria-label="Search results">{items.map((hit) => <li className="record-row" key={hit.chunk_id}>
    <div className="record-content">
      <Link href={`/knowledge/documents/${hit.citation.documentId}?version=${hit.version_number}#cited-revision`}><strong>{hit.title}</strong></Link>
      <p className="muted">{hit.source.name} · {hit.source.type} · {displayDate(hit)}{hit.content_type ? ` · ${hit.content_type}` : ''}</p>
      <p className="search-excerpt">{hit.excerpt}</p>
      <Link href={`/knowledge/documents/${hit.citation.documentId}?version=${hit.version_number}#cited-revision`}>Open cited revision {hit.version_number}</Link>
    </div>
  </li>)}</ul>;
}
