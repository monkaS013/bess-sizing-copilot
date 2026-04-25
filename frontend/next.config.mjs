/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Permite servir o frontend em PT-BR sem warnings de hydration por causa de chars especiais
  experimental: {
    typedRoutes: false,
  },
};

export default nextConfig;
