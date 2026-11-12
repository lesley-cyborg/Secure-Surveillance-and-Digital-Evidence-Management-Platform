"use client";

import { useEffect, useState } from "react";

// Add or remove images here as needed
const backgroundImages = [
  "/backgrounds/soc-1.jpg",
  "/backgrounds/soc-2.jpg",
  "/backgrounds/soc-3.jpg",
  "/backgrounds/soc-4.jpg",
];

export default function DynamicBackground() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFading, setIsFading] = useState(false);
  const [loadedImages, setLoadedImages] = useState<Set<string>>(new Set());

  useEffect(() => {
    // Preload all images
    backgroundImages.forEach((src) => {
      const img = new Image();
      img.src = src;
      img.onload = () => {
        setLoadedImages((prev) => new Set(prev).add(src));
      };
    });

    // Change image every 2 minutes (120,000 ms)
    const interval = setInterval(() => {
      setIsFading(true);
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % backgroundImages.length);
        setIsFading(false);
      }, 1000);
    }, 120000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed inset-0 -z-20 overflow-hidden">
      {/* 1. Base dark background (shows while images load) */}
      <div className="absolute inset-0 bg-[#09090b]" />

      {/* 2. The AI Image Layer */}
      <div
        className={`absolute inset-0 transition-opacity duration-1000 ease-in-out ${
          isFading ? "opacity-0" : "opacity-100"
        }`}
        style={{
          backgroundImage: `url(${backgroundImages[currentIndex]})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          opacity: loadedImages.has(backgroundImages[currentIndex]) ? 1 : 0,
        }}
      />

      {/* 3. Dark Overlay (Crucial: ensures your dashboard text remains readable) */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-[2px]" />

      {/* 4. Subtle Tech Grid Overlay */}
      <div
        className="absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage: `linear-gradient(rgba(56, 189, 248, 1) 1px, transparent 1px), linear-gradient(90deg, rgba(56, 189, 248, 1) 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
        }}
      />
      
      {/* 5. Vignette effect */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,0.6)_100%)]" />
    </div>
  );
}