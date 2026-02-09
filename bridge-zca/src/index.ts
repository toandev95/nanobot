#!/usr/bin/env node
/**
 * nanobot Zalo Bridge
 *
 * This bridge connects Zalo to nanobot's Python backend
 * via WebSocket. It handles authentication, message forwarding,
 * and reconnection logic using zca-js library.
 *
 * Usage:
 *   npm run build && npm start
 *
 * Or with custom settings:
 *   BRIDGE_PORT=3002 npm start
 */

import { BridgeServer } from "./server.js";

const PORT = parseInt(process.env.BRIDGE_PORT || "3002", 10);

console.log("🐈 nanobot Zalo Bridge");
console.log("=====================\n");

const server = new BridgeServer(PORT);

// Handle graceful shutdown
process.on("SIGINT", async () => {
  console.log("\n\nShutting down...");
  await server.stop();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await server.stop();
  process.exit(0);
});

// Start the server
server.start().catch((error) => {
  console.error("Failed to start bridge:", error);
  process.exit(1);
});
