export function SkeletonCard() {
  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div className="skeleton skeleton-text" style={{ width: "38%" }} />
      <div className="skeleton skeleton-text" style={{ width: "68%" }} />
      <div className="skeleton skeleton-text" style={{ width: "52%" }} />
    </div>
  );
}

export function SkeletonList({ count = 4 }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
