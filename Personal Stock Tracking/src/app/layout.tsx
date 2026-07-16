import type { Metadata, Viewport } from 'next';
import '../styles/tokens.css';
import '../styles/app.css';

export const metadata: Metadata = {
  title: 'Personal Portfolio Tracker',
  description: 'Private Vietnam portfolio tracking in VND.',
  icons: { icon: '/icons/icon-192.svg' },
  manifest: '/manifest.webmanifest'
};

export const viewport: Viewport = {
  themeColor: '#18181a',
  viewportFit: 'cover'
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  );
}
