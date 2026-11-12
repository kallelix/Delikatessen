import { NavLink, Route, Routes, useLocation } from "react-router";
import { useApp } from "./AppContext";
import { Icon } from "./components/Icon";
import { Einkauf } from "./pages/Einkauf";
import { Einstellungen } from "./pages/Einstellungen";
import { Journal } from "./pages/Journal";
import { Zutatensuche } from "./pages/Zutatensuche";
import { Familie } from "./pages/Familie";
import { Kochansicht } from "./pages/Kochansicht";
import { Mehr } from "./pages/Mehr";
import { Neu } from "./pages/Neu";
import { Profilwahl } from "./pages/Profilwahl";
import { Rangliste } from "./pages/Rangliste";
import { RezeptBearbeiten } from "./pages/RezeptBearbeiten";
import { RezeptDetail } from "./pages/RezeptDetail";
import { Rezepte } from "./pages/Rezepte";
import { Woche } from "./pages/Woche";

const NAV = [
  { to: "/", label: "Woche", icon: "woche", end: true },
  { to: "/rezepte", label: "Rezepte", icon: "rezepte" },
  { to: "/neu", label: "Neu", icon: "neu" },
  { to: "/einkauf", label: "Einkauf", icon: "einkauf" },
  { to: "/mehr", label: "Mehr", icon: "mehr" },
];

export function App() {
  const { ready, me, persons, offline } = useApp();
  const location = useLocation();
  const cooking = location.pathname.endsWith("/kochen");

  if (!ready) return <div className="splash" aria-busy="true" />;
  if (!me && (persons.length > 0 || !offline)) return <Profilwahl />;

  return (
    <div className={`app${cooking ? " cooking" : ""}`}>
      {offline && (
        <div className="offline-bar" role="status">
          Ohne Netz: Plan und Rezepte sind lesbar, Ändern geht erst wieder mit Verbindung.
        </div>
      )}
      <main className="content">
        <Routes>
          <Route path="/" element={<Woche />} />
          <Route path="/rezepte" element={<Rezepte />} />
          <Route path="/rezepte/zutaten" element={<Zutatensuche />} />
          <Route path="/rezepte/:id" element={<RezeptDetail />} />
          <Route path="/rezepte/:id/bearbeiten" element={<RezeptBearbeiten />} />
          <Route path="/rezepte/:id/kochen" element={<Kochansicht />} />
          <Route path="/neu" element={<Neu />} />
          <Route path="/einkauf" element={<Einkauf />} />
          <Route path="/mehr" element={<Mehr />} />
          <Route path="/mehr/rangliste" element={<Rangliste />} />
          <Route path="/mehr/journal" element={<Journal />} />
          <Route path="/mehr/familie" element={<Familie />} />
          <Route path="/mehr/einstellungen" element={<Einstellungen />} />
          <Route path="*" element={<p className="empty">Diese Seite gibt es nicht.</p>} />
        </Routes>
      </main>
      {!cooking && (
        <nav className="bottom-nav" aria-label="Hauptnavigation">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className="nav-item">
              <Icon name={n.icon} size={24} />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}
