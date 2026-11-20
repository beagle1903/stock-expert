import { signalWindowNotice } from "./signalWindowViewModel.mjs";

export function playbackNotices(playback) {
  if (!playback) return [];
  const notices = [];
  if (playback.signal.status === "unavailable") {
    notices.push("The exact signal snapshot is not available for this legacy review.");
  }
  // Only a recorded gap earns a playback notice; every pre-feature review is not_captured.
  if (playback.signal.signalWindow?.status === "gap") {
    notices.push(signalWindowNotice(playback.signal.signalWindow).text);
  }
  if (playback.strategy.weightsStatus === "unavailable") {
    notices.push("The persisted weights that generated this signal basket are not available.");
  }
  if (playback.basket.attributionStatus === "partial") {
    notices.push("Some basket members lack stored candidate attribution for this review.");
  } else if (playback.basket.attributionStatus === "unavailable") {
    notices.push("Candidate ranks and signal components were not captured for this review.");
  }
  if (playback.pilotComparison.status === "partial") {
    notices.push("The stored pilot comparison is incomplete; missing or incomplete arms are not a fair pair.");
  } else if (playback.pilotComparison.status === "unavailable") {
    notices.push("No paired pilot session was stored for this signal snapshot.");
  }
  return notices;
}
