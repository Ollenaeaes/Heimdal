/**
 * Converts a 2-letter ISO country code to a flag emoji using
 * regional indicator symbol pairs (Unicode codepoints 0x1F1E6–0x1F1FF).
 */
export function countryCodeToFlagEmoji(code: string | undefined): string {
  if (!code || code.length !== 2) return '';
  const upper = code.toUpperCase();
  const codePoints = [...upper].map(
    (ch) => 0x1f1e6 + ch.charCodeAt(0) - 65
  );
  return String.fromCodePoint(...codePoints);
}
