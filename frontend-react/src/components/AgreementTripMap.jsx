import { useEffect, useState } from "react";


export default function AgreementTripMap({ tripId, isActive }) {
  const [location, setLocation] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    if (!isActive || !tripId) {
      setLocation(null);
      setAvailable(false);
      return undefined;
    }

    let cancelled = false;

    async function fetchLocation() {
      try {
        const response = await fetch(`/api/agreements/trips/${tripId}/live-location`, {
          credentials: "include",
        });
        if (!response.ok) {
          throw new Error("Live location request failed");
        }
        const data = await response.json();
        if (cancelled) {
          return;
        }
        if (data.traccar_available === true) {
          setLocation({
            lat: Number(data.lat),
            lon: Number(data.lon),
            speed: data.speed,
            timestamp: data.timestamp,
          });
          setAvailable(true);
        } else {
          setLocation(null);
          setAvailable(false);
        }
        setLastUpdated(new Date().toLocaleString());
      } catch (error) {
        if (!cancelled) {
          setLocation(null);
          setAvailable(false);
          setLastUpdated(new Date().toLocaleString());
        }
      }
    }

    fetchLocation();
    const intervalId = window.setInterval(fetchLocation, 30000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [tripId, isActive]);

  if (!isActive) {
    return null;
  }

  if (!available || !location) {
    return (
      <div style={{ color: "var(--color-text-secondary)" }}>
        <p>Live location not available</p>
        <p style={{ fontSize: '12px', marginTop: '4px' }}>GPS tracking will be active once provider is configured.</p>
        {lastUpdated ? <small>Last updated: {lastUpdated}</small> : null}
      </div>
    );
  }

  const { lat, lon } = location;
  const mapUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${lon - 0.01},${lat - 0.01},${lon + 0.01},${lat + 0.01}&layer=mapnik&marker=${lat},${lon}`;

  return (
    <div>
      <iframe
        title="Live truck location"
        src={mapUrl}
        style={{ width: "100%", height: "300px", border: "none", borderRadius: "8px" }}
      />
      {lastUpdated ? (
        <small style={{ color: "var(--color-text-secondary)" }}>Last updated: {lastUpdated}</small>
      ) : null}
    </div>
  );
}
