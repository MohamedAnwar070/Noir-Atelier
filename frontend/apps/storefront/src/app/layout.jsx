import "@noir/ui/tokens.css";
import "../../styles.css";

export const metadata = {
  title: "Noir Atelier — AI-Native Luxury Garment Platform",
  description:
    "Unified AI-Native Luxury Garment Storefront, 9-Agent LangGraph Concierge, and Admin Governance Portal (Men, Women, Kids · HSN 61/62).",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" data-font-scale="default" data-theme="light">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500&family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link rel="icon" href="/icon.svg" type="image/svg+xml" />
        <link rel="alternate icon" href="/favicon.ico" />
      </head>
      <body>{children}</body>
    </html>
  );
}
