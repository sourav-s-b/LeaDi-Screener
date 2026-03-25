import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar               from './components/layout/Sidebar';
import Header                from './components/layout/Header';
import ErrorBoundary         from './components/ui/ErrorBoundary';
import Home                  from './pages/Home';
import ScreeningOrchestrator from './pages/ScreeningOrchestrator';
import SessionsPage          from './pages/Sessions';
import SettingsPage          from './pages/Settings';
import NotFound              from './pages/NotFound';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <Sidebar />
        <div className="flex flex-col min-h-screen" style={{ marginLeft: 'var(--nav-w, 240px)' }}>
          <Header />
          <main className="flex-1 px-6 py-6" style={{ marginTop: 'var(--header-h, 60px)' }}>
            <ErrorBoundary>
              <Routes>
                <Route path="/"              element={<Home />}                        />
                <Route path="/screening/*"   element={<ScreeningOrchestrator />}       />
                <Route path="/sessions"      element={<SessionsPage />}                />
                <Route path="/settings"      element={<SettingsPage />}                />
                <Route path="*"             element={<NotFound />}                     />
              </Routes>
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}
