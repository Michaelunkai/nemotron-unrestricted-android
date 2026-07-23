const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(
  path.join(
    root,
    "vendor/codexapp-native-npm/node_modules/codexapp/dist/assets/ThreadConversation-BjC7GMPc.js",
  ),
  "utf8",
);
const start = source.indexOf("function nemotronGalleryResult");
const end = source.indexOf("function O(e)", start);
assert(start >= 0 && end > start, "verified gallery parser is absent");
const parserSource = source.slice(start, end);
const parseGallery = Function(`${parserSource}; return nemotronGalleryResult;`)();

function commandWith(payload, overrides = {}) {
  return {
    messageType: "commandExecution",
    commandExecution: {
      command: "/data/data/com.termux/files/home/project/bin/codex-gallery faces --limit 20",
      status: "completed",
      exitCode: 0,
      aggregatedOutput: [
        "Gallery progress: checking images 1–20 of 20 for visible faces.",
        JSON.stringify(payload),
      ].join("\n"),
      ...overrides,
    },
  };
}

const validPayload = {
  schema: "nemotron.gallery-result.v1",
  verified: true,
  displayMessage: "Found one verified gallery image. It is displayed below.",
  hasMore: true,
  nextOffset: 20,
  render: {
    type: "verified-local-image-grid",
    verified: true,
    images: [{
      path: "/storage/emulated/0/DCIM/Camera/person.jpg",
      mediaId: 42,
      label: "person.jpg",
      mimeType: "image/jpeg",
      verified: true,
    }],
  },
};

const parsed = parseGallery(commandWith(validPayload));
assert(parsed, "valid verified gallery receipt was rejected");
assert.strictEqual(parsed.images.length, 1);
assert.strictEqual(
  parsed.images[0].url,
  "/codex-local-image?path=%2Fstorage%2Femulated%2F0%2FDCIM%2FCamera%2Fperson.jpg",
);
assert.strictEqual(parsed.hasMore, true);
assert.strictEqual(parsed.nextOffset, 20);

assert.strictEqual(
  parseGallery(commandWith({...validPayload, schema: "untrusted"})),
  null,
  "unknown schemas must remain plain command text",
);
assert.strictEqual(
  parseGallery(commandWith({
    ...validPayload,
    render: {
      ...validPayload.render,
      images: [{
        ...validPayload.render.images[0],
        path: "/data/data/com.example/private.jpg",
      }],
    },
  })),
  null,
  "private app paths must never enter the gallery renderer",
);
assert.strictEqual(
  parseGallery(commandWith(validPayload, {exitCode: 7})),
  null,
  "failed commands must never render image receipts",
);
assert.strictEqual(
  parseGallery(commandWith(validPayload, {command: "printf codex-gallery"})),
  null,
  "unrelated commands must never activate the gallery renderer",
);

console.log("GALLERY_FRONTEND_HARNESS_OK");
