import { BellRing, RadioTower } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import BackButton from "../components/BackButton.jsx";
import IncidentCard from "../components/IncidentCard.jsx";
import StatCard from "../components/StatCard.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { api } from "../services/api.js";

export default function ResponderDashboard() {
  const { user } = useAuth();
  const [incidents, setIncidents] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [filter, setFilter] = useState("All");

  async function load() {
    const [incidentData, notificationData] = await Promise.all([
      api("/incidents"),
      api("/responders/notifications")
    ]);
    setIncidents(incidentData);
    setNotifications(notificationData);
  }

  useEffect(() => {
    load().catch(console.error);
    const timer = window.setInterval(() => load().catch(console.error), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const critical = useMemo(() => incidents.filter((incident) => incident.severity === "Critical"), [incidents]);
  const filteredIncidents = useMemo(
    () => incidents.filter((incident) => filter === "All" || incident.severity === filter || incident.status === filter),
    [incidents, filter]
  );
  const resolved = incidents.filter((item) => item.status === "Resolved").length;
  const pending = incidents.filter((item) => item.status !== "Resolved").length;

  return (
    <main className="page">
      <BackButton />
      <section className="hero-panel">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center">
          <div>
            <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-red-600"><RadioTower size={17} /> Responder dashboard</p>
            <h1 className="mt-2 text-4xl font-black">Live Incident Queue</h1>
            <p className="mt-2 max-w-3xl text-slate-200">Showing incidents related to {user.responder_type || "your response team"}, sorted by severity for fast dispatch and status updates.</p>
            <p className="mt-3 text-sm font-bold text-emerald-300">Availability: {user.availability_status || "Available"}</p>
          </div>
          <div className="grid min-w-80 grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Queue" value={incidents.length} />
            <StatCard label="Critical" value={critical.length} tone="red" />
            <StatCard label="Pending" value={pending} tone="amber" />
            <StatCard label="Resolved" value={resolved} tone="green" />
          </div>
        </div>
      </section>

      <section className="mt-8">
        <div className="section-heading">
          <h2>Related Incident Notifications</h2>
          <span>{notifications.length} active</span>
        </div>
        <div className="grid gap-3">
          {notifications.length ? notifications.slice(0, 5).map((notification) => (
            <Link key={notification.id} to={`/incidents/${notification.id}`} className={`flex items-start gap-3 rounded-lg border border-red-100 bg-red-50 p-4 text-red-800 shadow-sm transition hover:bg-red-100 ${notification.is_emergency ? "emergency-card" : ""}`}>
              <BellRing className="mt-0.5 shrink-0" size={20} />
              <div>
                <p className="font-bold">{notification.message}</p>
                <p className="mt-1 text-sm text-red-700">{notification.incident_type} at {notification.location}</p>
              </div>
            </Link>
          )) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-slate-500">No related incident notifications right now.</div>
          )}
        </div>
      </section>

      <section className="mt-8">
        <div className="section-heading">
          <h2>Incident Dashboard</h2>
          <div className="filter-row">
            {["All", "Critical", "High", "Medium", "Low", "Waiting for Responder", "Accepted", "In Progress", "Resolved"].map((item) => (
              <button key={item} className={`filter-chip ${filter === item ? "filter-chip-active" : ""}`} onClick={() => setFilter(item)}>{item}</button>
            ))}
          </div>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {filteredIncidents.length ? filteredIncidents.map((incident) => <IncidentCard key={incident.id} incident={incident} />) : <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-slate-500">No incidents have been reported yet.</div>}
        </div>
      </section>
    </main>
  );
}
