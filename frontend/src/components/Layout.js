import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { logout } from "../api/auth";
import { useAuth, useRole } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";

const ROLE_LABELS = { owner: "Owner", manager: "Manager", team_lead: "Team lead" };

function navGroups(canManage) {
  return [
    {
      label: "Work",
      links: [
        { to: "/projects", label: "Projects" },
        { to: "/board", label: "Board" },
        { to: "/sheet", label: "Sheet" },
        { to: "/timeline", label: "Timeline" },
        { to: "/reports", label: "Daily log" },
        { to: "/planning", label: "Planning" },
      ],
    },
    {
      label: "People",
      links: [
        { to: "/teams", label: "Teams" },
        { to: "/workers", label: "Workers" },
      ],
    },
    {
      label: "Resources",
      links: [
        { to: "/stock", label: "Stock" },
        ...(canManage ? [{ to: "/work-types", label: "Work types" }] : []),
      ],
    },
    {
      label: "Settings",
      links: [
        { to: "/company", label: "Company" },
        ...(canManage ? [{ to: "/settings/workflow", label: "Workflow" }] : []),
      ],
    },
  ];
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={toggleTheme}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
    >
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5z" />
        </svg>
      )}
    </button>
  );
}

function Layout() {
  const { user, setUser } = useAuth();
  const { canManage } = useRole();
  const navigate = useNavigate();
  const company = user?.active_company;
  const location = useLocation();
  const needsCompany = location.pathname !== "/company" && location.pathname !== "/dashboard";

  async function handleLogout() {
    await logout();
    setUser(null);
    navigate("/login");
  }

  const groups = company ? navGroups(canManage) : [navGroups(false)[3]];

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link to="/dashboard" className="app-brand">
          <img className="app-mark" src="/logo.svg" alt="" />
          <span>
            <strong>WorkPulse</strong>
            <span>Site operations</span>
          </span>
        </Link>
        <nav className="app-nav">
          {groups.map((group) => (
            <div key={group.label}>
              <span className="app-nav-label">{group.label}</span>
              {group.links.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) => (isActive ? "app-nav-link is-active" : "app-nav-link")}
                >
                  {link.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <div className="app-company">
            <strong>{company ? company.name : "No company selected"}</strong>
            <span>{company ? ROLE_LABELS[company.role] || company.role : "Choose a company to continue"}</span>
          </div>
          <div className="app-topbar-actions">
            <ThemeToggle />
            <button type="button" className="ghost-btn" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </header>
        <main className="app-content">{!company && needsCompany ? <Navigate to="/company" replace /> : <Outlet />}</main>
      </div>
    </div>
  );
}

export default Layout;
