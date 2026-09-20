(function initializePickCodec(root) {
  function toBase64Url(bytes) {
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  }

  function fromBase64Url(value) {
    const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const binary = atob(padded);
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  }

  function encode(event, picks) {
    let packed = 0n;
    let place = 1n;

    event.bouts.forEach((bout) => {
      const fighterIndex = bout.fighters.findIndex((fighter) => fighter.id === picks[bout.id]);
      const choice = fighterIndex < 0 ? 0 : fighterIndex + 1;
      packed += BigInt(choice) * place;
      place *= 3n;
    });

    const bytes = [];
    do {
      bytes.unshift(Number(packed & 255n));
      packed >>= 8n;
    } while (packed > 0n);
    return toBase64Url(Uint8Array.from(bytes));
  }

  function decodeCompact(event, value) {
    const bytes = fromBase64Url(value);
    let packed = bytes.reduce((result, byte) => (result << 8n) | BigInt(byte), 0n);
    const picks = {};

    event.bouts.forEach((bout) => {
      const choice = Number(packed % 3n);
      packed /= 3n;
      const fighter = bout.fighters[choice - 1];
      if (fighter) {
        picks[bout.id] = fighter.id;
      }
    });

    if (packed !== 0n) {
      throw new Error("Pick payload contains extra data");
    }
    return picks;
  }

  function decodeLegacy(value) {
    const bytes = fromBase64Url(value);
    const json = new TextDecoder().decode(bytes);
    const entries = JSON.parse(json);
    if (!Array.isArray(entries)) {
      throw new Error("Legacy pick payload is invalid");
    }
    return Object.fromEntries(entries);
  }

  function decode(event, value) {
    if (!value) return {};
    if (value.length > 512) {
      throw new Error("Pick payload is too long");
    }

    try {
      return decodeLegacy(value);
    } catch {
      return decodeCompact(event, value);
    }
  }

  const codec = { decode, encode };
  root.PickCodec = codec;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = codec;
  }
})(typeof window === "undefined" ? globalThis : window);
