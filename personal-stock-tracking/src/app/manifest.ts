import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Theo dõi danh mục đầu tư cá nhân',
    short_name: 'Danh mục',
    description: 'Theo dõi riêng tư danh mục đầu tư Việt Nam bằng VND.',
    start_url: '/',
    display: 'standalone',
    background_color: '#fafafa',
    theme_color: '#18181a',
    icons: [
      { src: '/icons/icon-192.svg', sizes: '192x192', type: 'image/svg+xml', purpose: 'any' },
      { src: '/icons/icon-512.svg', sizes: '512x512', type: 'image/svg+xml', purpose: 'maskable' }
    ]
  };
}
