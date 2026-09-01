type NavigationProps = {
  activeTab: string;
  onSelectTab: (tab: string) => void;
  openCount?: number;
  readinessScore?: number;
};

export const TABS = [
  { id: "Command Center", label: "Command Center", icon: "📊" },
  { id: "Opportunities", label: "Opportunities", icon: "🎯" },
  { id: "Evaluation", label: "Evaluation", icon: "🧪" },
  { id: "Reliability & Security", label: "Reliability & Security", icon: "🛡️" },
  { id: "Production Readiness", label: "Production Readiness", icon: "🚀" },
] as const;

export function Navigation({ activeTab, onSelectTab, openCount }: NavigationProps) {
  return (
    <nav className="nav-tabs-bar" role="tablist" aria-label="RecoverIQ Main Sections">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            className={`nav-tab-btn ${isActive ? "active" : ""}`}
            onClick={() => onSelectTab(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
            {tab.id === "Opportunities" && typeof openCount === "number" && openCount > 0 && (
              <span className="tab-count-badge">{openCount}</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
