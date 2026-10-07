import type { ClientMessage, ServerMessage } from "./protocol";

export interface WsClientHandlers {
  onOpen?: () => void;
  onMessage: (msg: ServerMessage) => void;
  onAudio: (chunk: ArrayBuffer) => void;
  onClose?: (event: CloseEvent) => void;
  onError?: () => void;
}

export function wsUrl(deckId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws?deck_id=${encodeURIComponent(deckId)}`;
}

export class WsClient {
  private ws: WebSocket | null = null;

  constructor(private readonly handlers: WsClientHandlers) {}

  connect(url: string): void {
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => this.handlers.onOpen?.();
    ws.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
      if (typeof event.data === "string") {
        try {
          this.handlers.onMessage(JSON.parse(event.data) as ServerMessage);
        } catch {
          // Ignore malformed frames rather than tearing down the session.
        }
      } else {
        this.handlers.onAudio(event.data);
      }
    };
    ws.onclose = (event) => {
      this.ws = null;
      this.handlers.onClose?.(event);
    };
    ws.onerror = () => this.handlers.onError?.();
    this.ws = ws;
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  send(msg: ClientMessage): void {
    if (this.isOpen) this.ws!.send(JSON.stringify(msg));
  }

  sendAudio(frame: ArrayBuffer): void {
    if (this.isOpen) this.ws!.send(frame);
  }

  close(): void {
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onclose = null;
      ws.onmessage = null;
      ws.close();
    }
  }
}
