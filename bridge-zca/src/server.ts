/**
 * WebSocket server for Python-Node.js bridge communication.
 */

import { WebSocketServer, WebSocket } from "ws";
import { Credentials } from "zca-js";
import { ZaloClient } from "./zalo.js";

interface LoginCommand {
  type: "login";
  cookie: any;
  imei: string;
  userAgent: string;
}

interface SendCommand {
  type: "send";
  to: string;
  text: string;
}

interface TypingCommand {
  type: "typing";
  to: string;
}

type BridgeCommand = LoginCommand | SendCommand | TypingCommand;

interface BridgeMessage {
  type: "message" | "status" | "login" | "error";
  [key: string]: unknown;
}

export class BridgeServer {
  private wss: WebSocketServer | null = null;
  private zalo: ZaloClient | null = null;
  private clients: Set<WebSocket> = new Set();

  constructor(private port: number) {}

  async start(): Promise<void> {
    // Create WebSocket server
    this.wss = new WebSocketServer({ port: this.port });
    console.log(`🌉 Bridge server listening on ws://localhost:${this.port}`);

    // Handle WebSocket connections
    this.wss.on("connection", (ws) => {
      console.log("🔗 Python client connected");
      this.clients.add(ws);

      ws.on("message", async (data) => {
        try {
          const cmd = JSON.parse(data.toString()) as BridgeCommand;
          await this.handleCommand(cmd, ws);
        } catch (error) {
          console.error("Error handling command:", error);
          ws.send(JSON.stringify({ type: "error", error: String(error) }));
        }
      });

      ws.on("close", async () => {
        console.log("🔌 Python client disconnected");
        this.clients.delete(ws);

        if (this.clients.size === 0 && this.zalo) {
          console.log("🧹 No clients remaining, disconnecting Zalo...");
          await this.zalo.disconnect();
          this.zalo = null;
        }
      });

      ws.on("error", (error) => {
        console.error("WebSocket error:", error);
        this.clients.delete(ws);

        if (this.clients.size === 0 && this.zalo) {
          this.zalo.disconnect().catch(console.error);
          this.zalo = null;
        }
      });
    });
  }

  private async handleCommand(
    cmd: BridgeCommand,
    ws: WebSocket,
  ): Promise<void> {
    if (cmd.type === "login") {
      await this.handleLogin(cmd, ws);
    } else if (cmd.type === "send" && this.zalo) {
      await this.zalo.sendMessage(cmd.to, cmd.text);
    } else if (cmd.type === "typing" && this.zalo) {
      await this.zalo.sendTypingEvent(cmd.to);
    }
  }

  private async handleLogin(cmd: LoginCommand, ws: WebSocket): Promise<void> {
    try {
      // Initialize Zalo client if not already done
      if (!this.zalo) {
        this.zalo = new ZaloClient({
          onMessage: (msg) => this.broadcast({ type: "message", ...msg }),
          onStatus: (status) => this.broadcast({ type: "status", status }),
        });
      }

      // Login to Zalo
      const credentials: Credentials = {
        cookie: cmd.cookie,
        imei: cmd.imei,
        userAgent: cmd.userAgent,
      };

      await this.zalo.login(credentials);

      ws.send(JSON.stringify({ type: "login", success: true }));
    } catch (error) {
      console.error("❌ Failed to login to Zalo:", error);
      ws.send(
        JSON.stringify({
          type: "login",
          success: false,
          error: String(error),
        }),
      );
    }
  }

  private broadcast(msg: BridgeMessage): void {
    const data = JSON.stringify(msg);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  async stop(): Promise<void> {
    // Close all client connections
    for (const client of this.clients) {
      client.close();
    }
    this.clients.clear();

    // Close WebSocket server
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }

    // Disconnect Zalo
    if (this.zalo) {
      await this.zalo.disconnect();
      this.zalo = null;
    }
  }
}
