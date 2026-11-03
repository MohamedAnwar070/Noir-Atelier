import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const PORT = Number(process.env.PORT || 3000);
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
};

const server = http.createServer((req, res) => {
  const reqUrl = new URL(req.url || "/", `http://localhost:${PORT}`);
  const pathname = decodeURIComponent(reqUrl.pathname);

  let filePath;
  if (pathname.startsWith("/packages/")) {
    filePath = path.join(FRONTEND_ROOT, pathname);
  } else if (pathname === "/admin" || pathname === "/admin/") {
    filePath = path.join(FRONTEND_ROOT, "apps", "admin", "index.html");
  } else if (pathname === "/" || pathname === "/index.html") {
    filePath = path.join(__dirname, "index.html");
  } else {
    filePath = path.join(__dirname, pathname);
  }

  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ code: "not_found", path: pathname }));
    return;
  }

  const ext = path.extname(filePath).toLowerCase();
  const contentType = MIME_TYPES[ext] || "application/octet-stream";
  let content = fs.readFileSync(filePath);

  if (ext === ".html") {
    const htmlStr = content
      .toString("utf-8")
      .replace("</head>", `<script>window.NOIR_API_BASE = "${API_BASE}";</script></head>`);
    content = Buffer.from(htmlStr, "utf-8");
  }

  res.writeHead(200, {
    "Content-Type": contentType,
    "Cache-Control": "no-store",
  });
  res.end(content);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[Noir Atelier] Storefront & Admin UI listening on http://localhost:${PORT}`);
  console.log(`[Noir Atelier] Connected to Database API at ${API_BASE}`);
});
