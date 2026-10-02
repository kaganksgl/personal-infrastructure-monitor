import { Center, Loader } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { useAuth } from "./hooks/useAuth";
import { useLiveEvents } from "./hooks/useLive";
import { liveStore } from "./services/live";
import { AlertsPage } from "./pages/AlertsPage";
import { LoginPage } from "./pages/LoginPage";
import { MachinePage } from "./pages/MachinePage";
import { MachinesPage } from "./pages/MachinesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RulesPage } from "./pages/RulesPage";

function AlertToasts() {
  useLiveEvents((event) => {
    if (event.type !== "alert" || event.action === "acknowledged") return;
    const fired = event.action === "fired";
    notifications.show({
      title: `${fired ? "Alert" : "Resolved"} · ${event.alert.agent_id}`,
      message: `${event.alert.rule_name}: ${event.alert.message}`,
      color: fired ? (event.alert.severity === "critical" ? "red" : "yellow") : "green",
      autoClose: fired ? 10_000 : 5_000,
    });
  });
  return null;
}

export function App() {
  const { user, checking } = useAuth();

  useEffect(() => {
    if (!user) return;
    liveStore.connect();
    return () => liveStore.disconnect();
  }, [user]);

  if (checking) {
    return (
      <Center mih="100vh">
        <Loader />
      </Center>
    );
  }
  if (!user) return <LoginPage />;

  return (
    <>
      <AlertToasts />
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="machines" element={<MachinesPage />} />
          <Route path="machines/:id" element={<MachinePage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}
