export function dashboardBootKind(status, hasData) {
  if (status === "error") return "error";
  if (status !== "loaded") return "loading";
  if (!hasData) return "empty";
  return "ready";
}
