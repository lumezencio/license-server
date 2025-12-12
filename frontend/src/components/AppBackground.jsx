import React from 'react';

export default function AppBackground({ children, patternOpacity = 0.08 }) {
  const plusPattern = `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%2394a3b8' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`;

  return (
    <div
      className="relative min-h-screen w-full overflow-y-auto overflow-x-hidden"
      style={{ background: 'linear-gradient(135deg, #070b14 0%, #0a0e1a 50%, #0d1221 100%)' }}
    >
      <div
        className="pointer-events-none absolute inset-0"
        style={{ backgroundImage: plusPattern, backgroundRepeat: 'repeat', opacity: patternOpacity }}
      />
      <div className="relative mx-auto w-full min-h-screen">
        {children}
      </div>
    </div>
  );
}
