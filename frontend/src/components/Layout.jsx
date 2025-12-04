import { Outlet } from 'react-router-dom';
import AppBackground from './AppBackground';
import Sidebar from './Sidebar';

export default function Layout() {
  return (
    <AppBackground>
      <div className="flex h-screen">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </AppBackground>
  );
}
