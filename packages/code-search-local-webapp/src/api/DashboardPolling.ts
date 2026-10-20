/** How often the dashboard refreshes what it shows from the service. */
export namespace DashboardPolling {
  /**
   * Interval of every dashboard query (stats, health, paths) in ms. Lowering it makes counters
   * and job progress move sooner at the cost of more snapshot reads on the service; raising it
   * leaves the dashboard staler.
   */
  export const IntervalMs = 2_000
}
