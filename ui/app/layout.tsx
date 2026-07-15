import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Nav } from "@/components/Nav";
import { Disclaimer } from "@/components/Disclaimer";
import { CurrencyProvider } from "@/components/CurrencyProvider";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Hisse Fiyatı Tahmincisi",
  description:
    "Olasılıksal günlük getiri tahmini ve portföy takibi. Yatırım tavsiyesi değildir.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr" className={inter.variable}>
      <body>
        <CurrencyProvider>
          <Nav />
          <main className="container">{children}</main>
          <Disclaimer />
        </CurrencyProvider>
      </body>
    </html>
  );
}
