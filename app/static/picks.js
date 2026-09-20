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

  function cardLayout(event) {
    return event.bouts
      .map((bout) => ({
        ...bout,
        fighters: [...bout.fighters].sort((left, right) =>
          left.id < right.id ? -1 : left.id > right.id ? 1 : 0,
        ),
      }))
      .sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
  }

  function cardFingerprint(event) {
    const input = cardLayout(event)
      .map((bout) => `${bout.id}:${bout.fighters.map((fighter) => fighter.id).join(",")}`)
      .join("|");
    const bytes = new TextEncoder().encode(input);
    let crc = 0xffff;

    bytes.forEach((byte) => {
      crc ^= byte << 8;
      for (let bit = 0; bit < 8; bit += 1) {
        crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
      }
    });
    return crc;
  }

  function encode(event, picks) {
    let packed = 0n;
    let place = 1n;

    cardLayout(event).forEach((bout) => {
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

    const fingerprint = cardFingerprint(event);
    bytes.unshift(fingerprint >> 8, fingerprint & 255);
    return `1.${toBase64Url(Uint8Array.from(bytes))}`;
  }

  function decodeCompact(event, value, bouts = event.bouts) {
    const bytes = fromBase64Url(value);
    let packed = bytes.reduce((result, byte) => (result << 8n) | BigInt(byte), 0n);
    const picks = {};

    bouts.forEach((bout) => {
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

  function decodeVersionOne(event, value) {
    const bytes = fromBase64Url(value);
    if (bytes.length < 3) {
      throw new Error("Pick payload is incomplete");
    }

    const fingerprint = (bytes[0] << 8) | bytes[1];
    if (fingerprint !== cardFingerprint(event)) {
      throw new Error("The fight card changed after this link was created");
    }
    return decodeCompact(event, toBase64Url(bytes.slice(2)), cardLayout(event));
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
    if (value.startsWith("1.")) {
      return decodeVersionOne(event, value.slice(2));
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
