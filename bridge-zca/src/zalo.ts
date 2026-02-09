/**
 * Zalo client using zca-js library.
 */

import { Zalo, API, ThreadType, Credentials } from "zca-js";

export interface InboundMessage {
  senderId: string;
  threadId: string;
  content: string;
  messageId: string;
  timestamp: number;
  isGroup: boolean;
}

interface ZaloClientOptions {
  onMessage: (msg: InboundMessage) => void;
  onStatus: (status: string) => void;
}

export class ZaloClient {
  private zalo: Zalo | null = null;
  private api: API | null = null;
  private onMessage: (msg: InboundMessage) => void;
  private onStatus: (status: string) => void;

  constructor(options: ZaloClientOptions) {
    this.onMessage = options.onMessage;
    this.onStatus = options.onStatus;
  }

  async login(credentials: Credentials): Promise<void> {
    try {
      // Initialize Zalo instance
      this.zalo = new Zalo({
        selfListen: false,
        checkUpdate: false,
        logging: true,
      });

      // Login with credentials
      this.api = await this.zalo.login({
        cookie: credentials.cookie,
        imei: credentials.imei,
        userAgent: credentials.userAgent,
      });

      console.log("🔐 Logged in to Zalo");
      this.onStatus("connected");

      // Set up message listener
      this.setupMessageListener();

      // Start listening for events
      this.api.listener.start();
      console.log("👂 Listening for Zalo messages...");
    } catch (error) {
      console.error("Failed to login to Zalo:", error);
      this.onStatus("disconnected");
      throw error;
    }
  }

  private setupMessageListener(): void {
    if (!this.api) return;

    this.api.listener.on("message", (message) => {
      try {
        // Ignore non-text messages
        if (typeof message.data.content !== "string") {
          return;
        }

        // Extract message data
        const senderId = message.data?.uidFrom;
        const threadId = message.threadId;
        const content = message.data?.content;
        const messageId = message.data?.msgId;
        const timestamp = Number(message.data?.ts) || Date.now();
        const isGroup = message.type === ThreadType.Group;

        // Forward to Python backend
        this.onMessage({
          senderId,
          threadId,
          content,
          messageId,
          timestamp,
          isGroup,
        });
      } catch (error) {
        console.error("Error processing message:", error);
      }
    });

    // Handle other events (optional)
    this.api.listener.on("error", (error: any) => {
      console.error("Zalo listener error:", error);
      this.onStatus("error");
    });
  }

  async sendMessage(
    threadId: string,
    text: string,
    type?: ThreadType,
  ): Promise<void> {
    if (!this.api) {
      throw new Error("Not logged in to Zalo");
    }

    try {
      await this.api.sendMessage(text, threadId, type);
    } catch (error) {
      console.error("Failed to send message:", error);
      throw error;
    }
  }

  async sendTypingEvent(threadId: string): Promise<void> {
    if (!this.api) {
      console.warn("Not logged in to Zalo");
      return;
    }

    try {
      await this.api.sendTypingEvent(threadId);
    } catch (error) {
      console.error("Failed to send typing event:", error);
    }
  }

  async disconnect(): Promise<void> {
    if (this.api && this.api.listener) {
      this.api.listener.stop();
    }
    this.api = null;
    this.zalo = null;
    this.onStatus("disconnected");
    console.log("👋 Disconnected from Zalo");
  }
}
