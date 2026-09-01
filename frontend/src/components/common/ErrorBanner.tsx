type ErrorBannerProps = {
  title?: string;
  message: string;
  onRetry?: () => void;
  isRetrying?: boolean;
};

export function ErrorBanner({
  title = "Unable to load data",
  message,
  onRetry,
  isRetrying = false,
}: ErrorBannerProps) {
  return (
    <div className="panel error-banner" role="alert">
      <div className="error-banner-content">
        <div className="error-banner-icon">⚠️</div>
        <div className="error-banner-text">
          <h4 className="error-banner-title">{title}</h4>
          <p className="error-banner-desc">{message}</p>
        </div>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={isRetrying}
          className="btn btn-danger btn-sm"
        >
          {isRetrying ? "Retrying..." : "Retry"}
        </button>
      )}
    </div>
  );
}
