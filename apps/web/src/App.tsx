/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect } from 'react';
import { 
  BrowserRouter as Router, 
  Routes, 
  Route, 
  useLocation,
  useParams
} from 'react-router-dom';
import { MantineProvider } from "@mantine/core";
import "@mantine/core/styles.css";

// Layout Components
import { AppBar } from './components/layout/AppBar';
import { SubSidebar } from './components/layout/SubSidebar';

// Views
import { HomeView } from './components/views/HomeView';
import { AIView } from './components/views/AIView';
import { PMSView } from './components/views/PMSView/PMSView';
import { DocsView } from './components/views/DocsView';
import { PlannerView } from './components/views/PlannerView';
import { ToolView } from './components/views/ToolView';

// Constants & Types
import { NAV_ITEMS } from './constants';

const ToolViewWrapper = () => {
  const { toolId } = useParams();
  const item = NAV_ITEMS.find(i => i.id === toolId);
  if (!item) return <div className="p-8 text-gray-500">Tool not found</div>;
  
  if (item.appId === 'pms') {
    return <PMSView />;
  }
  
  if (item.appId === 'docs') {
    return <DocsView />;
  }
  
  return <ToolView item={item} />;
};

const AppContent = () => {
  const location = useLocation();
  const [activeAppId, setActiveAppId] = useState<'home' | 'ai' | 'pms' | 'docs' | 'planner'>('home');
  const [activeNavItemId, setActiveNavItemId] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null;
    if (savedTheme) {
      setTheme(savedTheme);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setTheme('dark');
    }
  }, []);

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  useEffect(() => {
    const path = location.pathname;
    if (path === '/') {
      setActiveAppId('home');
      setActiveNavItemId('');
    } else if (path === '/ai') {
      setActiveAppId('ai');
      setActiveNavItemId('');
    } else if (path === '/pms') {
      setActiveAppId('pms');
      setActiveNavItemId('');
    } else if (path === '/docs' || path.startsWith('/docs/')) {
      setActiveAppId('docs');
      setActiveNavItemId('');
    } else if (path === '/planner') {
      setActiveAppId('planner');
      setActiveNavItemId('');
    } else if (path.startsWith('/tool/')) {
      const toolId = path.split('/')[2];
      const item = NAV_ITEMS.find(i => i.id === toolId);
      if (item) {
        setActiveAppId(item.appId);
        setActiveNavItemId(item.id);
      }
    }
  }, [location]);

  return (
    <div className="flex h-screen bg-clickup-sidebar text-clickup-text overflow-hidden transition-colors">
      <AppBar 
        activeAppId={activeAppId} 
        theme={theme} 
        onToggleTheme={toggleTheme} 
      />
      
      <div className="flex-1 flex overflow-hidden">
        <SubSidebar 
          activeAppId={activeAppId} 
          activeNavItemId={activeNavItemId} 
        />
        
        <main className="flex-1 bg-clickup-bg overflow-y-auto relative transition-colors">
          <Routes>
            <Route path="/" element={<HomeView />} />
            <Route path="/ai" element={<AIView />} />
            <Route path="/pms" element={<PMSView />} />
            <Route path="/docs" element={<DocsView />} />
            <Route path="/docs/:docId" element={<DocsView />} />
            <Route path="/planner" element={<PlannerView />} />
            <Route path="/tool/:toolId" element={<ToolViewWrapper />} />
            <Route path="/tool/:toolId/:docId" element={<ToolViewWrapper />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export default function App() {
  return (
    <MantineProvider defaultColorScheme="dark">
      <Router>
        <AppContent />
      </Router>
    </MantineProvider>
  );
}
