const assert = require("node:assert/strict");
const test = require("node:test");

const codec = require("../app/static/picks.js");

function makeEvent(boutCount = 14) {
  return {
    bouts: Array.from({ length: boutCount }, (_, index) => ({
      id: `bout-${index}`,
      fighters: [{ id: `red-${index}` }, { id: `blue-${index}` }],
    })),
  };
}

test("round trips a full card in a compact payload", () => {
  const event = makeEvent();
  const picks = Object.fromEntries(
    event.bouts.map((bout, index) => [bout.id, bout.fighters[index % 2].id]),
  );

  const token = codec.encode(event, picks);

  assert.deepEqual(codec.decode(event, token), picks);
  assert.ok(token.length <= 9, `expected at most 9 characters, received ${token}`);
});

test("round trips partial picks", () => {
  const event = makeEvent(4);
  const picks = {
    "bout-0": "red-0",
    "bout-3": "blue-3",
  };

  assert.deepEqual(codec.decode(event, codec.encode(event, picks)), picks);
});

test("decodes legacy JSON share links", () => {
  const event = makeEvent(2);
  const picks = { "bout-0": "red-0", "bout-1": "blue-1" };
  const token = Buffer.from(JSON.stringify(Object.entries(picks))).toString("base64url");

  assert.deepEqual(codec.decode(event, token), picks);
});

test("survives display-order changes", () => {
  const event = makeEvent(4);
  const picks = { "bout-0": "red-0", "bout-3": "blue-3" };
  const token = codec.encode(event, picks);
  const reorderedEvent = {
    bouts: [...event.bouts]
      .reverse()
      .map((bout) => ({ ...bout, fighters: [...bout.fighters].reverse() })),
  };

  assert.deepEqual(codec.decode(reorderedEvent, token), picks);
});

test("rejects a link when the fight card changes", () => {
  const event = makeEvent(4);
  const token = codec.encode(event, { "bout-0": "red-0" });
  const changedEvent = makeEvent(4);
  changedEvent.bouts[0].fighters[0].id = "replacement";

  assert.throws(() => codec.decode(changedEvent, token), /fight card changed/);
});

test("rejects compact payloads with data beyond the event card", () => {
  const token = Buffer.from([3]).toString("base64url");

  assert.throws(() => codec.decode(makeEvent(1), token), /extra data/);
});
