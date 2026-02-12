/**
 * Zalo client using zca-js library.
 */

import { Zalo, API as ZaloAPI, ThreadType, Credentials } from "zca-js";

interface TAttachmentContent {
  type: "attachment";
  href: string;
}

interface InboundMessage {
  senderId: string;
  threadId: string;
  content: string | TAttachmentContent;
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
  private api: ZaloAPI | null = null;
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
        console.debug(
          "Received message content:",
          JSON.stringify(message.data.content),
        );

        // Extract message data
        const senderId = message.data?.uidFrom;
        const threadId = message.threadId;
        const messageId = message.data?.msgId;
        const timestamp = Number(message.data?.ts) || Date.now();
        const isGroup = message.type === ThreadType.Group;

        let content: string | TAttachmentContent;

        // Handle different content types
        if (typeof message.data.content === "string") {
          content = message.data.content;
        } else if (message.data.content.href !== null) {
          content = {
            type: "attachment",
            href: message.data.content.href as string,
          };
        } else {
          return;
        }

        // Forward to Python backend
        console.log(
          `📨 Message from ${senderId} in thread ${threadId.slice(0, 8)}...`,
        );
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
      console.log(`📤 Sending message to thread ${threadId.slice(0, 8)}...`);
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
