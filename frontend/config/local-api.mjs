export const DEFAULT_STOCK_EXPERT_API_PORT = 18765;

export function resolveStockExpertApiPort(environment = process.env) {
  const configured = environment.STOCK_EXPERT_API_PORT?.trim();
  if (!configured) return String(DEFAULT_STOCK_EXPERT_API_PORT);

  if (!/^\d+$/.test(configured)) {
    throw new Error("STOCK_EXPERT_API_PORT must be an integer between 1 and 65535");
  }

  const port = Number(configured);
  if (port < 1 || port > 65535) {
    throw new Error("STOCK_EXPERT_API_PORT must be an integer between 1 and 65535");
  }
  return String(port);
}
