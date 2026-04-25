import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BESS Sizing Copilot",
  description:
    "Dimensionamento de Sistemas de Armazenamento de Energia (BESS) no mercado brasileiro com IA.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
