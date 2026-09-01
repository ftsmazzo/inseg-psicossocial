const LOGO_SRC = "/img/inseg-logo.png";

export default function BrandLogo({ className = "", compact = false, alt = "INSEG" }) {
  return (
    <img
      src={LOGO_SRC}
      alt={alt}
      className={`inseg-logo ${compact ? "inseg-logo-compact" : ""} ${className}`.trim()}
    />
  );
}
