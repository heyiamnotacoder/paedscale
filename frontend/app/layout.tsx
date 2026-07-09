import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PaedScale — Pediatric Dose-Extrapolation Agent",
  description:
    "Dosing children where the guidelines run out — allometry x organ maturation, with a cited, auditable rationale.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="topbar">
          <div className="wrap">
            <div className="brand">
              <b>PaedScale</b> · dose-extrapolation agent
            </div>
          </div>
        </div>
        {children}
        <footer>PaedScale · working title, provisional · decision support, not prescribing</footer>
      </body>
    </html>
  );
}
