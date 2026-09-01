type RemediationBannerProps = {
  recommendation?: string;
};

export function RemediationBanner({ recommendation }: RemediationBannerProps) {
  if (!recommendation) {
    return null;
  }

  return (
    <div className="panel remediation-recommendation-card">
      <div className="remediation-head">
        <span className="remediation-icon">🎯</span>
        <div>
          <span className="remediation-tag">RELEASE ACTION PLAN</span>
          <h4 className="remediation-title">Recommended Path to Full Production Sign-Off</h4>
        </div>
      </div>
      <p className="remediation-body">{recommendation}</p>
    </div>
  );
}
