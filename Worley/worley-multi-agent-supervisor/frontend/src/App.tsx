import { useRef } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Chat from "./pages/Chat";
import Monitoring from "./pages/Monitoring";

export default function App() {
  const chatResetRef = useRef<() => void>();

  return (
    <Layout onNewChat={() => chatResetRef.current?.()}>
      <Routes>
        <Route path="/" element={<Chat onResetRef={chatResetRef} />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
