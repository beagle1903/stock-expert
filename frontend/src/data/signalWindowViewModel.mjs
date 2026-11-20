const COMPONENT_WORDS = {
  momentum: "momentum",
  volume: "volume baseline",
  fade_then_rechase: "fade-then-rechase",
};

const FULL_LIST_LIMIT = 5;
const TRUNCATED_LIST_SIZE = 3;

const NOT_CAPTURED_NOTICE = {
  tone: "neutral",
  label: "Window not captured",
  text: "This basket was published before signal-window coverage was recorded.",
};

function stringList(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.length > 0) : [];
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function dateList(dates) {
  if (dates.length > FULL_LIST_LIMIT) {
    return `${dates.slice(0, TRUNCATED_LIST_SIZE).join(", ")} +${dates.length - TRUNCATED_LIST_SIZE} more`;
  }
  return dates.join(", ");
}

function wordList(words) {
  if (words.length <= 1) return words.join("");
  if (words.length === 2) return `${words[0]} and ${words[1]}`;
  return `${words.slice(0, -1).join(", ")}, and ${words[words.length - 1]}`;
}

function componentWord(component) {
  return COMPONENT_WORDS[component] ?? component.replaceAll("_", " ");
}

function gapText(signalWindow) {
  const missing = stringList(signalWindow.missingSessions);
  const nonSession = stringList(signalWindow.nonSessionDates);
  const components = stringList(signalWindow.affectedComponents).map(componentWord);
  const windowName = signalWindow.windowStart && signalWindow.windowEnd
    ? `Signal window ${signalWindow.windowStart} to ${signalWindow.windowEnd}`
    : "Signal window";

  const sentences = [];
  if (missing.length > 0) {
    sentences.push(`${windowName} has no snapshot for ${plural(missing.length, "trading session")}: ${dateList(missing)}.`);
  }
  if (nonSession.length > 0) {
    const lead = missing.length > 0 ? "It also includes" : `${windowName} includes`;
    sentences.push(`${lead} ${plural(nonSession.length, "non-session snapshot date")}: ${dateList(nonSession)}.`);
  }
  if (sentences.length === 0) {
    sentences.push(`${windowName} does not cover contiguous trading sessions.`);
  }
  if (components.length > 0) {
    sentences.push(`Affected component${components.length === 1 ? "" : "s"}: ${wordList(components)}.`);
  }
  sentences.push("Scores are unchanged; treat this basket as degraded evidence.");
  return sentences.join(" ");
}

export function signalWindowNotice(signalWindow) {
  if (!signalWindow || typeof signalWindow !== "object") return null;
  if (signalWindow.status === "gap") {
    return { tone: "partial", label: "Window gap", text: gapText(signalWindow) };
  }
  if (signalWindow.status === "not_captured") {
    return { ...NOT_CAPTURED_NOTICE };
  }
  return null;
}

export function latestBasketSignalWindowNotice(signalWindow) {
  return signalWindowNotice(signalWindow ?? { status: "not_captured" });
}
