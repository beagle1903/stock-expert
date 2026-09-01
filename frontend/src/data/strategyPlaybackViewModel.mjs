export function playbackNotices(playback) {
  if (!playback) return [];
  const notices = [];
  if (playback.signal.status === "unavailable") {
    notices.push("The exact signal snapshot is not available for this legacy review.");
  }
  if (playback.basket.attributionStatus === "partial") {
    notices.push("Some basket members lack stored candidate attribution for this review.");
  } else if (playback.basket.attributionStatus === "unavailable") {
    notices.push("Candidate ranks and signal components were not captured for this review.");
  }
  if (playback.pilotComparison.status === "unavailable") {
    notices.push("No paired pilot session was stored for this signal snapshot.");
  }
  return notices;
}
