import "@noir/ui/tokens.css";
import "../styles/index.css";

export const metadata = {
  title: "Noir Atelier — Maison de Haute Confection",
  description:
    "Curated 100-piece natural-fiber fashion house across Men, Women, and Kids—with Personal Fashion Consultant and CBIC HSN 61/62 GST provenance.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" data-font-scale="default" data-theme="light">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link rel="icon" href="/icon.svg" type="image/svg+xml" />
        <link rel="alternate icon" href="/favicon.ico" />
      </head>
      <body>{children}</body>
    </html>
  );
}
