type EmptyStateProps = {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  isLoadingAction?: boolean;
  icon?: string;
};

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  isLoadingAction = false,
  icon = "📂",
}: EmptyStateProps) {
  return (
    <div className="empty-state-card">
      <div className="empty-state-icon">{icon}</div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-desc">{description}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          disabled={isLoadingAction}
          className="btn btn-primary mt-lg"
        >
          {isLoadingAction ? "Processing..." : actionLabel}
        </button>
      )}
    </div>
  );
}
