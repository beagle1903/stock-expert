import type { SignalWindow } from "../domain/dashboard";

export type SignalWindowNoticeTone = "partial" | "neutral";

export interface SignalWindowNotice {
  tone: SignalWindowNoticeTone;
  label: string;
  text: string;
}

export function signalWindowNotice(signalWindow: SignalWindow | null | undefined): SignalWindowNotice | null;
export function latestBasketSignalWindowNotice(signalWindow: SignalWindow | null | undefined): SignalWindowNotice | null;
