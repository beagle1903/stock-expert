export function dashboardBootKind(
  status: "idle" | "loading" | "loaded" | "error",
  hasData: boolean,
): "loading" | "empty" | "error" | "ready";
